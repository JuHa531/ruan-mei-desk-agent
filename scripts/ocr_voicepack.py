# -*- coding: utf-8 -*-
r"""
从游戏语音界面录屏里提取训练数据（全程离线，不需要任何下载）。

适用素材
--------
《崩坏：星穹铁道》这类游戏的「角色语音界面」录屏。这类界面同时提供三样东西：

    左/右栏菜单项  →  情境（如「关于黑塔」「爱好·听戏」「战斗胜利」）
    中间大字        →  台词全文
    配音            →  音频（本脚本不处理音频，只提取文字）

所以**不需要语音识别**，Windows 自带的离线 OCR 就够了。

原理
----
1. 按固定间隔抽帧（默认 0.5 秒），画面没变化的帧直接跳过（省时间）
2. 每帧做 OCR，用字号的**高度**区分角色：大字号=台词，小字号=菜单项
3. 把台词相同的连续帧合并成一段
4. 为每段确定「情境」：先用菜单项与台词的**文字重叠**判断（可靠），
   重叠不到时退回用背景**亮度**（当前高亮项通常最亮）

用法
----
    # 先把视频拆开的音频和视频文件都放好，然后：
    python ocr_voicepack.py --src "D:\b站下载\1382489951" --out G:\ai\data\ruanmei.jsonl

    # 只看识别结果，不生成训练数据
    python ocr_voicepack.py --src <目录> --out <out> --dry-run

产出
----
    <out>              训练用 jsonl（含 system / instruction / output）
    <out>.review.txt   逐条列出「情境 + 台词 + 依据」，供人工校对
    <out>.frames\      每个段落对应的原始帧图片，校对时对照看
"""

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
import time
import av

TRANSITION_PAUSE = 0.4        # 同一句台词允许的短暂抖动（秒）


def clean(s):
    """OCR 会在汉字之间插空格，去掉它；同时统一一下括号。"""
    s = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", s)
    s = s.replace("[", "「").replace("]", "」")
    return s.strip()


def norm(s):
    """用于比较的归一化：只留汉字和字母数字。"""
    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", s or "")


def overlap_score(a, b):
    """a、b 的最长公共连续子串长度（只看长度>=2 的）。"""
    a, b = norm(a), norm(b)
    if len(a) < 2 or len(b) < 2:
        return 0
    best = 0
    for i in range(len(a)):
        for j in range(len(b)):
            k = 0
            while i + k < len(a) and j + k < len(b) and a[i + k] == b[j + k]:
                k += 1
            best = max(best, k)
    return best


def text_ratio(a, b):
    """两段文字的相似度 0~1，容忍 OCR 偶尔读错一两个字。"""
    import difflib
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def contains_in(a, b):
    """a、b 归一化后是否存在包含关系（用于识别打字机效果的中间状态）。"""
    na, nb = norm(a), norm(b)
    if len(na) < 3 or len(nb) < 3:
        return False
    return na in nb or nb in na


def list_videos(src):
    exts = {".mp4", ".mkv", ".avi", ".flv", ".mov"}
    if os.path.isfile(src):
        return [src]
    out = []
    for root, _, files in os.walk(src):
        for fn in files:
            if os.path.splitext(fn)[1].lower() in exts:
                # 跳过 B 站的纯音频流文件（数字后缀 3xxxx 表示音频）
                stem = os.path.splitext(fn)[0]
                tail = stem.rsplit("-", 1)[-1]
                if tail.isdigit() and 30000 <= int(tail) <= 39999:
                    continue
                out.append(os.path.join(root, fn))
    return sorted(out)


async def ocr_image(engine, path, StorageFile, FileAccessMode, BitmapDecoder):
    f = await StorageFile.get_file_from_path_async(path)
    stream = await f.open_async(FileAccessMode.READ)
    try:
        decoder = await BitmapDecoder.create_async(stream)
        bmp = await decoder.get_software_bitmap_async()
        res = await engine.recognize_async(bmp)
    finally:
        stream.close()
    lines = []
    for line in res.lines:
        ws = list(line.words)
        if not ws:
            continue
        lines.append({
            "text": clean(line.text),
            "x": min(w.bounding_rect.x for w in ws),
            "y": min(w.bounding_rect.y for w in ws),
            "h": max(w.bounding_rect.height for w in ws),
            "x2": max(w.bounding_rect.x + w.bounding_rect.width for w in ws),
            "y2": max(w.bounding_rect.y + w.bounding_rect.height for w in ws),
        })
    return lines


def split_lines(lines, width, height):
    """
    按「相对比例」而非绝对像素分类，这样换分辨率也不会出错。

    从实测布局得出的规则（1280x720 和 1920x1080 都适用）：
        台词   左下区域，字号较大        x<0.72w, y>0.55h, 字高>=0.014w
        菜单项 右栏，字号中等            x>0.78w, y在0.155h~0.95h 之间
        标签页 右栏最上方两个            x>0.78w, y<0.155h
        其余（标题、角色名、右上水印、左下版权、配音演员）一律丢弃
    """
    main, menu, tabs = [], [], []
    w_thr = width * 0.014
    for l in lines:
        if l["x"] > width * 0.78:
            if l["y"] < height * 0.155:
                tabs.append(l)
            elif l["y"] < height * 0.95:
                menu.append(l)
        elif l["x"] < width * 0.72 and l["y"] > height * 0.55 and l["h"] >= w_thr:
            main.append(l)
    return main, menu, tabs


def frame_signature(img):
    g = img.convert("L").resize((64, 36))
    return hashlib.md5(g.tobytes()).hexdigest()[:16], g.tobytes()


def similar(a, b, threshold=0.005):
    if a is None or b is None:
        return False
    diff = sum(1 for p, q in zip(a, b) if abs(p - q) > 12)
    return diff / len(a) < threshold


def brightness_at(img, x, y, w=18, h=8):
    from PIL import Image
    box = (max(0, int(x - 22)), max(0, int(y - 4)),
           max(1, int(x - 22 + w)), max(1, int(y - 4 + h)))
    px = list(img.crop(box).convert("L").getdata())
    return sum(px) / len(px) if px else 0


async def scan_video(path, args, mods, cache, frames_dir=None, tag="v"):
    engine, StorageFile, FileAccessMode, BitmapDecoder = mods
    tmp = os.path.join(args.workdir, "_frame.png")
    samples = []
    seen_texts = {}
    last_norm = None
    shot = 0
    with av.open(path) as c:
        vs = c.streams.video[0]
        width = vs.codec_context.width or 1920
        last_bytes = None
        next_t = 0.0
        total_ocr = 0
        for frame in c.decode(vs):
            if frame.pts is None:
                continue
            t = float(frame.pts * vs.time_base)
            if t < next_t:
                continue
            next_t = t + args.interval
            img = frame.to_image()
            sig, raw = frame_signature(img)
            if similar(last_bytes, raw):
                continue
            last_bytes = raw
            if sig in cache:
                lines = cache[sig]
            else:
                img.save(tmp)
                lines = await ocr_image(engine, tmp, StorageFile,
                                        FileAccessMode, BitmapDecoder)
                cache[sig] = lines
                total_ocr += 1
            height = vs.codec_context.height or 1080
            main, menu, tabs = split_lines(lines, width, height)
            main_text = "".join(m["text"] for m in sorted(main, key=lambda k: k["y"]))
            if not main_text:
                continue
            section = None
            if tabs:
                best = max(tabs, key=lambda l: brightness_at(img, l["x"], l["y"]))
                section = best["text"]
            menu_obs = [{"text": m["text"],
                         "bright": round(brightness_at(img, m["x"], m["y"]), 1)}
                        for m in sorted(menu, key=lambda k: k["y"])]
            samples.append({"t": round(t, 2), "text": main_text,
                            "section": section, "menu": menu_obs})
            seen_texts[norm(main_text)] = main_text
            if frames_dir and norm(main_text) != last_norm:
                last_norm = norm(main_text)
                shot += 1
                img.save(os.path.join(frames_dir, "%s_%03d_%06.1fs.png" % (tag, shot, t)))
                samples[-1]["shot"] = shot
        print("  实际 OCR 帧数 %d（画面未变化时自动跳过）" % total_ocr)
    return samples


def resolve_context(samples_in_segment):
    """在若干帧的观测里，挑出最可能的「情境」。"""
    texts = [s["text"] for s in samples_in_segment]
    joined = "".join(texts)
    cand = {}
    for s in samples_in_segment:
        for m in s["menu"]:
            key = m["text"]
            rec = cand.setdefault(key, {"text": key, "bright": 0.0, "hits": 0})
            rec["bright"] = max(rec["bright"], m["bright"])
            rec["hits"] += 1
    # 过滤明显是噪声的菜单项：太短、含「配音」、纯符号数字
    cand = {k: v for k, v in cand.items()
            if len(norm(k)) >= 3 and "配音" not in k and norm(k).strip()}
    if not cand:
        return None, "无菜单项"
    scored = []
    for v in cand.values():
        ov = overlap_score(v["text"], joined)
        scored.append((ov, v["bright"], v))
    best_ov = max(s[0] for s in scored)
    if best_ov >= 3:
        winners = [s for s in scored if s[0] == best_ov]
        winners.sort(key=lambda s: -s[1])
        return winners[0][2]["text"], "文字重叠(%d字)" % best_ov
    scored.sort(key=lambda s: -s[1])
    return scored[0][2]["text"], "背景亮度"


def build_segments(samples, max_gap):
    """
    把连续且**意思相同**的帧合并成段。
    注意：游戏界面背景有动画，OCR 每一帧都会有细微抖动（偶尔读错一两个字），
    所以不能要求文本完全相等，要用相似度。同理，最终文本取出现次数最多的那个版本，
    这样能自动把偶发的错读过滤掉。
    """
    segs = []
    for s in samples:
        if segs:
            prev = segs[-1]
            gap_ok = s["t"] - prev["end"] <= max_gap
            dur_ok = s["t"] - prev["start"] <= max_gap * 20   # 防跑飞
            same = (text_ratio(prev["best"], s["text"]) >= 0.82
                    or contains_in(prev["best"], s["text"]))
            if gap_ok and dur_ok and same:
                prev["end"] = s["t"]
                prev["samples"].append(s)
                if len(norm(s["text"])) > len(norm(prev["best"])):
                    prev["best"] = s["text"]
                continue
        segs.append({"start": s["t"], "end": s["t"], "text": s["text"],
                     "best": s["text"], "samples": [s]})
    # 最终文本取「最长的那次观测」——打字机效果会把台词逐字补全，
    # 所以最长的那个版本就是完整台词
    for seg in segs:
        longest = max(seg["samples"], key=lambda x: len(norm(x["text"])))
        seg["text"] = longest["text"]
    for seg in segs:
        sec = [x["section"] for x in seg["samples"] if x["section"]]
        seg["section"] = max(set(sec), key=sec.count) if sec else None
        ctx, how = resolve_context(seg["samples"])
        seg["context"] = ctx
        seg["how"] = how
    return segs


SECTION_HINT = {
    "互动语音": "对方和你交谈",
    "战斗语音": "战斗中",
    "故事": "角色故事",
}


def make_instruction(seg):
    ctx = seg.get("context")
    sec = seg.get("section") or ""
    hint = SECTION_HINT.get(sec.replace(" ", ""), "")
    if ctx and hint:
        return "（%s：%s）" % (hint, ctx)
    if ctx:
        return "（%s）" % ctx
    if hint:
        return "（%s）" % hint
    return "（未知情境）"


def dedupe_segments(segs, window=5.0, lookback=4):
    """
    局部去重。OCR 会在「两行都读到」「只读到第一行」「只读到第二行」之间抖动，
    导致同一句台词被切成好几段。这里只跟时间上相邻的最近几段比较，避免误并。
    """
    out = []
    for seg in segs:
        merged = False
        for cand in reversed(out[-lookback:]):
            if seg["start"] - cand["end"] > window:
                break
            if contains_in(cand["text"], seg["text"]) or \
                    text_ratio(cand["text"], seg["text"]) >= 0.75:
                cand["end"] = max(cand["end"], seg["end"])
                cand["start"] = min(cand["start"], seg["start"])
                cand["samples"].extend(seg["samples"])
                if len(norm(seg["text"])) > len(norm(cand["text"])):
                    cand["text"] = seg["text"]
                merged = True
                break
        if not merged:
            out.append({"start": seg["start"], "end": seg["end"],
                        "text": seg["text"], "samples": list(seg["samples"])})
    # 合并后重新判定分类和情境
    for seg in out:
        sec = [x["section"] for x in seg["samples"] if x["section"]]
        seg["section"] = max(set(sec), key=sec.count) if sec else None
        ctx, how = resolve_context(seg["samples"])
        seg["context"] = ctx
        seg["how"] = how
    return out


def main():
    p = argparse.ArgumentParser(description="从游戏语音界面录屏提取训练数据")
    p.add_argument("--src", required=True, help="视频文件或目录")
    p.add_argument("--out", required=True, help="输出 jsonl")
    p.add_argument("--interval", type=float, default=0.5, help="抽帧间隔（秒）")
    p.add_argument("--max-gap", type=float, default=1.5,
                   help="同一句台词允许的最大帧间隔，超过就分成两段")
    p.add_argument("--min-chars", type=int, default=4, help="短于这个字数的台词丢弃")
    p.add_argument("--system", default=None,
                   help="写进每条的 system 字段（角色设定卡内容）")
    p.add_argument("--workdir", default=None, help="临时目录")
    p.add_argument("--no-cache", action="store_true", help="不使用 OCR 缓存")
    args = p.parse_args()

    try:
        from winsdk.windows.media.ocr import OcrEngine
        from winsdk.windows.globalization import Language
        from winsdk.windows.storage import StorageFile, FileAccessMode
        from winsdk.windows.graphics.imaging import BitmapDecoder
    except ImportError:
        sys.exit("[错误] 缺少 winsdk。安装：\n"
                 "  D:\\ai\\envs\\llm\\python.exe -m pip install winsdk "
                 "-i https://pypi.tuna.tsinghua.edu.cn/simple")

    engine = OcrEngine.try_create_from_language(Language("zh-Hans-CN"))
    if not engine:
        sys.exit("[错误] 无法创建中文 OCR 引擎（需要系统装了简体中文语言包）")

    videos = list_videos(args.src)
    if not videos:
        sys.exit("[错误] 没找到视频文件（已自动跳过 B 站的纯音频流文件）")
    print("[输入] %d 个视频文件" % len(videos))
    for v in videos:
        print("   " + os.path.basename(v))

    outdir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(outdir, exist_ok=True)
    args.workdir = args.workdir or os.path.join(outdir, "_work")
    os.makedirs(args.workdir, exist_ok=True)
    frames_dir = args.out + ".frames"
    os.makedirs(frames_dir, exist_ok=True)

    cache_path = args.out + ".ocr_cache.json"
    cache = {}
    if not args.no_cache and os.path.exists(cache_path):
        try:
            cache = json.load(open(cache_path, encoding="utf-8"))
            print("[缓存] 复用上次的 OCR 结果 %d 条" % len(cache))
        except Exception:
            cache = {}

    mods = (engine, StorageFile, FileAccessMode, BitmapDecoder)
    all_samples = []
    for i, v in enumerate(videos, 1):
        print("\n[%d/%d] 扫描 %s" % (i, len(videos), os.path.basename(v)))
        t0 = time.time()
        samples = asyncio.run(scan_video(v, args, mods, cache,
                                         frames_dir=frames_dir,
                                         tag="v%d" % i))
        print("  用时 %.0f 秒，记录 %d 个采样点" % (time.time() - t0, len(samples)))
        all_samples.extend(samples)

    try:
        json.dump(cache, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception as e:
        print("[提示] 缓存写入失败：%s" % e)

    if not all_samples:
        sys.exit("[错误] 没有提取到任何台词，检查视频是否真的是语音界面录屏")

    segs = build_segments(all_samples, args.max_gap)
    before = len(segs)
    segs = dedupe_segments(segs)
    if len(segs) != before:
        print("[去重] %d 段 -> %d 段（合并了重复的同一句）" % (before, len(segs)))
    segs = [s for s in segs if len(norm(s["text"])) >= args.min_chars]
    print("\n[结果] 合并出 %d 段台词" % len(segs))
    if not segs:
        sys.exit("[错误] 没有一段达到最低字数要求")

    with open(args.out, "w", encoding="utf-8") as f:
        for seg in segs:
            item = {"instruction": make_instruction(seg), "output": seg["text"]}
            if args.system:
                item = {"system": args.system, "instruction": item["instruction"],
                        "output": item["output"]}
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    review = args.out + ".review.txt"
    with open(review, "w", encoding="utf-8") as f:
        f.write("校对清单：逐条核对「情境」和「台词」，OCR 可能有错字。\n")
        f.write("对应的画面截图在 %s 目录下，文件名带段落编号和时间戳。\n" % frames_dir)
        f.write("改完直接保存 jsonl 即可用于训练。\n\n")
        for i, seg in enumerate(segs, 1):
            f.write("--- 第 %d 条  [%s - %s] ---\n"
                    % (i, fmt(seg["start"]), fmt(seg["end"])))
            f.write("  分类: %s\n" % (seg.get("section") or "未识别"))
            f.write("  情境: %s   （判断依据：%s）\n"
                    % (seg.get("context") or "未识别", seg.get("how", "")))
            f.write("  台词: %s\n" % seg["text"])
            f.write("  指令: %s\n\n" % make_instruction(seg))

    print("[完成] 训练数据 -> %s" % os.path.abspath(args.out))
    print("[完成] 校对清单 -> %s" % os.path.abspath(review))
    print("[完成] 截图 %d 张 -> %s" % (len(os.listdir(frames_dir)), frames_dir))
    print("")
    print("下一步：对着截图改错字，然后体检：")
    print('  D:\\ai\\envs\\llm\\python.exe scripts\\prepare_data.py check --src "%s"'
          % args.out)


def fmt(t):
    return "%d:%04.1f" % (int(t // 60), t % 60)


if __name__ == "__main__":
    main()
