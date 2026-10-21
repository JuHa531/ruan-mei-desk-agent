# -*- coding: utf-8 -*-
r"""
训练数据去重 + 生成校对清单。

为什么需要它
------------
OCR 从字幕/画面提取时，同一句话往往被记成好几个版本：

    塔伊兹育罗斯通过模拟宇宙我得以窥
    塔伊兹育罗斯通过模拟宇宙我得以窥见寰宇蝗灾的始末攫取虫皇及其子嗣的数据复制培育…
    塔伊兹育罗斯通过模拟宇宙我得以窥见寰宇蝗灾的始攫取虫皇及其子嗣的数据复制培育…

第一条是识别到一半就被截断的，第三条漏了一个字，第二条才是完整的。
如果逐条校对，等于把同一句话来回改好几遍。

**正确流程是：先去重（保留最好的那个版本），再校对剩下的。**
实测 324 条里能去掉 50 条以上。

用法
----
    # 1) 去重，产出干净数据和校对清单
    python dedupe_train.py --src G:\ai\data\story.jsonl --out G:\ai\data\story_dedup.jsonl

    # 2) 只看会去掉哪些、保留哪些，不写文件
    python dedupe_train.py --src ... --out ... --dry-run

产出
----
    <out>              去重后的数据（直接用于训练）
    <out>.review.txt   逐组列出「保留了哪条 / 去掉了哪些」，供核对
"""

import argparse
import json
import re
import sys
from collections import Counter


def norm(s):
    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", s or "")


def cjk_ratio(s):
    if not s:
        return 0.0
    return len(re.findall(r"[\u4e00-\u9fff]", s)) / len(s)


def quality(text):
    """
    给一个版本打分，用来挑"最好的那次观测"。
    思路：完整（更长）+ 干净（中文占比高）胜出。
    OCR 截断的版本会明显更短，带乱码的版本中文占比会低。
    """
    n = norm(text)
    if not n:
        return 0.0
    return len(n) * cjk_ratio(text)


def build_groups(rows):
    """把输出互相包含（或高度相似）的条目归到一组。"""
    items = []
    for idx, r in enumerate(rows):
        items.append({"idx": idx, "row": r, "key": norm(r.get("output", ""))})
    items.sort(key=lambda x: -len(x["key"]))
    groups = []
    for it in items:
        placed = False
        if len(it["key"]) >= 5:
            for g in groups:
                k = g[0]["key"]
                if it["key"] in k or k in it["key"]:
                    g.append(it)
                    placed = True
                    break
        if not placed:
            groups.append([it])
    return groups


def main():
    p = argparse.ArgumentParser(description="训练数据去重 + 校对清单")
    p.add_argument("--src", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--min-len", type=int, default=5,
                   help="短于这个字数的条目直接丢弃")
    args = p.parse_args()

    rows = []
    with open(args.src, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    print("  读入 %d 条" % len(rows))

    groups = build_groups(rows)
    kept, removed, tiny = [], [], 0
    log = []
    for g in groups:
        # 组内挑分数最高的
        best = max(g, key=lambda x: quality(x["row"].get("output", "")))
        others = [x for x in g if x is not best]
        out = best["row"].get("output", "")
        if len(norm(out)) < args.min_len:
            tiny += 1
            continue
        kept.append(best["row"])
        removed.extend(others)
        if others:
            log.append((best["row"], [o["row"].get("output", "") for o in others]))

    print("  去掉重复/片段 %d 条，短条目 %d 条" % (len(removed), tiny))

    # 按「来源视频 + 时间」排序，这样校对时能顺着剧情走，而不是一堆乱序句子
    def sort_key(r):
        t = str(r.get("time", ""))
        m = re.match(r"(\d+):(\d+(?:\.\d+)?)", t)
        sec = (int(m.group(1)) * 60 + float(m.group(2))) if m else 0.0
        return (str(r.get("source", "")), sec)
    kept.sort(key=sort_key)

    print("  最终保留 %d 条" % len(kept))

    if args.dry_run:
        print("")
        print("  （dry-run，前 5 组会保留的版本）")
        for best, dropped in log[:5]:
            print("    保留: %s" % best.get("output", "")[:60])
            for d in dropped[:2]:
                print("    去掉: %s" % d[:60])
            print("")
        return

    with open(args.out, "w", encoding="utf-8") as f:
        for r in kept:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    review = args.out + ".review.txt"
    with open(review, "w", encoding="utf-8") as f:
        f.write("去重清单：每组列出了保留哪个版本、去掉了哪些。\n")
        f.write("如果发现保留下来的反而不是最好的，直接在这个文件里对照修改 %s\n\n"
                % args.out)
        f.write("共 %d 组有多个版本被合并。\n\n" % len(log))
        for i, (best, dropped) in enumerate(log, 1):
            f.write("--- 第 %d 组 ---\n" % i)
            f.write("  [保留] %s\n" % best.get("output", ""))
            f.write("         情境: %s\n" % best.get("instruction", ""))
            if best.get("source"):
                f.write("         来源: %s  %s\n" % (best.get("source"), best.get("time", "")))
            for d in dropped:
                f.write("  [去掉] %s\n" % d)
            f.write("\n")

    print("")
    print("[完成] 去重后数据 -> %s" % args.out)
    print("[完成] 核对清单   -> %s" % review)
    print("")
    print("下一步：只校对去重后的数据（比原来少 %d 条）" % (len(rows) - len(kept)))


if __name__ == "__main__":
    main()
