# -*- coding: utf-8 -*-
r"""
从 B 站下载的视频里切出一段干净的参考音频，用于音色克隆。

原理
----
B 站缓存的 `-30280.m4s` 是纯音频流（AAC）。去掉开头 9 字节前缀后可以直接解码，
按时间点截取一段，转成 wav 就能当参考音频用。

不需要 ffmpeg —— 用 PyAV 解码、wave 模块写文件。

用法
----
    python extract_ref_audio.py --video "D:\b站下载\31248287184" \
                                --start 5.0 --dur 9 \
                                --out "G:\ai\voice\ref\ruanmei.wav"

    # 列出一批候选（按台词长度推荐，越长越适合作参考）
    python extract_ref_audio.py --list --data G:\ai\data\story_titled.jsonl
"""

import argparse
import glob
import os
import sys
import wave

import av
import numpy as np


def strip_prefix(path, workdir):
    with open(path, "rb") as f:
        head = f.read(16)
    n = 0
    while n < len(head) and head[n] == 0x30:
        n += 1
    if n == 0:
        return path, False
    data = open(path, "rb").read()
    tmp = os.path.join(workdir, "_audio.mp4")
    with open(tmp, "wb") as f:
        f.write(data[n:])
    return tmp, True


def find_audio(folder):
    for x in os.listdir(folder):
        if x.endswith(".m4s") and "-30280" in x:
            return os.path.join(folder, x)
    for x in os.listdir(folder):
        if x.endswith((".m4a", ".mp3", ".wav")):
            return os.path.join(folder, x)
    return None


def cut(src, start, dur, out, workdir):
    video, cleanup = strip_prefix(src, workdir)
    chunks, sr = [], 48000
    with av.open(video) as c:
        st = c.streams.audio[0]
        sr = st.codec_context.sample_rate or 48000
        start_pts = int(start * sr)
        end_pts = int((start + dur) * sr)
        pos = 0
        for fr in c.decode(st):
            a = fr.to_ndarray()
            if a.ndim > 1:
                a = a.mean(axis=0)
            n = len(a)
            lo, hi = max(0, start_pts - pos), min(n, end_pts - pos)
            if hi > lo:
                chunks.append(a[lo:hi])
            pos += n
            if pos >= end_pts:
                break
    if cleanup and os.path.exists(video):
        os.remove(video)
    if not chunks:
        sys.exit("[错误] 这段时间里没取到音频，检查 --start / --dur")
    audio = np.concatenate(chunks).astype(np.float32)
    peak = float(np.abs(audio).max()) or 1.0
    audio = audio / peak * 0.95                      # 归一化，避免削波
    pcm = (audio * 32767).astype(np.int16).tobytes()
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    return len(audio) / sr, sr, peak


def main():
    ap = argparse.ArgumentParser(description="切取参考音频")
    ap.add_argument("--video", help="下载文件夹（含 -30280 音频）或音频文件")
    ap.add_argument("--start", type=float, default=5.0)
    ap.add_argument("--dur", type=float, default=9.0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--list", action="store_true", help="列出候选片段")
    ap.add_argument("--data", default=r"G:\ai\data\story_titled.jsonl")
    args = ap.parse_args()

    if args.list:
        import json
        rows = [json.loads(l) for l in open(args.data, encoding="utf-8") if l.strip()]
        rows = [r for r in rows if r.get("file")]
        rows.sort(key=lambda r: -len(r["output"]))
        print("  台词最长的 8 条（越适合作参考音频）：")
        for r in rows[:8]:
            print("    [%s] %s" % (r.get("time", "?"), r["output"][:56]))
            print("         %s" % r.get("file", ""))
        return

    if not args.video:
        sys.exit("[错误] 需要 --video")
    src = args.video
    if os.path.isdir(src):
        a = find_audio(src)
        if not a:
            sys.exit("[错误] 该目录里没找到音频流文件")
        src = a
    workdir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(workdir, exist_ok=True)
    dur, sr, peak = cut(src, args.start, args.dur, args.out, workdir)
    print("  参考音频已生成: %s" % args.out)
    print("  时长 %.1f 秒，采样率 %d，原始峰值 %.3f" % (dur, sr, peak))
    print("")
    print("  下一步：试听确认音色和清晰度，然后配到 voices.json 里")


if __name__ == "__main__":
    main()
