# `scripts` 目录

素材导入、数据整理、语音处理、模型工具和界面回归测试脚本。

## 数据与素材

| 文件 | 作用 |
| --- | --- |
| `add_source_titles.py` | 把训练数据的来源文件名替换成视频标题和 BV 号。 |
| `audio_to_pairs.py` | 把角色语音转成文本/音频训练对。 |
| `build_dialogues.py` | 把字幕整理成多轮对话数据。 |
| `build_training_sets.py` | 从主数据生成不同训练用途的子集。 |
| `build_tts_dataset.py` | 构建 GPT-SoVITS 语音数据集。 |
| `clean_data.py` | 清洗 OCR 文本和已知识别错误。 |
| `dedupe_train.py` | 训练数据去重并生成校对清单。 |
| `export_timeline.py` | 从 OCR 缓存重建完整时间线。 |
| `extract_ref_audio.py` | 从视频中切取音色参考片段。 |
| `import_asset_folders.py` | 导入背景图、表情包并生成缩略图和元数据。 |
| `mine_pairs.py` | 从原始笔记中抽取训练样本。 |
| `ocr_databank.py` | 从游戏百科/智库视频提取文字。 |
| `ocr_subtitles.py` | 从剧情视频硬字幕提取文字。 |
| `ocr_voicepack.py` | 从游戏语音界面录屏提取台词。 |
| `prepare_data.py` | 准备和检查训练数据。 |
| `replace_vocative.py` | 安全替换文本中的称呼。 |
| `show_source.py` | 按视频标题反查训练台词。 |

## 模型与语音

| 文件 | 作用 |
| --- | --- |
| `export_gguf.py` | 合并 LoRA、导出 GGUF 并生成 Ollama Modelfile。 |
| `finetune_tts.py` | 命令行驱动 GPT-SoVITS 精调流程。 |
| `merge_voice_dataset.py` | 合并新旧语音片段到主数据集。 |
| `import_voice_videos.py` | 切分语音视频并用本地 ASR 标注。 |
| `train_qlora.py` | 面向 8 GB 显存的 QLoRA 训练脚本。 |

## 配置与品牌

| 文件 | 作用 |
| --- | --- |
| `set_branding.py` | 更换图标和背景图。 |
| `set_character.py` | 写角色提示词并同步训练数据。 |
| `setup_env.ps1` | 创建缓存目录并设置本地环境变量。 |

## 功能自检

| 文件 | 作用 |
| --- | --- |
| `smoke_office_tools.py` | 逐个运行 Office/视频工具并检查输出。 |
| `test_agent_office.py` | 通过模型真实工具调用做端到端文件生成测试。 |

## 浏览器界面回归测试

| 文件 | 作用 |
| --- | --- |
| `check_appearance.mjs` | 检查外观、背景和侧栏状态。 |
| `check_backend_recover.mjs` | 检查后端重启后的页面恢复。 |
| `check_bg_hold.mjs` | 检查朗读期间背景视频暂停和恢复。 |
| `check_layout.mjs` | 检查桌面、小窗和窄屏布局尺寸。 |
| `check_mic.mjs` | 检查浏览器和 Windows 的麦克风权限。 |
| `check_text_watchdog.mjs` | 检查语音卡住时文字看门狗。 |
| `check_video_recover.mjs` | 检查视频在后端故障后的恢复。 |
| `check_voice_cache.mjs` | 检查语音缓存和音色设置持久化。 |
| `check_wake.mjs` | 检查唤醒词行为。 |

| `README.md` | 本目录的用途和文件清单。 |
