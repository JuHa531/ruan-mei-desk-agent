# -*- coding: utf-8 -*-
r"""
训练数据准备 / 体检工具。

用法
----
1) 把「原始笔记」直接变成风格数据集（不需要人工标注，可立刻训练）：
       python prepare_data.py completion --src 我的笔记.md --out G:\ai\data\style.jsonl

2) 开训之前，先给已写好的指令数据集做一次体检：
       python prepare_data.py check --src G:\ai\data\train.jsonl
"""

import argparse
import json
import re
import sys
from collections import Counter


def _pack(paras, max_chars):
    """把段落打包成不超过 max_chars 的块。"""
    out, buf = [], ""
    for p in paras:
        if len(p) > max_chars:
            if buf:
                out.append(buf)
                buf = ""
            for i in range(0, len(p), max_chars):
                out.append(p[i:i + max_chars])
        elif buf and len(buf) + len(p) + 2 > max_chars:
            out.append(buf)
            buf = p
        else:
            buf = f"{buf}\n\n{p}" if buf else p
    if buf:
        out.append(buf)
    return out


def split_blocks(text, min_chars=80, max_chars=800):
    """
    先按 Markdown 标题切成「语义块」，块内再按段落打包。
    这样做出来的每一条样本都是完整的一段思路，而不是被从中间截断的半句话。
    """
    # 把 --- / *** / ___ 这类纯分隔线去掉，它们不该进训练数据
    text = re.sub(r"^[ \t]*([-*_])(?:[ \t]*\1){2,}[ \t]*$", "", text, flags=re.M)
    # 标题处断开（保留标题文字本身）
    sections = re.split(r"^([ \t]*#{1,6}[ \t]+)", text, flags=re.M)
    merged = []
    for i, s in enumerate(sections):
        if re.fullmatch(r"[ \t]*#{1,6}[ \t]+", s or ""):
            merged.append(s)
        elif merged:
            merged[-1] = merged[-1] + s
        else:
            merged.append(s)

    chunks = []
    for sec in merged:
        paras = [p.strip() for p in re.split(r"\n\s*\n", sec) if p.strip()]
        if paras:
            chunks.extend(_pack(paras, max_chars))
    return [c for c in chunks if len(c) >= min_chars]


def cmd_completion(args):
    with open(args.src, "r", encoding="utf-8") as f:
        text = f.read()

    blocks = split_blocks(text, args.min_chars, args.max_chars)
    if not blocks:
        sys.exit("[错误] 没有切出任何有效片段，检查一下 --min-chars 是不是设太大了。")

    # 可选：在每段前面加一句引导语，让模型学到「被要求写这类东西」的场景
    with open(args.out, "w", encoding="utf-8") as f:
        for b in blocks:
            f.write(json.dumps({"text": b}, ensure_ascii=False) + "\n")

    total = sum(len(b) for b in blocks)
    print(f"[完成] 写出 {len(blocks)} 条到 {args.out}")
    print(f"       总字数 {total}，平均每条 {total // len(blocks)} 字")
    print("       注意：这是「续写式」数据集，学到的是语气和表达习惯，不是事实记忆。")
    if len(blocks) < 20:
        print("")
        print("[提示] 样本数偏少。续写式数据靠「量」堆效果，建议原始文字至少攒到几万字，")
        print("       或者用 --max-chars 300 切成更细的块来增加条数。")


def cmd_check(args):
    records, bad = [], 0
    with open(args.src, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append((i, json.loads(line)))
            except json.JSONDecodeError as e:
                bad += 1
                print(f"[第 {i} 行] JSON 语法错误：{e}")

    if not records:
        sys.exit("[错误] 文件里没有可解析的 JSON 行。")

    lengths, dup, kinds = [], 0, Counter()
    seen = set()
    for lineno, r in records:
        if "text" in r:
            kinds["text"] += 1
            body = r["text"]
        elif "instruction" in r and ("output" in r or "response" in r):
            kinds["instruction"] += 1
            body = r["instruction"] + (r.get("output") or r.get("response"))
        elif "messages" in r:
            kinds["messages"] += 1
            body = "".join(m.get("content", "") for m in r["messages"])
        else:
            print(f"[第 {lineno} 行] 字段不认识，需要 text / instruction+output / messages 之一")
            continue

        lengths.append(len(body))
        key = body[:200]
        if key in seen:
            dup += 1
        seen.add(key)

    lengths.sort()
    n = len(lengths)
    print("")
    print("=" * 46)
    print(f"  样本数        {n}")
    print(f"  格式分布      {dict(kinds)}")
    print(f"  JSON 错误行   {bad}")
    print(f"  疑似重复      {dup}")
    print(f"  长度中位数    {lengths[n // 2]} 字")
    print(f"  长度范围      {lengths[0]} ~ {lengths[-1]} 字")
    print("=" * 46)

    print("")
    if n < 100:
        print("[建议] 少于 100 条：先别急着训练，效果大概率不如把系统提示词写好。")
    elif n < 500:
        print("[建议] 100~500 条：适合改语气、改输出格式。可以开跑，但要盯着效果。")
    else:
        print("[建议] 500 条以上：可以认真跑一轮了。")

    if dup > n * 0.1:
        print("[警告] 重复样本超过 10%，去掉重复项再训练，否则模型会过度记住那几条。")
    if lengths[0] < 20:
        print("[警告] 有极短样本，可能给模型噪声，建议删掉。")
    if lengths[-1] > 4000:
        print("[警告] 有超长样本，训练时会占大量显存，考虑拆短或删掉。")


def main():
    p = argparse.ArgumentParser(description="训练数据准备 / 体检")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("completion", help="原始笔记 -> 续写式数据集")
    c.add_argument("--src", required=True, help="输入：.md / .txt")
    c.add_argument("--out", required=True, help="输出：.jsonl")
    c.add_argument("--min-chars", type=int, default=80, help="短于这个字数的块丢弃")
    c.add_argument("--max-chars", type=int, default=800, help="长于这个字数的块继续切分")
    c.set_defaults(func=cmd_completion)

    k = sub.add_parser("check", help="检查一份 jsonl 数据集")
    k.add_argument("--src", required=True)
    k.set_defaults(func=cmd_check)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
