# -*- coding: utf-8 -*-
r"""
从校对好的主数据生成几种训练集，供不同训练策略使用。

流程
----
    1. 你校对 G:\ai\data\story_final.jsonl（一行一条，只改文字别动 JSON 结构）
    2. 跑本脚本生成训练集
    3. 用生成的某个文件去训练

产出
----
    train_all.jsonl         全部条目，指令式（相当于现状）
    train_context.jsonl     只含带真实情境的（价值最高，但数量少）
    train_style.jsonl       把没有情境的台词转成「续写式」，让模型学语气

train_style.jsonl 的原理
------------------------
那批台词本来就没有对应的提问，硬配一个假情境（比如统一写「（剧情推进）」）
反而会让模型学成"看到没意义的指令就随便说一句"。
不如直接当纯文本训练，让它学"阮梅会怎么组织语言"。脚本用的是 train_qlora.py
原生支持的 {"text": "..."} 格式，不需要额外改动。
"""

import argparse
import json
import os
import re
import sys


def norm(s):
    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", s or "")


def main():
    p = argparse.ArgumentParser(description="生成多种训练集")
    p.add_argument("--src", default=r"G:\ai\data\story_final.jsonl",
                   help="校对好的主数据")
    p.add_argument("--outdir", default=r"G:\ai\data\sets")
    p.add_argument("--min-len", type=int, default=8)
    args = p.parse_args()

    if not os.path.exists(args.src):
        sys.exit("[错误] 找不到 %s" % args.src)
    rows = []
    bad = 0
    with open(args.src, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                bad += 1
                print("  [警告] 第 %d 行 JSON 有语法错误：%s" % (i, e))
    if bad:
        sys.exit("[错误] 有 %d 行 JSON 不合法，先修好再跑（注意引号、逗号）" % bad)
    print("  读入 %d 条，JSON 全部合法" % len(rows))

    os.makedirs(args.outdir, exist_ok=True)
    ctx = [r for r in rows if "剧情推进" not in r.get("instruction", "")]
    noctx = [r for r in rows if "剧情推进" in r.get("instruction", "")]
    noctx = [r for r in noctx if len(norm(r.get("output", ""))) >= args.min_len]

    def dump(name, items, mapper=None):
        path = os.path.join(args.outdir, name)
        with open(path, "w", encoding="utf-8") as f:
            for r in items:
                f.write(json.dumps(mapper(r) if mapper else r, ensure_ascii=False) + "\n")
        print("    %-24s %3d 条" % (name, len(items)))
        return path

    print("")
    print("  生成：")
    dump("train_all.jsonl", rows)
    dump("train_context.jsonl", ctx)
    dump("train_style.jsonl", noctx, lambda r: {"text": r["output"]})

    print("")
    print("  说明：")
    print("    train_all      全部 %d 条（指令式，现状）" % len(rows))
    print("    train_context    %d 条带真实情境（价值最高）" % len(ctx))
    print("    train_style      %d 条转成续写式（只学语气，不需要情境）" % len(noctx))
    print("")
    print("  训练示例：")
    print("    # 只学语气（推荐先试这个）")
    print('    python scripts\\train_qlora.py --data "%s" --out G:\\ai\\out\\style1 --offline --epochs 1 --max-seq-length 512'
          % os.path.join(args.outdir, "train_style.jsonl"))
    print("    # 全部数据")
    print('    python scripts\\train_qlora.py --data "%s" --out G:\\ai\\out\\all1 --offline --no-think --epochs 1 --max-seq-length 1024'
          % os.path.join(args.outdir, "train_all.jsonl"))


if __name__ == "__main__":
    main()
