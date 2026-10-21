# 梅梅 · 本地 AI Agent

梅梅是一套运行在 Windows 上的本地 AI 桌面助手。对话、工具调用、界面、
语音合成和语音识别都在本机完成，不依赖云端 AI API。

## 功能

- **自然对话**：本地 Ollama 模型、角色人设、长对话和上下文裁剪。
- **真正调用工具**：文件读写、命令执行、系统/显卡信息、看图与 OCR、提醒、习惯、日程表。
- **生成办公文件**：Word、Excel、PowerPoint 和基础视频处理。
- **操作电脑**：启动或切换应用、安卓设备、QQ 音乐点播和播放控制。
- **本地语音**：语音朗读、自动语气、本地语音输入；可配置平静、轻快和调侃三种语气。
- **桌面界面**：三栏 Agent 布局、小窗自适应、无边框窗口、背景图库和表情包回复。
- **隐私优先**：模型、聊天、日志和个人数据默认保存在本机。

## 快速开始

### 环境要求

- Windows 10/11 64 位
- Python 3.12
- [Ollama](https://ollama.com/)
- 可选：GPT-SoVITS（语音合成）、FunASR（语音识别）、FFmpeg

### 1. 获取代码

```powershell
git clone https://github.com/JuHa531/meimei-local-ai-agent.git
cd meimei-local-ai-agent
```

### 2. 准备模型

将 `ruanmei.Modelfile` 中的 `FROM` 改成本机的 GGUF 模型路径，然后：

```powershell
ollama create ruanmei -f .\ruanmei.Modelfile
ollama run ruanmei --think=false
```

没有自己的 GGUF 时，也可以先在 `app\agent_server.py` 启动命令中用
`--model` 指定任意已完成安装的 Ollama 模型。

### 3. 准备本地配置

```powershell
Copy-Item .\app\appearance.example.json .\app\appearance.json
Copy-Item .\voice\voices.example.json .\voice\voices.json
```

按自己的目录修改 `voice\voices.json` 中的参考音频路径。若暂时不使用语音，
可以关闭界面的自动朗读，文字聊天和工具功能仍可正常使用。

### 4. 启动

双击：

```text
启动阮梅.bat
```

或在终端运行：

```powershell
python .\app\desktop.py
```

也可以只启动 Web 服务：

```powershell
python .\app\agent_server.py --no-browser --workdir "$env:USERPROFILE\Documents\rm-workspace"
```

然后打开 <http://127.0.0.1:7788>。

## 使用方法

直接在输入框里说需求即可，例如：

- “帮我整理这个文件夹里的资料。”
- “看一下显卡温度和占用。”
- “把刚才的内容做成一个 PPT。”
- “播放周杰伦的晴天。”
- “暂停音乐，切到下一首。”
- “晚上十点提醒我休息。”
- “记住我一般用深色主题。”

输入框左侧的麦克风用于本地语音输入；“自动朗读”控制梅梅是否用语音回答。
播放语音时也可以点击回复下方的重播按钮。

## 常用配置

| 配置 | 作用 |
| --- | --- |
| `app\appearance.json` | 背景、图标、透明度和额外只读目录。 |
| `voice\voices.json` | TTS 后端、参考音频、语速、语气和音频后处理。 |
| `data\习惯.md` | 梅梅长期遵循的个人偏好。 |
| `data\提醒.json` | 定时提醒。 |
| `data\听歌记录.json` | 播放入口统计和音乐偏好。 |

这些运行时文件不会上传到仓库；示例文件和恢复说明见
[`docs/ASSETS_AND_PRIVACY.md`](docs/ASSETS_AND_PRIVACY.md)。

## 目录

| 目录 | 内容 |
| --- | --- |
| `app\` | 桌面应用、Agent 后端、Web UI、媒体控制和办公工具。 |
| `app\assets\` | 背景、图标、表情包及其元数据。 |
| `archive\` | 已停用但仍保留的历史启动方式。 |
| `data\` | 运行时数据目录与可公开的模板。 |
| `scripts\` | 素材导入、数据整理和界面自检工具。 |
| `docs\` | 文件说明和隐私/素材说明。 |
| `voice\` | TTS、ASR 及语音服务配置示例。 |

每个子目录都有自己的 `README.md`，进入目录即可看到其中每个文件的作用。
完整索引见 [`docs/FILE_MAP.md`](docs/FILE_MAP.md)。

### 根目录文件

| 文件 | 作用 |
| --- | --- |
| `.gitattributes` | Git 换行和二进制文件规则。 |
| `.gitignore` | 排除个人数据、缓存、日志、媒体和模型文件。 |
| `README.md` | 项目简介、功能和启动使用说明。 |
| `TASKS.md` | 项目开发与验证清单。 |
| `tasks.html` | 可在浏览器中查看的交互式清单。 |
| `CHARACTER.md` | 角色人设和训练资料说明。 |
| `VOICE.md` | 语音架构、音色配置和音频问题记录。 |
| `ruanmei.Modelfile` | Ollama 模型定义与人设参数。 |
| `启动阮梅.bat` | 一键启动桌面应用。 |
| `启动语音.ps1` | 启动 TTS 和语音识别服务。 |
| `修复麦克风权限.bat` | 修复 Windows 麦克风访问权限。 |
| `修复Tailscale.bat` | 修复 Tailscale 远程连接。 |

## 端口

| 端口 | 服务 |
| --- | --- |
| `7788` | 梅梅 Web/Agent 服务 |
| `9880` | GPT-SoVITS |
| `9881` | TTS 适配器 |
| `9882` | 本地语音识别 |
| `11434` | Ollama |

## 说明

仓库不包含模型权重、语音样本、大型背景视频、日志或个人运行数据。
QQ 音乐和部分桌面操作依赖本机应用及其界面能力；失败时梅梅会明确说明，
不会假装操作成功。

**本应用及数据库仅用于学习与参考，切勿用于商务用途，后果自负。**
