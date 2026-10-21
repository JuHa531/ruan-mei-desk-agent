# -*- coding: utf-8 -*-
r"""
QLoRA 微调脚本 —— 按 8GB 显存（RTX 4060 Laptop）调好默认参数。

装环境（在 G:\ai\envs\llm 这个 conda 环境里，Python 3.11/3.12，不要用系统里的 3.13）
------------------------------------------------------------------------------
    pip install torch --index-url https://download.pytorch.org/whl/cu124
    pip install "unsloth[cu124-torch250] @ git+https://github.com/unslothai/unsloth.git"
    pip install hf_transfer          # 可选，下载模型更快

开跑
----
    python train_qlora.py --data G:\ai\data\train.jsonl --out G:\ai\out\run1

显存不够（报 CUDA out of memory）时，按这个顺序往下降：
    --max-seq-length 1024  ->  --lora-r 8  ->  --model unsloth/Qwen3-1.7B-unsloth-bnb-4bit

支持三种数据格式，自动识别：
    {"text": "..."}                                     续写式（原始笔记直接用这个）
    {"instruction": "...", "output": "..."}             指令式（最常用）
    {"messages": [{"role": "user", ...}, ...]}          多轮对话
"""

import os

# 必须在 import torch 之前设置：缓解 8GB 显存下的碎片化问题
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import argparse
import json
import sys


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--data", required=True, help="训练数据 .jsonl")
    p.add_argument("--out", required=True, help="输出目录，LoRA adapter 会存这里")
    p.add_argument("--model", default="unsloth/Qwen3-4B-unsloth-bnb-4bit",
                   help="基座模型；8GB 显存建议 4B，想试 8B 就换 unsloth/Qwen3-8B-unsloth-bnb-4bit")
    p.add_argument("--max-seq-length", type=int, default=2048)
    p.add_argument("--epochs", type=float, default=3.0)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--batch", type=int, default=1)
    p.add_argument("--grad-accum", type=int, default=8)
    p.add_argument("--lora-r", type=int, default=16)
    p.add_argument("--val-split", type=float, default=0.1, help="留多少做验证集，0 表示不留")
    p.add_argument("--seed", type=int, default=3407)
    p.add_argument("--no-mask-prompt", action="store_true",
                   help="默认只在「回答」部分算 loss，加这个参数就整段都算")
    p.add_argument("--offline", action="store_true",
                   help="强制离线：只用本地缓存，不联网检查更新。"
                        "模型已经下载过、或者没有网络时建议加上，避免卡在超时等待")
    p.add_argument("--no-think", action="store_true",
                   help="在回答前预先填空思考块（<think></think>），让带思考模式的模型"
                        "（Qwen3 等）直接说话。训练数据和推理格式一致时效果最好")
    return p.parse_args()


def load_records(path):
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                sys.exit(f"[错误] 第 {i} 行不是合法 JSON：{e}")
    if not records:
        sys.exit("[错误] 数据文件是空的。")
    return records


def detect_mode(records):
    if any("text" in r for r in records):
        return "text"
    if any("messages" in r for r in records):
        return "chat"
    if all(("instruction" in r and ("output" in r or "response" in r)) for r in records):
        return "chat"
    sys.exit("[错误] 字段不认识。每行需要 text / instruction+output / messages 之一。")


NO_THINK_PREFIX = "<think>\n\n</think>\n\n"


def to_text(rec, tokenizer, no_think=False):
    messages = rec.get("messages")
    if messages is None:
        messages = [
            {"role": "user", "content": rec["instruction"]},
            {"role": "assistant", "content": rec.get("output") or rec.get("response")},
        ]
    if rec.get("system") and not any(m.get("role") == "system" for m in messages):
        messages = [{"role": "system", "content": rec["system"]}] + messages

    # 关键：如果模型默认会「思考」，就在回答前预先填空思考块。
    # 这样模型学到的模式是「思考已经结束了，直接回答」，
    # 推理时配合同样的模板，就不会再输出一大段通用推理。
    if no_think:
        messages = [dict(m) for m in messages]
        for m in messages:
            if m.get("role") == "assistant":
                m["content"] = NO_THINK_PREFIX + m["content"]

    text = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=False
    )
    # 补上 EOS，否则模型学不会「该停下来了」
    if tokenizer.eos_token and not text.endswith(tokenizer.eos_token):
        text += tokenizer.eos_token
    return text


def main():
    args = parse_args()

    # 必须在 import transformers/unsloth 之前设置
    if args.offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        print("[设置] 已启用离线模式（只用本地缓存）")

    try:
        import torch
        from unsloth import FastLanguageModel, is_bfloat16_supported
        from datasets import Dataset
        from trl import SFTTrainer
        from transformers import TrainingArguments
    except ImportError as e:
        sys.exit(
            f"[错误] 缺少依赖：{e}\n"
            "先激活训练环境并安装：\n"
            "  conda activate G:\\ai\\envs\\llm\n"
            '  pip install torch --index-url https://download.pytorch.org/whl/cu124\n'
            '  pip install "unsloth[cu124-torch250] @ git+https://github.com/unslothai/unsloth.git"'
        )

    if not torch.cuda.is_available():
        sys.exit("[错误] 没有检测到可用的 CUDA 显卡，训练无法进行。检查 NVIDIA 驱动。")

    props = torch.cuda.get_device_properties(0)
    print(f"[环境] GPU: {props.name}，显存 {props.total_memory / 1024**3:.1f} GB")

    records = load_records(args.data)
    mode = detect_mode(records)
    print(f"[数据] {len(records)} 条，格式识别为：{mode}")

    if len(records) < 50:
        print("[警告] 样本少于 50 条，微调大概率不值得，建议先把系统提示词写扎实。")

    os.makedirs(args.out, exist_ok=True)

    # ---- 加载基座模型（4bit 量化，才能塞进 8GB）----
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.model,
        max_seq_length=args.max_seq_length,
        dtype=None,
        load_in_4bit=True,
    )

    if tokenizer.chat_template is None:
        from unsloth import get_chat_template
        tokenizer = get_chat_template(tokenizer, chat_template="qwen-2.5")

    # ---- 挂 LoRA ----
    model = FastLanguageModel.get_peft_model(
        model,
        r=args.lora_r,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        lora_alpha=args.lora_r,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=args.seed,
    )

    # ---- 数据集 ----
    rows = []
    for r in records:
        rows.append({"text": r["text"] if mode == "text"
                     else to_text(r, tokenizer, args.no_think)})
    ds = Dataset.from_list(rows)

    eval_ds = None
    if args.val_split > 0 and len(ds) >= 20:
        split = ds.train_test_split(test_size=args.val_split, seed=args.seed)
        ds, eval_ds = split["train"], split["test"]
        print(f"[数据] 训练集 {len(ds)} 条，验证集 {len(eval_ds)} 条")

    # ---- 训练参数 ----
    train_kwargs = dict(
        output_dir=args.out,
        per_device_train_batch_size=args.batch,
        gradient_accumulation_steps=args.grad_accum,
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        warmup_ratio=0.03,
        lr_scheduler_type="linear",
        optim="adamw_8bit",
        weight_decay=0.01,
        logging_steps=1,
        save_strategy="epoch",
        save_total_limit=2,
        eval_strategy="epoch" if eval_ds is not None else "no",
        seed=args.seed,
        fp16=not is_bfloat16_supported(),
        bf16=is_bfloat16_supported(),
        report_to="none",
    )

    # TRL 新版把数据集相关参数移进了 SFTConfig，这里做兼容
    try:
        from trl import SFTConfig
        cfg = SFTConfig(
            **train_kwargs,
            dataset_text_field="text",
            max_length=args.max_seq_length,
            dataset_num_proc=2,
            packing=False,
        )
        trainer = SFTTrainer(
            model=model,
            processing_class=tokenizer,
            train_dataset=ds,
            eval_dataset=eval_ds,
            args=cfg,
        )
    except ImportError:
        trainer = SFTTrainer(
            model=model,
            tokenizer=tokenizer,
            train_dataset=ds,
            eval_dataset=eval_ds,
            dataset_text_field="text",
            max_seq_length=args.max_seq_length,
            dataset_num_proc=2,
            packing=False,
            args=TrainingArguments(**train_kwargs),
        )

    # ---- 只在回答部分算 loss（效果提升明显）----
    if mode == "chat" and not args.no_mask_prompt:
        try:
            from unsloth.chat_templates import train_on_responses_only
        except ImportError:
            from unsloth import train_on_responses_only
        try:
            trainer = train_on_responses_only(
                trainer,
                instruction_part="<|im_start|>user\n",
                response_part="<|im_start|>assistant\n",
            )
            print("[设置] 已启用 prompt 掩码：只训练回答部分")
        except Exception as e:
            print(f"[警告] prompt 掩码未启用，将训练整段文本（效果会差一些）：{e}")

    # ---- 开跑 ----
    print("[开始] 训练中…… 第一次跑遇到 CUDA out of memory 是正常的，按提示降参数。")
    stats = trainer.train()

    adapter_dir = os.path.join(args.out, "adapter")
    model.save_pretrained(adapter_dir)
    tokenizer.save_pretrained(adapter_dir)

    used = getattr(stats, "metrics", {}).get("train_runtime")
    if used:
        print(f"[完成] 耗时 {used / 60:.1f} 分钟")
    print(f"[完成] LoRA adapter 已保存到：{adapter_dir}")
    print("")
    print("下一步 —— 合并权重并导出成 Ollama 能用的 GGUF：")
    print(f'  python export_gguf.py --adapter "{adapter_dir}" '
          f'--base "{args.model}" --out {os.path.join(args.out, "gguf")}')


if __name__ == "__main__":
    main()
