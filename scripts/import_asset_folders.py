# -*- coding: utf-8 -*-
r"""
把用户整理好的背景图 / 表情包导入梅梅的 app\assets。

原图保留在 D:\ai\图片素材 和 D:\ai\表情包素材；这里生成：
  assets\bg-lib-01.jpg + bg-lib-01-thumb.jpg + bg-library.json
  assets\sticker-01.jpg + sticker-01-thumb.jpg + stickers.json

背景图最长边压到 1920，缩略图裁成 320 方图；表情包压到 512 方图。
"""

import glob
import json
import os

from PIL import Image, ImageOps

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
ASSETS = os.path.join(APP, "assets")
BG_SRC = r"D:\ai\图片素材"
ST_SRC = r"D:\ai\表情包素材"

STICKER_RULES = {
    "叹气": ["叹气", "唉", "无奈", "累了", "好累", "累死", "疲惫", "算了",
             "又来了", "没辙", "失望", "可惜"],
    "无语": ["无语", "离谱", "沉默", "不知道说什么", "服了", "尴尬",
             "真行", "没话说"],
    "疑惑": ["疑惑", "困惑", "不明白", "不懂", "奇怪", "怎么回事", "嗯？",
             "为什么", "不确定", "搞不懂"],
    "疑问（要什么奖励？）": ["奖励", "要什么", "想要什么", "猜猜", "奖励你",
                       "期待", "要求", "想要点", "给我什么"],
    "悠闲": ["悠闲", "休息", "喝茶", "茶点", "放松", "慢慢来", "不急",
             "舒服", "惬意", "闲暇", "偷懒"],
}


def merge_custom_stickers(stickers, assets=ASSETS):
    """Keep generated additions when re-importing the user's original folders."""
    custom = os.path.join(assets, 'stickers.custom.json')
    if os.path.isfile(custom):
        with open(custom, encoding='utf-8') as f:
            additions = json.load(f)
        existing = {item['file'] for item in stickers}
        for item in additions:
            rel = str(item.get('file', ''))
            if not rel.startswith('assets/') or '..' in rel.split('/'):
                continue
            if rel not in existing and os.path.isfile(os.path.join(assets, rel[7:])):
                stickers.append(item)
                existing.add(rel)
    return stickers


def save_jpeg(im, path, max_side, quality=88, square=False):
    im = ImageOps.exif_transpose(im).convert("RGB")
    if square:
        im = ImageOps.fit(im, (max_side, max_side), Image.Resampling.LANCZOS)
    else:
        im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    im.save(path, "JPEG", quality=quality, optimize=True)
    return im.size


def main():
    os.makedirs(ASSETS, exist_ok=True)
    bg_items, stickers = [], []

    bg_files = sorted(glob.glob(os.path.join(BG_SRC, "*")))
    bg_files = [p for p in bg_files if os.path.splitext(p)[1].lower() in
                (".jpg", ".jpeg", ".png", ".webp", ".bmp")]
    for i, src in enumerate(bg_files, 1):
        name = "bg-lib-%02d" % i
        dst = os.path.join(ASSETS, name + ".jpg")
        thumb = os.path.join(ASSETS, name + "-thumb.jpg")
        try:
            size = save_jpeg(Image.open(src), dst, 1920, 88)
            save_jpeg(Image.open(src), thumb, 320, 82, square=True)
        except Exception as e:
            print("[跳过背景] %s: %s" % (src, e))
            continue
        bg_items.append({"id": i, "file": "assets/%s.jpg" % name,
                         "thumb": "assets/%s-thumb.jpg" % name,
                         "width": size[0], "height": size[1]})

    st_files = sorted(glob.glob(os.path.join(ST_SRC, "*")))
    st_files = [p for p in st_files if os.path.splitext(p)[1].lower() in
                (".jpg", ".jpeg", ".png", ".webp", ".bmp")]
    for i, src in enumerate(st_files, 1):
        name = "sticker-%02d" % i
        dst = os.path.join(ASSETS, name + ".jpg")
        thumb = os.path.join(ASSETS, name + "-thumb.jpg")
        try:
            save_jpeg(Image.open(src), dst, 512, 90, square=True)
            save_jpeg(Image.open(src), thumb, 220, 86, square=True)
        except Exception as e:
            print("[跳过表情] %s: %s" % (src, e))
            continue
        label = os.path.splitext(os.path.basename(src))[0]
        mood = label.split("（", 1)[0]
        keywords = STICKER_RULES.get(label) or STICKER_RULES.get(mood) or [mood]
        stickers.append({"id": i, "file": "assets/%s.jpg" % name,
                         "thumb": "assets/%s-thumb.jpg" % name,
                         "label": label, "mood": mood,
                         "keywords": keywords})

    with open(os.path.join(ASSETS, "bg-library.json"), "w", encoding="utf-8") as f:
        json.dump(bg_items, f, ensure_ascii=False, indent=2)
    stickers = merge_custom_stickers(stickers)
    with open(os.path.join(ASSETS, "stickers.json"), "w", encoding="utf-8") as f:
        json.dump(stickers, f, ensure_ascii=False, indent=2)
    print("背景 %d 张，表情 %d 张" % (len(bg_items), len(stickers)))
    print("输出：%s" % ASSETS)


if __name__ == "__main__":
    main()
