# -*- coding: utf-8 -*-
r"""
把 import_voice_videos.py 产出的新片段合并进 GPT-SoVITS 数据集。

- 老片段（0001~0106）原样保留；
- "全语音"全部采纳；
- "博物馆导览"按时间均匀抽到指定分钟数，避免某一小段独白占比过高；
- 新片段从 0107 开始编号，list.txt 重写为 老 + 新。

用法
----
    D:\ai\envs\tts\python.exe scripts\merge_voice_dataset.py `
        --staging G:\ai\voice\staging_20261020 --museum-minutes 12
"""

import argparse
import json
import os
import shutil
import sys


def load_rows(path):
    if not os.path.isfile(path):
        sys.exit("找不到 %s" % path)
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return [r for r in rows if r.get("kept")]


# 这几条是 ASR 明显听错/没听全的：宁可少 30 秒，也别把错误音素喂进模型。
SKIP_ALL_VOICE = {"0002.wav", "0007.wav", "0019.wav", "0040.wav", "0055.wav"}


def pick_even(rows, target_seconds):
    rows = sorted(rows, key=lambda r: r.get("start", 0))
    total = sum(float(r["dur"]) for r in rows)
    if total <= target_seconds or not rows:
        return rows
    # 按累计时长的分位点取，保证覆盖整段视频，而不是只取开头。
    picked, used = [], set()
    n = max(1, int(round(len(rows) * target_seconds / total)))
    for i in range(n):
        want = (i + 0.5) * total / n
        acc, best = 0.0, None
        for idx, r in enumerate(rows):
            acc += float(r["dur"])
            if best is None or abs(acc - want) < best[0]:
                best = (abs(acc - want), idx)
        idx = best[1]
        if idx not in used:
            used.add(idx)
            picked.append(rows[idx])
    return picked


def main():
    ap = argparse.ArgumentParser(description="合并新语音片段到 GPT-SoVITS 数据集")
    ap.add_argument("--old-list", default=r"G:\ai\voice\list.txt")
    ap.add_argument("--old-dir", default=r"G:\ai\voice\dataset")
    ap.add_argument("--staging", default=r"G:\ai\voice\staging_20261020")
    ap.add_argument("--out-list", default=r"G:\ai\voice\list.txt")
    ap.add_argument("--out-dir", default=r"G:\ai\voice\dataset")
    ap.add_argument("--museum-minutes", type=float, default=12.0)
    args = ap.parse_args()

    old_lines = []
    if os.path.isfile(args.old_list):
        with open(args.old_list, encoding="utf-8") as f:
            old_lines = [l.rstrip("\n") for l in f if l.strip()]
    existing = [int(os.path.splitext(n)[0]) for n in os.listdir(args.old_dir)
                if n.endswith(".wav") and n[:4].isdigit()]
    next_idx = (max(existing) + 1) if existing else 1

    all_rows = [r for r in load_rows(os.path.join(args.staging, "all_voice", "metadata.jsonl"))
                if os.path.basename(r["path"]) not in SKIP_ALL_VOICE]
    museum_rows = load_rows(os.path.join(args.staging, "museum", "metadata.jsonl"))
    museum_pick = pick_even(museum_rows, args.museum_minutes * 60)

    picked = ([("all_voice", r) for r in sorted(all_rows, key=lambda x: x["index"])]
              + [("museum", r) for r in museum_pick])
    print("老片段 %d 条；新片段 all_voice %d + museum %d"
          % (len(old_lines), len(all_rows), len(museum_pick)))

    new_lines = []
    for source, r in picked:
        dst = os.path.join(args.out_dir, "%04d.wav" % next_idx)
        shutil.copy2(r["path"].replace("/", os.sep), dst)
        new_lines.append("%s|ruanmei|zh|%s"
                         % (dst.replace("\\", "/"), r["text"]))
        r["merged_path"] = dst.replace("\\", "/")
        r["merged_index"] = next_idx
        next_idx += 1

    with open(args.out_list, "w", encoding="utf-8") as f:
        for line in old_lines + new_lines:
            f.write(line + "\n")

    total = sum(float(r["dur"]) for _, r in picked)
    print("写入 %d 条新片段，新增 %.1f 分钟；list.txt 共 %d 条"
          % (len(new_lines), total / 60, len(old_lines) + len(new_lines)))
    print("新片段编号 %04d ~ %04d" % (next_idx - len(new_lines), next_idx - 1))
    report = os.path.join(args.staging, "merge_report.json")
    with open(report, "w", encoding="utf-8") as f:
        json.dump({"picked": picked, "new_minutes": total / 60}, f,
                  ensure_ascii=False, indent=2)
    print("报告：%s" % report)


if __name__ == "__main__":
    main()
