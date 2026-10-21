# -*- coding: utf-8 -*-
r"""
把校对过的台词 + 视频原声，做成 GPT-SoVITS 精调数据集。

输入
----
    story_named.jsonl    校对过的台词（带 file / time）
    timeline.jsonl       带文件名的时间线（由 export_timeline.py 从 OCR 缓存重建）
    D:\b站下载\*\*-30280.m4s   音频流

输出
----
    G:\ai\voice\dataset\*.wav    切好的音频
    G:\ai\voice\list.txt         GPT-SoVITS 格式：路径|角色|语言|文本

为什么用 timeline.jsonl 而不是 all.txt
--------------------------------------
all.txt 只有时间戳、没有文件名，判断某条字幕属于哪个视频只能靠"推导视频顺序"，
而那个顺序取决于当时目录里有哪些文件，事后无法可靠还原（实测会整体错位）。
timeline.jsonl 每条都带文件名，直接查，不存在对齐问题。

对齐校验
--------
音频和文本必须严格对应，否则精调会比零样本更差。每条要过两关：
  1. 在同一视频、时间 ±5 秒内找到最像的字幕，相似度 >= 0.38
     （阈值不能高：用户校对时改掉了 OCR 错字，校对得越认真差异反而越大）
  2. 时长在 2.5~12 秒之间（GPT-SoVITS 训练的最佳区间）
"""

import argparse
import glob
import json
import os
import re
import wave
from collections import Counter
from difflib import SequenceMatcher

import av
import numpy as np


def norm(s):
    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", s or "")


def ratio(a, b):
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def strip_prefix(path):
    with open(path, "rb") as f:
        head = f.read(16)
    n = 0
    while n < len(head) and head[n] == 0x30:
        n += 1
    return n


class AudioCache:
    """按需解码某视频的音频并缓存（一个视频只解一次）。"""

    def __init__(self):
        self.c = {}

    def get(self, folder):
        if folder in self.c:
            return self.c[folder]
        cands = glob.glob(os.path.join(folder, "*-30280.m4s"))
        if not cands:
            self.c[folder] = None
            return None
        src = cands[0]
        skip = strip_prefix(src)
        tmp = os.path.join(os.environ.get("TEMP", "."), "_tts_tmp.mp4")
        with open(src, "rb") as f:
            data = f.read()[skip:]
        with open(tmp, "wb") as f:
            f.write(data)
        chunks, sr = [], 44100
        try:
            with av.open(tmp) as c:
                st = c.streams.audio[0]
                sr = st.codec_context.sample_rate or 44100
                for fr in c.decode(st):
                    a = fr.to_ndarray()
                    if a.ndim > 1:
                        a = a.mean(axis=0)
                    chunks.append(a.astype(np.float32))
        except Exception:
            self.c[folder] = None
            return None
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        audio = np.concatenate(chunks) if chunks else None
        self.c[folder] = (audio, sr)
        return self.c[folder]


def main():
    ap = argparse.ArgumentParser(description="构建 GPT-SoVITS 精调数据集")
    ap.add_argument("--data", default=r"G:\ai\data\story_named.jsonl")
    ap.add_argument("--timeline", default=r"G:\ai\data\timeline.jsonl")
    ap.add_argument("--downloads", default=r"D:\b站下载")
    ap.add_argument("--outdir", default=r"G:\ai\voice\dataset")
    ap.add_argument("--speaker", default="ruanmei")
    ap.add_argument("--min-dur", type=float, default=2.5)
    ap.add_argument("--max-dur", type=float, default=12.0)
    ap.add_argument("--min-sim", type=float, default=0.38)
    ap.add_argument("--window", type=float, default=5.0)
    # 语速体检：正常中文约 4~6 字/秒。
    # 太快 = 音频被切短，文本和声音对不上（会训出"又快又糊"的电子音）；
    # 太慢 = 混进了笑声、停顿或别人的台词。两头都要剔掉。
    ap.add_argument("--min-cps", type=float, default=2.5,
                    help="字/秒 下限，低于此值视为混入非语音")
    ap.add_argument("--max-cps", type=float, default=7.0,
                    help="字/秒 上限，高于此值视为音频被截断")
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.data, encoding="utf-8") if l.strip()]
    rows = [r for r in rows if r.get("file") and r.get("time")]
    print("  校对数据 %d 条" % len(rows))

    tl = {}
    for line in open(args.timeline, encoding="utf-8"):
        line = line.strip()
        if line:
            e = json.loads(line)
            tl.setdefault(e["source"], []).append(e)
    for k in tl:
        tl[k].sort(key=lambda x: x["start"])
    print("  时间线：%d 个视频、%d 条字幕"
          % (len(tl), sum(len(v) for v in tl.values())))

    os.makedirs(args.outdir, exist_ok=True)
    cache = AudioCache()
    kept, dropped = [], []
    idx = 0

    for r in rows:
        fn = str(r["file"])
        folder = fn.split("-")[0]
        entries = tl.get(fn)
        if not entries:
            dropped.append((r, "时间线里没有这个视频"))
            continue
        m = re.match(r"(\d+):(\d+(?:\.\d+)?)", str(r["time"]))
        if not m:
            dropped.append((r, "时间格式不对"))
            continue
        t0 = int(m.group(1)) * 60 + float(m.group(2))

        near = None
        for e in entries:
            if abs(e["start"] - t0) > args.window:
                continue
            s = ratio(e["text"], r["output"])
            if near is None or s > near[0]:
                near = (s, e)
        if not near or near[0] < args.min_sim:
            dropped.append((r, "文本对不上"))
            continue
        e = near[1]
        # 结束点优先用这条字幕**自己的** end（OCR 记录的最后出现时间），
        # 而不是"下一条的开始"——字幕会重叠，用后者会把这一句切短。
        t1 = float(e.get("end") or e["start"]) + 0.25
        if t1 - e["start"] < args.min_dur:
            t1 = e["start"] + args.min_dur
        t1 = min(t1, e["start"] + args.max_dur)
        dur = t1 - e["start"]
        if not (args.min_dur <= dur <= args.max_dur):
            dropped.append((r, "时长不合适"))
            continue

        n_char = len(re.sub(r"[^\u4e00-\u9fff]", "", r["output"]))
        cps = n_char / dur if dur else 0
        if not (args.min_cps <= cps <= args.max_cps):
            dropped.append((r, "语速 %.1f 字/秒（正常 4~6）" % cps))
            continue

        got = cache.get(os.path.join(args.downloads, folder))
        if not got:
            dropped.append((r, "读不到音频"))
            continue
        audio, sr = got
        a, b = int(e["start"] * sr), min(int(t1 * sr), len(audio))
        if b - a < int(args.min_dur * sr):
            dropped.append((r, "切出来太短"))
            continue
        seg = audio[a:b]
        idx += 1
        path = os.path.join(args.outdir, "%04d.wav" % idx)
        peak = float(np.abs(seg).max()) or 1.0
        pcm = ((seg / peak * 0.95) * 32767).astype(np.int16).tobytes()
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(pcm)
        kept.append((path, r["output"], dur))

    list_path = os.path.join(os.path.dirname(args.outdir), "list.txt")
    with open(list_path, "w", encoding="utf-8") as f:
        for path, text, _ in kept:
            f.write("%s|%s|zh|%s\n" % (path.replace("\\", "/"), args.speaker, text))

    total = sum(d for _, _, d in kept)
    print("")
    print("  ================ 结果 ================")
    print("  采纳 %d 条，合计 %.1f 分钟语音" % (len(kept), total / 60))
    print("  剔除 %d 条：" % len(dropped))
    for reason, n in Counter(x[1] for x in dropped).most_common(5):
        print("     %s: %d 条" % (reason, n))
    print("  ======================================")
    print("  音频目录: %s" % args.outdir)
    print("  list.txt: %s" % list_path)
    if total / 60 < 3:
        print("  [提示] 不足 3 分钟，精调效果可能有限（建议 5~20 分钟）")
    else:
        print("  数据量够精调用（GPT-SoVITS 建议 5~20 分钟）")
    print("")
    for path, text, d in kept[:3]:
        print("    [%.1fs] %s" % (d, text[:52]))


if __name__ == "__main__":
    main()
