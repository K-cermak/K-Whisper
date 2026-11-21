"""Render the README and website screenshots from a mocked queue, in light and dark.

Nothing is transcribed and no settings, models or queue of the real app are touched: everything lives in a
temporary folder. Writes github-{queue,models,advanced}-{light,dark}.png at twice the window size:
    uv run python scripts/make_screenshots.py [output folder]   # default: build/screenshots
"""

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["QT_SCALE_FACTOR"] = "2"

from PySide6.QtCore import QCoreApplication, QLocale, QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from k_whisper import APP_NAME  # noqa: E402
from k_whisper.batch.job import Job, JobStatus  # noqa: E402
from k_whisper.batch.queue import JobQueue  # noqa: E402
from k_whisper.engine.options import TranscribeOptions  # noqa: E402
from k_whisper.models.catalog import BUILTIN_CATALOG  # noqa: E402
from k_whisper.models.manager import ModelManager  # noqa: E402
from k_whisper.settings import AppSettings  # noqa: E402
from k_whisper.ui.advanced_dialog import AdvancedDialog  # noqa: E402
from k_whisper.ui.main_window import PAGE_MODELS, PAGE_QUEUE, MainWindow  # noqa: E402
from k_whisper.ui.theme import install, theme  # noqa: E402

WINDOW = (1280, 800)
DIALOG = (620, 760)
MODEL = "ggml-large-v3-turbo-q5_0.bin"
INSTALLED = ["ggml-tiny.bin", "ggml-small.bin", MODEL]
HOME = Path.home()


def mock_models(folder: Path) -> None:
    """Sparse files of the real sizes: the Models page shows sizes on disk for downloaded models."""
    sizes = {m.filename: m.size for m in BUILTIN_CATALOG}
    for name in INSTALLED:
        with (folder / name).open("wb") as fh:
            fh.truncate(sizes[name])


def mock_jobs(opts: dict) -> tuple[list[Job], Job]:
    now = time.time()

    def job(path: str, duration: float, **fields) -> Job:
        return Job(source=str(HOME / path), options=opts, media_duration=duration, **fields)

    def done(path: str, duration: float, took: float) -> Job:
        source = HOME / path
        outputs = [str(source.with_suffix(".srt")), str(source.with_suffix(".txt"))]
        return job(
            path,
            duration,
            status=JobStatus.DONE,
            progress=1.0,
            outputs=outputs,
            started=now - took - 600,
            finished=now - 600,
            language="en",
        )

    # 46 % done after this long leaves "about 3 min left" (Job.eta_seconds).
    running = job(
        "Movies/Interviews/interview-mayor-2026-03.mp4",
        761,
        status=JobStatus.RUNNING,
        progress=0.46,
        started=now - 153,
        last_text="And so, my fellow Americans, ask not what your country can do for you",
    )
    jobs = [
        running,
        done("Music/Podcasts/podcast-episode-12.mp3", 2882, 190),
        done("Movies/Meetings/team-meeting-2026-10-14.mov", 3127, 320),
        job(
            "Documents/Lectures/lecture-week-3.m4a",
            0,
            status=JobStatus.FAILED,
            error="The file is no longer there. It was moved, renamed or deleted.",
            finished=now - 300,
        ),
        job("Documents/Lectures/lecture-week-4.m4a", 4211),
        job("Documents/Lectures/lecture-week-5.m4a", 3954),
    ]
    return jobs, running


def grab(widget, path: Path) -> None:
    QApplication.processEvents()
    widget.grab().save(str(path))
    print("wrote", path)


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "build" / "screenshots"
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="k-whisper-screenshots-"))

    # Settings go to an INI file in the temporary folder, never to the app's own settings.
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp))
    QCoreApplication.setOrganizationName(f"{APP_NAME} screenshots")
    QCoreApplication.setApplicationName(APP_NAME)
    _app = QApplication(sys.argv[:1])
    # As in app.py: the interface is English, whatever the system locale (7.0 s, not 7,0 s).
    QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))

    models_dir = tmp / "models"
    models_dir.mkdir()
    mock_models(models_dir)
    opts = TranscribeOptions(model=MODEL, language="auto", formats=["srt", "txt"], resegment=True)
    # Any existing file stands in for the tools, so the top bar shows the backend instead of a missing engine.
    settings = AppSettings(
        models_dir=str(models_dir),
        whisper_cli_path=sys.executable,
        ffmpeg_path=sys.executable,
        options=opts.to_dict(),
    )

    install("light")
    models = ModelManager(models_dir)
    queue = JobQueue(settings, models, state_file=tmp / "queue.json")
    queue.jobs, queue.current = mock_jobs(opts.to_dict())
    queue.running = True

    window = MainWindow(settings, models, queue)
    # The Models page refreshes the catalog from Hugging Face when first shown; the built-in list is enough.
    window.models_page._refreshed = True
    queue.jobs_reset.emit()
    window._on_backend("Metal")
    # On macOS the menu bar belongs to the system bar; offscreen would draw it inside the window.
    window.menuBar().hide()
    window.resize(*WINDOW)
    window.show()

    for mode in ("light", "dark"):
        theme().set_mode(mode)
        window.show_page(PAGE_QUEUE)
        grab(window, out / f"github-queue-{mode}.png")
        window.show_page(PAGE_MODELS)
        grab(window, out / f"github-models-{mode}.png")
        dialog = AdvancedDialog(opts, {}, window)
        dialog.resize(*DIALOG)
        dialog.show()
        grab(dialog, out / f"github-advanced-{mode}.png")
        dialog.close()


if __name__ == "__main__":
    main()
