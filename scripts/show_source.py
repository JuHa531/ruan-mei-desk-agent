# -*- coding: utf-8 -*-
r"""
按视频标题查训练数据里的对应台词，方便回 B 站核对。

用法
----
    # 看某个视频的全部台词（按时间顺序）
    python show_source.py --title 1.6同行⑥

    # 只看第一句
    python show_source.py --title 1.6同行⑥ --first 1

    # 列出现在有哪些视频、各多少条
    python show_source.py --list

输出里会带 B 站直达链接和时间点，打开链接跳到那个时间就能听原句。
"""

import argparse
import json
import os
import sys
from collections import Counter


def main():
    ap = argparse.ArgumentParser(description="按视频标题查台词")
    ap.add_argument("--data", default=r"G:\ai\data\story_titled.jsonl")
    ap.add_argument("--title", help="视频标题关键词，支持部分匹配")
    ap.add_argument("--first", type=int, help="只看前 N 条")
    ap.add_argument("--list", action="store_true", help="列出所有视频及条数")
    args = ap.parse_args()

    if not os.path.exists(args.data):
        sys.exit("[错误] 找不到 %s" % args.data)
    rows = []
    with open(args.data, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    if args.list or not args.title:
        print("  数据文件: %s（共 %d 条）" % (args.data, len(rows)))
        print("")
        c = Counter(r.get("source", "?") for r in rows)
        for k, v in c.most_common():
            u = next((r.get("url", "") for r in rows if r.get("source") == k), "")
            print("  %3d 条  %-40s %s" % (v, k[:40], u))
        print("")
        print("  查某个视频：python show_source.py --title \"标题关键词\"")
        return

    hit = [r for r in rows if args.title in str(r.get("source", ""))]
    if not hit:
        print("  没有匹配「%s」的条目。" % args.title)
        print("  用 --list 看看有哪些标题。")
        return

    print("  【%s】共 %d 条" % (hit[0].get("source"), len(hit)))
    if hit[0].get("url"):
        print("  链接: %s" % hit[0]["url"])
    print("")

    n = args.first if args.first else len(hit)
    for i, r in enumerate(hit[:n], 1):
        print("  %d. [%s]" % (i, r.get("time", "?")))
        if r.get("instruction") and "剧情推进" not in r["instruction"]:
            print("     情境: %s" % r["instruction"][:60])
        print("     台词: %s" % r["output"])
        print("")


if __name__ == "__main__":
    main()
