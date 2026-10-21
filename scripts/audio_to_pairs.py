# -*- coding: utf-8 -*-
r"""
把角色语音素材变成训练数据（本地语音识别，不需要 API）。

核心认知：语音不能直接喂给训练
------------------------------
训练数据必须是**文字**。而且「性格」训练还额外需要**情境**——也就是这个角色当时在
回应什么。所以流程是：

    音频  →  语音识别  →  带时间轴的文本  →  切出「情境 → 台词」  →  训练数据

同一份音频可以同时服务两个目标：

    音色  →  5~10 秒参考音频就够（免训练克隆，详见 VOICE.md）
    性格  →  必须转成文字，而且要带上情境（本文档的流程）

两种素材，难度差很多
--------------------
  语音包 / 角色歌（单人、干净）  →  直接识别就行，最简单
  动画 / 游戏片段（多人 + BGM）  →  先用 UVR5 分离人声，再识别，还要判断谁在说话

用法
----
    # 1) 转成带时间轴的文本，人工过一遍（最常用）
    python audio_to_pairs.py --src 语音素材目录 --out G:\ai\data\char.txt

    # 2) 如果是对话，顺带生成候选配对（需要人工筛选）
    python audio_to_pairs.py --src 目录 --out G:\ai\data\char.txt --pairs G:\ai\data\char_pairs.jsonl

    # 3) 换模型提高准确率（默认 medium，可换 large-v3）
    python audio_to_pairs.py --src a.wav --out t.txt --model large-v3

模型会从 HuggingFace 下载，走 hf-mirror 镜像（HF_ENDPOINT 已设好）。
"""

import argparse
import json
import os
import sys
import time

MEDIA_EXT = {".wav", ".mp3", ".m4a", ".flac", ".aac", ".ogg", ".wma", ".mp4", ".mkv", ".webm"}
# faster-whisper 的模型名（不是 openai/whisper 那套）
MODELS = ["tiny", "base", "small", "medium", "large-v2", "large-v3", "large-v3-turbo"]


def collect_files(src):
    if os.path.isfile(src):
        return [src]
    if not os.path.isdir(src):
        sys.exit(f"[错误] 找不到输入：{src}")
    out = []
    for root, _, files in os.walk(src):
        for fn in files:
            if os.path.splitext(fn)[1].lower() in MEDIA_EXT:
                out.append(os.path.join(root, fn))
    return sorted(out)


def fmt_ts(seconds):
    m = int(seconds // 60)
    s = seconds - m * 60
    return f"{m:02d}:{s:05.2f}"


def main():
    p = argparse.ArgumentParser(description="角色语音 -> 训练数据")
    p.add_argument("--src", required=True, help="音频文件或目录")
    p.add_argument("--out", required=True, help="输出的带时间轴文本")
    p.add_argument("--pairs", default=None, help="可选：顺带输出候选配对 jsonl")
    p.add_argument("--model", default="medium", choices=MODELS)
    p.add_argument("--lang", default="zh", help="语言，zh / ja / en；不确定用 auto")
    p.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    p.add_argument("--min-chars", type=int, default=8, help="短于这个字数的段丢弃")
    args = p.parse_args()

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit(
            "[错误] 缺少 faster-whisper，先装：\n"
            "  D:\\ai\\envs\\llm\\python.exe -m pip install faster-whisper "
            "-i https://pypi.tuna.tsinghua.edu.cn/simple")

    files = collect_files(args.src)
    if not files:
        sys.exit(f"[错误] 在 {args.src} 里没找到音频/视频文件")
    print(f"[输入] {len(files)} 个文件")

    print(f"[加载] 语音识别模型 {args.model}（首次会下载，走 hf-mirror 镜像）……")
    t0 = time.time()
    model = WhisperModel(args.model, device=args.device, compute_type="float16"
                         if args.device == "cuda" else "int8")
    print(f"[加载] 完成，耗时 {time.time() - t0:.0f} 秒")

    all_segments = []
    for idx, path in enumerate(files, 1):
        name = os.path.basename(path)
        print(f"  识别 {idx}/{len(files)}：{name} ……", end="", flush=True)
        t0 = time.time()
        segments, info = model.transcribe(
            path,
            language=None if args.lang == "auto" else args.lang,
            vad_filter=True,               # 跳过静音，减少幻听
            beam_size=5,
        )
        got = 0
        for seg in segments:
            text = seg.text.strip()
            if len(text) < args.min_chars:
                continue
            all_segments.append({
                "file": name, "start": seg.start, "end": seg.end, "text": text,
            })
            got += 1
        print(f" {got} 段，用时 {time.time() - t0:.0f} 秒")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("# 角色语音识别结果\n")
        f.write("# 格式：[时间] 台词内容 —— 请人工过一遍，改掉识别错误\n")
        f.write("# 接下来要做的是：把这些台词和它们对应的「情境」配对\n\n")
        cur_file = None
        for s in all_segments:
            if s["file"] != cur_file:
                cur_file = s["file"]
                f.write(f"\n===== {cur_file} =====\n")
            f.write(f"[{fmt_ts(s['start'])}-{fmt_ts(s['end'])}] {s['text']}\n")
    print(f"\n[完成] {len(all_segments)} 段 -> {os.path.abspath(args.out)}")

    if args.pairs:
        pairs = []
        for i in range(1, len(all_segments)):
            prev, cur = all_segments[i - 1], all_segments[i]
            if prev["file"] != cur["file"]:
                continue
            if len(prev["text"]) < 5:
                continue
            pairs.append({"instruction": prev["text"], "output": cur["text"]})
        with open(args.pairs, "w", encoding="utf-8") as f:
            for pair in pairs:
                f.write(json.dumps(pair, ensure_ascii=False) + "\n")
        print(f"[完成] {len(pairs)} 条候选配对 -> {os.path.abspath(args.pairs)}")
        print("")
        print("⚠ 这些配对是「上一句 → 下一句」，还没区分说话人。你需要人工筛选：")
        print("   - 只保留 output 是目标角色说的话（其他角色的行删掉）")
        print("   - 只保留 instruction 确实是「情境」的（同一人连着说两句的删掉）")
        print("   - 识别错误要当场改正，错别字会被模型学进去")

    print("")
    print("下一步：把筛选好的 jsonl 做体检")
    print("  D:\\ai\\envs\\llm\\python.exe scripts\\prepare_data.py check --src <你的 jsonl>")


if __name__ == "__main__":
    main()
