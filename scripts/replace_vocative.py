# -*- coding: utf-8 -*-
r"""
把训练数据里对「你」的称呼替换成别的词（安全版）。

为什么不能直接全文替换
----------------------
「星」这个字在《崩坏：星穹铁道》里到处都是：星神、星球、行星、群星……
直接 replace("星", "亲爱的") 会得到「亲爱的神」「亲爱的球」这种荒谬结果。

所以这里只替换**作称呼的那一个**，也就是前后被标点或句子边界包起来的「星」：
    星，你还记得我的研究        → 亲爱的，你还记得我的研究
    现在，星，你还想问什么？     → 现在，亲爱的，你还想问什么？
而「星神」「星球」这类不受影响。

用法
----
    python replace_vocative.py --src G:\ai\data\story_titled.jsonl \
                               --out G:\ai\data\story_named.jsonl \
                               --word 星 --to 亲爱的

    # 只看会改哪些，不写文件
    python replace_vocative.py --src ... --out ... --word 星 --to 亲爱的 --dry-run
"""

import argparse
import json
import re
import sys


def main():
    ap = argparse.ArgumentParser(description="安全替换称呼")
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--word", required=True, help="被替换的称呼，如 星")
    ap.add_argument("--to", required=True, help="替换成什么，如 亲爱的")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # 只匹配「前后是标点/空格/句首句尾」的称呼
    pat = re.compile(r"(^|[，。！？、；：…\s（「])" + re.escape(args.word)
                     + r"(?=[，。！？、；：…\s）」]|$)")

    rows, changed, total_hits = [], 0, 0
    with open(args.src, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            old = r.get("output", "")
            new, n = pat.subn(lambda m: m.group(1) + args.to, old)
            if n:
                changed += 1
                total_hits += n
                if args.dry_run:
                    print("  改前: %s" % old[:60])
                    print("  改后: %s" % new[:60])
                    print("")
            r["output"] = new
            rows.append(r)

    print("  共 %d 条，%d 条被修改，替换 %d 处「%s」-> 「%s」"
          % (len(rows), changed, total_hits, args.word, args.to))
    # 检查有没有误伤
    bad = [r["output"] for r in rows if args.to + "神" in r["output"]
           or args.to + "球" in r["output"] or args.to + "系" in r["output"]]
    if bad:
        print("  [警告] 发现可疑结果：")
        for b in bad[:3]:
            print("    " + b[:60])
    else:
        print("  未发现误伤（没有出现「%s神」这类组合）" % args.to)

    if args.dry_run:
        print("")
        print("  （dry-run，未写文件）")
        return

    with open(args.out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("")
    print("[完成] -> %s" % args.out)


if __name__ == "__main__":
    main()
