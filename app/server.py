# -*- coding: utf-8 -*-
r"""
阮·梅 本地对话应用 —— 一个端口，浏览器打开就能聊，回复自动带声音。

用法
----
    D:\ai\envs\llm\python.exe app\server.py
    然后浏览器打开 http://127.0.0.1:7788

它其实是个反向代理 + 静态页：
    /            -> index.html（聊天界面）
    /api/status  -> 检查 Ollama / 语音适配器是否就绪
    /api/chat    -> 转发到 Ollama（11434），流式返回
    /api/tts     -> 转发到语音适配器（9881），返回 wav

只用标准库，不需要装任何东西。语音适配器没启动时只出文字，不影响聊天。
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from local_security import LocalRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))


def get(url, timeout=10):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def post(url, payload, timeout, stream=False):
    req = urllib.request.Request(
        url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    return urllib.request.urlopen(req, timeout=timeout)


class Handler(LocalRequestHandler):
    cfg = {}
    server_version = "RuanMeiApp/1.0"

    def log_message(self, fmt, *a):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % a))

    def _send(self, code, body, ctype):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        body=json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        if not isinstance(body,dict):raise ValueError('JSON object required')
        return body

    # ---------- 静态页 ----------
    def do_GET(self):
        p = self.path.split("?")[0]
        if p in ("/", "/index.html"):
            path = os.path.join(HERE, "index.html")
            if not os.path.exists(path):
                self._send(500, "index.html 不存在", "text/plain; charset=utf-8")
                return
            with open(path, "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        elif p == "/api/status":
            ollama_ok = tts_ok = False
            try:
                get(self.cfg["ollama"] + "/api/tags", 5)
                ollama_ok = True
            except Exception:
                pass
            try:
                get(self.cfg["tts"].rstrip("/") + "/healthz", 5)
                tts_ok = True
            except Exception:
                pass
            self._send(200, json.dumps({"ollama": ollama_ok, "tts": tts_ok}),
                       "application/json; charset=utf-8")
        else:
            self._send(404, "not found", "text/plain; charset=utf-8")

    # ---------- 聊天 / 语音 ----------
    def do_POST(self):
        p = self.path.split("?")[0]

        if p == "/api/chat":
            try:
                req = self._body()
            except Exception as e:
                self._send(400, json.dumps({"error": str(e)}), "application/json")
                return
            payload = {
                "model": self.cfg["model"],
                "messages": req.get("messages", []),
                "stream": True,
                "think": bool(req.get("think", False)),
                "options": {"temperature": 0.75, "top_p": 0.9},
            }
            try:
                up = post(self.cfg["ollama"] + "/api/chat", payload, timeout=600)
            except urllib.error.URLError as e:
                self._send(502, json.dumps(
                    {"error": "连不上 Ollama：%s（Ollama 在运行吗？）" % e.reason},
                    ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                while True:
                    chunk = up.read(4096)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except Exception:
                pass
            finally:
                up.close()
            return

        if p == "/api/tts":
            try:
                req = self._body()
            except Exception as e:
                self._send(400, json.dumps({"error": str(e)}), "application/json")
                return
            text = (req.get("text") or "").strip()
            if not text:
                self._send(400, '{"error":"text 为空"}', "application/json")
                return
            payload = {
                "input": text,
                "voice": self.cfg["voice"],
                "response_format": "wav",
            }
            try:
                up = post(self.cfg["tts"].rstrip("/") + "/v1/audio/speech",
                          payload, timeout=900)
                data = up.read()
                ctype = up.headers.get("Content-Type", "audio/wav")
                up.close()
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:300]
                self._send(502, json.dumps({"error": detail},
                                           ensure_ascii=False).encode("utf-8"),
                           "application/json; charset=utf-8")
                return
            except Exception as e:
                self._send(502, json.dumps(
                    {"error": "语音服务不可用：%s" % str(e)[:120]},
                    ensure_ascii=False).encode("utf-8"),
                    "application/json; charset=utf-8")
                return
            self._send(200, data, ctype)
            return

        self._send(404, "not found", "text/plain; charset=utf-8")


def main():
    ap = argparse.ArgumentParser(description="阮·梅 本地对话应用")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7788)
    ap.add_argument("--model", default="ruanmei")
    ap.add_argument("--voice", default="ruanmei")
    ap.add_argument("--ollama", default="http://127.0.0.1:11434")
    ap.add_argument("--tts", default="http://127.0.0.1:9881")
    ap.add_argument("--no-browser", action="store_true",
                    help="启动时不要自动打开浏览器")
    ap.add_argument("--browser-delay", type=float, default=1.5,
                    help="延迟几秒再打开浏览器，等端口就绪")
    args = ap.parse_args()

    Handler.cfg = {"model": args.model, "voice": args.voice,
                   "ollama": args.ollama, "tts": args.tts}
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print("=" * 56)
    print("  阮·梅 本地对话应用")
    print("=" * 56)
    print("  浏览器打开   http://%s:%d" % (args.host, args.port))
    print("  对话模型     %s（Ollama @ %s）" % (args.model, args.ollama))
    print("  语音音色     %s（适配器 @ %s）" % (args.voice, args.tts))
    print("")
    print("  语音适配器没启动也不影响聊天，只是不出声。")
    print("  按 Ctrl+C 停止。")
    print("=" * 56)

    # 延迟一点再弹浏览器，等端口真正开始监听
    if not args.no_browser:
        import threading
        import webbrowser

        def _open():
            import time
            time.sleep(args.browser_delay)
            try:
                webbrowser.open("http://%s:%d" % (args.host, args.port))
                print("[提示] 已在浏览器中打开；没自动弹出就手动访问上面的地址。")
            except Exception as e:
                print("[提示] 自动打开浏览器失败：%s" % e)
        threading.Thread(target=_open, daemon=True).start()

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[退出]")


if __name__ == "__main__":
    main()
