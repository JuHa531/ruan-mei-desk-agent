# 本地 AI 任务清单

按顺序打勾即可。每项都标了 **必做** 还是 **可选**（可选的是锦上添花，不做也能用），
以及「完成标准」——做到什么程度算这一步过了，避免卡在半路自己不知道。

最短路径只有 5 项：`0.1 → 1.1 → 1.2 → 1.3 → 1.4`，做完你就有一个完全离线、
不依赖任何 API 的 AI 了。后面所有步骤都是为了让它更像你、能出声。

## 总览

| 阶段 | 目标 | 必做项 | 预计耗时 |
|---|---|---|---|
| 开始前 | 准备素材和账号 | — | 10 分钟 |
| 0 | 腾出 C 盘空间 | 3 项 | 5 分钟 |
| 1 | 本地推理跑起来 | 4 项 | 30~60 分钟 |
| 2 | 决定要不要训练 + 准备数据 | 3 项 | 半天~一周 |
| 3 | 微调模型 | 7 项 | 1~3 小时（含等待） |
| 4 | 导出并挂到 Ollama | 4 项 | 30 分钟 |
| 5 | 让它出声 | 7 项 | 1~2 小时 |
| 6 | 情绪控制 | 4 项 | 30 分钟~2 小时 |
| 7 | 让它干活（出文件 / 联动手机 / 语音对话） | 6 项 | 2~4 小时 |

**第一次做，建议在第 1 阶段结束后停下来用几天。** 很多需求用提示词或知识库就能解决，
可以省掉整个第 2~4 阶段。

---

## 开始前：先备齐这些东西

- [ ] **确认硬盘**：F 盘或 G 盘有 40GB 以上空闲。C 盘只剩 8.5GB，不够用
- [ ] **准备文件目录**：在 G 盘建好 `G:\ai\voice\ref\`，后面参考音频放这里
- [ ] **想清楚一个问题**：你希望这个 AI 具体帮你做什么？写下来，后面所有决策都靠它
- [ ] **准备原始素材**（第 2 阶段才用，可以先攒着）
  - 想让它"说话像我"：你自己的文字，目标几万字
  - 想让它"用某个音色"：5~10 秒干净人声片段

---

## 阶段 0：腾出 C 盘空间 ⏱ 5 分钟

- [ ] **0.1 跑环境变量脚本** — 必做

```powershell
cd C:\Users\qqqqq\Documents\Codex\2026-10-06\wo\outputs\local-ai-toolkit\scripts
powershell -ExecutionPolicy Bypass -File .\setup_env.ps1
```

完成标准：输出里看到 5 个环境变量指向 `G:\ai\...`，并打印 G 盘剩余空间。

- [ ] **0.2 重开窗口让变量生效** — 必做

关掉当前 PowerShell，重新开一个，然后验证：

```powershell
echo $env:HF_HOME
```

完成标准：输出 `G:\ai\hf-cache`。如果为空，说明 0.1 没跑成功或没重开窗口。

- [ ] **0.3 确认磁盘余量** — 必做

```powershell
Get-PSDrive C,D,F,G | Select-Object Name,@{n='Free_GB';e={[math]::Round($_.Free/1GB,1)}}
```

完成标准：G 盘剩余 200GB 以上（当前约 265GB）。

---

## 阶段 1：让本地 AI 跑起来 ⏱ 30~60 分钟

- [ ] **1.1 下载安装 Ollama** — 必做

从 https://ollama.com/download 下载 Windows 安装包，双击安装。

- [ ] **1.2 验证安装** — 必做

```powershell
ollama -v
```

完成标准：打印出版本号。如果提示找不到命令，重开一个 PowerShell 再试。

- [ ] **1.3 拉取并运行中文模型** — 必做

```powershell
ollama run qwen3:8b
```

第一次会下载约 5GB（下载到 G 盘）。进入对话界面后随便问一句，能正常回答就算成功。
输入 `/bye` 退出。

完成标准：模型能连贯回答中文问题。

- [ ] **1.4 断网验证** — 必做

把网络断开（拔网线或关 Wi-Fi），再问它一个问题。

完成标准：断网状态下仍能正常回答。**做到这一步，不依赖 API 的本地 AI 就已经成立了。**

- [ ] **1.5 装网页界面** — 可选，但强烈建议

```powershell
pip install open-webui
open-webui serve
```

浏览器打开 http://localhost:8080。它自带知识库和语音输入，后面第 5 阶段接语音也靠它。

- [ ] **1.6 记录"它哪里不懂我"** — 必做

正常用几天，把答得不对、不像你的场景记在一个文件里。这份清单决定第 2 阶段走哪条路。

---

## 阶段 2：决定要不要训练，并准备数据 ⏱ 半天~一周

- [ ] **2.1 按清单分流** — 必做

拿着 1.6 的记录对照下表，决定后面做什么：

| 你记录的抱怨 | 解决方案 | 要不要训练 |
|---|---|---|
| 它不知道我的资料 | 文档丢进 Open WebUI 知识库 | 不用 |
| 它记不住我的个人信息 | 写进 Modelfile 的 SYSTEM | 不用 |
| 它说话不像我 | 续写式微调 | 要 |
| 它不按我的格式干活 | 指令式微调 | 要 |

如果结论是"不用训练"，直接跳到阶段 5。这不是失败，这是省了好几天。

- [ ] **2.2 准备训练数据** — 必做（前提是决定训练）

路线 A，用你写过的文字，不需要标注：

```powershell
python scripts\prepare_data.py completion --src 你的笔记.md --out G:\ai\data\style.jsonl
```

路线 B，照 `data\template_instruction.jsonl` 的格式自己写问答对（每行一个 JSON，
`instruction` 写情境、`output` 写你会怎么回答），写到 200 条左右再进入 2.3。

完成标准：`G:\ai\data\` 下有一个 jsonl 文件。

- [ ] **2.3 数据体检** — 必做

```powershell
python scripts\prepare_data.py check --src G:\ai\data\train.jsonl
```

完成标准：脚本给出的建议是"可以认真跑一轮"。如果提示少于 100 条，先补充数据，
不要急着训练——这是最容易被浪费掉的一个下午。

---

## 阶段 3：微调 ⏱ 1~3 小时（大部分在等）

- [x] **3.1 建独立环境** — 已完成 2026-10-08

环境已经装好并验证通过，位于 `D:\ai\envs\llm`。要重建的话：

```powershell
conda create -p D:\ai\envs\llm python=3.12 -y
conda activate D:\ai\envs\llm
```

**三个必须注意的点，都是实际踩过的：**

- 不要用系统里的 Python 3.13，PyTorch 生态跟不上
- **环境放 D 盘，不要放 G 盘**。G 盘是 USB 机械硬盘，实测写入只有 84 MB/s，装环境会慢好几倍，而且训练中途被拔掉会损坏环境
- **`HF_ENDPOINT` 必须设为 `https://hf-mirror.com`**，否则 `huggingface.co` 连不上（实测 15 秒超时），模型根本下不下来

- [x] **3.2 装 CUDA 版 PyTorch** — 已完成

```powershell
pip install torch==2.14.1+cu130 torchvision==0.29.1+cu130 --index-url https://download.pytorch.org/whl/cu130
```

- [x] **3.3 装 Unsloth** — 已完成

```powershell
pip install numpy unsloth -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**这里有个大坑**：用国内镜像装 unsloth 时，pip 会把 CUDA 版的 torch 换成 PyPI 上的
CPU 版（`2.14.1+cpu`），`torch.cuda.is_available()` 直接变成 `False`，训练完全跑不了。
装完**必须**做 3.4 自检，发现被换了就重跑 3.2。

- [x] **3.4 环境自检** — 已完成

```powershell
D:\ai\envs\llm\python.exe -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

期望输出：`2.14.1+cu130 True NVIDIA GeForce RTX 4060 Laptop GPU`

只看到 `True` 还不够，QLoRA 真正依赖的是 4bit 量化，用这条命令验证它能在 GPU 上真跑：

```powershell
D:\ai\envs\llm\python.exe -c "import torch, bitsandbytes as bnb; m=bnb.nn.Linear4bit(128,128,bias=False,quant_type='nf4',compute_dtype=torch.float16).cuda(); print('4bit OK', m(torch.randn(4,128,device='cuda',dtype=torch.float16)).shape)"
```

期望输出：`4bit OK torch.Size([4, 128])`

**实测结果（2026-10-08）**：torch 2.14.1+cu130 / 编译时 CUDA 13.0 / sm_89 / 8.0GB 显存 /
bitsandbytes 0.50.2 四比特前向成功 / unsloth 2026.10.2 / xformers 0.0.35 / triton 3.8.0 /
模型经 hf-mirror 下载成功。环境可用。

- [ ] **3.5 先用小模型跑通全流程** — 必做

```powershell
D:\ai\envs\llm\python.exe scripts\train_qlora.py --data G:\ai\data\train.jsonl --out G:\ai\out\dryrun --model unsloth/Qwen3-1.7B-unsloth-bnb-4bit
```

完成标准：跑完并生成 `G:\ai\out\dryrun\adapter\`。这一步只是为了确认流程没坑，
效果好不好先不管，约 20 分钟。

- [ ] **3.6 换 4B 正式训练** — 必做

```powershell
D:\ai\envs\llm\python.exe scripts\train_qlora.py --data G:\ai\data\train.jsonl --out G:\ai\out\run1
```

完成标准：`G:\ai\out\run1\adapter\` 里出现模型文件。

- [ ] **3.7 盯住两个数字** — 必做

训练过程中看屏幕输出：

- `loss` 稳步下降，通常落到 1.0 以下说明学到东西了
- 验证集 `eval_loss` 如果开始回升，说明过拟合，减少轮数或补数据

报 `CUDA out of memory` 是 8GB 显卡的常态，按顺序降：`--max-seq-length 1024` →
`--lora-r 8`，并关掉浏览器和其他占显存的程序。

---

## 阶段 4：变成你专属的 Ollama 模型 ⏱ 30 分钟

- [ ] **4.1 导出 GGUF** — 必做

```powershell
python scripts\export_gguf.py --adapter G:\ai\out\run1\adapter --out G:\ai\out\run1\gguf
```

完成标准：`gguf` 目录里出现 `.gguf` 文件和 `Modelfile`。

- [ ] **4.2 导入 Ollama** — 必做

```powershell
ollama create my-ai -f G:\ai\out\run1\gguf\Modelfile
ollama run my-ai
```

完成标准：能用 `my-ai` 这个名字对话。

- [ ] **4.3 准备对照测试** — 必做

写 15~20 个你真正关心的问题，外加 **5 个和训练完全无关的普通问题**（比如
"解释一下什么是光合作用"）。同一份问题分别问微调前和微调后的模型。

完成标准：能明确说出"哪几个变好了、哪几个变差了"。

- [ ] **4.4 判断有没有变笨** — 必做

如果那 5 个无关问题明显退步，就是灾难性遗忘，说明数据太窄。往回掺几百条通用问答
数据，重跑一次 3.6。

---

## 阶段 5：让它出声 ⏱ 1~2 小时

- [ ] **5.0 先解决显存冲突** — 必做

8GB 装不下 8B 模型 + 语音模型。把对话模型换成 4B：

```powershell
ollama pull qwen3:4b
```

- [ ] **5.1 下载 GPT-SoVITS 整合包** — 必做

从 https://github.com/RVC-Boss/GPT-SoVITS 的 README 里找 Windows 整合包下载链接，
解压到一个空间充足的盘。

- [ ] **5.2 准备参考音频** — 必做

放到 `G:\ai\voice\ref\`。要求：5~10 秒、单人、无背景音乐、无混响。
**并把这 5~10 秒里说的那句话逐字抄下来**，一会儿要填进配置，抄错会串音。

如果你用的是动画、游戏角色的素材，几乎都带 BGM 和音效，需要先过一遍整合包自带的
UVR5（`tools/uvr5`）做人声分离，再降噪。挑片段的优先级和完整工具清单见
[VOICE.md](VOICE.md) 的「角色语音：样本怎么挑」一节。

- [ ] **5.3 启动 GPT-SoVITS 接口** — 必做

启动整合包里的 `api_v2.py`（注意不是 WebUI），默认监听 9880 端口。

完成标准：浏览器打开 `http://127.0.0.1:9880/docs` 能看到接口文档。

- [ ] **5.4 配置音色** — 必做

把 `voice\voices.example.json` 复制成 `voice\voices.json`，填入参考音频路径和那句话。

- [ ] **5.5 单独验证能出声** — 必做

```powershell
python voice\tts_server.py --config voice\voices.json --say "你好，我现在在本地运行。"
```

完成标准：生成 `out.wav`，播放出来是你要的音色。
音色不对就换参考音频，读错字就核对 `prompt_text`。**这一步过了再往下走。**

- [ ] **5.6 启动语音适配器** — 必做

```powershell
python voice\tts_server.py --config voice\voices.json
```

- [ ] **5.7 在 Open WebUI 里接通** — 必做

设置 → 音频 → TTS 引擎选 `OpenAI`：

| 字段 | 填什么 |
|---|---|
| API Base URL | `http://127.0.0.1:9881/v1` |
| API Key | 随便填 |
| TTS Voice | 你配置里的音色名 |

完成标准：AI 的每条回复都用你的音色读出来。

---

## 阶段 6：情绪控制 ⏱ 30 分钟~2 小时

- [ ] **6.1 先试零成本方案** — 必做

给同一个音色准备几段不同情绪的参考音频，在 `voices.json` 里加 `emotions` 段，
然后用 `音色:情绪` 调用：

```powershell
python voice\tts_server.py --config voice\voices.json --say "你怎么才回来？" --say-emotion 生气
```

完成标准：同一音色能读出不同情绪。

- [ ] **6.2 判断够不够用** — 必做

如果"要么生气要么平静、没法有点生气"这件事让你不满意，再往下走。否则到此为止。

- [ ] **6.3 装 IndexTTS2** — 可选

按官方 README 部署，然后用封装脚本把它变成 HTTP 服务：

```powershell
uv run python voice\index_tts_backend.py --model-dir ./checkpoints --warmup
```

- [ ] **6.4 切换后端** — 可选

把 `voices.json` 的 backend 改成 `{"base_url": "http://127.0.0.1:9880", "type": "index_tts"}`，
参考 `voice\voices.example.index.json`。之后八种内置情绪（happy/angry/sad/afraid/
disgusted/melancholic/surprised/calm）和中文别名都能直接用，还能用 `emotion_strength`
调浓度。

注意显存：IndexTTS2 更重，建议把对话模型降到 `qwen3:1.7b`。

---

## 阶段 7：让它真的干活 ⏱ 2~4 小时

到这一步 AI 已经能聊天、能出声、能看文件了，但还不会**产出成品**。这一阶段就是把
"写个 PPT""把这几段视频拼一下"变成一句话就能做的事。**大部分已经做完了**，剩下的
是等你手上设备到位才能继续的部分。

- [x] **7.1 文档类工具**（必做，30 分钟，✅ 10-11 完成）
  `make_pptx` / `make_docx` / `make_xlsx` 三个工具，一句话直接生成文件。
  完成标准：说"做个 PPT，文件名 xxx.pptx"能真的在工作目录得到一个能打开的 .pptx
- [x] **7.2 视频剪辑工具**（必做，30 分钟，✅ 10-11 完成）
  走 ffmpeg 本机离线处理：剪一段 / 拼接 / 抽音频 / 转 gif / 变速 / 静音 / 改分辨率。
  完成标准："把 A 的前 15 秒剪出来存成 B.mp4"能出文件，时长对得上
- [x] **7.3 媒体生产库**（必做，10 分钟，✅ 已装）
  python-pptx / python-docx / openpyxl / moviepy / matplotlib / reportlab
- [x] **7.4 语音输入**（必做，30 分钟，✅ 已完成）
  输入框左边「🎙 说话」，离线识别（SenseVoiceSmall），识别完自动发送
- [x] **7.5 手机与外部访问**（必做，1 小时，✅ 电脑侧完成）
  Tailscale 内网 + HTTPS 反代，手机浏览器用 `https://node.tail2e67c6.ts.net/` 打开，
  界面会自动切成手机模式（侧栏收成 ☰ 抽屉）。**剩下的是你在手机上装 APK 并登录**
- [ ] **7.6 智能家居联动**（可选，暂缓）
  你现在手上没有这类设备，等以后租房/买房买设备时再定。买之前记住一句话：
  **优先选支持本地协议（MQTT / Home Assistant / 米家局域网）的，别选只能连云端的**，
  否则梅梅碰不到它。到时候告诉我品牌和型号，我按那套生态接
- [x] **7.7 独立桌面窗口**（必做，1 小时，✅ 10-11 完成）
  用系统自带的 WebView2 内核跑 `app/desktop.py`：不用浏览器、没有地址栏、
  自己的标题和图标，实测占 97MB。**桌面「梅梅」快捷方式 10-12 起已经换成它**，
  旧的浏览器启动方式挪到了 `archive\old-browser-launcher\`（想退回就挪回来）
- [ ] **7.8 打开 Windows 麦克风开关**（必做，1 分钟，⚠️ 只能你来做）
  现在 HKLM 的麦克风隐私开关是 Deny，所以点 🎙 会报 `Permission denied by system`。
  设置 → 隐私和安全性 → 麦克风，三个开关都打开；或者以管理员身份运行
  toolkit 目录里的 `修复麦克风权限.bat`。改完把梅梅窗口完全关掉再开

**这一阶段的边界**：梅梅只写工作目录（默认 `C:\Users\qqqqq\Documents\rm-workspace`），
越界会被拒绝。要处理别的盘的文件，先在界面的「外观 → 额外只读目录」里把它加上（只读）。

---

## 每阶段之间该停下来检查什么

| 做完 | 检查 | 不通过怎么办 |
|---|---|---|
| 阶段 1 | 断网能对话 | 检查 Ollama 是否在运行 |
| 阶段 2 | 体检结论是"可以跑" | 补数据，别硬训 |
| 阶段 3 | `adapter` 目录有文件 | 看报错，多数是显存或 CUDA 版本 |
| 阶段 4 | 微调前后对照有明确结论 | 数据太窄就掺通用数据重训 |
| 阶段 5 | `out.wav` 音色正确 | 换参考音频、核对 `prompt_text` |
| 阶段 6 | 同一音色能读出不同情绪 | 退回 6.1 的换素材方案 |
| 阶段 7 | 一句话能出 pptx/docx/xlsx，剪视频有时长正确的成品 | 跑 `scripts\smoke_office_tools.py` 看哪项挂 |

## 时间不够时的优先级

如果只有一天时间，按这个顺序做，做完一个是一个：

1. 阶段 0 + 阶段 1（必须做，1 小时）
2. 阶段 5 的 5.1~5.5（让 AI 出声，1 小时）
3. 阶段 2 + 3 + 4（训练自己的模型，半天）
4. 阶段 6（情绪，最后再说）

**第 1 步做完就已经交付了 80% 的价值。** 后面每一步的边际收益都在递减，
所以任何一个阶段卡住了，都可以停下来先用着，不必一次做完。
