# -*- coding: utf-8 -*-
r"""
提取「智库/词条」类视频的文字（针对游戏百科界面布局）。

和 ocr_subtitles.py 的区别
--------------------------
ocr_subtitles  适用于「底部有字幕」的视频（剧情、解说）
本脚本          适用于「画面面板里放长文本」的视频（智库、角色故事、图鉴）

实测布局（1920x1080）：
    左侧 0~0.42w   条目列表
    右侧 0.44w~w   当前条目：标题（字号较大，h>=26）+ 正文（h≈24）
    顶部/左下       水印，丢弃

用法
----
    python ocr_databank.py --src "D:\b站下载\1191495085" --out G:\ai\data\zhiku.txt
"""

import argparse
import asyncio
import json
import os
import sys
import av


def strip_prefix(path, workdir):
    with open(path, "rb") as f:
        head = f.read(16)
    n = 0
    while n < len(head) and head[n] == 0x30:
        n += 1
    if n == 0:
        return path, False
    data = open(path, "rb").read()
    tmp = os.path.join(workdir, "_src.mp4")
    with open(tmp, "wb") as f:
        f.write(data[n:])
    return tmp, True


def clean(s):
    import re
    s = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", s)
    s = s.replace("[", "「").replace("]", "」")
    s = s.replace("r ", "「").replace("厶厶", "")
    return s.strip()


async def main():
    ap = argparse.ArgumentParser(description="提取智库/图鉴类视频的文字")
    ap.add_argument("--src", required=True, help="视频文件或目录")
    ap.add_argument("--out", required=True, help="输出 txt")
    ap.add_argument("--interval", type=float, default=4.0, help="抽样间隔（秒）")
    args = ap.parse_args()

    try:
        from winsdk.windows.media.ocr import OcrEngine
        from winsdk.windows.globalization import Language
        from winsdk.windows.storage import StorageFile, FileAccessMode
        from winsdk.windows.graphics.imaging import BitmapDecoder
    except ImportError:
        sys.exit("[错误] 缺少 winsdk")

    src = args.src
    if os.path.isdir(src):
        cands = [os.path.join(src, x) for x in os.listdir(src)
                 if x.endswith(".m4s") and "-30080" in x]
        if not cands:
            sys.exit("[错误] 目录里没找到视频流文件")
        src = cands[0]

    workdir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(workdir, exist_ok=True)
    video, cleanup = strip_prefix(src, workdir)
    tmpimg = os.path.join(workdir, "_panel.png")

    engine = OcrEngine.try_create_from_language(Language("zh-Hans-CN"))
    entries = []          # [(title, [body lines])]
    last_key = None
    seq = 0

    with av.open(video) as c:
        vs = c.streams.video[0]
        W = vs.codec_context.width
        H = vs.codec_context.height
        nxt = 0.0
        n_ocr = 0
        for fr in c.decode(vs):
            if fr.pts is None:
                continue
            t = float(fr.pts * vs.time_base)
            if t < nxt:
                continue
            nxt = t + args.interval
            img = fr.to_image()
            # 从 0.10H 开始裁，避开顶部的「已收录 19/19」计数器，
            # 否则它会被当成词条标题。
            panel = img.crop((int(W * 0.44), int(H * 0.10), W, int(H * 0.62)))
            # 每次换一个新文件名：WinRT 读过之后会占用该文件，覆盖写会报 EINVAL
            seq += 1
            shot = os.path.join(workdir, "_panel_%04d.png" % seq)
            panel.save(shot)
            f = await StorageFile.get_file_from_path_async(shot)
            st = await f.open_async(FileAccessMode.READ)
            try:
                dec = await BitmapDecoder.create_async(st)
                bmp = await dec.get_software_bitmap_async()
                res = await engine.recognize_async(bmp)
            finally:
                st.close()
            try:
                os.remove(shot)
            except OSError:
                pass
            n_ocr += 1
            lines = []
            for line in res.lines:
                ws = list(line.words)
                if not ws:
                    continue
                lines.append({
                    "text": clean(line.text),
                    "y": min(w.bounding_rect.y for w in ws),
                    "h": max(w.bounding_rect.height for w in ws),
                })
            lines.sort(key=lambda x: x["y"])
            if not lines:
                continue
            title = lines[0]["text"]
            body = "".join(l["text"] for l in lines[1:])
            key = (title, body[:40])
            if key == last_key:
                continue
            last_key = key
            if len(body) < 20:      # 只有标题没有正文，跳过
                continue
            # 同一标题如果正文更长，替换
            if entries and entries[-1][0] == title and len(body) > len(entries[-1][1]):
                entries[-1] = (title, body)
            else:
                entries.append((title, body))
            print("  [%s] %s" % (title[:22], body[:44]))

    if cleanup and os.path.exists(video):
        os.remove(video)

    print("")
    print("  OCR %d 帧，得到 %d 个词条" % (n_ocr, len(entries)))
    with open(args.out, "w", encoding="utf-8") as f:
        for title, body in entries:
            f.write("【%s】\n%s\n\n" % (title, body))
    print("  [完成] -> %s" % args.out)


if __name__ == "__main__":
    asyncio.run(main())
