# 文件索引

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
