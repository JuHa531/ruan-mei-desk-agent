# 梅梅 · 本地 AI 助手

梅梅是运行在 Windows 上的角色型 AI Agent，使用本地模型完成对话、语音交流和日常工具调用。

## 功能

- **角色对话**：本地 Ollama 模型、人设、会话历史与上下文管理。
- **语音交流**：离线语音识别、角色音色朗读、语气与停顿控制、回复重播。
- **图片理解**：上传、粘贴或拖入图片，进行中文 OCR 和本地视觉描述。
- **音乐陪伴**：QQ 音乐点播与播放控制，记录听歌习惯并回顾偏好。
- **生活规划**：记录长期习惯和个人偏好，设置提醒，生成日常与学习计划。
- **电脑与设备**：文件读写和搜索、系统与显卡检查、应用启动与切换，以及经授权的安卓设备操作。
- **办公与视频**：生成 Word、Excel、PowerPoint；剪切、拼接、变速视频，提取音轨、生成动图。
- **桌面交互**：会话管理、背景图库、可收起侧栏、自适应布局，以及按回复内容搭配角色表情。

模型、个人记录和语音素材保存在本机；控制接口默认仅供本机使用，高影响操作需要明确授权。

## 运行

需要 Windows 10/11、Python 3.12 和 [Ollama](https://ollama.com/)。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-app.lock.txt
.\.venv\Scripts\python.exe app\desktop.py --no-voice
```

Ollama 需准备本地模型；角色配置见 `ruanmei.Modelfile`。语音使用独立的 GPT-SoVITS / SenseVoice 环境，
参考音频和模型路径需自行配置。可复制 `voice/voices.example.json` 为 `voice/voices.json` 后填写本机路径。
使用一键启动脚本时，请先调整其中的 Python、GPT-SoVITS、FFmpeg 等本机路径。

QQ 音乐需要安装并登录；安卓操作需要连接设备并授权 ADB。视频能力为基础媒体处理，
远程控制需另配鉴权网关。仓库不包含模型权重、私人聊天、习惯记录和音色原始素材。

[组件与配置](docs/DEPENDENCIES.md) · [功能范围](docs/CAPABILITIES.md) · [语音配置](VOICE.md) · [安全边界](docs/SECURITY_REVIEW.md)
