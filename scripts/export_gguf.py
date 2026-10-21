# -*- coding: utf-8 -*-
r"""
把 LoRA adapter 合并回基座模型，导出 GGUF，并自动生成 Ollama 的 Modelfile。

用法
----
    python export_gguf.py --adapter G:\ai\out\run1\adapter --out G:\ai\out\run1\gguf

跑完会在 --out 目录里得到 .gguf 和 Modelfile，然后：
    ollama create my-ai -f G:\ai\out\run1\gguf\Modelfile
    ollama run my-ai
"""

import argparse
import glob
import os
import sys


def build_modelfile(gguf_name, system_prompt):
    lines = [
        "FROM ./" + gguf_name,
        "",
        "PARAMETER temperature 0.7",
        "PARAMETER top_p 0.9",
        "PARAMETER repeat_penalty 1.1",
        "PARAMETER num_ctx 8192",
        "",
        'SYSTEM """',
        system_prompt,
        '"""',
        "",
    ]
    return "\n".join(lines)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--adapter", required=True, help="train_qlora.py 输出的 adapter 目录")
    p.add_argument("--base", default="unsloth/Qwen3-4B-unsloth-bnb-4bit")
    p.add_argument("--out", required=True, help="导出目录")
    p.add_argument("--quant", default="q4_k_m", help="量化方式：q4_k_m / q5_k_m / q8_0")
    p.add_argument("--system",
                   default="你是一个用中文交流的私人助理，说话直接、给具体建议，不说空话。",
                   help="写进 Modelfile 的系统提示词")
    return p.parse_args()


def main():
    args = parse_args()
    os.makedirs(args.out, exist_ok=True)

    try:
        from unsloth import FastLanguageModel
    except ImportError:
        sys.exit("[错误] 没找到 unsloth，先激活训练环境：conda activate G:\\ai\\envs\\llm")

    print(f"[1/3] 加载 adapter：{args.adapter}")
    # 直接从 adapter 目录加载，unsloth 会自动找出基座并套上 LoRA
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.adapter,
        max_seq_length=2048,
        dtype=None,
        load_in_4bit=True,
    )

    gguf_path = None
    print(f"[2/3] 合并权重并导出 GGUF（{args.quant}）…… 这一步比较慢，耐心等")
    try:
        model.save_pretrained_gguf(args.out, tokenizer, quantization_method=args.quant)
        found = sorted(glob.glob(os.path.join(args.out, "*.gguf")))
        gguf_path = found[0] if found else None
    except Exception as e:
        print(f"[警告] 自动导出 GGUF 失败：{e}")
        print("       这通常是 Windows 上 llama.cpp 的编译问题。改用两步法：")
        merged = os.path.join(args.out, "merged_16bit")
        model.save_pretrained_merged(merged, tokenizer, save_method="merged_16bit")
        print(f"       已导出 16bit 合并权重到：{merged}")
        print("       然后手动转换（需要 llama.cpp）：")
        print("         git clone https://github.com/ggml-org/llama.cpp")
        print("         pip install -r llama.cpp/requirements.txt")
        print(f'         python llama.cpp/convert_hf_to_gguf.py "{merged}" '
              f'--outfile "{os.path.join(args.out, "model-f16.gguf")}" --outtype f16')
        print('         llama.cpp\\llama-quantize '
              f'"{os.path.join(args.out, "model-f16.gguf")}" '
              f'"{os.path.join(args.out, "model-Q4_K_M.gguf")}" Q4_K_M')
        return

    if not gguf_path:
        sys.exit(f"[错误] 没在 {args.out} 里找到 .gguf 文件。")

    size_gb = os.path.getsize(gguf_path) / 1024 ** 3
    print(f"[3/3] 生成 Modelfile（{size_gb:.2f} GB）")
    modelfile = os.path.join(args.out, "Modelfile")
    with open(modelfile, "w", encoding="utf-8") as f:
        f.write(build_modelfile(os.path.basename(gguf_path), args.system))

    print("")
    print("[完成] 现在导入 Ollama：")
    print(f'  ollama create my-ai -f "{modelfile}"')
    print("  ollama run my-ai")
    print("")
    print("提示：想改系统提示词或温度，编辑那个 Modelfile，再重跑一次 ollama create 即可。")


if __name__ == "__main__":
    main()
