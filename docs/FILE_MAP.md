# 文件索引

2026-11-01：桌宠动作仅保留待机／点心／双手端杯。`renderer/state.mjs` 与 `electron/host-policy.cjs` 同步移除 F4，旧倾听偏好回退待机；`key-cloud.mjs` 使用梅梅青蓝色板，`settings.css` 统一映射卡片与快捷键提示配色。`settings-window-check.cjs` 验证三动作入口、快捷键与实际计算样式；`key-cloud-preview.cjs` 输出三动作青蓝按键预览。

双手端杯：`renderer/grasp-binding.mjs` 的 `CUP_ART.base`／`SUPPORT_PALM.contact` 定义真实杯底和掌面；`daily-actions.mjs` 为端杯、抬杯和放杯提供双手目标，`puppet-art.mjs` 校准实际掌面接触并将头部跟随位移应用到两只手。`meimei-human-actions-check.cjs` 检查真实杯底接触和嘴部对应。

人物左手握叉素材：`desktop-pet/assets/character/ruanmei-fork-left-dorsal-v3.png` 为内置 imagegen 重绘的手背视角手型，同名 `.prompt.txt`、`.source.json` 记录提示词和来源；只供 `hand-fork` 使用。其余手型仍从 `ruanmei-hands-v2.png` 读取，`grasp-binding.mjs` 区分近侧食指／中指与握柄远侧细节。

握持透视：`desktop-pet/renderer/grasp-binding.mjs` 保存原画指缝、叉柄细杆、杯柄内环与拇指／食指前景轮廓；`puppet-art.mjs` 将其用于分层绘制与逆向拾取，`daily-actions.mjs` 用相同素材比例定义道具接触。`meimei-human-actions-check.cjs` 检查真实指缝透明度和露出细柄像素，避免仅测坐标对齐而漏掉错误握持。

2026-10-31：`desktop-pet/renderer/daily-actions.mjs` 定义交叠待机、上方落叉、分离小口、抬起／撤叉、单手握杯与放回；叉尖、杯柄、杯沿使用显式接触锚点，`puppet-art.mjs` 校准到真实素材坐标并限制前置指尖的接触范围。`scripts/meimei-human-actions-check.cjs` 验证实际 GPU 盘面遮挡、素材接触点以及转头时的嘴／耳对应。`app/agent_server.py` 等待 QQ 播放控件加载。`scripts/gptsovits_train_wrapper.py` 初始化首步学习率，`finetune_tts.py --s1-learning-rate` 可设置固定值；不修改上游推理源码。

桌宠延迟：`desktop-pet/renderer/faithful-character.mjs` 根据实际画布尺寸控制离屏分辨率；`motion-blur.mjs` 根据可见位移选择短曝光次数；`state.mjs` 使用真实时间并单独细分弹簧积分；`cursor-trail.cjs` 与 `cursor-trail-paint.mjs` 计入 IPC 时间。对照脚本 `meimei-performance-check.cjs`，说明 `docs/DESKTOP_PET_PERFORMANCE.md`。`app/window_focus.py` 由桌宠设置就绪事件触发父进程激活，并处理返回主窗口。

桌宠动作演出：`desktop-pet/renderer/action-motion.mjs` 定义伸手、拿入点心、变杯、进食、抿茶与收回时间线；`puppet-art.mjs` 绑定净身图、连续手臂、手掌与道具，负责承托掌在后、盘杯在中、抓握指尖在前的遮挡。`arm-skin.mjs` 将 `ruanmei-continuous-arms-v3.png` 蒙皮到三维 IK 的肩／肘／腕，肘部混合保持横向宽度，原身体不再残留另一套肩膀。GPU 渲染、逆向拾取和窗口包络使用相同形变。`pose-transition.mjs` 提供动作选择兼容入口；生产渲染不再切换整张姿态图。`motion-blur.mjs` 对完整动作采样，`hit-region.mjs` 结合缓存身体范围与手臂／道具的短期运动范围。`scripts/meimei-action-check.cjs --record` 检查 6 种切换和 48 个窗口覆盖样本；`meimei-shoulder-check.cjs` 检查肩部所有权、连续手肘及真实盘沿／手掌遮挡并输出近景。新素材提示词在 `assets/character/ruanmei-puppet-generation.md`。

桌宠骨骼：`desktop-pet/renderer/skeleton.mjs` 定义 28 个身体骨骼、父子层级、旋转矩阵、四项归一化权重及运动包络；`arm-kinematics.mjs` 单独求解定长上臂／前臂／手掌的三维关节再正交投影，保留肘部向外的弯曲方向，并限制手腕相对前臂最多 25 度，防止端盘或抬手反折。`head-tracking.mjs` 负责头颈角度，`body-regions.mjs`、`mesh-envelope.mjs` 和 `puppet-art.mjs` 同步点击与窗口范围。新增 `tests/arm-kinematics.test.mjs` 专门检查抬手／放下的连续性与关节朝向。

桌宠入口在梅梅顶栏「桌宠」。`app/pet_controller.py` 管理内置组件、私有命名管道及 Windows Job Object 退出清理；`app/desktop.py` 提供桌面 API，`app/agent.html` 提供开关与大小控制。说明见 `docs/DESKTOP_PET.md`、`desktop-pet/README.md`。`desktop-pet/electron/` 是透明窗口与原生交互；`desktop-pet/renderer/facial-rig.mjs`、`mesh-rig.mjs` 绑定同一立绘的虹膜／眼睑与身体；`motion-blur.mjs` 提供短曝光采样。`desktop-pet/assets/` 存阮梅美术和 54 条本机语音，`tests/` 为回归检查；`scripts/check_pet_mode.py` 检查实际组件生命周期。构建目录 `desktop-pet/release/win-unpacked` 由梅梅调用，不提供独立桌面启动入口。

D1 英文：`voice/english_client.py`（本机子进程、缓存、故障回退），`voice/english_worker.py`（逐句生成与角色音色重建），`voice/english.example.json`（可选配置模板），`scripts/test_english_route.py`（中文保持、英文分流和故障回退回归）。

| 文件 | 用途 |
| --- | --- |
| `.gitattributes` | Normalizes line endings and marks image files as binary. |
| `.gitignore` | Excludes local data, logs, browser profiles, large media, model weights, and generated audio. |
| `app/agent.html` | Main three-column desktop UI: chat, sessions, character tasks, backgrounds, stickers, speech playback, and responsive window layouts. |
| `app/agent_server.py` | Main backend: streaming chat API, Ollama function-calling loop, tools, RAG hooks, reminders, media control, safety checks, and desktop-service orchestration. |
| `app/appearance.example.json` | Safe example of the local appearance configuration; uses the included static background and icon. |
| `app/assets/bg-lib-01-thumb.jpg` | Thumbnail for background-library image 01. |
| `app/assets/bg-lib-01.jpg` | Background-library image 01. |
| `app/assets/bg-lib-02-thumb.jpg` | Thumbnail for background-library image 02. |
| `app/assets/bg-lib-02.jpg` | Background-library image 02. |
| `app/assets/bg-lib-03-thumb.jpg` | Thumbnail for background-library image 03. |
| `app/assets/bg-lib-03.jpg` | Background-library image 03. |
| `app/assets/bg-lib-04-thumb.jpg` | Thumbnail for background-library image 04. |
| `app/assets/bg-lib-04.jpg` | Background-library image 04. |
| `app/assets/bg-lib-05-thumb.jpg` | Thumbnail for background-library image 05. |
| `app/assets/bg-lib-05.jpg` | Background-library image 05. |
| `app/assets/bg-lib-06-thumb.jpg` | Thumbnail for background-library image 06. |
| `app/assets/bg-lib-06.jpg` | Background-library image 06. |
| `app/assets/bg-lib-07-thumb.jpg` | Thumbnail for background-library image 07. |
| `app/assets/bg-lib-07.jpg` | Background-library image 07. |
| `app/assets/bg-lib-08-thumb.jpg` | Thumbnail for background-library image 08. |
| `app/assets/bg-lib-08.jpg` | Background-library image 08. |
| `app/assets/bg-lib-09-thumb.jpg` | Thumbnail for background-library image 09. |
| `app/assets/bg-lib-09.jpg` | Background-library image 09. |
| `app/assets/bg-lib-10-thumb.jpg` | Thumbnail for background-library image 10. |
| `app/assets/bg-lib-10.jpg` | Background-library image 10. |
| `app/assets/bg-lib-11-thumb.jpg` | Thumbnail for background-library image 11. |
| `app/assets/bg-lib-11.jpg` | Background-library image 11. |
| `app/assets/bg-lib-12-thumb.jpg` | Thumbnail for background-library image 12. |
| `app/assets/bg-lib-12.jpg` | Background-library image 12. |
| `app/assets/bg-lib-13-thumb.jpg` | Thumbnail for background-library image 13. |
| `app/assets/bg-lib-13.jpg` | Background-library image 13. |
| `app/assets/bg-lib-14-thumb.jpg` | Thumbnail for background-library image 14. |
| `app/assets/bg-lib-14.jpg` | Background-library image 14. |
| `app/assets/bg-lib-15-thumb.jpg` | Thumbnail for background-library image 15. |
| `app/assets/bg-lib-15.jpg` | Background-library image 15. |
| `app/assets/bg-library.json` | Metadata for the background library and its thumbnails. |
| `app/assets/bg.jpg` | Default static application background. |
| `app/assets/icon-192.png` | Web/PWA icon at 192 pixels. |
| `app/assets/icon.ico` | Windows multi-size icon. |
| `app/assets/icon.png` | Primary application icon. |
| `app/assets/README.md` | Directory index for icons, backgrounds, thumbnails, stickers, and metadata. |
| `app/assets/sticker-01-thumb.jpg` | Thumbnail for sticker image 01. |
| `app/assets/sticker-01.jpg` | Sticker image 01. |
| `app/assets/sticker-02-thumb.jpg` | Thumbnail for sticker image 02. |
| `app/assets/sticker-02.jpg` | Sticker image 02. |
| `app/assets/sticker-03-thumb.jpg` | Thumbnail for sticker image 03. |
| `app/assets/sticker-03.jpg` | Sticker image 03. |
| `app/assets/sticker-04-thumb.jpg` | Thumbnail for sticker image 04. |
| `app/assets/sticker-04.jpg` | Sticker image 04. |
| `app/assets/sticker-05-thumb.jpg` | Thumbnail for sticker image 05. |
| `app/assets/sticker-05.jpg` | Sticker image 05. |
| `app/assets/sticker-rm-approve-thumb.jpg` | 表情素材或缩略图。 |
| `app/assets/sticker-rm-approve-v2-thumb.jpg` | 表情素材或缩略图。 |
| `app/assets/sticker-rm-approve-v2.png` | Unblushed approval revision, active id102. |
| `app/assets/sticker-rm-approve.png` | New restrained approval sticker. |
| `app/assets/sticker-rm-goodnight-thumb.jpg` | 表情素材或缩略图。 |
| `app/assets/sticker-rm-goodnight-v2-thumb.jpg` | 表情素材或缩略图。 |
| `app/assets/sticker-rm-goodnight-v2.png` | Unblushed goodnight revision, active id103. |
| `app/assets/sticker-rm-goodnight.png` | New goodnight sticker. |
| `app/assets/sticker-rm-leisure-v2-thumb.jpg` | 表情素材或缩略图。 |
| `app/assets/sticker-rm-leisure-v2.png` | Unblushed eating-cake alternative, active id104. |
| `app/assets/sticker-rm-listen-thumb.jpg` | 表情素材或缩略图。 |
| `app/assets/sticker-rm-listen-v2-thumb.jpg` | 表情素材或缩略图。 |
| `app/assets/sticker-rm-listen-v2.png` | Unblushed listening revision, active id101. |
| `app/assets/sticker-rm-listen.png` | New listening sticker, based on existing sticker-02/05 style references. |
| `app/assets/stickers.custom.json` | Generated sticker metadata merged into stickers.json during asset reimport. |
| `app/assets/stickers.json` | Maps sticker filenames to moods and scene keywords. |
| `app/assets/window.ico` | Dedicated window icon used by the desktop shell. |
| `app/assets/说明.txt` | Source and usage notes for the bundled visual assets. |
| `app/desktop.py` | PyWebView2 desktop shell, frameless window controls, service startup, health watching, and cache-busting. |
| `app/window_focus.py` | 从桌宠工作线程恢复和激活主窗口，完成后释放临时置顶。 |
| `app/index.html` | Legacy single-page chat interface used by `app/server.py`. |
| `app/local_security.py` | 本机请求与文件访问边界。 |
| `app/ocr_image.ps1` | Local Windows OCR helper used by the image-reading tool. |
| `app/office_tools.py` | Generates and edits Word, Excel, PowerPoint, and video artifacts for agent tool calls. |
| `app/README.md` | Directory index describing every file in `app/`. |
| `app/server.py` | Lightweight legacy browser chat server retained for compatibility and basic voice responses. |
| `app/smtc.ps1` | Windows System Media Transport Controls bridge for querying and controlling QQ Music without mouse input. |
| `archive/old-browser-launcher/open_ruanmei.vbs` | Legacy hidden browser-launcher entry point retained for reference. |
| `archive/old-browser-launcher/README.md` | Directory index for the two legacy launcher files. |
| `archive/old-browser-launcher/rm_app.ps1` | Legacy browser-mode launcher superseded by `app/desktop.py`. |
| `archive/README.md` | Directory index explaining the historical launcher archive. |
| `CHARACTER.md` | Character prompt and training-data workflow for the Ruan Mei persona. |
| `data/README.md` | Directory index explaining public templates and excluded runtime files. |
| `data/ruanmei_reaction_examples.jsonl` | Curated situation-to-response examples for character and tone training. |
| `data/template_character.json` | Example character record used by the character setup workflow. |
| `data/template_instruction.jsonl` | Minimal instruction-tuning sample in JSONL format. |
| `data/template_notes.md` | Empty note template for source material and style extraction. |
| `data/阮梅角色故事.md` | Four-part character backstory used for question-specific memory retrieval. |
| `docs/ASSETS_AND_PRIVACY.md` | Explains excluded personal data, large media, model files, and restoration steps. |
| `docs/CAPABILITIES.md` | Current capabilities, local verification, and known limits. |
| `docs/COST_OPTIMIZATION.md` | Documents measured token reductions and the new context-budget strategy. |
| `docs/DEPENDENCIES.md` | Functional component matrix, environment separation and reconstruction instructions. |
| `docs/FILE_MAP.md` | This complete inventory of uploaded files and their responsibilities. |
| `docs/README.md` | Directory index for publishing and maintenance documentation. |
| `docs/SECURITY_REVIEW.md` | 工具与服务的安全边界。 |
| `README.md` | Repository landing page: product features, required environment, configuration setup, launch methods, and usage examples. |
| `requirements-app.lock.txt` | 应用依赖锁文件。 |
| `requirements-app.txt` | 应用直接依赖。 |
| `ruanmei.Modelfile` | Ollama model definition, persona prompt, generation parameters, and local model configuration. |
| `scripts/add_source_titles.py` | Replaces source filenames with Bilibili video titles and BV IDs in training data. |
| `scripts/audio_to_pairs.py` | Converts character voice clips into text/audio training pairs using local ASR. |
| `scripts/build_dialogues.py` | Reconstructs subtitle streams into multi-turn dialogue training data. |
| `scripts/build_economy_training.py` | Builds a lower-token training set with a compact system prompt. |
| `scripts/build_training_sets.py` | Produces task-specific training subsets from the reviewed master dataset. |
| `scripts/build_tts_dataset.py` | Builds a GPT-SoVITS dataset from reviewed transcripts and source audio. |
| `scripts/check_appearance.mjs` | Verifies sidebar text, image/video background state, and active playback. |
| `scripts/check_backend_recover.mjs` | Verifies that video playback recovers after the backend restarts. |
| `scripts/check_bg_hold.mjs` | Exercises a real streaming reply while sampling background-video state. |
| `scripts/check_layout.mjs` | Measures desktop, compact, narrow, and tiny layout geometry. |
| `scripts/check_mic.mjs` | Distinguishes browser microphone restrictions from Windows privacy restrictions. |
| `scripts/check_text_watchdog.mjs` | Verifies that text still appears when TTS is stalled. |
| `scripts/check_video_recover.mjs` | Reproduces and verifies background-video recovery after backend failure. |
| `scripts/check_voice_cache.mjs` | Verifies TTS cache behavior and voice-selection persistence. |
| `scripts/check_wake.mjs` | Verifies wake-word handling and the resulting response behavior. |
| `scripts/clean_data.py` | Cleans OCR-derived text and normalizes known extraction errors. |
| `scripts/dedupe_train.py` | Deduplicates training samples and writes a review list. |
| `scripts/doctor.py` | Read-only service, dependency, executable, and voice-reference diagnostics. |
| `scripts/export_gguf.py` | Merges a LoRA adapter, exports GGUF, and creates an Ollama Modelfile. |
| `scripts/export_timeline.py` | Rebuilds a named timeline from the OCR cache. |
| `scripts/extract_ref_audio.py` | Extracts a short clean reference clip from downloaded video for voice cloning. |
| `scripts/finetune_tts.py` | Drives GPT-SoVITS preprocessing, SoVITS training, and GPT training from the CLI. |
| `scripts/import_asset_folders.py` | Imports user background and sticker folders, creates thumbnails, and writes asset metadata. |
| `scripts/import_voice_videos.py` | Splits downloaded Bilibili audio into voice clips and labels them with local ASR. |
| `scripts/merge_voice_dataset.py` | Merges newly imported voice clips into the main GPT-SoVITS dataset. |
| `scripts/mine_pairs.py` | Extracts training samples from source notes with local Ollama without rewriting content. |
| `scripts/ocr_databank.py` | Extracts text from game encyclopedia and data-bank video layouts. |
| `scripts/ocr_subtitles.py` | Extracts locally OCR'd hard subtitles from story videos. |
| `scripts/ocr_voicepack.py` | Extracts dialogue from game voice-pack recordings. |
| `scripts/prepare_data.py` | Prepares, validates, and reports on training datasets. |
| `scripts/README.md` | Directory index describing every utility script and regression test. |
| `scripts/replace_vocative.py` | Safely replaces direct-address terms while avoiding false matches inside names. |
| `scripts/set_branding.py` | Updates the desktop icon and background image. |
| `scripts/set_character.py` | Writes the character prompt into the model definition and training records. |
| `scripts/setup_env.ps1` | Creates local model/cache directories and configures environment variables. |
| `scripts/show_source.py` | Looks up training lines by video title for manual verification. |
| `scripts/smoke_office_tools.py` | Exercises every Office/video helper and verifies generated outputs. |
| `scripts/test_agent_office.py` | End-to-end tool-calling test for document generation. |
| `scripts/test_agent_regressions.py` | Routing, music records, Android selection, video input preservation, ASR cleanup, and TTS signal rejection/retry checks. |
| `scripts/test_music_voice_recovery.py` | Verifies QQ Music playback state after COM errors, prevents false success, and checks speech error and dependency health reporting. |
| `scripts/test_bilingual_role.py` | Checks bilingual pronunciation routing, unchanged Chinese voice settings, and factual, role-aware music replies. |
| `scripts/test_reply_expression.mjs` | Checks restrained tone selection, reply-based stickers, streaming tone selection, and replay timing. |
| `scripts/test_security.py` | 11 security regressions for HTTP, paths, confirmations, history, shortcuts and TTS input types. |
| `scripts/test_speech_queue.mjs` | Queue release, interruption isolation, and complete speech chunking for song recommendations. |
| `scripts/train_qlora.py` | QLoRA training script tuned for an 8 GB laptop GPU. |
| `tasks.html` | Standalone interactive version of the setup checklist. |
| `TASKS.md` | Ordered implementation checklist with validation steps and known prerequisites. |
| `voice/asr_server.py` | Local FunASR/SenseVoice HTTP service for speech recognition. |
| `voice/gptsovits_local_api.py` | GPT-SoVITS 本机安全入口。 |
| `voice/index_tts_backend.py` | HTTP wrapper that exposes IndexTTS2 to the TTS adapter. |
| `voice/README.md` | Directory index for TTS, ASR, adapter backends, and configuration examples. |
| `voice/tts_server.py` | OpenAI-compatible TTS adapter with role sentence splitting, native speed, emotion mapping, retries, and signal checks; historical external post-processing is optional and disabled in the current voice. |
| `voice/voices.example.index.json` | IndexTTS2 configuration template. |
| `voice/voices.example.json` | GPT-SoVITS configuration template with calm/warm/wry reference-audio examples. |
| `VOICE.md` | Offline TTS/ASR architecture, voice cloning, fine-tuning, and audio-quality notes. |
| `修复Tailscale.bat` | Enables or repairs Tailscale connectivity for remote access. |
| `修复麦克风权限.bat` | Enables Windows microphone access required by the in-app voice input. |
| `启动语音.ps1` | Starts GPT-SoVITS, the TTS adapter, and local ASR, then loads the selected weights. |
| `启动阮梅.bat` | Windows launcher for the complete desktop application and backend services. |
