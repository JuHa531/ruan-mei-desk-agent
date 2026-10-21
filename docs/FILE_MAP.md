# File map

This inventory describes every file uploaded to the repository. Files excluded
from the source distribution are listed in
[`ASSETS_AND_PRIVACY.md`](ASSETS_AND_PRIVACY.md).

## Repository root

| File | Purpose |
| --- | --- |
| `.gitattributes` | Normalizes line endings and marks image files as binary. |
| `.gitignore` | Excludes local data, logs, browser profiles, large media, model weights, and generated audio. |
| `README.md` | Main project manual: environment setup, local model workflow, desktop app, tools, troubleshooting, and design history. |
| `TASKS.md` | Ordered implementation checklist with validation steps and known prerequisites. |
| `tasks.html` | Standalone interactive version of the setup checklist. |
| `CHARACTER.md` | Character prompt and training-data workflow for the Ruan Mei persona. |
| `VOICE.md` | Offline TTS/ASR architecture, voice cloning, fine-tuning, and audio-quality notes. |
| `ruanmei.Modelfile` | Ollama model definition, persona prompt, generation parameters, and local model configuration. |
| `启动阮梅.bat` | Windows launcher for the complete desktop application and backend services. |
| `启动语音.ps1` | Starts GPT-SoVITS, the TTS adapter, and local ASR, then loads the selected weights. |
| `修复麦克风权限.bat` | Enables Windows microphone access required by the in-app voice input. |
| `修复Tailscale.bat` | Enables or repairs Tailscale connectivity for remote access. |

## Application

| File | Purpose |
| --- | --- |
| `app/agent_server.py` | Main backend: streaming chat API, Ollama function-calling loop, tools, RAG hooks, reminders, media control, safety checks, and desktop-service orchestration. |
| `app/agent.html` | Main three-column desktop UI: chat, sessions, character tasks, backgrounds, stickers, speech playback, and responsive window layouts. |
| `app/desktop.py` | PyWebView2 desktop shell, frameless window controls, service startup, health watching, and cache-busting. |
| `app/office_tools.py` | Generates and edits Word, Excel, PowerPoint, and video artifacts for agent tool calls. |
| `app/server.py` | Lightweight legacy browser chat server retained for compatibility and basic voice responses. |
| `app/index.html` | Legacy single-page chat interface used by `app/server.py`. |
| `app/smtc.ps1` | Windows System Media Transport Controls bridge for querying and controlling QQ Music without mouse input. |
| `app/ocr_image.ps1` | Local Windows OCR helper used by the image-reading tool. |
| `app/appearance.example.json` | Safe example of the local appearance configuration; uses the included static background and icon. |

## UI assets

| File | Purpose |
| --- | --- |
| `app/assets/bg.jpg` | Default static application background. |
| `app/assets/bg-library.json` | Metadata for the background library and its thumbnails. |
| `app/assets/说明.txt` | Source and usage notes for the bundled visual assets. |
| `app/assets/icon.png` | Primary application icon. |
| `app/assets/icon-192.png` | Web/PWA icon at 192 pixels. |
| `app/assets/icon.ico` | Windows multi-size icon. |
| `app/assets/window.ico` | Dedicated window icon used by the desktop shell. |
| `app/assets/bg-lib-01.jpg` | Background-library image 01. |
| `app/assets/bg-lib-01-thumb.jpg` | Thumbnail for background-library image 01. |
| `app/assets/bg-lib-02.jpg` | Background-library image 02. |
| `app/assets/bg-lib-02-thumb.jpg` | Thumbnail for background-library image 02. |
| `app/assets/bg-lib-03.jpg` | Background-library image 03. |
| `app/assets/bg-lib-03-thumb.jpg` | Thumbnail for background-library image 03. |
| `app/assets/bg-lib-04.jpg` | Background-library image 04. |
| `app/assets/bg-lib-04-thumb.jpg` | Thumbnail for background-library image 04. |
| `app/assets/bg-lib-05.jpg` | Background-library image 05. |
| `app/assets/bg-lib-05-thumb.jpg` | Thumbnail for background-library image 05. |
| `app/assets/bg-lib-06.jpg` | Background-library image 06. |
| `app/assets/bg-lib-06-thumb.jpg` | Thumbnail for background-library image 06. |
| `app/assets/bg-lib-07.jpg` | Background-library image 07. |
| `app/assets/bg-lib-07-thumb.jpg` | Thumbnail for background-library image 07. |
| `app/assets/bg-lib-08.jpg` | Background-library image 08. |
| `app/assets/bg-lib-08-thumb.jpg` | Thumbnail for background-library image 08. |
| `app/assets/bg-lib-09.jpg` | Background-library image 09. |
| `app/assets/bg-lib-09-thumb.jpg` | Thumbnail for background-library image 09. |
| `app/assets/bg-lib-10.jpg` | Background-library image 10. |
| `app/assets/bg-lib-10-thumb.jpg` | Thumbnail for background-library image 10. |
| `app/assets/bg-lib-11.jpg` | Background-library image 11. |
| `app/assets/bg-lib-11-thumb.jpg` | Thumbnail for background-library image 11. |
| `app/assets/bg-lib-12.jpg` | Background-library image 12. |
| `app/assets/bg-lib-12-thumb.jpg` | Thumbnail for background-library image 12. |
| `app/assets/bg-lib-13.jpg` | Background-library image 13. |
| `app/assets/bg-lib-13-thumb.jpg` | Thumbnail for background-library image 13. |
| `app/assets/bg-lib-14.jpg` | Background-library image 14. |
| `app/assets/bg-lib-14-thumb.jpg` | Thumbnail for background-library image 14. |
| `app/assets/bg-lib-15.jpg` | Background-library image 15. |
| `app/assets/bg-lib-15-thumb.jpg` | Thumbnail for background-library image 15. |
| `app/assets/stickers.json` | Maps sticker filenames to moods and scene keywords. |
| `app/assets/sticker-01.jpg` | Sticker image 01. |
| `app/assets/sticker-01-thumb.jpg` | Thumbnail for sticker image 01. |
| `app/assets/sticker-02.jpg` | Sticker image 02. |
| `app/assets/sticker-02-thumb.jpg` | Thumbnail for sticker image 02. |
| `app/assets/sticker-03.jpg` | Sticker image 03. |
| `app/assets/sticker-03-thumb.jpg` | Thumbnail for sticker image 03. |
| `app/assets/sticker-04.jpg` | Sticker image 04. |
| `app/assets/sticker-04-thumb.jpg` | Thumbnail for sticker image 04. |
| `app/assets/sticker-05.jpg` | Sticker image 05. |
| `app/assets/sticker-05-thumb.jpg` | Thumbnail for sticker image 05. |

## Data templates

| File | Purpose |
| --- | --- |
| `data/template_character.json` | Example character record used by the character setup workflow. |
| `data/template_instruction.jsonl` | Minimal instruction-tuning sample in JSONL format. |
| `data/template_notes.md` | Empty note template for source material and style extraction. |

## Data and voice pipeline scripts

| File | Purpose |
| --- | --- |
| `scripts/add_source_titles.py` | Replaces source filenames with Bilibili video titles and BV IDs in training data. |
| `scripts/audio_to_pairs.py` | Converts character voice clips into text/audio training pairs using local ASR. |
| `scripts/build_dialogues.py` | Reconstructs subtitle streams into multi-turn dialogue training data. |
| `scripts/build_training_sets.py` | Produces task-specific training subsets from the reviewed master dataset. |
| `scripts/build_tts_dataset.py` | Builds a GPT-SoVITS dataset from reviewed transcripts and source audio. |
| `scripts/clean_data.py` | Cleans OCR-derived text and normalizes known extraction errors. |
| `scripts/dedupe_train.py` | Deduplicates training samples and writes a review list. |
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
| `scripts/replace_vocative.py` | Safely replaces direct-address terms while avoiding false matches inside names. |
| `scripts/set_branding.py` | Updates the desktop icon and background image. |
| `scripts/set_character.py` | Writes the character prompt into the model definition and training records. |
| `scripts/setup_env.ps1` | Creates local model/cache directories and configures environment variables. |
| `scripts/show_source.py` | Looks up training lines by video title for manual verification. |
| `scripts/smoke_office_tools.py` | Exercises every Office/video helper and verifies generated outputs. |
| `scripts/test_agent_office.py` | End-to-end tool-calling test for document generation. |
| `scripts/train_qlora.py` | QLoRA training script tuned for an 8 GB laptop GPU. |

## Browser and UI regression checks

Each file below is a headless Chrome DevTools Protocol test for a specific UI or
backend behavior.

| File | Purpose |
| --- | --- |
| `scripts/check_appearance.mjs` | Verifies sidebar text, image/video background state, and active playback. |
| `scripts/check_backend_recover.mjs` | Verifies that video playback recovers after the backend restarts. |
| `scripts/check_bg_hold.mjs` | Exercises a real streaming reply while sampling background-video state. |
| `scripts/check_layout.mjs` | Measures desktop, compact, narrow, and tiny layout geometry. |
| `scripts/check_mic.mjs` | Distinguishes browser microphone restrictions from Windows privacy restrictions. |
| `scripts/check_text_watchdog.mjs` | Verifies that text still appears when TTS is stalled. |
| `scripts/check_video_recover.mjs` | Reproduces and verifies background-video recovery after backend failure. |
| `scripts/check_voice_cache.mjs` | Verifies TTS cache behavior and voice-selection persistence. |
| `scripts/check_wake.mjs` | Verifies wake-word handling and the resulting response behavior. |

## Voice services

| File | Purpose |
| --- | --- |
| `voice/asr_server.py` | Local FunASR/SenseVoice HTTP service for speech recognition. |
| `voice/tts_server.py` | OpenAI-compatible TTS adapter with emotion mapping, retries, tempo correction, noise gating, and WAV repair. |
| `voice/index_tts_backend.py` | HTTP wrapper that exposes IndexTTS2 to the TTS adapter. |
| `voice/voices.example.json` | GPT-SoVITS configuration template with calm/warm/wry reference-audio examples. |
| `voice/voices.example.index.json` | IndexTTS2 configuration template. |

## Archive

| File | Purpose |
| --- | --- |
| `archive/old-browser-launcher/open_ruanmei.vbs` | Legacy hidden browser-launcher entry point retained for reference. |
| `archive/old-browser-launcher/rm_app.ps1` | Legacy browser-mode launcher superseded by `app/desktop.py`. |

## Documentation added for publishing

| File | Purpose |
| --- | --- |
| `docs/FILE_MAP.md` | This complete inventory of uploaded files and their responsibilities. |
| `docs/ASSETS_AND_PRIVACY.md` | Explains excluded personal data, large media, model files, and restoration steps. |
