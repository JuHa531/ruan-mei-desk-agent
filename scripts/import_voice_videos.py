# -*- coding: utf-8 -*-
r"""
把 B 站下载的语音视频（-30280.m4s）切成可训练的短句，并用本地 ASR 标注。

这不是"把整段视频丢给模型"：先按静音切分、限制 2.5~12 秒、按字/秒过滤，
只把真正像一句台词的片段写进数据集。原始音轨和切片都保留，方便复查。

用法
----
    D:\ai\envs\tts\python.exe scripts\import_voice_videos.py `
        --source all_voice=D:\b站下载\1382614882 `
        --source museum=D:\b站下载\1384092048

输出
----
    G:\ai\voice\staging_20261020\<source>\*.wav
    G:\ai\voice\staging_20261020\<source>\metadata.jsonl
    G:\ai\voice\staging_20261020\<source>\kept_list.txt
"""

import argparse
import glob
import json
import math
import os
import re
import sys
import tempfile
import urllib.request
import wave
from collections import Counter

import av
import numpy as np
from scipy.signal import resample_poly

GS = r"G:\ai\GPT-SoVITS\GPT-SoVITS-main"
sys.path.insert(0, os.path.join(GS, "tools"))
from slicer2 import Slicer  # noqa: E402

ASR_URL = "http://127.0.0.1:9882/asr?format=wav"
NOISE_WORDS = ("字幕", "感谢观看", "订阅", "点赞", "关注", "哔哩", "B站",
               "视频", "片头", "片尾", "下期再见", "未完待续")


def strip_prefix(path):
    """B 站下载器会在 m4s 前写 9 个 ASCII 0，ffmpeg 会把它当成坏文件。"""
    with open(path, "rb") as f:
        head = f.read(16)
    n = 0
    while n < len(head) and head[n] == 0x30:
        n += 1
    return n


def audio_file(folder):
    got = glob.glob(os.path.join(folder, "*-30280.m4s"))
    if not got:
        raise FileNotFoundError("目录里没有 *-30280.m4s：%s" % folder)
    return got[0]


def decode_audio(path):
    skip = strip_prefix(path)
    fd, tmp = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    try:
        with open(path, "rb") as f:
            data = f.read()[skip:]
        with open(tmp, "wb") as f:
            f.write(data)
        chunks, sr = [], 44100
        with av.open(tmp) as c:
            st = c.streams.audio[0]
            sr = st.codec_context.sample_rate or 44100
            for fr in c.decode(st):
                a = fr.to_ndarray()
                if a.ndim > 1:
                    a = a.mean(axis=0)
                chunks.append(a.astype(np.float32))
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    audio = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)
    if sr != 32000:
        g = math.gcd(sr, 32000)
        audio = resample_poly(audio, 32000 // g, sr // g).astype(np.float32)
        sr = 32000
    return audio, sr


def split_long(chunk, sr, max_dur=11.5, min_dur=2.5):
    """连续旁白可能十几秒没有静音，在低能量点再切一刀。"""
    out, start = [], 0
    while (len(chunk) - start) / sr > max_dur:
        lo = start + int(min_dur * sr)
        hi = start + int(max_dur * sr)
        seg = chunk[lo:hi]
        win = int(0.05 * sr)
        n = len(seg) // win
        if n < 2:
            cut = hi
        else:
            rms = np.sqrt(np.mean(seg[:n * win].reshape(n, win) ** 2, axis=1))
            cut = lo + int(np.argmin(rms)) * win + win // 2
        out.append(chunk[start:cut])
        start = cut
    out.append(chunk[start:])
    return [x for x in out if len(x) >= int(min_dur * sr * 0.8)]


def write_wav(path, chunk, sr):
    peak = float(np.abs(chunk).max()) or 1.0
    pcm = (np.clip(chunk / peak * 0.9, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def asr(path):
    with open(path, "rb") as f:
        data = f.read()
    req = urllib.request.Request(
        ASR_URL, data=data, method="POST",
        headers={"Content-Type": "application/octet-stream"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode("utf-8")).get("text", "")


def clean_text(text):
    text = re.sub(r"<\|[^|]*\|>", "", text or "")
    text = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9，。！？、；：]", "", text)
    return text.strip(" ，。！？、；：")


def judge(text, dur, min_chars, min_cps, max_cps, min_dur, max_dur):
    if not (min_dur <= dur <= max_dur):
        return False, "时长 %.1f 秒" % dur
    cn = len(re.findall(r"[\u4e00-\u9fff]", text))
    if cn < min_chars:
        return False, "文字太少"
    if len(set(text)) < 2:
        return False, "重复字符"
    if any(w in text for w in NOISE_WORDS):
        return False, "片头/字幕残留"
    cps = cn / dur if dur else 0
    if not (min_cps <= cps <= max_cps):
        return False, "语速 %.1f 字/秒" % cps
    return True, ""


def main():
    ap = argparse.ArgumentParser(description="从 B 站语音视频构建 GPT-SoVITS 片段")
    ap.add_argument("--source", action="append", required=True,
                    help="name=folder，可重复，例如 all_voice=D:\\b站下载\\1382614882")
    ap.add_argument("--outdir", default=r"G:\ai\voice\staging_20261020")
    ap.add_argument("--min-dur", type=float, default=2.5)
    ap.add_argument("--max-dur", type=float, default=12.0)
    ap.add_argument("--min-chars", type=int, default=4)
    ap.add_argument("--min-cps", type=float, default=2.2)
    ap.add_argument("--max-cps", type=float, default=7.5)
    args = ap.parse_args()

    for spec in args.source:
        name, _, folder = spec.partition("=")
        if not name or not folder or not os.path.isdir(folder):
            sys.exit("--source 格式不对或目录不存在：%s" % spec)
        src = audio_file(folder)
        out = os.path.join(args.outdir, name)
        os.makedirs(out, exist_ok=True)
        print("[%s] 解码 %s" % (name, src), flush=True)
        audio, sr = decode_audio(src)
        print("[%s] %.1f 秒，开始切片" % (name, len(audio) / sr), flush=True)
        slicer = Slicer(sr=sr, threshold=-40.0, min_length=2500,
                        min_interval=300, hop_size=10, max_sil_kept=500)
        pieces = []
        for chunk, start, end in slicer.slice(audio):
            for sub in split_long(chunk, sr, args.max_dur - 0.5, args.min_dur):
                pieces.append((start, sub))
                start += len(sub)
        print("[%s] 切出 %d 段，开始 ASR" % (name, len(pieces)), flush=True)

        meta_path = os.path.join(out, "metadata.jsonl")
        kept_path = os.path.join(out, "kept_list.txt")
        kept, dropped = [], []
        with open(meta_path, "w", encoding="utf-8") as mf, \
                open(kept_path, "w", encoding="utf-8") as kl:
            for i, (start_frame, chunk) in enumerate(pieces, 1):
                dur = len(chunk) / sr
                wav_path = os.path.join(out, "%04d.wav" % i)
                write_wav(wav_path, chunk, sr)
                ok, reason = False, ""
                try:
                    text = clean_text(asr(wav_path))
                except Exception as e:
                    text = ""
                    reason = "ASR失败：%s" % str(e)[:60]
                else:
                    ok, reason = judge(text, dur, args.min_chars,
                                       args.min_cps, args.max_cps,
                                       args.min_dur, args.max_dur)
                if not text:
                    ok, reason = False, reason or "空文本"
                row = {"source": name, "index": i, "path": wav_path.replace("\\", "/"),
                       "start": round(start_frame / sr, 2), "dur": round(dur, 2),
                       "text": text, "kept": ok, "reason": "" if ok else reason}
                mf.write(json.dumps(row, ensure_ascii=False) + "\n")
                mf.flush()
                if ok:
                    kept.append(row)
                    kl.write("%s|ruanmei|zh|%s\n" % (row["path"], text))
                    kl.flush()
                else:
                    dropped.append(reason)
                if i % 20 == 0:
                    print("[%s] %d/%d，已留 %d 条" % (name, i, len(pieces), len(kept)),
                          flush=True)

        total = sum(r["dur"] for r in kept)
        print("")
        print("[%s] 采纳 %d 条，%.1f 分钟；剔除 %d 条"
              % (name, len(kept), total / 60, len(dropped)))
        for reason, n in Counter(dropped).most_common(6):
            print("   %s: %d" % (reason, n))
        print("   %s" % kept_path)


if __name__ == "__main__":
    main()
