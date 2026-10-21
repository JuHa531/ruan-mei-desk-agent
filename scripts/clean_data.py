# -*- coding: utf-8 -*-
r"""
清洗 OCR 提取出来的训练数据。

为什么需要它
------------
从字幕/画面 OCR 出来的文本会带各种残渣：
    "、 0 相信，在座的人中…"     开头多了标点和数字
    "r 花开的时间很短…"          开头多了一个孤立字母
    "《 科学怪人 」 。"           括号错配
训练 1 轮时模型学不进去，训练 3 轮就会**照单全收**，输出的开头带乱码。

处理内容
--------
1. 去掉开头结尾的孤立标点、数字、字母
2. 统一全角/半角标点，修正错配的引号括号
3. 丢弃「非中文占比过高」的条目（基本是 OCR 失败的）
4. 报告统计

用法
----
    python clean_data.py --src G:\ai\data\story.jsonl --out G:\ai\data\story_clean.jsonl
"""

import argparse
import json
import re
import sys

# 允许出现的字符：中文、英文字母数字、常用中英文标点
KEEP = re.compile(r"[\u4e00-\u9fffA-Za-z0-9，。！？、；：「」『』（）《》…—～·\-—\s]")
# 开头要剥掉的东西：标点、数字、孤立字母
# 注意：括号（）和引号「」**不剥**，因为「（剧情推进）」这种整体是有意义的，
# 之前把它们剥掉会把左括号吃掉，变成「剧情推进）」。
LEAD_JUNK = re.compile(r"^[\s、。，．·\-—~～*#@$%^&|\\/+=:;'\"`0-9a-zA-Z]+")
# 注意：句末的 。！？ 是正常标点，**不能**剥掉；只剥落单的顿号/逗号/符号
TAIL_JUNK = re.compile(r"[\s、，,．·\-—~～*#@$%^&|\\/+=:;'\"`]+$")
PAIR_FIX = [
    ("《", "「"), ("》", "」"), ("[", "「"), ("]", "」"),
    ("<", "「"), (">", "」"),
]

# 已知的系统性 OCR 错误 —— 这些不是随机噪声，是重复出现的固定误读，
# 可以放心批量替换。都是实际在阮梅数据里观察到的。
OCR_FIXES = {
    # 偏旁被拆开
    "礻也": "祂", "亻十": "什", "亻尔": "你", "亻门": "们", "亻本": "体",
    "亻方": "仿", "亻为": "伪", "目刂": "前", "月刂": "前",
    "彳艮": "很", "讠人": "认", "讠吾": "语", "讠寸": "讨",
    "扌是": "提", "扌旨": "指", "扌圭": "挂",
    "忄青": "情", "氵去": "法", "氵青": "清",
    "纟工": "红", "纟巠": "经",
    # 形近误读
    "别弓": "别紧张", "茸闻": "耳闻", "拄热": "狂热", "掩兰": "掩埋",
    "尸又": "尸骸", "尸只": "尸骸", "泳川": "冰川", "泌密": "秘密",
    "咼度": "高度", "旃究": "研究", "培合": "培育", "找斗": "战斗",
    "木绝": "未绝", "責重": "贵重", "城滇": "城镇", "剩绣": "刺绣",
    "刺手手法": "刺绣手法", "不爱适": "不爱说话", "解铥": "解谜",
    "鹅斗": "战斗", "開启": "开启", "苦斗": "战斗",
    # 繁体混入
    "短暫": "短暂", "這": "这", "們": "们", "說": "说", "時": "时",
    "間": "间", "歲": "岁", "機": "机", "體": "体", "愛": "爱",
    "後": "后", "點": "点", "實": "实", "驗": "验", "東": "东",
    # 语气词/标点误读
    "冫": "", "彐": "", "凵": "",
}


def ratio_cjk(s):
    if not s:
        return 0.0
    return len(re.findall(r"[\u4e00-\u9fff]", s)) / len(s)


def clean_text(s):
    s = (s or "").strip()
    for a, b in PAIR_FIX:
        s = s.replace(a, b)
    for a, b in OCR_FIXES.items():
        s = s.replace(a, b)
    s = re.sub(r"[ \t]+", " ", s)
    s = LEAD_JUNK.sub("", s)
    s = TAIL_JUNK.sub("", s)
    # 中文之间多余的空格去掉
    s = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", s)
    # 中文标点前后的空格也去掉（OCR 会在「了 。 无论」这种地方插空格）
    CJK_PUNC = "，。！？、；：「」『』（）《》…—～·"
    s = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[%s])" % CJK_PUNC, "", s)
    s = re.sub(r"(?<=[%s])\s+(?=[\u4e00-\u9fff])" % CJK_PUNC, "", s)
    s = re.sub(r"(?<=[%s])\s+(?=[%s])" % (CJK_PUNC, CJK_PUNC), "", s)
    # 杂散的 OCR 残片
    s = s.replace("丷", "、").replace("冫", "").replace("彐", "").replace("凵", "")
    # OCR 常把左书名号「读成 r / 《 / ( 后面跟个空格
    s = re.sub(r"(?:^|[\s，。、；：])[rR]\s+(?=[\u4e00-\u9fff]{2,8}[」』])", "「", s)
    s = re.sub(r"(?<![A-Za-z])[rR]\s*(?=[\u4e00-\u9fff]{2,8}」)", "「", s)
    # 中文之间夹着单个孤立字母（OCR 残渣），去掉
    s = re.sub(r"(?<=[\u4e00-\u9fff])\s+[A-Za-z]\s+(?=[\u4e00-\u9fff])", "", s)
    # 连续标点收敛
    s = re.sub(r"[，。、]{2,}", "，", s)
    s = re.sub(r"[。]{2,}", "。", s)
    return s.strip()


def main():
    p = argparse.ArgumentParser(description="清洗训练数据")
    p.add_argument("--src", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--min-cjk", type=float, default=0.65,
                   help="中文字符占比低于这个值就丢弃（默认 0.65）")
    p.add_argument("--min-len", type=int, default=6)
    p.add_argument("--drop-placeholder", action="store_true",
                   help="丢弃指令是「（剧情推进）」这类占位符的条目")
    args = p.parse_args()

    kept, dropped = [], []
    with open(args.src, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            old_out = rec.get("output", "")
            new_out = clean_text(old_out)
            new_in = clean_text(rec.get("instruction", ""))
            reason = None
            if len(new_out) < args.min_len:
                reason = "太短"
            elif ratio_cjk(new_out) < args.min_cjk:
                reason = "中文占比 %.2f" % ratio_cjk(new_out)
            elif args.drop_placeholder and "剧情推进" in new_in:
                reason = "占位指令"
            if reason:
                dropped.append((reason, old_out[:40]))
                continue
            item = {"instruction": new_in or "（继续）", "output": new_out}
            # 保留来源、时间戳等附加字段，校对时要用
            for k, v in rec.items():
                if k not in ("instruction", "output"):
                    item[k] = v
            kept.append(item)

    with open(args.out, "w", encoding="utf-8") as f:
        for item in kept:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    changed = sum(1 for k, (r, o) in zip(kept, []))
    print("  原始 %d 条 -> 保留 %d 条，丢弃 %d 条" %
          (len(kept) + len(dropped), len(kept), len(dropped)))
    if dropped:
        from collections import Counter
        for reason, n in Counter(r for r, _ in dropped).most_common(5):
            print("    丢弃原因「%s」: %d 条" % (reason, n))
    print("")
    print("  清洗前后对照（前 5 条）：")
    with open(args.src, "r", encoding="utf-8") as f:
        originals = [json.loads(l) for l in f if l.strip()][:5]
    for i, o in enumerate(originals):
        print("    原: %s" % o.get("output", "")[:44])
        if i < len(kept):
            print("    新: %s" % kept[i]["output"][:44])
    print("")
    print("[完成] -> %s" % args.out)


if __name__ == "__main__":
    main()
