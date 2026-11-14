# Third-party software

K-Whisper distributes the following third-party components in its packages.

| Component | License | Notes |
|---|---|---|
| [whisper.cpp / ggml](https://github.com/ggml-org/whisper.cpp) | MIT | Built from source by `scripts/build_whispercpp.py` (`whisper-cli`). |
| [Qt](https://www.qt.io/) via [PySide6](https://pypi.org/project/PySide6/) | LGPL-3.0 | Dynamically linked shared libraries; can be replaced by the user. |
| [FFmpeg](https://ffmpeg.org/) | LGPL-2.1-or-later | Separate `ffmpeg` executable built without GPL/non-free components. macOS/Linux: built from the official source release by `scripts/fetch_ffmpeg.py` (the exact configure flags are in `ffmpeg/BUILD_INFO.txt` inside the package). Windows: LGPL build from [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds). |
| [Lucide icons](https://lucide.dev/) | ISC | SVG icons in `src/k_whisper/resources/icons/` (fetched by `scripts/fetch_ui_assets.py`). |
| [Atkinson Hyperlegible Next and Mono](https://www.brailleinstitute.org/freefont/) | SIL Open Font License 1.1 | Fonts in `src/k_whisper/resources/fonts/` (license in `OFL.txt` there). |
| [Python](https://www.python.org/) | PSF License | Embedded interpreter (PyInstaller). |
| [PyInstaller](https://pyinstaller.org/) bootloader | GPL-2.0 with bootloader exception | The exception allows distributing the bootloader with applications under any license. |

Speech recognition models are not bundled. They are downloaded by the user from Hugging Face ([ggerganov/whisper.cpp](https://huggingface.co/ggerganov/whisper.cpp), OpenAI Whisper weights, MIT license) and [ggml-org/whisper-vad](https://huggingface.co/ggml-org/whisper-vad) (Silero VAD, MIT license).
