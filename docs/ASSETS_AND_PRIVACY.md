# Assets and private data

This repository is a source-distribution snapshot of the MeiMei local AI agent.
Runtime data and large local media are intentionally not committed.

## Included

- Small UI images under `app/assets/`: background thumbnails, sticker images,
  the default background, and application icons.
- Empty/sanitized templates under `data/`.
- Example voice and appearance configuration files.

## Excluded

| Path or pattern | Reason |
| --- | --- |
| `app/assets/*.mp4` | Large game/background videos; one file exceeds GitHub's 100 MB limit. |
| `data/习惯.md` | Personal habits and preferences. |
| `data/提醒.json` | Personal reminders. |
| `data/提醒记录.json` | Runtime reminder history. |
| `data/听歌记录.json` | Personal listening history. |
| `app/appearance.json` | Live local appearance state. Use `app/appearance.example.json`. |
| `voice/voices.json` | Live voice paths and selected local weights. Use the example files. |
| `logs/` | Runtime logs. |
| `app/app-profile/`, `app/desktop-profile/` | WebView/browser profile and cache. |
| `**/__pycache__/`, `*.pyc` | Python bytecode cache. |
| `*.wav`, `*.mp3`, `*.pth`, `*.ckpt`, `*.onnx`, `*.gguf` | Local audio, model weights, and generated model files. |
| `C盘清理记录.md`, `手机与设备连接.md`, `下载清单.md` | Machine-specific personal notes. |

## Restoring a working local setup

1. Copy `app/appearance.example.json` to `app/appearance.json`, or let the app
   create it on first launch.
2. Copy `voice/voices.example.json` to `voice/voices.json` and replace the
   reference-audio paths with paths on your own machine.
3. Add background videos to `app/assets/` if you want video backgrounds.
4. Create the runtime data files under `data/` or let the application create
   them during first use.

Do not commit browser profiles, model weights, voice samples, logs, or personal
data when publishing a fork.
