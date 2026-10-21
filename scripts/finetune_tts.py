# -*- coding: utf-8 -*-
r"""
用命令行驱动 GPT-SoVITS 精调（不用开 WebUI）。

GPT-SoVITS 的训练脚本从**环境变量**读路径，WebUI 也只是帮忙设了这些变量。
这个脚本做同样的事，但可以无人值守地跑完三步：

    1A  格式化      1-get-text → 2-get-hubert-wav32k → 3-get-semantic
    1B  训 SoVITS   s2_train.py
    1C  训 GPT      s1_train.py

用法
----
    D:\ai\envs\tts\python.exe scripts\finetune_tts.py --step 1a
    D:\ai\envs\tts\python.exe scripts\finetune_tts.py --step 1b
    D:\ai\envs\tts\python.exe scripts\finetune_tts.py --step 1c

    # 也可以一次跑完
    D:\ai\envs\tts\python.exe scripts\finetune_tts.py --step all
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = r"G:\ai\GPT-SoVITS\GPT-SoVITS-main"
PY = r"D:\ai\envs\tts\python.exe"
EXP_NAME = "ruanmei"
EXP_ROOT = r"G:\ai\GPT-SoVITS\logs"
OPT_DIR = os.path.join(EXP_ROOT, EXP_NAME)
WAV_DIR = "G:/ai/voice/dataset"
LIST_FILE = "G:/ai/voice/list.txt"
BERT_DIR = os.path.join(ROOT, "GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large")
FFMPEG_BIN = r"G:\ai\ffmpeg\ffmpeg-9.0.2-essentials_build\bin"
S2G = os.path.join(ROOT, "GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s2G2333k.pth")


def run(script, env=None, extra=None):
    cmd = [PY, "-s", script] + (extra or [])
    e = dict(os.environ)
    e["PYTHONIOENCODING"] = "utf-8"
    # GPT-SoVITS 的脚本会 import text.cleaner / tools.xxx，
    # 这些模块在 GPT_SoVITS/ 目录下，必须把该目录加进 PYTHONPATH。
    gs = os.path.join(ROOT, "GPT_SoVITS")
    e["PYTHONPATH"] = gs + os.pathsep + e.get("PYTHONPATH", "")
    # 2-get-hubert 会用 ffmpeg 命令行把音频重采样到 32k，系统 PATH 里没有就得手动加
    if os.path.isdir(FFMPEG_BIN):
        e["PATH"] = FFMPEG_BIN + os.pathsep + e.get("PATH", "")
    if env:
        e.update({k: str(v) for k, v in env.items()})
    print("  $ %s" % " ".join(cmd))
    p = subprocess.run(cmd, cwd=ROOT, env=e)
    if p.returncode != 0:
        sys.exit("[错误] %s 退出码 %d" % (script, p.returncode))


def step_1a(gpu=0):
    os.makedirs(OPT_DIR, exist_ok=True)
    base = {
        "inp_text": LIST_FILE,
        "inp_wav_dir": WAV_DIR,
        "exp_name": EXP_NAME,
        "opt_dir": OPT_DIR,
        "bert_pretrained_dir": BERT_DIR,
        # 注意变量名是 cnhubert_base_dir（不是 _path），2-get-hubert 脚本读这个
        "cnhubert_base_dir": os.path.join(
            ROOT, "GPT_SoVITS/pretrained_models/chinese-hubert-base"),
        # 3-get-semantic 需要 s2G 模型来算语义 token
        "pretrained_s2G": S2G,
        # 3-get-semantic 还要 s2 的配置文件路径 + 版本号
        "s2config_path": os.path.join(ROOT, "GPT_SoVITS/configs/s2.json"),
        "version": "v2",
        "i_part": "0",
        "all_parts": "1",
        "_CUDA_VISIBLE_DEVICES": str(gpu),
        "is_half": "True",
    }
    print("[1A] 文本与音素")
    run("GPT_SoVITS/prepare_datasets/1-get-text.py", base)
    print("[1A] HuBERT 特征")
    run("GPT_SoVITS/prepare_datasets/2-get-hubert-wav32k.py", base)
    print("[1A] 语义 token")
    run("GPT_SoVITS/prepare_datasets/3-get-semantic.py", base)
    # i_part=0/all_parts=1 时脚本只产出带 -0 的文件；训练配置读的是合并名。
    for src_name, dst_name in (("2-name2text-0.txt", "2-name2text.txt"),
                               ("6-name2semantic-0.tsv", "6-name2semantic.tsv")):
        src = os.path.join(OPT_DIR, src_name)
        dst = os.path.join(OPT_DIR, dst_name)
        if os.path.isfile(src):
            shutil.copyfile(src, dst)
    print("[1A] 完成，产出：")
    for f in sorted(os.listdir(OPT_DIR)):
        print("    %s" % f)


def backup_preprocess():
    """换数据集时强制重建 1A：GPT-SoVITS 见 2-name2text-0.txt 存在就会跳过。"""
    stamp = time.strftime("%Y%m%d_%H%M%S")
    bak = os.path.join(OPT_DIR, "pre_" + stamp)
    os.makedirs(bak, exist_ok=True)
    for name in ("2-name2text-0.txt", "2-name2text.txt", "3-bert",
                 "6-name2semantic-0.tsv", "6-name2semantic.tsv"):
        src = os.path.join(OPT_DIR, name)
        if os.path.exists(src):
            shutil.move(src, os.path.join(bak, name))
    print("[1A] 旧预处理已备份到 %s" % bak)


def write_s2_config(epochs, batch):
    src = os.path.join(ROOT, "GPT_SoVITS/configs/s2.json")
    cfg = json.load(open(src, encoding="utf-8"))
    # 完全照 WebUI 的写法（webui.py 里 open1Ba 那一段），少一个字段就报 AttributeError
    pre = os.path.join(ROOT, "GPT_SoVITS/pretrained_models/gsv-v2final-pretrained")
    opt = OPT_DIR.replace("\\", "/")
    cfg["train"]["batch_size"] = batch
    cfg["train"]["epochs"] = epochs
    cfg["train"]["text_low_lr_rate"] = 0.4
    cfg["train"]["pretrained_s2G"] = os.path.join(pre, "s2G2333k.pth").replace("\\", "/")
    cfg["train"]["pretrained_s2D"] = os.path.join(pre, "s2D2333k.pth").replace("\\", "/")
    cfg["train"]["if_save_latest"] = True
    cfg["train"]["if_save_every_weights"] = True
    cfg["train"]["save_every_epoch"] = 5
    cfg["train"]["gpu_numbers"] = "0"
    # 8GB 显存上必须开梯度检查点，否则训练第一个 batch 就 OOM
    # （实测：不开时只剩 4.27GB 可用，还差 20MB；开了之后能跑）
    cfg["train"]["grad_ckpt"] = True
    cfg["train"]["lora_rank"] = 32
    cfg["model"]["version"] = "v2"
    cfg["data"]["exp_dir"] = opt
    cfg["s2_ckpt_dir"] = opt
    cfg["save_weight_dir"] = "SoVITS_weights_v2"
    cfg["name"] = EXP_NAME
    cfg["version"] = "v2"
    out = os.path.join(ROOT, "GPT_SoVITS/configs/_tmp_s2.json")
    json.dump(cfg, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return out


def step_1b(epochs=20, batch=4):
    cfg = write_s2_config(epochs, batch)
    print("[1B] 训练 SoVITS（%d 轮，batch %d）" % (epochs, batch))
    run("GPT_SoVITS/s2_train.py", {"_CUDA_VISIBLE_DEVICES": "0"},
        ["--config", os.path.relpath(cfg, ROOT).replace("\\", "/")])


def write_s1_config(epochs, batch):
    import re
    import yaml
    src = os.path.join(ROOT, "GPT_SoVITS/configs/s1longer-v2.yaml")
    cfg = yaml.safe_load(open(src, encoding="utf-8"))
    pre = os.path.join(ROOT, "GPT_SoVITS/pretrained_models/gsv-v2final-pretrained",
                       "s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt").replace("\\", "/")
    opt = OPT_DIR.replace("\\", "/")
    # 完全照 WebUI 的写法（webui.py 里 open1C 那一段），少一个字段就 KeyError
    cfg["train"]["batch_size"] = batch
    cfg["train"]["epochs"] = epochs
    # 注意：之前"每 5 轮保存就崩溃"的真凶不是保存本身，而是本机 hosts 文件
    # 里缺 `127.0.0.1 localhost`（被深信服替换掉了），导致 PyTorch 分布式
    # 初始化连不上 localhost。修好 hosts 后恢复正常设置即可。
    cfg["train"]["save_every_n_epoch"] = 5
    cfg["train"]["if_save_every_weights"] = True
    cfg["train"]["if_save_latest"] = True
    cfg["train"]["if_dpo"] = False
    cfg["train"]["half_weights_save_dir"] = "GPT_weights_v2"
    cfg["train"]["exp_name"] = EXP_NAME
    cfg["pretrained_s1"] = pre
    cfg["train_semantic_path"] = os.path.join(opt, "6-name2semantic.tsv").replace("\\", "/")
    cfg["train_phoneme_path"] = os.path.join(opt, "2-name2text.txt").replace("\\", "/")
    cfg["output_dir"] = os.path.join(opt, "logs_s1_v2").replace("\\", "/")
    os.makedirs(os.path.join(OPT_DIR, "logs_s1_v2"), exist_ok=True)
    out = os.path.join(ROOT, "GPT_SoVITS/configs/_tmp_s1.yaml")
    with open(out, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)
    return out


def step_1c(epochs=15, batch=4):
    cfg = write_s1_config(epochs, batch)
    print("[1C] 训练 GPT（%d 轮，batch %d）" % (epochs, batch))
    run("GPT_SoVITS/s1_train.py", {"_CUDA_VISIBLE_DEVICES": "0", "hz": "25hz"},
        ["--config_file", os.path.relpath(cfg, ROOT).replace("\\", "/")])


def main():
    ap = argparse.ArgumentParser(description="GPT-SoVITS 精调（命令行）")
    ap.add_argument("--step", required=True, choices=["1a", "1b", "1c", "all"])
    ap.add_argument("--s2-epochs", type=int, default=20)
    ap.add_argument("--s2-batch", type=int, default=2)
    ap.add_argument("--s1-epochs", type=int, default=15)
    ap.add_argument("--s1-batch", type=int, default=4)
    ap.add_argument("--force", action="store_true",
                    help="1A 前备份旧文本/特征，强制按当前 list.txt 重建")
    args = ap.parse_args()

    if not os.path.exists(LIST_FILE):
        sys.exit("[错误] 找不到 %s，先跑 build_tts_dataset.py" % LIST_FILE)
    if not os.path.isdir(ROOT):
        sys.exit("[错误] 找不到 GPT-SoVITS：%s" % ROOT)

    print("=" * 56)
    print("  实验名: %s" % EXP_NAME)
    print("  数据  : %s" % LIST_FILE)
    print("  输出  : %s" % OPT_DIR)
    print("=" * 56)

    if args.step in ("1a", "all"):
        if args.force:
            backup_preprocess()
        step_1a()
    if args.step in ("1b", "all"):
        step_1b(args.s2_epochs, args.s2_batch)
    if args.step in ("1c", "all"):
        step_1c(args.s1_epochs, args.s1_batch)
    print("")
    print("[完成] step=%s" % args.step)


if __name__ == "__main__":
    main()
