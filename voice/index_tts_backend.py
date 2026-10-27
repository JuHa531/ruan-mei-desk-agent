# -*- coding: utf-8 -*-
r"""
IndexTTS2 的 HTTP 封装 —— 让 tts_server.py 能调用它。

IndexTTS 只提供 Python API 和 Gradio 界面，没有 HTTP 接口，所以需要这层薄封装。
它跑在你有 IndexTTS 环境的机器上，默认监听 9880。

准备（按官方 README，用 uv 管理环境）
------------------------------------
    git clone https://github.com/index-tts/index-tts
    cd index-tts
    uv sync
    # 模型权重按 README 指示下载到 checkpoints/

运行
----
    uv run python index_tts_backend.py --model-dir ./checkpoints --warmup

接口
----
    POST /tts       合成，返回 wav 字节
    GET  /healthz   健康检查

请求字段（和 IndexTTS 的 Python API 同名）
------------------------------------------
    spk_audio_prompt  音色参考音频，必填
    text              要合成的文字，必填
    lang              ZH / EN / JA / ES / AR（2.5 才有）
    emo_vector        8 维情绪强度 [happy, angry, sad, afraid,
                                   disgusted, melancholic, surprised, calm]
    emo_audio_prompt  用另一段音频指定情绪
    emo_text          用文字描述情绪，例如「你吓死我了！」
    emo_alpha         情绪强度 0~1

版本兼容
--------
IndexTTS 各版本的构造参数和 infer 参数有差异，本脚本会用 inspect 自动过滤掉
当前版本不支持的参数并打印提示，所以升级版本后一般不用改代码。
参数名以官方 README 和仓库里的 webui.py 为准。
"""

import argparse
import inspect
import json
import os
import sys
import tempfile
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0,os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'app'))
from local_security import LocalRequestHandler

_TTS = None


def build_tts(args):
    """按官方 README 的入口构造模型，自动丢弃当前版本不支持的参数。"""
    from indextts.infer_v2 import IndexTTS2
    opts = {
        "cfg_path": args.cfg,
        "model_dir": args.model_dir,
        "use_fp16": not args.no_fp16,
        "use_cuda_kernel": args.cuda_kernel,
        "use_deepspeed": args.deepspeed,
        "use_qwen_emo": args.qwen_emo,
    }
    opts = {k: v for k, v in opts.items() if v is not None}
    params = inspect.signature(IndexTTS2.__init__).parameters
    accepted = {k: v for k, v in opts.items() if k in params}
    dropped = sorted(set(opts) - set(accepted))
    if dropped:
        print(f"[注意] 当前 IndexTTS 版本不支持这些参数，已忽略：{dropped}")
    return IndexTTS2(**accepted)


def get_tts(args):
    global _TTS
    if _TTS is None:
        print("[加载] 正在载入 IndexTTS 模型……")
        _TTS = build_tts(args)
        print("[加载] 完成")
    return _TTS


def run_infer(tts, req, out_path):
    """把请求字段翻译成 infer() 的参数，同样自动过滤不支持的项。"""
    for key in ("spk_audio_prompt", "text"):
        if not req.get(key):
            raise ValueError(f"缺少必填字段 {key}")
    kwargs = {
        "spk_audio_prompt": req["spk_audio_prompt"],
        "text": req["text"],
        "output_path": out_path,
        "verbose": False,
    }
    for k in ("lang", "emo_vector", "emo_audio_prompt", "emo_text",
              "emo_alpha", "use_emo_text", "use_random", "max_mel_tokens"):
        if req.get(k) is not None:
            kwargs[k] = req[k]
    params = inspect.signature(tts.infer).parameters
    accepted = {k: v for k, v in kwargs.items() if k in params}
    dropped = sorted(set(kwargs) - set(accepted))
    if dropped:
        print(f"[注意] 当前版本 infer() 不支持这些参数，已忽略：{dropped}")
    tts.infer(**accepted)


class Handler(LocalRequestHandler):
    args = None

    def log_message(self, fmt, *a):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % a))

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.split("?")[0] == "/healthz":
            body = json.dumps({"ok": True, "loaded": _TTS is not None}).encode()
            self._send(200, body, "application/json")
        else:
            self._send(404, b'{"error":"not found"}', "application/json")

    def do_POST(self):
        if self.path.split("?")[0] != "/tts":
            self._send(404, b'{"error":"not found"}', "application/json")
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(n).decode("utf-8"))
            if not isinstance(req,dict):raise ValueError('JSON object required')
        except Exception as e:
            self._send(400, json.dumps({"error": f"请求体不是合法 JSON：{e}"},
                                       ensure_ascii=False).encode("utf-8"),
                       "application/json")
            return
        fd, out_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            run_infer(get_tts(self.args), req, out_path)
            with open(out_path, "rb") as f:
                audio = f.read()
        except Exception as e:
            traceback.print_exc()
            self._send(500, json.dumps({"error": str(e)},
                                       ensure_ascii=False).encode("utf-8"),
                       "application/json")
            return
        finally:
            try:
                os.unlink(out_path)
            except OSError:
                pass
        self._send(200, audio, "audio/wav")


def main():
    p = argparse.ArgumentParser(description="IndexTTS2 的 HTTP 封装")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=9880)
    p.add_argument("--model-dir", required=True,
                   help="checkpoints 目录，通常是 ./checkpoints")
    p.add_argument("--cfg", default=None, help="配置文件路径，按需指定")
    p.add_argument("--no-fp16", action="store_true",
                   help="关掉半精度。显存够的话不用加，加了更慢更占显存")
    p.add_argument("--cuda-kernel", action="store_true")
    p.add_argument("--deepspeed", action="store_true")
    p.add_argument("--qwen-emo", action="store_true",
                   help="启用「用文字描述情绪」，2.5 版本需要")
    p.add_argument("--warmup", action="store_true",
                   help="启动时就加载模型，避免第一次请求等很久")
    args = p.parse_args()
    if not os.path.isdir(args.model_dir):
        sys.exit(f"[错误] 找不到模型目录 {args.model_dir}")
    if args.warmup:
        get_tts(args)
    Handler.args = args
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[启动] IndexTTS 封装监听 http://{args.host}:{args.port}")
    print(f"[模型] {os.path.abspath(args.model_dir)}")
    print("       下一步把 voices.json 的 backend 指向它，")
    print('       并把 backend.type 设为 "index_tts"。')
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[退出]")


if __name__ == "__main__":
    main()
