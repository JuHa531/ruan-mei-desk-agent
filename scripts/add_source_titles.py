# -*- coding: utf-8 -*-
r"""
把训练数据里的来源从「文件名」换成「B 站视频标题 + BV 号」。

为什么需要它
------------
从 B 站下载的文件名是 `31248287184-1-30080.m4s` 这种 ID，光看文件名没法
回到原视频核对。每个下载文件夹里都有 videoInfo.json，里面存着标题和 BV 号，
读出来替换掉，就能：
    1. 直接看懂这句台词出自哪个视频
    2. 用 BV 号在 B 站打开原片，跳到对应时间点

用法
----
    python add_source_titles.py --src G:\ai\data\story_merged.jsonl \
                                --out G:\ai\data\story_titled.jsonl \
                                --downloads "D:\b站下载"

产出
----
    <out>   每行多出 title / bvid / file 三个字段：
              title  视频标题（用于人工识别）
              bvid   B 站编号（拼成 https://www.bilibili.com/video/<bvid> 可直达）
              file   本地文件名（用于在硬盘上找原文件）
"""

import argparse
import json
import os
import re
import sys


def build_title_map(downloads):
    """扫描下载目录，建立 文件夹ID -> {title, bvid} 的映射。"""
    m = {}
    if not os.path.isdir(downloads):
        return m
    for d in os.listdir(downloads):
        folder = os.path.join(downloads, d)
        if not os.path.isdir(folder):
            continue
        for fn in ("videoInfo.json", ".videoInfo"):
            p = os.path.join(folder, fn)
            if not os.path.exists(p):
                continue
            try:
                o = json.load(open(p, encoding="utf-8", errors="replace"))
            except Exception:
                continue
            title = str(o.get("title") or "").strip()
            bvid = str(o.get("bvid") or "").strip()
            p = o.get("p")
            group = str(o.get("groupTitle") or "").strip()
            if title:
                m[str(d)] = {"title": title, "bvid": bvid, "p": p, "group": group}
            break
    return m


def main():
    ap = argparse.ArgumentParser(description="来源换成 B 站标题")
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--downloads", default=r"D:\b站下载")
    args = ap.parse_args()

    tmap = build_title_map(args.downloads)
    print("  从 %s 读到 %d 个视频的标题" % (args.downloads, len(tmap)))
    if not tmap:
        sys.exit("[错误] 没读到任何 videoInfo.json，检查 --downloads 目录")

    rows, hit, miss = [], 0, 0
    with open(args.src, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            src = str(r.get("source", ""))
            vid = src.split("-")[0] if src else ""
            info = tmap.get(vid)
            r["file"] = src
            if info:
                r["source"] = info["title"]
                r["bvid"] = info["bvid"]
                r["page"] = info.get("p")
                if info.get("group"):
                    r["collection"] = info["group"]
                # 直达链接：合集用 ?p=分P编号
                if info["bvid"] and info.get("p"):
                    r["url"] = "https://www.bilibili.com/video/%s?p=%s" % (
                        info["bvid"], info["p"])
                elif info["bvid"]:
                    r["url"] = "https://www.bilibili.com/video/%s" % info["bvid"]
                hit += 1
            else:
                miss += 1
            rows.append(r)

    with open(args.out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print("  共 %d 条：匹配到标题 %d 条，未匹配 %d 条" % (len(rows), hit, miss))
    print("")
    print("  各视频条数：")
    from collections import Counter
    c = Counter(r.get("source", "?") for r in rows)
    for k, v in c.most_common():
        bv = next((r.get("bvid", "") for r in rows if r.get("source") == k), "")
        print("    %3d 条  %-42s %s" % (v, k[:42], bv))
    print("")
    print("[完成] -> %s" % args.out)


if __name__ == "__main__":
    main()
