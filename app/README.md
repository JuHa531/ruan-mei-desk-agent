# `app` 目录

桌面应用和 Agent 后端的主体代码。每个文件的作用如下：

| 文件 | 作用 |
| --- | --- |
| `agent_server.py` | 主后端：对话 API、Ollama 工具调用、提醒、媒体控制、安全检查和静态文件服务。 |
| `agent.html` | 当前三栏桌面界面：会话、聊天、任务、语音、背景和表情。 |
| `desktop.py` | PyWebView2 桌面外壳：无边框窗口、服务启动、自检和缓存刷新。 |
| `office_tools.py` | 生成或处理 Word、Excel、PowerPoint 和视频文件。 |
| `server.py` | 早期简易聊天服务，保留用于兼容。 |
| `index.html` | 早期简易聊天页面。 |
| `smtc.ps1` | Windows 媒体会话桥接，用于读取和控制 QQ 音乐。 |
| `ocr_image.ps1` | 使用 Windows OCR 读取图片文字。 |
| `appearance.example.json` | 外观配置示例，不含个人目录和大型背景视频。 |

子目录 [`assets/`](assets/README.md) 保存界面图片、图标、表情和对应元数据。
