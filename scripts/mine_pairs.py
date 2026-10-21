# -*- coding: utf-8 -*-
r"""
从你的原始材料里「抽取」训练样本 —— 用本地 Ollama 当助手，但只抽取、不改写。

为什么要这样做
--------------
「让 AI 学会我的思维方法」不能靠凭空写问答对，那样成本太高。更现实的做法是：
把你已有的聊天记录、邮件、笔记丢进来，让本地模型帮你**找出**「情境 → 你本人的回应」，
然后你只需要审核和修正，而不是从零写。

最关键的一条设计：output 必须是你的原话，逐字照抄，模型不允许改写。
脚本会自动校验这一点 —— 如果模型改写了，那条会被标记出来让你检查。
（如果训练数据里混进模型自己编的话，你克隆出来的是「模型的语气」，不是你的。）

用法
----
    # 先看会切成几块（不调用模型，最快）
    python mine_pairs.py --src 聊天记录.txt --out G:\ai\data\raw.jsonl --dry-run

    # 正式抽取（需要 Ollama 在运行）
    python mine_pairs.py --src 聊天记录.txt --out G:\ai\data\raw.jsonl

    # 换模型 / 调块大小
    python mine_pairs.py --src 邮件.txt --out G:\ai\data\mail.jsonl --model qwen3:8b --chunk 2500

产出
----
    <out>              可直接用于训练的 jsonl
    <out>.review.txt   需要人工检查的条目（模型改写过、或明显异常）
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request


SYSTEM_PROMPT = """你是一个中文训练数据整理助手。用户会给你一段他本人写的文字记录（可能是聊天、邮件、笔记）。

你的任务是：从这段记录里找出「情境 → 用户本人的回应」的配对。

必须严格遵守：
1. output 必须是用户的原话，一字不改地照抄，包括语气词和标点。绝对不要润色、补全、改写或换一种说法。
2. instruction 是你根据上下文概括出的情境，描述用户当时面对的是什么情况或问题。
3. 如果某段内容里找不到明确的「情境 → 回应」结构，就跳过，不要硬凑。
4. 如果用户的原话太短（少于 15 个字），跳过。
5. 只输出 JSON 数组，不要任何解释文字，不要 markdown 代码块。格式：
[{"instruction": "描述情境", "output": "用户的原话"}]

如果没有找到任何合适的配对，输出空数组 []。"""


def normalize(s):
    """去掉空白和标点，只留文字，用于校验模型有没有改写。"""
    return re.sub(r"[\s\W_]+", "", str(s))


def split_chunks(text, size):
    """按段落边界切块，尽量不切断句子。"""
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, buf = [], ""
    for p in paras:
        if len(p) > size:
            if buf:
                chunks.append(buf)
                buf = ""
            for i in range(0, len(p), size):
                chunks.append(p[i:i + size])
        elif buf and len(buf) + len(p) + 2 > size:
            chunks.append(buf)
            buf = p
        else:
            buf = f"{buf}\n\n{p}" if buf else p
    if buf:
        chunks.append(buf)
    return chunks


def call_ollama(model, chunk, timeout, base_url):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"以下是记录内容：\n\n{chunk}"},
        ],
        "stream": False,
        "options": {"temperature": 0.2},
    }
    req = urllib.request.Request(
        base_url.rstrip("/") + "/api/chat",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"连不上 Ollama（{base_url}）：{e.reason}\n"
            "先确认 Ollama 正在运行：在终端执行 ollama list 有输出即可。") from e
    return body.get("message", {}).get("content", "")


def parse_pairs(raw):
    """从模型输出里抠出 JSON 数组，容忍它多写了废话或代码块。"""
    if not raw:
        return []
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return []
    out = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        ins = str(item.get("instruction", "")).strip()
        resp = str(item.get("output", "")).strip()
        if ins and resp:
            out.append({"instruction": ins, "output": resp})
    return out


def main():
    p = argparse.ArgumentParser(description="从原始材料抽取训练样本")
    p.add_argument("--src", required=True, help="输入：你的聊天记录/邮件/笔记（txt 或 md）")
    p.add_argument("--out", required=True, help="输出 jsonl")
    p.add_argument("--model", default="qwen3:4b")
    p.add_argument("--chunk", type=int, default=3000, help="每块字数，太大模型会偷懒")
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--ollama", default="http://127.0.0.1:11434")
    p.add_argument("--dry-run", action="store_true", help="只切块，不调用模型")
    args = p.parse_args()

    if not os.path.exists(args.src):
        sys.exit(f"[错误] 找不到输入文件 {args.src}")
    with open(args.src, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    chunks = split_chunks(text, args.chunk)
    total_chars = sum(len(c) for c in chunks)
    print(f"[输入] {len(text)} 字 -> 切成 {len(chunks)} 块（每块约 {args.chunk} 字）")
    if args.dry_run:
        for i, c in enumerate(chunks[:3], 1):
            print(f"\n--- 第 {i} 块预览（共 {len(c)} 字）---")
            print(c[:300] + ("..." if len(c) > 300 else ""))
        if len(chunks) > 3:
            print(f"\n... 还有 {len(chunks) - 3} 块")
        print(f"\n[完成] 确认没问题就去掉 --dry-run 正式运行。")
        return

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    kept, flagged = [], []
    for i, chunk in enumerate(chunks, 1):
        print(f"  处理第 {i}/{len(chunks)} 块 ……", end="", flush=True)
        try:
            raw = call_ollama(args.model, chunk, args.timeout, args.ollama)
        except RuntimeError as e:
            sys.exit(f"\n[错误] {e}")
        pairs = parse_pairs(raw)
        norm_chunk = normalize(chunk)
        good = 0
        for pair in pairs:
            # 校验：output 必须能在原文里找到，否则说明模型改写了
            if normalize(pair["output"]) in norm_chunk:
                kept.append(pair)
                good += 1
            else:
                pair["_reason"] = "模型可能改写了原话，原文中找不到这段"
                flagged.append(pair)
        print(f" 得到 {len(pairs)} 条，其中原话校验通过 {good} 条")

    with open(args.out, "w", encoding="utf-8") as f:
        for pair in kept:
            f.write(json.dumps({"instruction": pair["instruction"],
                                "output": pair["output"]}, ensure_ascii=False) + "\n")

    review_path = args.out + ".review.txt"
    if flagged:
        with open(review_path, "w", encoding="utf-8") as f:
            f.write("以下条目模型可能改写了你的原话，需要人工核对。\n")
            f.write("确认是你本人的话就手动改回 jsonl，不是你写过的就删掉。\n\n")
            for j, pair in enumerate(flagged, 1):
                f.write(f"--- 第 {j} 条 ---\n")
                f.write(f"情境: {pair['instruction']}\n")
                f.write(f"模型给的: {pair['output']}\n")
                f.write(f"问题: {pair['_reason']}\n\n")

    print("")
    print(f"[完成] 保留 {len(kept)} 条 -> {os.path.abspath(args.out)}")
    if flagged:
        print(f"       待核对 {len(flagged)} 条 -> {os.path.abspath(review_path)}")
    print("")
    print("下一步：人工过一遍产出，把不像你的删掉，然后做体检：")
    print(f"  D:\\ai\\envs\\llm\\python.exe scripts\\prepare_data.py check --src \"{args.out}\"")


if __name__ == "__main__":
    main()
