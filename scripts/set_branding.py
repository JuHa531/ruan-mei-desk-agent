# -*- coding: utf-8 -*-
r"""
换「阮·梅」的图标和背景图（一条命令搞定）。

用法
----
    D:\ai\envs\llm\python.exe scripts\set_branding.py ^
        --icon "F:\qqqqq\Documents\图标.jpeg" ^
        --bg   "F:\qqqqq\Documents\背景.jpeg"

它做的事
--------
  1. 图标：居中裁成正方形 -> app\\assets\\icon.png（512）
                          -> app\\assets\\icon-192.png（给浏览器装应用用）
                          -> app\\assets\\icon.ico（多尺寸，给桌面快捷方式用）
  2. 背景：转成 app\\assets\\bg.jpg
  3. 写 app\\appearance.json，界面刷新后立刻生效

只换图标不换背景：加 --keep-bg（不给 --bg 就是只换图标）。
想调背景的明暗：--dim 0~100（0 最清楚，100 最暗，默认 70）。
"""

import argparse
import json
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(HERE), "app")
ASSETS = os.path.join(APP, "assets")
APPEARANCE = os.path.join(APP, "appearance.json")


def center_square(im):
    w, h = im.size
    s = min(w, h)
    left, top = (w - s) // 2, (h - s) // 2
    return im.crop((left, top, left + s, top + s))


def main():
    ap = argparse.ArgumentParser(description="设置图标和背景图")
    ap.add_argument("--icon", help="图标源文件（jpg/png）")
    ap.add_argument("--bg", help="背景源文件（jpg/png）")
    ap.add_argument("--dim", type=int, default=70, help="背景遮罩浓度 0~100，默认 70")
    a = ap.parse_args()

    if not a.icon and not a.bg:
        ap.error("至少要给 --icon 或 --bg 一个")

    os.makedirs(ASSETS, exist_ok=True)
    cur = {}
    if os.path.exists(APPEARANCE):
        try:
            with open(APPEARANCE, "r", encoding="utf-8") as f:
                cur = json.load(f)
        except Exception:
            cur = {}

    out = {"bg_type": cur.get("bg_type") or "none",
           "bg_file": cur.get("bg_file") or "",
           "icon": cur.get("icon") or "",
           "bg_dim": int(cur.get("bg_dim", a.dim)),
           "sidebar_blend": int(cur.get("sidebar_blend", 55))}

    if a.icon:
        if not os.path.isfile(a.icon):
            sys.exit("[错误] 找不到图标文件：%s" % a.icon)
        im = Image.open(a.icon).convert("RGBA")
        sq = center_square(im)
        sq.resize((512, 512), Image.LANCZOS).save(os.path.join(ASSETS, "icon.png"))
        sq.resize((192, 192), Image.LANCZOS).save(os.path.join(ASSETS, "icon-192.png"))
        sq.resize((256, 256), Image.LANCZOS).save(
            os.path.join(ASSETS, "icon.ico"),
            sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                   (128, 128), (256, 256)])
        out["icon"] = "assets/icon.png"
        print("[图标] %s  %dx%d -> 方形 %d" % (a.icon, im.size[0], im.size[1], sq.size[0]))
        print("       已生成 assets/icon.png / icon-192.png / icon.ico")

    if a.bg:
        if not os.path.isfile(a.bg):
            sys.exit("[错误] 找不到背景文件：%s" % a.bg)
        b = Image.open(a.bg).convert("RGB")
        b.save(os.path.join(ASSETS, "bg.jpg"), quality=92, subsampling=1)
        out["bg_type"] = "image"
        out["bg_file"] = "assets/bg.jpg"
        out["bg_dim"] = max(0, min(100, int(a.dim)))
        print("[背景] %s  %dx%d -> assets/bg.jpg" % (a.bg, b.size[0], b.size[1]))

    with open(APPEARANCE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("[配置] %s" % APPEARANCE)
    print("       " + json.dumps(out, ensure_ascii=False))
    print("")
    print("刷新界面（或重新打开）就能看到。")


if __name__ == "__main__":
    main()
