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

`english_worker.py` 提供 D1 英文合成与角色音色重建；`english_client.py` 负责按需启动、缓存和失败回退。
配置 `you_profile="u1"` 时，含独立单词 you 的句子使用用户选定的 U1 发音来源与原角色音色重建；其他句保留 D1。
将 `english.example.json` 复制为 `english.local.json`，填写本机环境与模型路径并启用；实际配置不会上传。
模型目录宜放在本机 SSD。本机已把同一 12Hz 模型的 33 个文件校验复制至 `D:/ai/models/Qwen3-TTS-12Hz-0.6B-Base`，原 G 盘副本保留。2026-10-31 同一句两句英文实测：外接盘首次请求含识别复核 165.5 秒，改用本机副本后首次合成 36.97 秒、含复核 37.86 秒；并非即时合成，也不能仅凭一次对照推断所有延迟都来自磁盘。worker 日志分开记录导入、模型加载、初始化及逐句耗时；D1／U1 的生成参数不变。
只接管匹配参考的独立英文 WAV 片段，中文中的短英文歌名仍由原模型处理。详见 VOICE.md。
