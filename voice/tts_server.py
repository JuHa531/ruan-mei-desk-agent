# -*- coding: utf-8 -*-
r"""
零依赖的 OpenAI 兼容 TTS 服务 —— 把本地语音模型包装成 /v1/audio/speech。

支持两种后端
------------
gpt_sovits （默认）  音色克隆强、中文好；情绪靠「切换参考音频」实现
index_tts           音色与情绪解耦；支持 8 维情绪向量和情绪描述文字

为什么需要它
------------
这些模型自带的接口各家不一样，而 Open WebUI、AnythingLLM 等客户端认的是
OpenAI 那套 /v1/audio/speech。这个小服务负责翻译两边，只用 Python 标准库；
启用 voice 的 speed_mode="post" 时额外调用现有的 ffmpeg 做变速和轻量修音。

情绪怎么用
----------
请求里加 emotion 字段，或把情绪写在音色名后面：
    {"input": "你怎么才回来？", "voice": "my-voice", "emotion": "生气"}
    {"input": "太好了！",       "voice": "my-voice:happy"}
emotion_strength 控制强度（0~1，默认 1.0）。八种内置情绪开箱即用：
    happy / angry / sad / afraid / disgusted / melancholic / surprised / calm

启动
----
    python tts_server.py --config voices.json

启动后：
    GET  http://127.0.0.1:9881/v1/models         列出可用音色
    POST http://127.0.0.1:9881/v1/audio/speech   合成语音
    GET  http://127.0.0.1:9881/healthz           检查后端通不通

自测（不需要任何客户端）：
    python tts_server.py --config voices.json --say "你好，我在本地运行。"

注意
----
--say 会把合成结果存成 out.wav，用它验证「模型是否真的在出声」最快。
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


# ---------------------------------------------------------------------------
# 朗读前的文本清理
# ---------------------------------------------------------------------------
# 为什么要做：AI 的回复是 Markdown，直接念会把 ```、**、#、| 这些符号也读出来，
# 而且代码块、表格念出来毫无意义、还特别长。这里先把它们处理掉再送进语音模型。
_CODE_FENCE = re.compile(r"```.*?```", re.S)
_INLINE_CODE = re.compile(r"`([^`]*)`")
_MD_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_HEADING = re.compile(r"(?m)^[ \t]{0,3}#{1,6}[ \t]*")
_LIST_MARK = re.compile(r"(?m)^[ \t]*(?:[-*+\u2022]|\d+[.)])[ \t]+")
_EMPHASIS = re.compile(r"(\*\*|__|~~|\*|_)")
_TABLE_SEP = re.compile(r"(?m)^[ \t]*\|?[ \t:|-]{4,}\|?[ \t]*$")
_PIPE = re.compile(r"[ \t]*\|[ \t]*")
_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U0001F000-\U0001F2FF"
    "\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\uFE0F\u2B00-\u2BFF]")
_ARROWS = re.compile(r"(->|=>|\u2192|\u21d2)")


def clean_for_speech(text, skip_code="这一段是代码，我就不念了。"):
    """把 Markdown 收拾成适合朗读的纯文本。"""
    t = str(text or "")
    t = _CODE_FENCE.sub(lambda m: "\n" + skip_code + "\n"
                        if len(m.group(0)) > 8 else "\n", t)
    t = _TABLE_SEP.sub("", t)
    t = _MD_LINK.sub(r"\1", t)
    t = _INLINE_CODE.sub(r"\1", t)
    t = _HEADING.sub("", t)
    t = _LIST_MARK.sub("", t)
    t = _PIPE.sub("，", t)
    t = _ARROWS.sub("，", t)
    t = _EMPHASIS.sub("", t)
    t = _EMOJI.sub("", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"(?m)^[ \t]+", "", t)
    # 换行当断句，避免一口气连读
    t = re.sub(r"\n+", "。", t)
    t = re.sub(r"。{2,}", "。", t)
    t = re.sub(r"[。、，]{2,}", "。", t)
    t = re.sub(r"[：:、，]+(?=。)", "", t)
    t = t.strip("。 \t")
    return t


# OpenAI 的 response_format -> GPT-SoVITS 的 media_type
# 注意：GPT-SoVITS api_v2 只支持 wav / ogg / aac / raw，其余一律退回 wav
FORMAT_MAP = {
    "wav": ("wav", "audio/wav"),
    "opus": ("ogg", "audio/ogg"),
    "ogg": ("ogg", "audio/ogg"),
    "aac": ("aac", "audio/aac"),
    "pcm": ("raw", "application/octet-stream"),
    "mp3": ("wav", "audio/wav"),
    "flac": ("wav", "audio/wav"),
}


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    if "backend" not in cfg or "base_url" not in cfg.get("backend", {}):
        sys.exit("[错误] 配置里缺少 backend.base_url，参考 voices.example.json")
    if not cfg.get("voices"):
        sys.exit("[错误] 配置里没有任何音色，参考 voices.example.json")
    return cfg


def normalize_ref_path(p):
    """GPT-SoVITS 两端路径都按「后端所在机器」解释，这里统一成正斜杠更稳。"""
    p = os.path.expandvars(os.path.expanduser(str(p)))
    return p.replace("\\", "/")


def ffmpeg_exe(cfg):
    """返回可用的 ffmpeg 路径；没有就返回空字符串。"""
    path = os.path.expandvars(os.path.expanduser(str(cfg.get("ffmpeg") or "")))
    if path and os.path.isfile(path):
        return path
    return shutil.which("ffmpeg") or ""


def use_post_speed(cfg, vcfg, media_type):
    """GPT-SoVITS 原生速度合成后，再用 ffmpeg 变速/修音。"""
    return (cfg.get("backend", {}).get("type", "gpt_sovits") == "gpt_sovits"
            and vcfg.get("speed_mode") == "post"
            and media_type == "wav"
            and bool(ffmpeg_exe(cfg)))


def fix_wav_stream_sizes(data):
    """
    ffmpeg 输出到管道时不能回填长度，RIFF/data 会写成 0xFFFFFFFF。
    Python wave 和部分播放器会误判成超长音频；这里按实际字节数补回。
    """
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return data
    import struct
    out = bytearray(data)
    struct.pack_into("<I", out, 4, len(out) - 8)
    pos = out.find(b"data", 12)
    if pos >= 0 and pos + 8 <= len(out):
        struct.pack_into("<I", out, pos + 4, len(out) - pos - 8)
    return bytes(out)


def polish_audio(cfg, vcfg, data, speed):
    """
    对 GPT-SoVITS 的 WAV 做保守后处理。

    speed_factor 直接改声码器上采样率，0.8 这类非原生速度容易带出金属感。
    所以模型先按 1.0 合成，再由 atempo 只改变时长、不动音高。deesser 和
    10 kHz 低通负责压掉最容易听成“电音”的高频毛刺，不影响说话主体。
    """
    if not vcfg.get("post_filter") and abs(float(speed) - 1.0) < 0.01:
        return data
    filters = []
    if abs(float(speed) - 1.0) >= 0.01:
        filters.append("atempo=%.5f" % float(speed))
    if vcfg.get("post_filter"):
        filters.append(str(vcfg["post_filter"]))
    if not filters:
        return data

    cmd = [
        ffmpeg_exe(cfg), "-hide_banner", "-loglevel", "error",
        "-i", "pipe:0", "-af", ",".join(filters),
        "-c:a", "pcm_s16le", "-f", "wav", "pipe:1",
    ]
    try:
        proc = subprocess.run(cmd, input=data, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=60)
        if proc.returncode == 0 and proc.stdout:
            return fix_wav_stream_sizes(proc.stdout)
        detail = proc.stderr.decode("utf-8", "replace")[:200]
        sys.stderr.write("[语音后处理] ffmpeg 失败，保留原始音频：%s\n" % detail)
    except Exception as e:
        sys.stderr.write("[语音后处理] 跳过，保留原始音频：%s\n" % e)
    return data


def build_gptsovits_payload(cfg, vcfg, text, speed, media_type, emo=None):
    """
    GPT-SoVITS 没有情绪参数，情绪完全由「参考音频」带出来。
    所以这里的情绪实现方式就是：换一套参考音频和对应的原文。
    """
    merged = dict(vcfg)
    if emo and "ref_audio_path" in emo:
        for k in ("ref_audio_path", "prompt_text", "prompt_lang"):
            if k in emo:
                merged[k] = emo[k]
    elif emo and "no_emo_ref" not in _warned:
        _warned.add("no_emo_ref")
        sys.stderr.write(
            "[警告] GPT-SoVITS 没有情绪参数，情绪只能靠换参考音频实现。\n"
            "       请在配置的 emotions 里为每种情绪指定 ref_audio_path，\n"
            "       或者把 backend.type 换成 index_tts 使用真正的情绪控制。\n")
    lang = merged.get("text_lang", "zh")
    # 原生速度交给 ffmpeg 调整，避免声码器使用非训练时的上采样率。
    native = use_post_speed(cfg, vcfg, media_type)
    speed_factor = speed if native else merged.get("speed", 1.0) * speed
    return {
        "text": text,
        "text_lang": lang,
        "ref_audio_path": normalize_ref_path(merged["ref_audio_path"]),
        "prompt_text": merged.get("prompt_text", ""),
        "prompt_lang": merged.get("prompt_lang", lang),
        "top_k": merged.get("top_k", 15),
        "top_p": merged.get("top_p", 1.0),
        "temperature": merged.get("temperature", 1.0),
        "text_split_method": merged.get("text_split_method", "cut5"),
        # 分句之间的静音时长。默认 0.3 秒太短，听起来"一句接一句喘不上气"；
        # 实测加到 0.65 秒明显自然。
        "fragment_interval": merged.get("fragment_interval", 0.3),
        "batch_size": merged.get("batch_size", 1),
        "speed_factor": speed_factor,
        "seed": merged.get("seed", -1),
        "media_type": media_type,
        "streaming_mode": False,
        "parallel_infer": merged.get("parallel_infer", True),
        "repetition_penalty": merged.get("repetition_penalty", 1.35),
        "sample_steps": merged.get("sample_steps", 32),
        "super_sampling": merged.get("super_sampling", False),
    }


# ---- 情绪控制 ----
# IndexTTS2 的 8 维情绪向量顺序，来自官方 README
EMO_ORDER = ["happy", "angry", "sad", "afraid",
             "disgusted", "melancholic", "surprised", "calm"]

# 中文叫法也认，方便直接在配置里写中文
EMO_ALIAS = {
    "开心": "happy", "高兴": "happy", "快乐": "happy",
    "生气": "angry", "愤怒": "angry",
    "难过": "sad", "悲伤": "sad", "伤心": "sad",
    "害怕": "afraid", "恐惧": "afraid",
    "厌恶": "disgusted", "嫌弃": "disgusted",
    "低落": "melancholic", "忧郁": "melancholic",
    "惊讶": "surprised", "吃惊": "surprised",
    "平静": "calm", "中性": "calm",
}

_warned = set()


def emotion_vector(name, intensity=1.0):
    key = EMO_ALIAS.get(name, name)
    if key not in EMO_ORDER:
        raise KeyError(f"不认识的情绪 {name!r}。可用：{', '.join(EMO_ORDER)}")
    vec = [0.0] * 8
    vec[EMO_ORDER.index(key)] = float(intensity)
    return vec


def resolve_emotion(vcfg, name, strength=1.0):
    """
    情绪有三种来源，优先级从高到低：
      1. 配置里 emotions 的显式定义（可给参考音频，也可给完整 8 维向量）
      2. 请求里直接传 8 个数字的向量
      3. 内置情绪名，不写任何配置就能用
    返回 None 表示不做情绪控制，交给模型默认行为。
    """
    if not name:
        return None
    if isinstance(name, (list, tuple)):
        if len(name) != 8:
            raise KeyError("情绪向量必须是 8 个数字")
        return {"emo_vector": [float(x) for x in name]}
    preset = (vcfg.get("emotions") or {}).get(str(name))
    if preset is not None:
        e = dict(preset)
        if "emo_vector" in e:
            e["emo_vector"] = [float(x) for x in e["emo_vector"]]
        if "emo_alpha" not in e and strength != 1.0:
            e["emo_alpha"] = strength
        return e
    if EMO_ALIAS.get(str(name), str(name)) in EMO_ORDER:
        # 向量给满强度，强度只用 emo_alpha 表达，避免缩放两次
        return {"emo_vector": emotion_vector(str(name), 1.0),
                "emo_alpha": strength}
    raise KeyError(f"没有名为 {name!r} 的情绪。内置可用：{', '.join(EMO_ORDER)}")


# IndexTTS 的语言代码
IDX_LANG = {"zh": "ZH", "en": "EN", "ja": "JA", "ko": "KO",
            "es": "ES", "ar": "AR", "auto": "ZH"}


def build_indextts_payload(vcfg, text, speed, media_type, emo=None):
    """IndexTTS2 的音色和情绪是解耦的，可以分别指定。"""
    payload = {
        "spk_audio_prompt": normalize_ref_path(vcfg["ref_audio_path"]),
        "text": text,
        "lang": IDX_LANG.get(str(vcfg.get("text_lang", "zh")).lower(), "ZH"),
    }
    if emo:
        for k in ("emo_vector", "emo_audio_prompt", "emo_text", "emo_alpha"):
            if k in emo:
                payload[k] = (normalize_ref_path(emo[k])
                              if k == "emo_audio_prompt" else emo[k])
        if "emo_text" in payload:
            payload["use_emo_text"] = True
    if vcfg.get("use_random") is not None:
        payload["use_random"] = vcfg["use_random"]
    if vcfg.get("max_mel_tokens"):
        payload["max_mel_tokens"] = vcfg["max_mel_tokens"]
    return payload


def build_request(cfg, vcfg, text, speed, media_type, emo):
    if cfg["backend"].get("type", "gpt_sovits") == "index_tts":
        return build_indextts_payload(vcfg, text, speed, media_type, emo)
    return build_gptsovits_payload(cfg, vcfg, text, speed, media_type, emo)


def wav_duration(data):
    """读 wav 的时长（秒）。解析失败返回 None。"""
    try:
        import wave
        import io
        with wave.open(io.BytesIO(data)) as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except Exception:
        return None


def looks_truncated(data, text, min_rate=5.0):
    """
    判断这次的合成是不是明显"念短了"。

    背景：这个模型偶发会只念出开头一小段就结束（实测 89 字的文本有时只出 3 秒音频，
    正常应该是 25 秒左右）。语速再快也不会超过每秒 5 个字（速度因子 0.8 时约 3.4 字/秒），
    所以低于 字数/5 秒 的基本可以判定是截断，直接重试。
    """
    dur = wav_duration(data)
    if dur is None:
        return False
    chars = len([c for c in text if not c.isspace()])
    if chars < 12:
        return False          # 太短的句子本来就没几秒，别误判
    return dur < chars / min_rate


def speech_min_rate(vcfg, speed):
    """按最终语速估算最短合理时长；0.8 倍速时约 4 字/秒。"""
    return max(2.8, 5.0 * float(vcfg.get("speed", 1.0)) * float(speed))


def call_backend(cfg, payload, path=None):
    path = path or cfg["backend"].get("tts_path", "/tts")
    url = cfg["backend"]["base_url"].rstrip("/") + path
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    timeout = cfg.get("timeout_seconds", 300)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"语音后端返回 {e.code}：{detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"连不上语音后端（{url}）：{e.reason}\n"
            "先确认语音服务已经启动，且端口和配置里一致。"
        ) from e


def resolve_voice(cfg, name):
    """
    支持两种写法：'my-voice' 和 'my-voice:angry'。
    返回 (音色名, 音色配置, 从名字里带出的情绪名或 None)。
    """
    voices = cfg["voices"]
    if not name:
        name = cfg.get("default_voice") or next(iter(voices))
    name = str(name)
    emo_name = None
    if name not in voices and ":" in name:
        base, _, emo_name = name.partition(":")
        if base in voices:
            name = base
    if name in voices:
        return name, voices[name], emo_name
    # 允许直接塞一个参考音频路径，方便临时试新音色，不用改配置
    if any(name.lower().endswith(x) for x in (".wav", ".mp3", ".flac", ".m4a", ".ogg")):
        return os.path.basename(name), {"ref_audio_path": name, "text_lang": "zh"}, emo_name
    raise KeyError(f"没有名为 {name!r} 的音色。可用：{', '.join(voices)}")


class Handler(BaseHTTPRequestHandler):
    cfg = None
    server_version = "LocalTTSAdapter/1.0"

    def log_message(self, fmt, *a):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % a))

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.split("?")[0] in ("/v1/models", "/models"):
            is_idx = self.cfg["backend"].get("type") == "index_tts"
            ids = []
            for name, vcfg in self.cfg["voices"].items():
                ids.append(name)
                for emo in (vcfg.get("emotions") or {}):
                    ids.append(f"{name}:{emo}")
                if is_idx:
                    ids.extend(f"{name}:{e}" for e in EMO_ORDER)
            seen, uniq = set(), []
            for i in ids:
                if i not in seen:
                    seen.add(i)
                    uniq.append(i)
            data = [{"id": i, "object": "model", "owned_by": "local"} for i in uniq]
            self._json({"object": "list", "data": data})
        elif self.path.split("?")[0] == "/healthz":
            self._json({"ok": True, "backend": self.cfg["backend"]["base_url"],
                        "type": self.cfg["backend"].get("type", "gpt_sovits"),
                        "emotions": EMO_ORDER,
                        "voices": list(self.cfg["voices"])})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path.split("?")[0] not in ("/v1/audio/speech", "/audio/speech"):
            self._json({"error": "not found"}, 404)
            return

        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        except Exception as e:
            self._json({"error": f"请求体不是合法 JSON：{e}"}, 400)
            return

        text = (body.get("input") or "").strip()
        if not text:
            self._json({"error": "缺少 input 字段"}, 400)
            return
        if self.cfg.get("clean_markdown", True):
            text = clean_for_speech(text) or "这段内容不适合朗读。"

        try:
            speed = float(body.get("speed") or 1.0)
        except (TypeError, ValueError):
            speed = 1.0

        fmt = str(body.get("response_format") or "wav").lower()
        media_type, content_type = FORMAT_MAP.get(fmt, ("wav", "audio/wav"))

        try:
            voice_name, vcfg, emo_from_name = resolve_voice(self.cfg, body.get("voice"))
        except KeyError as e:
            self._json({"error": str(e)}, 400)
            return

        try:
            strength = float(body.get("emotion_strength") or 1.0)
        except (TypeError, ValueError):
            strength = 1.0

        emo_name = body.get("emotion") or emo_from_name
        try:
            emo = resolve_emotion(vcfg, emo_name, strength)
        except KeyError as e:
            self._json({"error": str(e)}, 400)
            return

        try:
            payload = build_request(self.cfg, vcfg, text, speed, media_type, emo)
            audio = call_backend(self.cfg, payload)
            if use_post_speed(self.cfg, vcfg, media_type):
                audio = polish_audio(self.cfg, vcfg, audio,
                                     float(vcfg.get("speed", 1.0)) * speed)
            # 偶发截断（只念开头几秒）就重试，留长的那个。
            # 实测这个模型有 1/4 左右的概率给出残缺音频，不兜住的话用户会听到"突然中断"。
            tries = int(self.cfg.get("max_retry", 3))
            attempt = 1
            min_rate = speech_min_rate(vcfg, speed)
            while (looks_truncated(audio, text, min_rate) and attempt < tries):
                attempt += 1
                sys.stderr.write("[重试] 第 %d 次合成结果疑似截断（%s），重来\n"
                                 % (attempt, text[:20]))
                retry = dict(payload)
                retry["seed"] = -1
                try:
                    cand = call_backend(self.cfg, retry)
                except RuntimeError:
                    break
                if use_post_speed(self.cfg, vcfg, media_type):
                    cand = polish_audio(self.cfg, vcfg, cand,
                                        float(vcfg.get("speed", 1.0)) * speed)
                if not looks_truncated(cand, text, min_rate):
                    audio = cand
                    break
                if (wav_duration(cand) or 0) > (wav_duration(audio) or 0):
                    audio = cand
        except RuntimeError as e:
            self._json({"error": str(e)}, 502)
            return

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("X-Voice", voice_name.encode("ascii", "replace").decode("ascii"))
        if emo_name:
            self.send_header("X-Emotion",
                             str(emo_name).encode("ascii", "replace").decode("ascii"))
        self.send_header("Content-Length", str(len(audio)))
        self.end_headers()
        self.wfile.write(audio)


def do_say(cfg, args):
    say_text = args.say
    if cfg.get("clean_markdown", True):
        say_text = clean_for_speech(say_text) or say_text
    try:
        name, vcfg, emo_from_name = resolve_voice(cfg, args.say_voice)
        emo_name = args.say_emotion or emo_from_name
        emo = resolve_emotion(vcfg, emo_name, args.say_strength)
    except KeyError as e:
        sys.exit(f"[错误] {e}")
    tag = f"，情绪 {emo_name}（强度 {args.say_strength}）" if emo_name else ""
    print(f"[信息] 后端 {cfg['backend']['base_url']}，音色 {name}{tag}")
    audio = call_backend(cfg, build_request(cfg, vcfg, say_text, 1.0, "wav", emo))
    with open(args.say_out, "wb") as f:
        f.write(audio)
    print(f"[完成] {len(audio) / 1024:.0f} KB 已写入 {os.path.abspath(args.say_out)}")
    print("       播放它，确认音色和情绪对不对。")


def main():
    p = argparse.ArgumentParser(description="OpenAI 兼容的本地 TTS 适配器")
    p.add_argument("--config", default="voices.json")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=9881)
    p.add_argument("--say", help="不启服务，直接合成一句话用于验证")
    p.add_argument("--say-voice", default=None, help="配合 --say 指定音色名")
    p.add_argument("--say-emotion", default=None,
                   help="配合 --say 指定情绪，如 sad / 生气 / my-emo")
    p.add_argument("--say-strength", type=float, default=1.0,
                   help="情绪强度 0~1，默认 1.0")
    p.add_argument("--say-out", default="out.wav")
    args = p.parse_args()

    if not os.path.exists(args.config):
        sys.exit(f"[错误] 找不到配置文件 {args.config}\n"
                 "把 voices.example.json 复制成 voices.json 再改。")
    cfg = load_config(args.config)

    if args.say:
        do_say(cfg, args)
        return

    Handler.cfg = cfg
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    btype = cfg["backend"].get("type", "gpt_sovits")
    print(f"[启动] 监听 http://{args.host}:{args.port}")
    print(f"[后端] {cfg['backend']['base_url']}（{btype}）")
    print(f"[音色] {', '.join(cfg['voices'])}")
    if btype == "index_tts":
        print(f"[情绪] 内置 {', '.join(EMO_ORDER)}，用 音色:情绪 选择")
    elif any(v.get("emotions") for v in cfg["voices"].values()):
        print("[情绪] 通过切换参考音频实现，用 音色:情绪 选择")
    print("")
    print("Open WebUI 里填：")
    print(f"  TTS 引擎        OpenAI")
    print(f"  API Base URL    http://{args.host}:{args.port}/v1")
    print(f"  API Key         随便填（本地服务不校验）")
    print(f"  TTS Voice       {cfg.get('default_voice') or next(iter(cfg['voices']))}")
    print("")
    print("按 Ctrl+C 停止。")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[退出]")


if __name__ == "__main__":
    main()
