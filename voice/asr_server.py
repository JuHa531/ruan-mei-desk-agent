# -*- coding: utf-8 -*-
r"""
本地语音识别服务 —— 让「梅梅」能听懂你说话（全程离线，不联网）。

用 funasr 的 SenseVoiceSmall 模型（约 230MB，已下载到 G:\ai\hf-cache\modelscope）。
语音合成在 tts_server.py（9881），这个是 9882。

接口
----
    POST http://127.0.0.1:9882/asr
        请求体是音频二进制。默认按 webm/opus 处理（浏览器 MediaRecorder 的默认格式），
        会用 ffmpeg 转成 16k 单声道 wav 再识别；加 ?format=wav 可跳过转换。
        返回 {"text": "识别出的文字"}
    GET  http://127.0.0.1:9882/healthz   检查模型是否就绪

启动（必须用 tts 那个环境，funasr 和模型都在里面）
    D:\ai\envs\tts\python.exe voice\asr_server.py --preload

自测
    D:\ai\envs\tts\python.exe voice\asr_server.py --once 某个.wav
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
FFMPEG = r"G:\ai\ffmpeg\ffmpeg-9.0.2-essentials_build\bin\ffmpeg.exe"

# 这个服务是被 desktop.py 以"隐藏控制台"的方式拉起来的，它自己再起 ffmpeg
# （控制台程序）时，Windows 默认会新开一个黑框 —— 用户按下 🎙 就会看到一闪。
# 加这个标志 = 给控制台但不显示窗口。
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

_model = None
_lock = threading.Lock()          # funasr 模型不是线程安全的，串行处理


def get_model():
    global _model
    if _model is None:
        os.environ.setdefault("MODELSCOPE_CACHE", r"G:\ai\hf-cache\modelscope")
        from funasr import AutoModel
        print("[加载] SenseVoiceSmall ...（第一次约 10 秒）", flush=True)
        _model = AutoModel(model="iic/SenseVoiceSmall", disable_update=True, device="cpu")
        print("[加载] 完成", flush=True)
    return _model


def to_wav16k(data, src_format):
    """转成 16k 单声道 wav；本来就是 wav 就直接落盘。"""
    suffix = "." + (src_format or "webm")
    fd, src = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    if (src_format or "").lower() == "wav":
        return src
    dst = src + ".16k.wav"
    try:
        subprocess.run([FFMPEG, "-y", "-v", "error", "-i", src,
                        "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", dst],
                       capture_output=True, timeout=120, check=True,
                       creationflags=CREATE_NO_WINDOW)
        return dst
    finally:
        try:
            os.remove(src)
        except OSError:
            pass


def transcribe(data, src_format=None):
    path = to_wav16k(data, src_format)
    try:
        with _lock:
            r = get_model().generate(path, language="auto", use_itn=True)
        text = r[0]["text"] if r else ""
        text = re.sub(r"<\|[^|]*\|>", "", text).strip()   # 去掉 <|zh|><|NEUTRAL|> 这类标签
        return text
    finally:
        if path.endswith("16k.wav"):
            try:
                os.remove(path)
            except OSError:
                pass


class Handler(BaseHTTPRequestHandler):
    server_version = "RuanMeiASR/1.0"

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
        if self.path.split("?")[0] == "/healthz":
            self._json({"ok": _model is not None, "model": "iic/SenseVoiceSmall"})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        p, _, query = self.path.partition("?")
        if p != "/asr":
            self._json({"error": "not found"}, 404)
            return
        fmt = None
        for kv in query.split("&"):
            if kv.startswith("format="):
                fmt = kv.split("=", 1)[1]
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            self._json({"error": "请求体是空的"}, 400)
            return
        data = self.rfile.read(n)
        try:
            text = transcribe(data, fmt)
        except Exception as e:
            self._json({"error": "%s: %s" % (type(e).__name__, str(e)[:200])}, 500)
            return
        self._json({"text": text, "bytes": len(data)})


def main():
    ap = argparse.ArgumentParser(description="本地语音识别（SenseVoiceSmall，离线）")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9882)
    ap.add_argument("--preload", action="store_true", help="启动时先把模型加载好")
    ap.add_argument("--once", help="不启服务，直接识别一个音频文件（自测用）")
    args = ap.parse_args()

    if args.once:
        ext = os.path.splitext(args.once)[1].lstrip(".").lower() or "wav"
        with open(args.once, "rb") as f:
            print(transcribe(f.read(), ext))
        return

    if args.preload:
        get_model()

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print("=" * 56)
    print("  本地语音识别（离线）")
    print("=" * 56)
    print("  监听    http://%s:%d" % (args.host, args.port))
    print("  模型    iic/SenseVoiceSmall")
    print("  用法    POST /asr（身体放音频二进制，默认按 webm 处理）")
    print("  检查    GET  /healthz")
    print("=" * 56)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[退出]")


if __name__ == "__main__":
    main()
