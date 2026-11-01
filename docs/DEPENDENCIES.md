# 组件与配置

梅梅使用项目内置工具调用功能，没有依赖外部 skill 才能启用的插件加载器。

| 功能 | 组件 |
| --- | --- |
| 桌面 | pywebview、pythonnet、WebView2、psutil |
| 桌宠 | Electron 43.8.0；开发构建使用 Node.js 22+、electron-builder 26.15.3；打包后无需另装 Node.js |
| 对话 | Ollama、已安装的本地角色模型 |
| 文档 | python-docx、python-pptx、openpyxl |
| 图片 | Pillow、Windows OCR、PowerShell、本地视觉模型 |
| 音乐 | QQ 音乐、uiautomation、Windows SMTC |
| 视频 | FFmpeg、ffprobe |
| 语音输出 | GPT-SoVITS、参考音频、TTS 适配器、NLTK 英文词性资源 |
| 语音输入 | SenseVoiceSmall、FunASR、FFmpeg |
| 安卓 | ADB、已授权的手机或平板 |
| 设备网络 | 按需配置 Tailscale 与鉴权网关 |

使用 Python3.12 创建独立应用环境，再安装 `requirements-app.lock.txt`。
`requirements-app.txt` 是直接依赖，lock 是完整版本；语音和训练依赖应放在独立环境中。

配置：
- `app/appearance.example.json` 可复制为 `app/appearance.json`。
- `voice/voices.example.json` 可复制为 `voice/voices.json`，填写真实参考音频及转写。
- `启动语音.ps1` 中的解释器、GPT-SoVITS 和脚本路径需要按本机目录调整。
- FFmpeg、ADB 的路径及模型位置可按本机安装目录设置。
- `scripts/doctor.py` 使用 `RM_TTS_PYTHON`、`RM_GPTSOVITS_ROOT` 指定独立语音环境与项目目录。

聊天、习惯、提醒、听歌记录、浏览器资料和模型权重不随仓库发布。
语音模型环境的旧依赖需要按兼容性维护，不应把应用锁文件直接用于升级语音环境。

中英混合朗读需要 `averaged_perceptron_tagger_eng`，仅安装 NLTK Python 包不足以提供该数据。
在语音环境中运行 `python -m nltk.downloader -d <语音环境目录>/nltk_data averaged_perceptron_tagger_eng`。
本机 GPT-SoVITS 包装入口优先读取 `sys.prefix/nltk_data`；`/healthz` 检查资源能否找到。
启动脚本把语音底层日志保存在 `logs/gptsovits.*.log` 和 `logs/tts.*.log`，合成失败会保留底层错误说明。

D1 英文可选环境：`D:/ai/envs/meimei-english` 是原 tts Python 创建的 `--system-site-packages` venv，复用 Torch/CUDA；独立安装 `qwen-tts==0.1.1`、`transformers==4.57.3`、`accelerate==1.12.0`、`sox==1.5.0`，不更改原 tts 环境的版本。
模型为 Qwen/Qwen3-TTS-12Hz-0.6B-Base（revision `5d83992436eae1d760afd27aff78a71d676296fc`）及其 speech_tokenizer；另复用 v2ProPlus、CNHuBERT、原 warm 参考。无需新增监听端口或上传参考录音。
配置模板 `voice/english.example.json`；可选配置 `voice/english.local.json`。`doctor.py` 检查独立环境和权重是否齐全；`logs/english-worker.log` 记录故障与显存释放。12Hz 分支不使用导入时提示缺少的 SoX 可执行文件。
本机英文配置现使用 `D:/ai/models/Qwen3-TTS-12Hz-0.6B-Base` 的 NVMe 副本；33 个文件与原 `G:/ai/voice/models/Qwen3-TTS-12Hz-0.6B-Base` SHA256 一致，原文件未迁移或删除。两份模型约各占 2.39 GiB，校验记录见 `work/english-ssd-cache-20261031.json`。
