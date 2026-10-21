# -*- coding: utf-8 -*-
r"""
从剧情视频的硬字幕提取训练数据（全程离线，不需要下载任何模型）。

适用素材
--------
番剧 / 剧情录屏，画面底部有硬字幕；当某个角色说话时，
字幕正上方会显示该角色的名字。这样就能自动区分「谁在说话」。

实测布局（1920x872 和 1920x1080 都适用，用比例判断）：
    y < 0.80h 且字数<=5   ->  说话人标注（如「三月七」）
    y >= 0.80h           ->  字幕正文
    y > 0.95h 或含 UID    ->  水印，丢弃

B 站缓存的 .m4s 文件开头有 9 个字节的 0x30（字符 '0'）前缀，
去掉即可正常解码——这不是加密。

用法
----
    python ocr_subtitles.py --src "D:\b站下载" --out G:\ai\data\story.jsonl --speaker 阮梅

    # 先看一眼识别效果，不写文件
    python ocr_subtitles.py --src <目录> --out <out> --speaker 阮梅 --dry-run

产出
----
    <out>              训练用 jsonl
    <out>.review.txt   校对清单（含时间戳和前后文）
    <out>.all.txt      全部字幕（不过滤说话人），用来核对是否漏掉了阮梅的台词
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
import av

MEDIA_EXT = {".m4s", ".mp4", ".mkv", ".flv", ".mov"}

# 说话人名字的常见写法，用于匹配标注
SPEAKER_ALIASES = ["阮梅", "阮·梅", "阮 梅", "阮．梅", "梅"]


def strip_prefix(path, workdir):
    """B 站 m4s 开头的 9 字节 '0' 前缀去掉，写成临时 mp4 供解码。"""
    with open(path, "rb") as f:
        head = f.read(16)
    n = 0
    while n < len(head) and head[n] == 0x30:
        n += 1
    if n == 0:
        return path, False
    data = open(path, "rb").read()
    tmp = os.path.join(workdir, "_src.mp4")
    with open(tmp, "wb") as f:
        f.write(data[n:])
    return tmp, True


def clean(s):
    """去掉 OCR 在汉字间插入的空格，统一括号。"""
    s = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", s)
    s = s.replace("[", "「").replace("]", "」")
    for bad, good in CORRECTIONS.items():
        s = s.replace(bad, good)
    return s.strip()


# Windows OCR 会把某些汉字拆成偏旁（实测发现），这里做批量纠正。
# 这些是「结构性错误」，不是随机噪声，所以可以放心替换。
# 你可以把自己遇到的误读追加到这里。
CORRECTIONS = {
    "礻也": "祂", "礻兑": "说", "礻申": "神", "礻是": "提",
    "亻十": "什", "亻尔": "你", "亻立": "位", "亻门": "们", "亻本": "体",
    "亻然": "然", "亻言": "信", "亻方": "仿", "亻为": "伪",
    "目刂": "前", "刖": "前", "月刂": "前",
    "厶": "么", "彳艮": "很", "讠人": "认", "讠吾": "语", "讠寸": "讨",
    "扌是": "提", "扌旨": "指", "扌圭": "挂", "扌出": "拙",
    "忄青": "情", "忄夬": "快", "氵去": "法", "氵青": "清",
    "纟工": "红", "纟巠": "经", "钅艮": "银",
}


def norm(s):
    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", s or "")


def text_ratio(a, b):
    import difflib
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def contains_in(a, b):
    na, nb = norm(a), norm(b)
    if len(na) < 3 or len(nb) < 3:
        return False
    return na in nb or nb in na


def is_watermark(line, height):
    if line["y"] > height * 0.95:
        return True
    t = line["text"]
    if "UID" in t.upper() or "uid" in t:
        return True
    n = norm(t)
    # UID 水印常被 OCR 读成「U 旧 ：」这类，特征是带一长串数字
    if re.search(r"\d{6,}", n):
        return True
    return len(n) >= 5 and n.isdigit()


def is_speaker_label(line, height):
    return line["y"] < height * 0.80 and len(norm(line["text"])) <= 5


def match_speaker(label_text, target_aliases):
    n = norm(label_text)
    if not n:
        return None
    for a in target_aliases:
        if norm(a) and norm(a) in n:
            return True
    return False


async def ocr_image(engine, path, mods):
    StorageFile, FileAccessMode, BitmapDecoder = mods
    f = await StorageFile.get_file_from_path_async(path)
    st = await f.open_async(FileAccessMode.READ)
    try:
        dec = await BitmapDecoder.create_async(st)
        bmp = await dec.get_software_bitmap_async()
        res = await engine.recognize_async(bmp)
    finally:
        st.close()
    out = []
    for line in res.lines:
        ws = list(line.words)
        if not ws:
            continue
        out.append({
            "text": clean(line.text),
            "x": min(w.bounding_rect.x for w in ws),
            "y": min(w.bounding_rect.y for w in ws),
            "h": max(w.bounding_rect.height for w in ws),
        })
    return out


CROP_TOP = 0.68      # 只 OCR 画面下部这个比例之后的区域


async def scan_video(path, args, mods, workdir, cache):
    engine = mods[0]
    ck = "%s|%d" % (os.path.basename(path), os.path.getsize(path))
    if ck in cache:
        print("    复用缓存（%d 条字幕）" % len(cache[ck]))
        return cache[ck]
    src, need_cleanup = strip_prefix(path, workdir)
    tmpimg = os.path.join(workdir, "_sub.png")
    samples = []
    try:
        with av.open(src) as c:
            vs = c.streams.video[0]
            W = vs.codec_context.width or 1920
            H = vs.codec_context.height or 1080
            base = int(H * CROP_TOP)
            next_t = 0.0
            last_key = None
            n_ocr = 0
            for frame in c.decode(vs):
                if frame.pts is None:
                    continue
                t = float(frame.pts * vs.time_base)
                if t < next_t:
                    continue
                next_t = t + args.interval
                img = frame.to_image()
                crop = img.crop((0, base, W, H))
                key = (round(t, 1),)
                crop.save(tmpimg)
                lines = await ocr_image(engine, tmpimg, mods[1:])
                n_ocr += 1
                for l in lines:
                    l["y"] += base          # 换算回整幅画面的坐标
                lines = [l for l in lines if not is_watermark(l, H)]
                labels = [l for l in lines if is_speaker_label(l, H)]
                body = [l for l in lines if not is_speaker_label(l, H)]
                # 同一行的多个 OCR 框按 x 拼起来
                body.sort(key=lambda l: (round(l["y"] / 12), l["x"]))
                text = ""
                for l in body:
                    text += l["text"]
                if not text.strip():
                    continue
                label = ""
                for l in labels:
                    label += l["text"]
                k = (norm(label), norm(text))
                if k == last_key:
                    continue
                last_key = k
            samples.append({"t": round(t, 2), "label": label.strip(),
                            "text": text.strip(), "src": os.path.basename(path)})
    finally:
        if need_cleanup and os.path.exists(src):
            os.remove(src)
    print("    OCR %d 帧，得到 %d 条字幕" % (n_ocr, len(samples)))
    cache[ck] = samples
    return samples


def build_lines(samples, max_gap=1.6):
    """把连续相同的字幕合并成一条，打字机/抖动都能收敛。"""
    out = []
    for s in samples:
        if out:
            prev = out[-1]
            gap_ok = s["t"] - prev["end"] <= max_gap
            same = (norm(prev["label"]) == norm(s["label"]) and
                    (text_ratio(prev["text"], s["text"]) >= 0.62
                     or contains_in(prev["text"], s["text"])))
            if gap_ok and same:
                prev["end"] = s["t"]
                prev["samples"].append(s)
                if len(norm(s["text"])) > len(norm(prev["text"])):
                    prev["text"] = s["text"]
                if len(norm(s["label"])) > len(norm(prev["label"])):
                    prev["label"] = s["label"]
                continue
        out.append({"start": s["t"], "end": s["t"], "label": s["label"],
                    "text": s["text"], "samples": [s]})
    for seg in out:
        longest = max(seg["samples"], key=lambda x: len(norm(x["text"])))
        seg["text"] = longest["text"]
    return out


def attach_context(lines, aliases):
    """
    给每条台词找前一句别人的话作为情境。
    注意：不能用「标注文字是否相等」来判断是不是同一个人 —— 同一个角色
    可能被 OCR 成「阮梅」「阮·梅」「梅」等不同写法。正确做法是判断
    「上一句是不是本角色说的」。
    """
    for i, seg in enumerate(lines):
        seg["context"] = None
        seg["ctx_speaker"] = None
        if i == 0:
            continue
        prev = lines[i - 1]
        if seg["start"] - prev["end"] > 20:      # 隔太久，已经换场景
            continue
        if not norm(prev["label"]):
            continue                              # 不知道该谁说的，不用
        if match_speaker(prev["label"], aliases) is True:
            continue                              # 上一句也是本角色（独白），不算情境
        if text_ratio(prev["text"], seg["text"]) >= 0.85:
            continue                              # 上一句其实就是同一句（OCR 抖动残留）
        seg["context"] = prev["text"]
        seg["ctx_speaker"] = prev["label"]
    return lines


def dedupe_lines(lines, window=4.0, lookback=3):
    """
    局部去重：OCR 抖动会让同一句字幕被切成好几段，这里把时间相邻、
    文本高度相似（或互相包含）的段合并，每段取最长的那次观测。
    """
    out = []
    for seg in lines:
        merged = False
        for cand in reversed(out[-lookback:]):
            if seg["start"] - cand["end"] > window:
                break
            same_speaker = norm(seg["label"]) == norm(cand["label"])
            if same_speaker and (contains_in(cand["text"], seg["text"])
                                 or text_ratio(cand["text"], seg["text"]) >= 0.62):
                cand["end"] = max(cand["end"], seg["end"])
                cand["start"] = min(cand["start"], seg["start"])
                cand["samples"].extend(seg["samples"])
                if len(norm(seg["text"])) > len(norm(cand["text"])):
                    cand["text"] = seg["text"]
                merged = True
                break
        if not merged:
            out.append({"start": seg["start"], "end": seg["end"],
                        "label": seg["label"], "text": seg["text"],
                        "samples": list(seg["samples"])})
    for seg in out:
        longest = max(seg["samples"], key=lambda x: len(norm(x["text"])))
        seg["text"] = longest["text"]
    return out


# B 站纯音频流的固定 ID，这些要跳过（30080 是视频流，不能跳）
AUDIO_STREAM_IDS = {"30216", "30232", "30280", "30250", "30251"}


def list_videos(src, excludes=()):
    if os.path.isfile(src):
        return [src]
    out = []
    for root, _, files in os.walk(src):
        for fn in files:
            if os.path.splitext(fn)[1].lower() not in MEDIA_EXT:
                continue
            tail = os.path.splitext(fn)[0].rsplit("-", 1)[-1]
            if tail in AUDIO_STREAM_IDS:
                continue
            full = os.path.join(root, fn)
            if any(x and x in full for x in excludes):
                continue
            out.append(full)
    return sorted(out)


def main():
    p = argparse.ArgumentParser(description="从剧情硬字幕提取训练数据")
    p.add_argument("--src", required=True, help="视频文件或目录")
    p.add_argument("--out", required=True, help="输出 jsonl")
    p.add_argument("--speaker", default="阮梅", help="目标角色名，默认 阮梅")
    p.add_argument("--extra-aliases", default="",
                   help="额外的写法，逗号分隔，如「阮·梅」的其它误读")
    p.add_argument("--interval", type=float, default=0.6, help="抽帧间隔（秒）")
    p.add_argument("--min-chars", type=int, default=4, help="短于这个字数的台词丢弃")
    p.add_argument("--system", default=None, help="写进每条的 system（角色设定）")
    p.add_argument("--workdir", default=None, help="临时目录")
    p.add_argument("--dry-run", action="store_true", help="只打印，不写文件")
    p.add_argument("--exclude", default="",
                   help="路径包含这个字符串就跳过，多个用逗号分隔")
    args = p.parse_args()

    try:
        from winsdk.windows.media.ocr import OcrEngine
        from winsdk.windows.globalization import Language
        from winsdk.windows.storage import StorageFile, FileAccessMode
        from winsdk.windows.graphics.imaging import BitmapDecoder
    except ImportError:
        sys.exit("[错误] 缺少 winsdk：\n  D:\\ai\\envs\\llm\\python.exe -m pip install winsdk "
                 "-i https://pypi.tuna.tsinghua.edu.cn/simple")

    engine = OcrEngine.try_create_from_language(Language("zh-Hans-CN"))
    if not engine:
        sys.exit("[错误] 无法创建中文 OCR 引擎")

    aliases = [args.speaker] + [a for a in args.extra_aliases.split(",") if a.strip()]
    excludes = [x.strip() for x in args.exclude.split(",") if x.strip()]
    videos = list_videos(args.src, excludes)
    if not videos:
        sys.exit("[错误] 没找到视频文件")
    print("[输入] %d 个视频，目标角色：%s" % (len(videos), args.speaker))

    outdir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(outdir, exist_ok=True)
    workdir = args.workdir or os.path.join(outdir, "_work_sub")
    os.makedirs(workdir, exist_ok=True)

    mods = (engine, StorageFile, FileAccessMode, BitmapDecoder)
    cache_path = args.out + ".ocr_cache.json"
    cache = {}
    if os.path.exists(cache_path):
        try:
            cache = json.load(open(cache_path, encoding="utf-8"))
            print("[缓存] 已载入 %d 个视频的 OCR 结果" % len(cache))
        except Exception:
            cache = {}
    all_samples = []
    for i, v in enumerate(videos, 1):
        print("\n[%d/%d] %s" % (i, len(videos), os.path.basename(v)))
        t0 = time.time()
        try:
            samples = asyncio.run(scan_video(v, args, mods, workdir, cache))
        except Exception as e:
            print("    跳过（读取失败）：%s" % str(e)[:140])
            continue
        print("    用时 %.0f 秒" % (time.time() - t0))
        # 缓存里的旧数据没有来源字段，这里统一补上
        for s in samples:
            s.setdefault("src", os.path.basename(v))
        all_samples.extend(samples)
        try:
            json.dump(cache, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False)
        except Exception:
            pass

    if not all_samples:
        sys.exit("[错误] 没有提取到任何字幕")

    lines = build_lines(all_samples)
    before = len(lines)
    lines = dedupe_lines(lines)
    if len(lines) != before:
        print("[去重] %d 条 -> %d 条" % (before, len(lines)))
    lines = attach_context(lines, aliases)
    print("\n[结果] 共 %d 条字幕" % len(lines))

    mine = [l for l in lines
            if match_speaker(l["label"], aliases) and len(norm(l["text"])) >= args.min_chars]
    print("[筛选] 其中 %s 的台词 %d 条" % (args.speaker, len(mine)))

    all_path = args.out + ".all.txt"
    if not args.dry_run:
        with open(all_path, "w", encoding="utf-8") as f:
            f.write("# 全部字幕（未过滤说话人）。用来核对有没有漏掉 %s 的台词。\n" % args.speaker)
            f.write("# 格式：[时间] 说话人 | 台词\n\n")
            for l in lines:
                f.write("[%s] %s | %s\n"
                        % (fmt(l["start"]), l["label"] or "—", l["text"]))
        print("[完成] 全部字幕 -> %s" % os.path.abspath(all_path))

    if args.dry_run:
        print("\n（dry-run，预览前 25 条）")
        for l in mine[:25]:
            print("  [%s] 情境: %s" % (fmt(l["start"]),
                                      (l["context"] or "（无）")[:40]))
            print("        %s: %s" % (args.speaker, l["text"]))
        return

    with open(args.out, "w", encoding="utf-8") as f:
        for l in mine:
            ins = l["context"] or "（剧情推进）"
            # 带上来源和时间戳，方便回原片核对（校对时非常有用）
            src = ""
            for s in l.get("samples", []):
                if s.get("src"):
                    src = s["src"]
                    break
            item = {"instruction": ins, "output": l["text"],
                    "source": src, "time": fmt(l["start"])}
            if args.system:
                item["system"] = args.system
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    review = args.out + ".review.txt"
    with open(review, "w", encoding="utf-8") as f:
        f.write("%s 的台词校对清单。OCR 可能有错字，请逐条核对。\n" % args.speaker)
        f.write("带「情境」的条目更适合训练（能学到判断方式）；\n")
        f.write("「剧情推进」那批只有台词没有情境，只能学语气，可以按需删除。\n\n")
        for i, l in enumerate(mine, 1):
            f.write("--- %d  [%s - %s] ---\n" % (i, fmt(l["start"]), fmt(l["end"])))
            src = next((s.get("src") for s in l.get("samples", []) if s.get("src")), "")
            f.write("  来源: %s\n" % (src or "未知"))
            f.write("  台词: %s\n" % l["text"])
            if l["context"]:
                f.write("  情境: %s（%s）\n" % (l["context"], l["ctx_speaker"] or "未标注"))
            else:
                f.write("  情境: （无，仅台词）\n")
            f.write("\n")

    print("[完成] 训练数据 -> %s（%d 条）" % (os.path.abspath(args.out), len(mine)))
    print("[完成] 校对清单 -> %s" % os.path.abspath(review))
    with_ctx = len([l for l in mine if l["context"]])
    print("")
    print("其中带情境的 %d 条，纯台词 %d 条。" % (with_ctx, len(mine) - with_ctx))
    print("下一步体检：")
    print('  D:\\ai\\envs\\llm\\python.exe scripts\\prepare_data.py check --src "%s"'
          % args.out)


def fmt(t):
    return "%d:%04.1f" % (int(t // 60), t % 60)


if __name__ == "__main__":
    main()
