# 组件与配置

梅梅使用项目内置工具调用功能，没有依赖外部 skill 才能启用的插件加载器。

| 功能 | 组件 |
| --- | --- |
| 桌面 | pywebview、pythonnet、WebView2、psutil |
| 对话 | Ollama、已安装的本地角色模型 |
| 文档 | python-docx、python-pptx、openpyxl |
| 图片 | Pillow、Windows OCR、PowerShell、本地视觉模型 |
| 音乐 | QQ 音乐、uiautomation、Windows SMTC |
| 视频 | FFmpeg、ffprobe |
| 语音输出 | GPT-SoVITS、参考音频、TTS 适配器 |
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
