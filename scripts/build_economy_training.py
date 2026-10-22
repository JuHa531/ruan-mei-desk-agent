# -*- coding: utf-8 -*-
"""合并故事、对话和人工反应样本，生成使用精简 system 的低成本训练集。"""

import argparse
import json
import os
import sys

from set_character import TRAINING_SETTING


def load_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def normalize(row):
    if row.get("messages"):
        msgs = row["messages"]
        user = next((m.get("content", "") for m in msgs if m.get("role") == "user"), "")
        assistant = next((m.get("content", "") for m in msgs if m.get("role") == "assistant"), "")
    else:
        user = row.get("instruction", "")
        assistant = row.get("output") or row.get("response") or ""
    if not user or not assistant:
        return None
    return {
        "system": TRAINING_SETTING,
        "instruction": user,
        "output": assistant,
        "source": row.get("source") or os.path.basename(row.get("file", "")) or "unknown",
    }


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description="生成精简 system 的训练集")
    ap.add_argument("--story", default=r"G:\ai\data\story_v10.jsonl")
    ap.add_argument("--dialogues", default=r"G:\ai\data\dialogues.jsonl")
    ap.add_argument("--reactions", default=os.path.join(
        root, "data", "ruanmei_reaction_examples.jsonl"))
    ap.add_argument("--out", default=r"G:\ai\data\story_economy_v11.jsonl")
    args = ap.parse_args()

    inputs = [args.story, args.dialogues, args.reactions]
    rows = []
    for path in inputs:
        if not os.path.isfile(path):
            print("[警告] 跳过不存在的数据：%s" % path, file=sys.stderr)
            continue
        for row in load_jsonl(path):
            item = normalize(row)
            if item:
                rows.append(item)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("已生成 %d 条，system 每条 %d 字：%s"
          % (len(rows), len(TRAINING_SETTING), args.out))


if __name__ == "__main__":
    main()
