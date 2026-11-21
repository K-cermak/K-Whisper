# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

K-Whisper is a PySide6 desktop app (Python 3.14, managed with uv) that batch-transcribes recordings into subtitles and transcripts with whisper.cpp. User-facing copy is English, sentence case.

## Commands

```sh
uv sync                                          # environment (PySide6, pytest, ruff, pyinstaller)
uv run python scripts/build_whispercpp.py        # whisper.cpp -> vendor/<platform>/whisper (needs CMake, C/C++ compiler)
uv run python scripts/fetch_ffmpeg.py            # LGPL ffmpeg -> vendor/<platform>/ffmpeg (else ffmpeg on PATH is used)
uv run k-whisper                                 # run the app

uv run pytest                                    # all tests
uv run pytest tests/test_ui.py::test_language_list_can_be_searched   # one test
uv run python scripts/fetch_test_assets.py       # tiny model + JFK sample; enables tests/test_integration.py
uv run ruff check . && uv run ruff format --check .

uv run pyinstaller --noconfirm packaging/k-whisper.spec   # local package build
uv run python scripts/make_icons.py              # app icons (packaging/icons, resources/icon.png) from resources/logo.svg; on macOS also AppIcon.icon + Assets.car (needs Xcode's actool)
uv run python scripts/make_screenshots.py [dir]  # README/website screenshots from a mocked queue, light and dark
```

- `scripts/fetch_ui_assets.py` deletes every SVG in `resources/icons/` and downloads the `ICONS` list again; add a new Lucide icon to that list, not only to the folder.
- The version lives in both `pyproject.toml` and `src/k_whisper/__init__.py` (`tests/test_version.py` checks they match). Releases: bump both, push tag `vX.Y.Z`; the Build workflow rejects a tag that differs from the pyproject version.
- CI (`ci.yml`, push to main and PRs) runs ruff and pytest on Ubuntu only, with `QT_QPA_PLATFORM=offscreen`; the end-to-end test is skipped there. `build.yml` (tags, manual) runs the full suite on every platform, packages, and smoke-tests the packaged app.

## Architecture

**Transcription pipeline.** The app never links whisper.cpp. `engine/runner.py` (`TranscriptionTask`) runs `ffmpeg` (decode to 16 kHz WAV in a temp folder) and then `whisper-cli` as `QProcess`es; `engine/cli.py` builds both command lines and parses their output lines (progress, live segments, detected language, GPU backend). whisper-cli writes full JSON with token timestamps (`-ojf`), which `transcript/model.py` turns into a `Transcript` with words rebuilt from tokens; `transcript/resegment.py` splits it into subtitle cues and `transcript/formats.py` exports SRT/VTT/TXT/TSV/JSON. Plain text keeps whisper's own segments; the subtitle formats use the re-segmented cues.

**Tools and data locations** (`paths.py`): tools come from `vendor/<platform>/` in development and from `sys._MEIPASS` when frozen; Settings can override both paths. Models default to the app data folder (`QStandardPaths.AppDataLocation/models`), the queue is persisted to `queue.json` next to it, and settings are one JSON blob in `QSettings` under `settings/v1` (`settings.py`; unknown keys are dropped, migrations go in `AppSettings.load`).

**Queue** (`batch/queue.py`): runs one `TranscriptionTask` at a time and saves itself on every change. A job stores its `TranscribeOptions` as a dict. Waiting jobs always follow the run bar (`MainWindow._sync_pending`); finished jobs keep the options they were made with until transcribed again. Output names come from `batch/job.py:output_paths` (filename template, a `-2`… suffix while names are taken by other jobs or, unless replacing, already exist). What happens to existing files (`on_existing`: replace / number / skip) is decided when the queue is started: `MainWindow._existing_files_policy` asks the user or applies `settings.existing_files`.

**Models** (`models/`): `catalog.py` has a built-in list with sizes and SHA-256, refreshed from the Hugging Face API and cached as `.catalog.json` in the models folder. `manager.py` downloads to `.part` files with HTTP Range resume and verifies the checksum in a Python thread, relaying results back to the GUI thread through a signal. Installed models are the `*.bin` files in the folder (imports are renamed to `ggml-*.bin`), except the Silero VAD model, which the queue downloads on demand.

**UI** (`ui/`): `MainWindow` wires the queue, model manager and pages together. `RunBar` owns the `TranscribeOptions` for new recordings; it lists only downloaded models, a missing chosen model falls back to the biggest downloaded one, and with none it shows a button to the Models page. `AdvancedDialog` edits every other option. The queue list is a `QListView` with a painted delegate (`queue_view.py`): the running row's live caption band and the buttons of the row under the pointer are drawn and hit-tested there, not real widgets.

**Look and feel**: `docs/DESIGN.md` holds the visual direction, tokens and principles; keep it in step with UI changes. `ui/theme.py` defines the light/dark tokens and one app-wide stylesheet; widgets are styled through dynamic properties (`role` on labels, `variant`/`large` on buttons). Lucide icons are tinted at runtime: buttons with an `iconName` property get their icon from `refresh_icons()`, which runs again on theme changes. Shared building blocks (`button`, `form_section`, `align_forms`, `dialog_footer`, `confirm`, `inform`, `SearchCombo`, `capped`) are in `ui/widgets.py`.

## Qt/PySide pitfalls met in this code

- The stylesheet sets the font family globally, so `setFont()` on widgets is overridden; use label roles or QSS. Delegates paint with `ui_font()` / `mono_font()`.
- After changing a dynamic property used in a selector, call `repolish()`. Never name a property after an existing `QWidget` property (e.g. `size`): `setProperty` then fails silently.
- Qt sizes a button for its regular weight, so a checked state set in semibold by QSS (segments, tabs) clips the text, most visibly on Windows; such buttons are `CheckableButton` / `CheckableToolButton` from `ui/widgets.py`.
- A `Signal(int)` is 32-bit; byte counts use `"qint64"` (models are over 2 GB).
- A word-wrapped `QLabel` with a maximum width inside a vertical layout gets clipped; wrap it with `capped()`.
- Message boxes go through `confirm()` / `inform()`: no icon, a short headline (Qt bolds it on macOS) with details below, action-named buttons. Don't use `DestructiveRole`: Qt sets such buttons 28 px apart on macOS.
- Combo boxes need `combobox-popup: 0` (in the stylesheet), otherwise Fusion ignores `maxVisibleItems` and the list can fill the screen.
- On Windows, HTTPS must go through Schannel (`app.use_system_tls()`): Qt's OpenSSL backend loads the system's `libssl-3-x64.dll`, which clashes with the same-named, different-version `libcrypto-3-x64.dll` that Python's `hashlib` loads, and the first HTTPS request crashes natively (seen with an OpenSSL 3.1 in System32).
- `except A, B:` without parentheses is valid Python 3.14 syntax (PEP 758), not a bug.
- To check UI changes without a display, run with `QT_QPA_PLATFORM=offscreen` and save `widget.grab()`; button-box order, popups and focus differ on macOS, so check those with the native platform.
