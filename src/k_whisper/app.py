"""Application entry point (GUI and the headless --smoke-test used by CI)."""

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QLocale
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from k_whisper import APP_NAME, ORG_NAME, __version__

RESOURCES = Path(__file__).parent / "resources"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="k-whisper", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    parser.add_argument("files", nargs="*", type=Path, help="recordings or folders to add to the queue")
    smoke = parser.add_argument_group("smoke test (headless, used by CI)")
    smoke.add_argument("--smoke-test", action="store_true", help="transcribe --input with --model and exit")
    smoke.add_argument("--model", type=Path)
    smoke.add_argument("--input", type=Path)
    smoke.add_argument("--expect", default="", help="text that must appear in the transcript")
    smoke.add_argument("--log", type=Path, help="write output to this file (windowed builds have no stdout)")
    args, _qt_args = parser.parse_known_args(argv)
    return args


def run_smoke_test(args: argparse.Namespace) -> int:
    from k_whisper.engine.options import TranscribeOptions
    from k_whisper.engine.runner import TranscriptionTask
    from k_whisper.paths import bundled_ffmpeg, bundled_whisper_cli

    out = args.log.open("w", encoding="utf-8") if args.log else sys.stdout

    def log(text: str) -> None:
        if out:
            print(text, file=out, flush=True)

    app = QCoreApplication(sys.argv[:1])
    cli, ffmpeg = bundled_whisper_cli(), bundled_ffmpeg()
    log(f"whisper-cli: {cli}\nffmpeg: {ffmpeg}")
    if not cli or not args.model or not args.input:
        log("smoke test needs a bundled whisper-cli, --model and --input")
        return 2

    result = {"code": 1}
    task = TranscriptionTask(args.input, TranscribeOptions(language="auto"), cli, ffmpeg, args.model)
    task.backend_detected.connect(lambda b: log(f"backend: {b}"))
    task.segment.connect(lambda start, end, text: log(f"[{start} --> {end}]  {text}"))

    def done(transcript, error: str) -> None:
        if transcript is None:
            log(f"FAILED: {error}")
        else:
            text = transcript.plain_text()
            ok = args.expect.lower() in text.lower()
            log(f"language: {transcript.language}\n{'OK' if ok else 'UNEXPECTED TRANSCRIPT'}")
            result["code"] = 0 if ok else 1
        app.quit()

    task.finished.connect(done)
    task.start()
    app.exec()
    return result["code"]


def main() -> None:
    args = parse_args(sys.argv[1:])
    QCoreApplication.setApplicationName(APP_NAME)
    QCoreApplication.setOrganizationName(ORG_NAME)
    QCoreApplication.setApplicationVersion(__version__)

    if args.smoke_test:
        sys.exit(run_smoke_test(args))

    from k_whisper.batch.queue import JobQueue
    from k_whisper.models.manager import ModelManager
    from k_whisper.paths import default_models_dir
    from k_whisper.settings import AppSettings
    from k_whisper.ui.main_window import MainWindow
    from k_whisper.ui.theme import install as install_theme
    from k_whisper.ui.widgets import inform

    app = QApplication(sys.argv)
    # The interface is English, so numbers use English formatting whatever the system locale is.
    QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
    app.setWindowIcon(QIcon(str(RESOURCES / "icon.png")))

    settings = AppSettings.load()
    install_theme(settings.theme)
    models_dir = settings.resolved_models_dir()
    unreachable = None
    try:
        models_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        # E.g. a disconnected external drive. The setting is kept, so the folder is used again once it is back.
        unreachable, models_dir = models_dir, default_models_dir()
    models = ModelManager(models_dir)
    queue = JobQueue(settings, models)
    queue.load()

    window = MainWindow(settings, models, queue)
    window.show()
    if unreachable:
        inform(
            window,
            "Models folder not available",
            f"The models folder {unreachable} cannot be reached.",
            f"The default folder {models_dir} is used for now. You can change the folder in Settings.",
        )
    # Qt's own options (e.g. "-platform xcb") also land among the positional arguments.
    if files := [p for p in args.files if p.exists()]:
        window.add_paths(files)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
