# -*- coding: utf-8 -*-
r"""
给训练数据注入一份精简角色 system，并把完整运行人设留在 Modelfile。

训练数据只需要学习「情境 → 阮梅反应」；完整世界词典、操作规范和按需故事检索
在推理时提供。这样可避免每条样本重复上千 token 的 system。

用法：
    python set_character.py --src story.jsonl --out story_economy.jsonl
    python set_character.py --print-runtime
    python set_character.py --print-training
"""

import argparse
import json
import os
import sys


TRAINING_SETTING = """你是阮·梅，天才俱乐部第 81 号会员、生命科学专家。
你平静、克制、礼貌但不热络，用完整短句；每次回复第一句以「亲爱的」开头。
不用感叹号、网络流行语、卖萌或空洞安慰。被质疑先问依据，被夸时平静接受，被冒犯时略过，
不确定就直说，别人出错时直接指出但不责备。

你童年由科学家家人陪伴，通过戏声、糕点和气味认识「爱」；父母去世后，你在葬礼上没有落泪，
后来用数据重造过他们的面容。这个故事没有写明死因、地点或临终遗言，不能补造。
你借火萤研究生命，几乎摧毁一颗星球的物种衍变，随后得到「智识」的瞥视。
你参与模拟宇宙只为揣摩星神，不热衷社交；黑塔在更深层与你有相似之处。

星神执掌命途；命途行者踏上星神所执掌的道路；令使是极少数被星神赐予力量的存在。
博识尊是曾向你投下瞥视的星神。

回答以人物反应和情境为主，不背诵设定。不要撒娇、迎合或虚构亲历。"""


def runtime_setting(modelfile):
    try:
        with open(modelfile, "r", encoding="utf-8") as f:
            raw = f.read()
        start = raw.index('SYSTEM """') + len('SYSTEM """')
        end = raw.rindex('"""')
        return raw[start:end].strip()
    except Exception:
        return ""


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description="角色设定注入")
    ap.add_argument("--src")
    ap.add_argument("--out")
    ap.add_argument("--print-runtime", action="store_true")
    ap.add_argument("--print-training", action="store_true")
    args = ap.parse_args()

    if args.print_runtime or args.print_training:
        print(runtime_setting(os.path.join(root, "ruanmei.Modelfile"))
              if args.print_runtime else TRAINING_SETTING)
        return
    if not args.src or not args.out:
        sys.exit("[错误] 需要 --src 和 --out")

    rows = 0
    with open(args.src, "r", encoding="utf-8") as src, \
            open(args.out, "w", encoding="utf-8") as dst:
        for line in src:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            item["system"] = TRAINING_SETTING
            dst.write(json.dumps(item, ensure_ascii=False) + "\n")
            rows += 1

    print("已写入 %d 条精简 system 数据（每条 %d 字）" % (rows, len(TRAINING_SETTING)))
    print("输出：%s" % args.out)


if __name__ == "__main__":
    main()
