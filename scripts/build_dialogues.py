# -*- coding: utf-8 -*-
r"""
把「全部字幕」还原成多轮对话训练数据。

背景
----
之前只提取了阮梅一个人的台词，把其他角色的话丢掉了 —— 等于把对话拆成了独白。
但 OCR 时输出的 .all.txt 里**保留着所有角色**（黑塔、三月七、螺丝咕姆、停云…）。

这个脚本把它还原成：
    别人的话 -> user 回合
    阮梅的话 -> assistant 回合

输出是 train_qlora.py 原生支持的 messages 格式：
    {"messages": [{"role":"user","content":"…"}, {"role":"assistant","content":"…"}, …]}

多轮对话比单条问答更能学到「性格在交流中如何保持一致」。

用法
----
    python build_dialogues.py --src G:\ai\data\story.jsonl.all.txt \
                              --out G:\ai\data\dialogues.jsonl
"""

import argparse
import json
import re
import sys
from difflib import SequenceMatcher


ME = re.compile(r"阮|梅")          # 阮梅的标注写法


def norm(s):
    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", s or "")


def ratio(a, b):
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def parse(path):
    """解析 all.txt，返回 [{video, t, speaker, text}]。时间回跳说明换视频。"""
    out, vid, last = [], 0, -1.0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"\[(\d+):(\d+\.\d+)\]\s*(.*?)\s*\|\s*(.*)$", line)
            if not m:
                continue
            t = int(m.group(1)) * 60 + float(m.group(2))
            if t < last - 1.0:      # 时间回跳 -> 下一个视频
                vid += 1
            last = t
            out.append({"video": vid, "t": t,
                        "speaker": m.group(3).strip(), "text": m.group(4).strip()})
    return out


def is_me(speaker):
    n = norm(speaker)
    return bool(ME.search(speaker)) and len(n) <= 6


def dedupe(rows, window=6.0):
    """
    同一句台词会被 OCR 记成多条（标注时有时无）。合并成一个，
    标签优先取「有标注」的那个。
    """
    out = []
    for r in rows:
        merged = False
        for prev in reversed(out[-4:]):
            if r["t"] - prev["t"] > window:
                break
            if ratio(prev["text"], r["text"]) >= 0.8:
                # 保留更长的那条文本；标注优先取非空且更长的
                if len(norm(r["text"])) > len(norm(prev["text"])):
                    prev["text"] = r["text"]
                if r["speaker"] != "—" and len(norm(r["speaker"])) > len(norm(prev["speaker"])):
                    prev["speaker"] = r["speaker"]
                merged = True
                break
        if not merged:
            out.append(dict(r))
    return out


def build(rows, max_turns=8):
    """
    把流水账切成一段段对话。
    规则：遇到「不是阮梅」的台词就开始新的一段（那是别人的提问），
    阮梅自己的连续独白也单独成段。
    """
    convs, cur = [], []
    for r in rows:
        me = is_me(r["speaker"])
        if not me:
            # 别人的话：如果上一轮也是别人的，就继续接；否则开新段
            if cur and cur[-1]["role"] == "user":
                cur.append({"role": "user", "content": r["text"]})
            else:
                if cur:
                    convs.append(cur)
                cur = [{"role": "user", "content": r["text"]}]
        else:
            if cur and cur[-1]["role"] == "assistant":
                cur.append({"role": "assistant", "content": r["text"]})
            else:
                cur.append({"role": "assistant", "content": r["text"]})
        if len(cur) >= max_turns:
            convs.append(cur)
            cur = []
    if cur:
        convs.append(cur)
    # 合并连续的同角色回合：OCR 会把同一句记成好几条，留着会让模型学到"重复说"
    merged = []
    for c in convs:
        m = []
        for x in c:
            if m and m[-1]["role"] == x["role"]:
                # 同一角色连续发言：保留更长的那句
                if len(norm(x["content"])) > len(norm(m[-1]["content"])):
                    m[-1] = x
            else:
                m.append(x)
        merged.append(m)
    convs = merged
    # 只保留「有来有往」的：至少一个 user 和一个 assistant
    return [c for c in convs
            if any(x["role"] == "user" for x in c) and any(x["role"] == "assistant" for x in c)]


def main():
    ap = argparse.ArgumentParser(description="还原多轮对话")
    ap.add_argument("--src", required=True, help=".all.txt 全部字幕")
    ap.add_argument("--out", required=True, help="输出 jsonl")
    ap.add_argument("--min-chars", type=int, default=4)
    ap.add_argument("--system-file", default=None, help="可选的设定文件（一行 system）")
    args = ap.parse_args()

    rows = parse(args.src)
    print("  解析 %d 条（%d 个视频）" % (len(rows), len(set(r["video"] for r in rows))))
    rows = dedupe(rows)
    print("  去重后 %d 条" % len(rows))

    by_video = {}
    for r in rows:
        by_video.setdefault(r["video"], []).append(r)

    all_convs = []
    for v, rs in sorted(by_video.items()):
        rs.sort(key=lambda x: x["t"])
        cs = build(rs)
        all_convs.extend(cs)
    print("  还原出 %d 段对话" % len(all_convs))

    # 过滤太短的回合
    good = []
    for c in all_convs:
        c = [x for x in c if len(norm(x["content"])) >= args.min_chars]
        if any(x["role"] == "user" for x in c) and any(x["role"] == "assistant" for x in c):
            good.append(c)
    print("  有效对话 %d 段" % len(good))

    sys_text = None
    if args.system_file and __import__("os").path.exists(args.system_file):
        sys_text = open(args.system_file, encoding="utf-8").read().strip()

    with open(args.out, "w", encoding="utf-8") as f:
        for c in good:
            item = {"messages": c}
            if sys_text:
                item = {"system": sys_text, "messages": c}
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    turns = [len(c) for c in good]
    print("")
    print("  平均每段 %.1f 轮，最长 %d 轮" % (sum(turns) / len(turns), max(turns)))
    print("  总回合数 %d" % sum(turns))
    print("")
    print("  示例（前 2 段）：")
    for c in good[:2]:
        for x in c[:6]:
            print("    [%s] %s" % (x["role"][:4], x["content"][:52]))
        print("")
    print("[完成] -> %s" % args.out)


if __name__ == "__main__":
    main()
