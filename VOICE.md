# 让它出声：本地语音输出

给已经跑起来的本地 AI 加上「用指定音色说话」的能力。全程不需要任何云端 API。

## 架构：发声是独立的一层

```
你 --文字--> Ollama(你的模型) --文字--> TTS(音色克隆) --音频--> 你
                        ^
                 （可选）STT 语音输入
```

关键点：**TTS 跟模型训练完全解耦**。你之前微调好的模型一个字都不用改，只要在它后面接一层语音合成就行。没训练过也没关系，现成的模型一样能接。

## 第一步：选一个 TTS

| 方案 | 音色克隆 | 中文 | 8GB 显存 | 上手难度 |
|---|---|---|---|---|
| **GPT-SoVITS** | 5 秒免训练克隆 / 5 分钟精调 | 强 | 可以（约 3GB） | 低，有 Windows 整合包 |
| CosyVoice2 | 3 秒克隆 | 强 | 可以 | 中 |
| IndexTTS2 | 支持情绪控制 | 强 | 可以 | 中 |
| F5-TTS | 参考音频克隆 | 中上 | 可以 | 低 |
| Kokoro | **不支持克隆**，只有预设音色 | 中 | 很轻松 | 极低 |

**推荐 GPT-SoVITS**：中文社区用得最多，克隆效果对你的素材量要求最低，而且官方提供 Windows 整合包——解压即用，避开了自己配 Python 环境那堆坑，对你这台机器最省事。仓库在 [RVC-Boss/GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS)，整合包下载链接在它的 README 里。

如果你只是想让 AI「有声音」，不挑音色，那 [Kokoro](https://github.com/hexgrad/kokoro) 更简单——体积小、速度快、不用准备任何素材。但它的音色是固定的，克隆不了。

表格里的第一栏看的是「音色克隆」，其实还有一项更该看：**能不能把音色和情绪分开控制**。GPT-SoVITS 没有情绪参数，只能靠换参考音频来换情绪；IndexTTS2 可以单独指定情绪，音色不受影响。这一项单独放在后面讲。

## 先解决一个硬冲突：8GB 显存不够两个人分

你只有 8GB 显存，而 LLM 和 TTS 都想往里挤：

| 组合 | 显存占用 | 结果 |
|---|---|---|
| qwen3:8b + GPT-SoVITS | 约 5.5 + 3GB | 超了，会爆 |
| **qwen3:4b + GPT-SoVITS** | 约 2.6 + 3GB | **舒服，推荐** |
| qwen3:8b + TTS 走 CPU | 约 5.5 + 0GB | 能跑，但合成慢 5~15 倍 |

三个可选做法，按推荐程度排：

1. **把对话模型换成 4B**。日常聊天和「像我一样说话」这个目标，4B 微调后的效果不比 8B 差多少，但省下 3GB 正好给 TTS。这是最省心的方案。
2. **TTS 用 CPU 模式**。GPT-SoVITS 整合包里可以切换设备。显存全留给模型，代价是一句话要等十几秒。
3. **让 Ollama 用完就卸载模型**：

```powershell
[Environment]::SetEnvironmentVariable("OLLAMA_KEEP_ALIVE", "10s", "User")
```

这样对话模型闲置 10 秒后让出显存，TTS 拿到 GPU。缺点是每轮对话模型要重新加载，会有几秒空档，属于能用但体验一般。

## 第二步：准备音色素材

有两条路，先走免训练那条，够用就不用往下走。

### 路线 A：免训练（5 秒素材，立刻见效）

这是 GPT-SoVITS 最实用的能力——**不需要训练，给一段参考音频就能用那个音色说话**。

素材要求，每一条都重要：

- **5~10 秒**，单人说话，没有第二个人插话
- **无背景音乐、无混响、无环境噪音**（带 BGM 的片段效果会明显变差）
- `wav` 或 `mp3`，16k~48kHz
- **情绪要和你想要的一致**——参考音频里的语气会被带过去。想要它温柔，就别用一段吼叫的素材
- **参考音频里说的那句话，必须逐字打进配置的 `prompt_text` 里**

最后一条是最容易出错的地方。`prompt_text` 写错会导致严重的串音、漏字、语调错乱。参考音频说什么，你就一字不差地抄下来，标点也要对上。

### 路线 B：精调（5~20 分钟素材，效果更进一步）

如果免训练的效果在长句上偶尔不稳，再用 GPT-SoVITS 的 WebUI 走这套流程：

```
1A 切分+标注  ->  1B 训练 SoVITS  ->  1C 训练 GPT  ->  1D 推理
```

准备 5~20 分钟同一人的干净语音。8GB 显存下，小数据集跑完 1B+1C 大概 20~60 分钟。训练完的模型权重可以在 API 里用 `/set_gpt_weights` 和 `/set_sovits_weights` 切换，不用重启服务。

### 角色语音：样本怎么挑

动画、游戏角色的素材几乎都带背景音乐和音效，这是和真人录音最大的区别。所以角色语音的关键不在「录」，而在**挑**和**洗**——这两步做对了，免训练的几秒素材就能出很好的效果。

#### 第一步：挑片段，优先级很明确

按这个顺序筛，前面的最重要：

1. **干净 > 情绪合适 > 长度**。一段带 BGM 的 10 秒，不如一段干净的 5 秒
2. **优先日常对白**，避开战斗喊叫、哭泣、尖叫。极端情绪的片段克隆出来，平时说话也会带着那个腔调，而且很难去掉
3. **语速要接近你期望的效果**。快语速角色的素材克隆出来还是快的，改不掉
4. **必须是单人片段**，混进别人半句话也会污染。多人同框的直接放弃
5. **尽量同一来源**。不同季、不同设备、动画和游戏语音的频响不一样，混用会让音色发飘

#### 第二步：洗素材（整合包自带工具，不用另外装）

GPT-SoVITS 整合包里已经带齐整套音频处理工具，都在 `tools/` 目录下：

| 工具 | 位置 | 干什么 |
|---|---|---|
| UVR5 | `tools/uvr5` | **人声分离**，把 BGM 和音效剥掉。角色语音这步几乎必做 |
| 降噪 | `tools/cmd-denoise.py` | 去掉底噪、电流声 |
| 自动切分 | `tools/slicer2.py` | 长音频自动切成短片段 |
| 自动标注 | `tools/asr` | 语音转文字，给精调做标注（必须人工校对） |
| 音质修复 | `tools/audio_sr.py`、`tools/AP_BWE_main` | 老动画、低码率游戏语音的频宽补偿 |

典型流程：剪出候选片段 → 过一遍 UVR5 分离人声 → 降噪 → 试听挑最好的几段 → 丢进 `G:\ai\voice\ref\`。

#### 第三步：确认合格

一段能用的角色素材，应该同时满足这几条：

- [ ] 3~10 秒，中间没有明显断点或截断
- [ ] 只有这一个角色的声音，没有背景音乐、音效、其他人
- [ ] 没有削波爆音，音量适中不刺耳
- [ ] 情绪平稳、语速正常，接近你想要的效果
- [ ] 你能一字不差地听懂并抄下它说的每个字

最后一条经常被忽略：**如果你自己都听不清它在说什么，就不要用这段**。因为你没法填对 `prompt_text`，而 `prompt_text` 错了会直接导致串音、漏字、语调错乱。

#### 不用一次选对：多准备几段，试出来再定

准备 3~5 个候选片段，各跑一次 `--say`，听哪段效果最好就用哪段。免训练克隆对素材的容忍度比想象中高，别为了找「完美素材」卡住不动。

素材可以从角色台词、语音包、角色歌里截。想要多个情绪版本，就把同一个角色的开心、生气片段各留一段，对应配置里的 `emotions` 段。

#### 关于合规

有件事必须说清楚：按《民法典》第 1023 条，自然人的声音参照肖像权保护。**自己在本地用是一回事，公开分发、商用、或者用别人的声音发内容冒充本人，性质就完全变了。** 声优和演员的声音被明确保护，别拿去生成声称是本人说的话。

如果不想碰这个问题，有两条替代方案：一是用 CosyVoice2 的「音色设计」能力，用文字描述生成一个全新音色；二是直接从 Kokoro 这类预设音色里挑一个。都不涉及克隆具体的人。

## 情绪控制：让同一个音色表达不同感情

先说一个关键区别：**音色和情绪是两件事**。音色决定「听起来像谁」，情绪决定「用什么语气说」。能不能分开控制，是选型时最该看的一项。

### 方式一：换参考音频（GPT-SoVITS，零成本）

GPT-SoVITS 没有情绪参数，但参考音频里的语气会被带过去。所以给同一个音色准备几段不同情绪的素材，就能切换情绪——相当于把情绪编码进素材里。

在 `voices.json` 里这样写：

```json
{
  "my-voice": {
    "ref_audio_path": "G:/ai/voice/ref/base.wav",
    "prompt_text": "默认素材里说的原话",
    "text_lang": "zh",
    "emotions": {
      "开心": {
        "ref_audio_path": "G:/ai/voice/ref/happy.wav",
        "prompt_text": "开心素材里说的原话"
      },
      "生气": {
        "ref_audio_path": "G:/ai/voice/ref/angry.wav",
        "prompt_text": "生气素材里说的原话"
      }
    }
  }
}
```

每个情绪的 `prompt_text` 都要单独填对，这里最容易出错。

代价是：每种情绪都得有一段同一人的素材，而且情绪之间不能连续过渡——要么生气要么开心，做不到「有点生气」。

### 方式二：情绪向量（IndexTTS2，真正的解耦）

IndexTTS2 把音色和情绪拆开了：音色来自 `spk_audio_prompt`，情绪单独给。八种情绪的顺序是官方定义的：

```
[happy, angry, sad, afraid, disgusted, melancholic, surprised, calm]
```

每个位置填 0~1 的强度。比如「七分难过加三分惊讶」就是 `[0, 0, 0.7, 0, 0, 0, 0.3, 0]`。

配置里可以预定义常用组合：

```json
{
  "emotions": {
    "温柔": { "emo_vector": [0.2, 0, 0, 0, 0, 0, 0, 0.8], "emo_alpha": 0.7 },
    "撒娇": { "emo_text": "我好想你呀，抱抱我嘛~", "emo_alpha": 0.8 }
  }
}
```

`emo_text` 是用一段文字描述情绪，让模型自己理解，不用手工调向量，推荐优先用它。注意 IndexTTS-2.5 用这个功能时，启动后端要加 `--qwen-emo`。

### 方式三：从正文自动判断情绪

打开 `use_emo_text` 后，模型会从你要读的正文里推断情绪。适合「读到感叹句就自动带感情」，但控制力最弱，适合不想调参的场景。

### 怎么调用

适配器支持三种写法，效果一样：

```powershell
python voice\tts_server.py --config voice\voices.json --say "你怎么才回来？" --say-emotion 生气
```

```json
{"input": "你怎么才回来？", "voice": "my-voice:生气"}
```

```json
{"input": "你怎么才回来？", "voice": "my-voice", "emotion": "angry", "emotion_strength": 0.7}
```

八个内置情绪名开箱即用，不写任何配置也能用：`happy`、`angry`、`sad`、`afraid`、`disgusted`、`melancholic`、`surprised`、`calm`。中文别名也认：开心、生气、难过、害怕、厌恶、忧郁、惊讶、平静。

在 Open WebUI 里，音色下拉框会直接列出 `my-voice:happy`、`my-voice:生气` 这些组合，选哪个就用哪个。

### 换成 IndexTTS2 要动什么

1. 按官方 README 装好 IndexTTS 环境（`uv sync`；Windows 上可以跳过 DeepSpeed）
2. 用 [voice/index_tts_backend.py](voice/index_tts_backend.py) 把它的 Python API 包成 HTTP 服务
3. 把 `voices.json` 的 backend 改成 `{"base_url": "http://127.0.0.1:9880", "type": "index_tts"}`

完整模板见 [voice/voices.example.index.json](voice/voices.example.index.json)。

**显存提醒**：IndexTTS2 比 GPT-SoVITS 重，8GB 够用但不宽裕，务必开 FP16 并关掉其他占显存的程序。如果用「文字描述情绪」，还会额外加载一部分权重，8GB 上再叠一个 4B 对话模型可能就顶不住了——这种情况把对话模型降到 1.7B，或者让 TTS 和 LLM 轮流使用显存。

## 第三步：把 TTS 接到你的 AI 上

GPT-SoVITS 自己的接口是 `/tts`，而 Open WebUI 这类客户端认的是 OpenAI 那套 `/v1/audio/speech`。所以仓库里带了一个零依赖的适配器负责翻译两边，不用装 FastAPI，也不用改 GPT-SoVITS 的源码：

[voice/tts_server.py](voice/tts_server.py)

### 3.1 启动 GPT-SoVITS 接口

用整合包的话，启动 `api_v2.py`（不是 WebUI），它默认监听 `9880` 端口。

### 3.2 配置音色

把 `voice/voices.example.json` 复制成 `voice/voices.json`，然后改内容：

```json
{
  "backend": { "base_url": "http://127.0.0.1:9880" },
  "default_voice": "my-voice",
  "voices": {
    "my-voice": {
      "ref_audio_path": "G:/ai/voice/ref/my-voice.wav",
      "prompt_text": "参考音频里一字不差的那句话",
      "prompt_lang": "zh",
      "text_lang": "zh",
      "speed": 1.0,
      "sample_steps": 32
    }
  }
}
```

可以放任意多个音色，`voice` 字段选哪个就用哪个。常用参数：`speed` 调语速，`temperature` 调音调起伏（调低更稳、调高更活泼），`sample_steps` 调质量（32 是默认，降到 16 更快）。

配置里的路径是给 **GPT-SoVITS 所在的机器**看的，两边不在同一台电脑时要写对端能访问的路径。

### 3.3 先自测，再连线

别急着配客户端，先用一条命令确认能出声：

```powershell
python voice\tts_server.py --config voice\voices.json --say "你好，我现在在本地运行。"
```

它会生成 `out.wav`。播放一下——如果音色不对，回去换参考音频或改 `prompt_text`；如果报连不上，说明 GPT-SoVITS 的接口没启动。**这一步跑通了，后面的问题基本都只是配置问题。**

### 3.4 启动适配器

```powershell
python voice\tts_server.py --config voice\voices.json
```

它监听 `9881`，提供 `/v1/models`、`/v1/audio/speech` 和 `/healthz`。

### 3.5 在 Open WebUI 里填

设置里的「音频」选 TTS 引擎 `OpenAI`，然后：

| 字段 | 填什么 |
|---|---|
| API Base URL | `http://127.0.0.1:9881/v1` |
| API Key | 随便填，本地服务不校验 |
| TTS Voice | `my-voice`（你配置里的音色名） |

设好之后，AI 的每条回复都会用你指定的音色读出来。

### 3.6 想要语音输入（可选）

Open WebUI 自带本地语音识别，用 faster-whisper，不需要联网。在同一个音频设置里打开 STT，选一个 `base` 或 `small` 模型即可。浏览器里按住说话，就变成完整的语音对话了。

### 3.7 现在实际用的：界面上的 🎙 说话

梅梅的输入框左边那颗「🎙 说话」不走 Open WebUI，走的是自己的识别服务：
`voice/asr_server.py`（端口 **9882**，funasr SenseVoiceSmall，同样离线）。
点一下开始录、再点一下结束，识别完自动发送，`启动语音.ps1` 会把它一起拉起来。

**它有个前置条件，在这台机器上当初是没过的那一关**：

```
NotAllowedError: Permission denied by system
```

这句话不是梅梅报的，是 Windows 报的 —— 系统的麦克风隐私开关关着
（实测 `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\
ConsentStore\microphone` = `Deny`）。**同样的错误在 Chrome / Edge 里直接测也会出现**
（`node scripts\check_mic.mjs` 就是干这个的），所以跟换不换浏览器、是不是独立窗口都无关。

打开方式任选一种：

* 设置 → 隐私和安全性 → 麦克风 → 「麦克风访问」「让应用访问你的麦克风」
  「让桌面应用访问你的麦克风」三个都打开；
* 或者以管理员身份运行 toolkit 目录里的 `修复麦克风权限.bat`（只改这一个开关）。

改完把梅梅窗口完全关掉再重新打开 —— 权限只在页面加载时申请一次。

## 延迟预期（说实话）

| 场景 | 耗时 |
|---|---|
| 第一次调用 | 10~30 秒（模型预热，正常现象） |
| 之后每句话 | 4 秒的音频约需 1~3 秒生成 |
| 对比真人对话 | 有明显停顿，但节奏能接受 |

想要更接近实时，可以把 `sample_steps` 降到 16，并尽量让回复短一些。GPT-SoVITS 也支持流式输出，但需要在适配器里额外处理，先跑通非流式版本再考虑优化。

## 常见问题

| 现象 | 原因 | 解决 |
|---|---|---|
| 报错连不上 `9880` | GPT-SoVITS 接口没启动 | 启动 `api_v2.py`，不是 WebUI |
| 音色不对 / 像另一个人 | 参考音频质量差或含多人 | 换一段干净的单人音频 |
| 明显串音、漏字、怪腔调 | `prompt_text` 和参考音频不一致 | 逐字核对，连标点一起改 |
| 生成很慢 | 跑在 CPU 上 | 检查 GPT-SoVITS 的设备设置，改回 GPU |
| 报 CUDA out of memory | 模型和 TTS 抢显存 | 换 4B 对话模型，见前面的显存表 |
| 中文读成英文 | `text_lang` 不对 | 改成 `zh`；中英混排用 `auto` |
| 语音听起来没感情 | 参考音频本身平淡 | 换一段有起伏的参考音频，或调高 `temperature` |

## 支持的语种

GPT-SoVITS 的 `text_lang` / `prompt_lang` 支持：`zh` 中文、`en` 英文、`ja` 日文、`ko` 韩文、`yue` 粤语，以及 `auto` 自动判断。中日英混排时用 `auto` 最省事。

## 2026-10-20 重训记录

这次用了两条 B 站素材：

| 素材 | 时长 | 处理 |
|---|---|---|
| 「阮梅全语音」`BV12a4y167PL` | 5:54 | 切片 + 本地 ASR，保留 39 条 |
| 「苏州博物馆·阮梅导览语音」`BV1c64y1n7tH` | 24:58 | 切片 + 本地 ASR，按时间均匀抽 12 分钟 |

新片段和老片段合并为 **341 条 / 25.9 分钟**，数据集在 `G:\ai\voice\dataset`，
切片和转写在 `G:\ai\voice\staging_20261020`（原始转写保留，方便复查）。

权重：

* SoVITS：`SoVITS_weights_v2/ruanmei_e10_s870.pth`
* GPT：`GPT_weights_v2/ruanmei-e10.ckpt`
* `启动语音.ps1` 里 `$UseFinetune = $true`；要回退零样本改成 `$false`

A/B 样本在 `G:\ai\voice\ab\zero.wav` / `finetuned.wav`。同一句两边 ASR 都完整；
零样本静音段约 **-180 dB**，新精调约 **-93 dB**，旧一轮精调是 -29~-35 dB。
新权重仍有一层很轻的底噪，但已经不是之前那种背景音乐/电流声；如果主观听着更闷，
把 `$UseFinetune` 改回 `$false` 即可，权重和旧权重都留着。

这轮踩到的三个坑：

1. `1-get-text.py` 只要看到 `2-name2text-0.txt` 存在就跳过；换数据集必须用
   `finetune_tts.py --step 1a --force`，否则会拿旧文本训练新音频。
2. 本机 GPT 训练的 DDP 会在第 5 轮崩（`0xC0000005`）；已改成单卡 `strategy="auto"`，
   并让 `bucket_sampler` 在未初始化进程组时按单卡处理。
3. Lightning 的完整 checkpoint 在本机会误报 `ENOSPC`；GPT 训练改为只存推理用的
   半精度 `.ckpt`，不再写完整 Lightning checkpoint。

## 2026-10-21 电音修正

GPT-SoVITS 的 `speed_factor` 会直接改变声码器上采样率，`0.80` 不是普通的波形变速，
因此容易把尾音和齿音拉出金属毛刺。平静语气也已从偏亮的 `ruanmei_v3.wav`
换回频谱更干净、更稳定的 `ruanmei_v2.wav`。现在 `voices.json` 使用 `speed_mode: "post"`：
模型按原生 `1.0` 速度合成，FFmpeg 的 `atempo` 再变慢，同时用低电平噪声门处理
换气段，再用 `deesser` 和 9 kHz 低通压掉高频毛刺。精调权重仍然是 `ruanmei-e10.ckpt` +
`ruanmei_e10_s870.pth`，没有退回零样本。后处理失败时会自动保留原始音频。
