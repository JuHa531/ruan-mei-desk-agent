# `voice` 目录

本地语音输入输出服务和配置示例。

| 文件 | 作用 |
| --- | --- |
| `tts_server.py` | OpenAI 兼容 TTS 适配器，负责语气、重试、语速后处理和音频修复。 |
| `asr_server.py` | 本地 FunASR/SenseVoice 语音识别 HTTP 服务。 |
| `index_tts_backend.py` | IndexTTS2 的 HTTP 封装。 |
| `voices.example.json` | GPT-SoVITS 配置模板，包含平静、轻快、调侃三种参考音。 |
| `voices.example.index.json` | IndexTTS2 配置模板。 |
| `README.md` | 本目录的用途和文件清单。 |

本机实际使用的 `voices.json` 含私人路径和所选模型，因此不会上传。
