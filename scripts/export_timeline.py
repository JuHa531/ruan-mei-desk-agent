# -*- coding: utf-8 -*-
r"""
从 OCR 缓存重建「带文件名的完整时间线」。

为什么需要它
------------
story.jsonl.all.txt 里只有时间戳、没有文件名，要确定某条字幕属于哪个视频，
只能靠"推导 all.txt 里的视频顺序"——而那个顺序取决于当时目录里有哪些文件，
事后无法可靠还原（实测推导出来的顺序整体错位）。

好在 OCR 缓存 .ocr_cache.json 的键就是「文件名|大小」，天然带来源。
这个脚本直接读缓存、复用 ocr_subtitles 的合并逻辑，导出带文件名的时间线。

用法
----
    python export_timeline.py --cache G:\ai\data\story.jsonl.ocr_cache.json \
                              --out G:\ai\data\timeline.jsonl
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from ocr_subtitles import build_lines, dedupe_lines   # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="从缓存重建时间线")
    ap.add_argument("--cache", default=r"G:\ai\data\story.jsonl.ocr_cache.json")
    ap.add_argument("--out", default=r"G:\ai\data\timeline.jsonl")
    ap.add_argument("--min-chars", type=int, default=4)
    args = ap.parse_args()

    cache = json.load(open(args.cache, encoding="utf-8"))
    print("  缓存里有 %d 个视频" % len(cache))

    rows = []
    for key, samples in cache.items():
        src = key.split("|")[0]
        for s in samples:
            s["src"] = src
        lines = build_lines(samples)
        lines = dedupe_lines(lines)
        for l in lines:
            if len(l["text"].strip()) < args.min_chars:
                continue
            rows.append({
                "source": src,
                "start": round(l["start"], 2),
                "end": round(l["end"], 2),
                "speaker": (l.get("label") or "").strip(),
                "text": l["text"],
            })

    rows.sort(key=lambda x: (x["source"], x["start"]))
    with open(args.out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    vids = sorted(set(r["source"] for r in rows))
    print("  导出 %d 条字幕，覆盖 %d 个视频" % (len(rows), len(vids)))
    print("")
    print("  各视频条数（前 8 个）：")
    from collections import Counter
    c = Counter(r["source"] for r in rows)
    for k, v in c.most_common(8):
        print("    %-28s %d 条" % (k, v))
    print("")
    print("[完成] -> %s" % args.out)


if __name__ == "__main__":
    main()
