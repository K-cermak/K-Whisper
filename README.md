# K-Whisper

Desktop application that turns recordings into subtitles and transcripts, built on [whisper.cpp](https://github.com/ggml-org/whisper.cpp) and Qt (PySide6).

> **Note:** K-Whisper is heavily vibe-coded: most of its code was written with an AI assistant and only partly reviewed by a human. It is fine for everyday transcription, but it is not recommended for critical systems or anywhere a wrong or missing transcript could cause harm.

- **One-button workflow**: pick a model, choose Subtitles / Transcript / Both and the spoken language, press Transcribe. Waiting recordings always follow these settings
- **Queue**: drag & drop files or whole folders, media length shown up front, a live caption of the recording being transcribed, pause/stop/retry, open the results or show them in Finder/Explorer right from the row, transcribe finished recordings again with new settings; the queue survives restarts
- **No silent overwrites**: when the subtitles or transcript already exist, K-Whisper asks whether to replace them, keep both or skip the recording
- **First run**: until a model is downloaded, the model choice is off and the queue points to the Models page
- **Advanced options** in their own window: output formats, subtitle line rules, names and terms prompt, silence skipping (Silero VAD), decoding, hardware, saved setups
- **Models**: a short list of the models most people need (every variant on request), smallest first, with compressed (quantized) versions explained; resumable SHA-256 verified downloads, import of custom GGML models, pick the model for new recordings
- **Outputs**: SRT, WebVTT, TXT, TSV and JSON with word timings; subtitles are re-segmented into readable lines (line length, line count, duration)
- **Acceleration**: Metal on macOS, Vulkan on Windows/Linux (NVIDIA, AMD, Intel), with automatic CPU fallback

## Downloads

Installers are built by GitHub Actions (`Build` workflow) for:

| Platform | Package |
|---|---|
| macOS (Apple Silicon) | `.dmg` |
| Windows x64 / arm64 | installer `.exe` and portable `.zip` |
| Linux x64 / arm64 | `.AppImage` and `.tar.gz` |

The builds are not code-signed. On macOS, the first launch is blocked: open *System Settings › Privacy & Security* and click **Open Anyway** (on macOS 14 and older, right-click › **Open** also works). On Windows, SmartScreen may ask for confirmation.

Linux builds need the usual Qt runtime libraries (e.g. `libxcb-cursor0`, `libxkbcommon-x11-0`, `libegl1`). The x64 build targets glibc 2.35+ (Ubuntu 22.04, Debian 12+); the arm64 build needs glibc 2.39+ (Ubuntu 24.04+).

## Development

Requirements: [uv](https://docs.astral.sh/uv/), CMake, a C/C++ compiler, Git. On macOS, Xcode command line tools are enough.

```sh
uv sync                                          # Python 3.14 environment with PySide6
uv run python scripts/build_whispercpp.py        # whisper.cpp -> vendor/<platform>/whisper
uv run python scripts/fetch_ffmpeg.py            # LGPL ffmpeg -> vendor/<platform>/ffmpeg
uv run k-whisper                                 # start the app
```

Without `fetch_ffmpeg.py` the app falls back to `ffmpeg` on `PATH`.

Tests (the end-to-end test runs once whisper.cpp is built and the test assets are downloaded):

```sh
uv run python scripts/fetch_test_assets.py       # tiny model + JFK sample
uv run python scripts/fetch_ui_assets.py         # only after changing the icon list or fonts (files are committed)
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

Local package build:

```sh
uv run pyinstaller --noconfirm packaging/k-whisper.spec
dist/K-Whisper.app/Contents/MacOS/K-Whisper --smoke-test \
  --model test-assets/ggml-tiny.bin --input test-assets/jfk.wav --expect "ask not"
```

## Releases

1. Bump `version` in `pyproject.toml` (and `src/k_whisper/__init__.py`).
2. Push a tag `vX.Y.Z`. The `Build` workflow builds all platforms, runs a smoke test on every packaged app and creates a **draft** GitHub release with the packages and `SHA256SUMS.txt`.

The `Build` workflow can also be started manually (*Actions › Build › Run workflow*); the packages are then available as workflow artifacts.

## How it works

The GUI does not link whisper.cpp; it runs the bundled `whisper-cli` and `ffmpeg` executables as subprocesses (`QProcess`):

1. `ffmpeg` decodes any audio/video file to 16 kHz mono WAV in a temporary folder.
2. `whisper-cli` transcribes it and writes full JSON output with token timestamps (`-ojf`); progress and finished segments are read from its output live.
3. The JSON is converted into the internal transcript model, words are rebuilt from tokens, the text is re-segmented into subtitle cues and exported.

The optional JSON output keeps every word with its timing for further processing.

## Project layout

```
src/k_whisper/        application package
  engine/             whisper-cli/ffmpeg command lines, QProcess runner, options and presets
  models/             model catalog and download manager
  transcript/         transcript model, re-segmentation, import/export
  batch/              jobs and the queue
  ui/                 main window, queue, run bar, models page, dialogs; theme.py holds the design tokens
  resources/          app icon, Lucide icons, Atkinson Hyperlegible fonts
scripts/              build whisper.cpp, fetch ffmpeg/test assets/UI assets, render the app icon
docs/DESIGN.md        visual direction, tokens and principles of the UI
packaging/            PyInstaller spec, Inno Setup, AppImage and dmg scripts, icons
.github/workflows/    CI (lint + tests) and Build (packages + release)
```
