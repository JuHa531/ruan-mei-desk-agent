# 本地语音

梅梅使用 GPT-SoVITS 合成角色语音，使用 SenseVoiceSmall 识别语音输入。
桌面通过本地 TTS 适配器接入语气、停顿、音频检查和重试，支持自动朗读与重播。

## 服务

| 端口 | 服务 |
| --- | --- |
| 9880 | GPT-SoVITS API，经 `voice/gptsovits_local_api.py` 保护 |
| 9881 | `voice/tts_server.py`，兼容 `/v1/audio/speech` |
| 9882 | `voice/asr_server.py`，本地语音识别 |

应用和语音环境分开维护。GPT-SoVITS 按其官方要求安装模型、PyTorch 与 CUDA；
SenseVoice 所需模型由本机语音环境准备。启动参数和路径集中在 `启动语音.ps1`，应按本机目录填写。
安全包装器从 GPT-SoVITS 的项目目录运行，保留上游模型加载与推理实现。

## 音色与节奏

复制 `voice/voices.example.json` 为 `voice/voices.json`，设置参考音频及逐字一致的转写。
`calm`、`warm`、`wry` 可分别绑定不同参考，以形成平静、柔和和克制调侃的语气。
角色音色的参考音频、训练权重不在仓库中，需要自行准备。

- `speed_mode: native` 使用模型原生语速；`speed` 控制节奏。
- `role_sentences` 保留句意和引号，将短开头与相邻内容一起生成。
- `fragment_interval` 控制模型分段留白，前端按标点衔接播放并保留重播节奏。
- `pause_padding_seconds` 可在已有可靠停顿处补静音；`opening_pause_seconds` 用于称呼后的留白。
- `post_filter` 为空可关闭可选外部滤镜。插静音保持原有语音采样，不进行逐字机械切分。

适配器检查损坏、近乎静音、严重削波和明显截断的 WAV；异常会重试。
这些检查不能替代音色、发音、语气和自然度的试听。固定 seed 也不保证不同进程生成的音频完全一致。

训练工具为 `scripts/finetune_tts.py`，不同实验应使用独立名称并保留原权重。
可替代的 IndexTTS 后端由 `voice/index_tts_backend.py` 接入，不是默认语音的必需组件。
