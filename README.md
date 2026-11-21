<p align="center">
  <img src="https://cdn.karlosoft.com/cdn-data/ks/img/kwhisper/logo.svg" width="700" alt="K-Whisper Logo">
</p>

<p align="center">
  <a href="https://k-whisper.karlosoft.com/"><strong>Website</strong></a>
  &nbsp;·&nbsp;
  <a href="https://github.com/K-cermak/K-Whisper/releases/latest"><strong>Download</strong></a>
  &nbsp;·&nbsp;
  <a href="https://github.com/K-cermak/K-Whisper/issues"><strong>Report a problem</strong></a>
</p>

K-Whisper turns interviews, lectures, podcasts and videos into subtitles and written transcripts. Everything happens on your own computer: recordings are never uploaded anywhere, and once a speech model is downloaded, it works without an internet connection.

> **Note:** K-Whisper is heavily vibe-coded: most of its code was written with an AI assistant and only partly reviewed by a human. It is fine for everyday transcription, but it is not recommended for critical systems or anywhere a wrong or missing transcript could cause harm.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://cdn.karlosoft.com/cdn-data/ks/img/kwhisper/github-queue-dark.png">
  <img alt="The queue: one recording being transcribed with its newest line as a live caption, others done, failed or waiting" src="https://cdn.karlosoft.com/cdn-data/ks/img/kwhisper/github-queue-light.png">
</picture>

## What it does

- **Subtitles, a transcript or both** from any audio or video file. Subtitles are split into lines that are easy to read.
- **Many languages**: it recognizes the spoken language by itself, or you choose it. Every model except the Turbo ones can also translate the speech into English.
- **Lots of recordings at once**: drop in files or whole folders and let it work through them. You see each line as it is recognized and how long is left, and you can pause, stop or try again. The list is still there after a restart.
- **Files saved next to each recording**, or in one folder of your choice. Before anything existing would be replaced, it asks.
- **A speech model that fits your computer**: small and fast, or larger and more accurate. A recommended one is marked, so you don't have to know the difference.
- **Uses your graphics card** when it can (Apple Silicon Macs, and NVIDIA, AMD or Intel graphics on Windows and Linux), and the processor otherwise.
- **More when you need it** in Advanced options: names and terms to spell correctly, skipping silent parts, subtitle line length, more file formats. Light and dark appearance.

## Install

Download the file for your computer from the **[latest release](https://github.com/K-cermak/K-Whisper/releases/latest)**:

| Your computer | File to download |
|---|---|
| Mac with Apple Silicon (M1 or newer) | `K-Whisper-<version>-macos-arm64.dmg` |
| Windows PC (Intel or AMD processor) | `K-Whisper-<version>-windows-x64-setup.exe`, or `K-Whisper-<version>-windows-x64-portable.zip` to run it without installing |
| Windows on ARM (e.g. Snapdragon laptops) | `K-Whisper-<version>-windows-arm64-setup.exe`, or `K-Whisper-<version>-windows-arm64-portable.zip` |
| Linux PC (Intel or AMD processor) | `K-Whisper-<version>-linux-x64.AppImage`, or `K-Whisper-<version>-linux-x64.tar.gz` |
| Linux on ARM | `K-Whisper-<version>-linux-arm64.AppImage`, or `K-Whisper-<version>-linux-arm64.tar.gz` |

Macs with an Intel processor are not supported.

### First launch

K-Whisper is not signed with a paid developer certificate, so your system asks once whether you trust it:

- **macOS**: open the `.dmg` and drag K-Whisper into Applications. The first launch is blocked: open *System Settings › Privacy & Security*, scroll down and click **Open Anyway** (on macOS 14 and older, right-click the app › **Open** also works).
- **Windows**: if a blue "Windows protected your PC" window appears, click **More info** › **Run anyway**.
- **Linux**: allow the AppImage to run (right-click › *Properties* › *Allow executing as program*, or `chmod +x`), then open it. It needs the usual Qt libraries (e.g. `libxcb-cursor0`, `libxkbcommon-x11-0`, `libegl1`). The x64 version runs on Ubuntu 22.04, Debian 12 or newer (glibc 2.35+), the ARM version on Ubuntu 24.04 or newer (glibc 2.39+).

## How to use it

1. Open **Models** and download a speech model. The one marked **Recommended** suits most recordings.
2. Drop recordings or whole folders onto the window, or click **Add files**.
3. Under the list, choose what to make (**Subtitles**, **Transcript** or **Both**) and the spoken language, or leave it on *Detect automatically*.
4. Click **Transcribe**. The files are saved next to each recording. Point at a finished row to open them or show them in Finder or Explorer.

## Screenshots

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://cdn.karlosoft.com/cdn-data/ks/img/kwhisper/github-models-dark.png">
  <img alt="The Models page: models smallest first with their size, the recommended one marked, the one in use highlighted" src="https://cdn.karlosoft.com/cdn-data/ks/img/kwhisper/github-models-light.png">
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://cdn.karlosoft.com/cdn-data/ks/img/kwhisper/github-advanced-dark.png">
  <img width="480" alt="Advanced options: saved setups, output files and subtitle line rules" src="https://cdn.karlosoft.com/cdn-data/ks/img/kwhisper/github-advanced-light.png">
</picture>

## For developers

K-Whisper is built on [whisper.cpp](https://github.com/ggml-org/whisper.cpp) and Qt (PySide6).

- **Outputs**: SRT, WebVTT, TXT, TSV and JSON with word timings; subtitles are re-segmented into readable lines (line length, line count, duration)
- **Models**: resumable SHA-256 verified downloads from Hugging Face, import of custom GGML models, every variant (quantized, English-only) on request
- **Advanced options**: output formats, subtitle line rules, names and terms prompt, silence skipping (Silero VAD), decoding, hardware, saved setups
- **Acceleration**: Metal on macOS, Vulkan on Windows/Linux (NVIDIA, AMD, Intel), with automatic CPU fallback

### Development

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

### Releases

Packages are built by GitHub Actions (`Build` workflow) for macOS (Apple Silicon) `.dmg`, Windows x64 / arm64 installer `.exe` and portable `.zip`, and Linux x64 / arm64 `.AppImage` and `.tar.gz`.

1. Bump `version` in `pyproject.toml` (and `src/k_whisper/__init__.py`).
2. Push a tag `vX.Y.Z`. The `Build` workflow builds all platforms, runs a smoke test on every packaged app and creates a **draft** GitHub release with the packages and `SHA256SUMS.txt`.

The `Build` workflow can also be started manually (*Actions › Build › Run workflow*); the packages are then available as workflow artifacts.

### How it works

The GUI does not link whisper.cpp; it runs the bundled `whisper-cli` and `ffmpeg` executables as subprocesses (`QProcess`):

1. `ffmpeg` decodes any audio/video file to 16 kHz mono WAV in a temporary folder.
2. `whisper-cli` transcribes it and writes full JSON output with token timestamps (`-ojf`); progress and finished segments are read from its output live.
3. The JSON is converted into the internal transcript model, words are rebuilt from tokens, the text is re-segmented into subtitle cues and exported.

The optional JSON output keeps every word with its timing for further processing.

### Project layout

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
