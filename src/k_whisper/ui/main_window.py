"""Main window: top bar with Queue and Models, the queue sheet and the run bar."""

import sys
import time
from pathlib import Path

from PySide6.QtCore import QPoint, QProcess, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QStackedWidget,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from k_whisper import APP_NAME, __version__
from k_whisper.batch.job import MEDIA_EXTENSIONS, Job, JobStatus
from k_whisper.batch.queue import JobQueue, resolve_ffmpeg, resolve_whisper_cli
from k_whisper.models.catalog import format_size
from k_whisper.models.manager import ModelManager
from k_whisper.paths import whisper_cpp_version
from k_whisper.settings import AppSettings
from k_whisper.ui.advanced_dialog import AdvancedDialog
from k_whisper.ui.models_page import ModelsPage
from k_whisper.ui.queue_view import FILE_MANAGER, JobListModel, QueueView
from k_whisper.ui.run_bar import RunBar, model_name
from k_whisper.ui.settings_dialog import SettingsDialog
from k_whisper.ui.theme import install, logo, mono_font, repolish, theme
from k_whisper.ui.widgets import (
    EmptyQueue,
    Toast,
    button,
    confirm,
    inform,
    label,
    message_box,
    refresh_icons,
    tool,
)

PAGE_QUEUE, PAGE_MODELS = 0, 1


def reveal(path: Path) -> None:
    """Show a file selected in the system file manager (Linux has no common way to select, so open the folder)."""
    if sys.platform == "darwin":
        QProcess.startDetached("open", ["-R", str(path)])
    elif sys.platform == "win32":
        # Separate arguments: Qt quotes an argument containing spaces as a whole, which explorer does not accept.
        QProcess.startDetached("explorer", ["/select,", str(path)])
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))


class LogDialog(QDialog):
    def __init__(self, job: Job, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Log for {job.name}")
        self.resize(820, 520)
        text = QPlainTextEdit(readOnly=True, objectName="Console")
        text.setFont(mono_font(12))
        parts = []
        if job.error:
            parts.append(f"What went wrong\n\n{job.error}\n")
        parts.append("\n".join(job.log) or "Nothing was logged for this recording since K-Whisper started.")
        text.setPlainText("\n".join(parts))
        copy = button("Copy", None, "quiet")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(text.toPlainText()))
        close = button("Close")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addWidget(copy)
        row.addStretch(1)
        row.addWidget(close)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.addWidget(text, 1)
        layout.addLayout(row)


class TopBar(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

        mark = QLabel()
        mark.setPixmap(logo(26))
        theme().changed.connect(lambda: mark.setPixmap(logo(26)))
        wordmark = label(APP_NAME)
        wordmark.setObjectName("Wordmark")
        self.tabs = QButtonGroup(self)
        self.queue_tab = self._tab("Queue", PAGE_QUEUE)
        self.models_tab = self._tab("Models", PAGE_MODELS)
        self.queue_tab.setChecked(True)
        self.engine = label("", "small")
        self.settings_btn = tool("settings", "Settings")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 14, 0)
        layout.setSpacing(0)
        layout.addWidget(mark)
        layout.addSpacing(8)
        layout.addWidget(wordmark)
        layout.addSpacing(36)
        layout.addWidget(self.queue_tab)
        layout.addSpacing(22)
        layout.addWidget(self.models_tab)
        layout.addStretch(1)
        layout.addWidget(self.engine)
        layout.addSpacing(12)
        layout.addWidget(self.settings_btn)

    def _tab(self, text: str, page: int) -> QToolButton:
        tab = QToolButton(text=text)
        tab.setObjectName("Tab")
        tab.setCheckable(True)
        tab.setCursor(Qt.CursorShape.PointingHandCursor)
        # Ctrl+1 / Ctrl+2 switch pages from the keyboard; tabs taking focus would only paint a stray outline.
        tab.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tabs.addButton(tab, page)
        return tab


class MainWindow(QMainWindow):
    def __init__(self, settings: AppSettings, models: ModelManager, queue: JobQueue) -> None:
        super().__init__()
        self.settings = settings
        self.models = models
        self.queue = queue
        self.backend = ""
        self._run_started = 0.0
        self._tray: QSystemTrayIcon | None = None

        self.setWindowTitle(APP_NAME)
        self.resize(1200, 780)

        self.top = TopBar()
        self.top.tabs.idClicked.connect(self.show_page)
        self.top.settings_btn.clicked.connect(self._open_settings)

        self._save_timer = QTimer(self, singleShot=True, interval=600)
        self._save_timer.timeout.connect(self._persist_settings)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_queue_page())
        self.models_page = ModelsPage(models)
        self.models_page.set_current_model(self.run_bar.options().model)
        self.models_page.use_requested.connect(self._use_model)
        self.pages.addWidget(self.models_page)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.top)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(central)
        self.toast = Toast(central)
        self.pages.currentChanged.connect(lambda _i: self.toast.hide())

        self._build_actions()

        queue.running_changed.connect(lambda _running: self._update_state())
        queue.job_updated.connect(lambda _id: self._update_state())
        queue.jobs_reset.connect(self._update_state)
        queue.job_added.connect(lambda _row: self._update_state())
        queue.job_removed.connect(lambda _row: self._update_state())
        queue.backend_detected.connect(self._on_backend)
        queue.job_finished.connect(self._on_job_finished)
        queue.all_done.connect(self._on_all_done)
        models.installed_changed.connect(self._on_models_changed)
        theme().changed.connect(lambda: refresh_icons(self))

        self._tick = QTimer(self, interval=1000)
        self._tick.timeout.connect(self.job_model.refresh_running)
        self._tick.start()

        refresh_icons(self)
        self._refresh_model_list()
        self._sync_pending()
        self._update_state()
        self._update_empty_state()
        self._on_backend("")
        # The run bar decides how narrow the window may get; a fixed minimum would let it squash its fields.
        self.setMinimumSize(max(900, self.minimumSizeHint().width()), 600)
        # Start without keyboard focus on any control, so nothing shows a focus outline before it is used.
        central.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        QTimer.singleShot(0, central.setFocus)

    # --- construction ---------------------------------------------------------------------------

    def _build_queue_page(self) -> QWidget:
        self.job_model = JobListModel(self.queue, self)
        self.queue_view = QueueView(self.job_model)
        self.queue_view.files_dropped.connect(self.add_paths)
        self.queue_view.activated.connect(lambda idx: self._open_job(self.job_model.job(idx.row())))
        self.queue_view.action_triggered.connect(self._row_action)
        self.queue_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.queue_view.customContextMenuRequested.connect(self._queue_menu)
        self.queue_view.selectionModel().selectionChanged.connect(lambda *_: self._update_state())

        self.empty = EmptyQueue()
        self.empty.files_dropped.connect(self.add_paths)
        self.empty.choose_files.connect(self._add_files)
        self.empty.choose_folder.connect(self._add_folder)
        self.empty.show_models.connect(lambda: self.show_page(PAGE_MODELS))

        self.queue_stack = QStackedWidget()
        self.queue_stack.addWidget(self.empty)
        self.queue_stack.addWidget(self.queue_view)

        # The tab already says "Queue"; the heading states what is in it instead.
        self.queue_heading = label("", "title")
        self.queue_summary = label("", "muted")
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(self.queue_heading)
        titles.addWidget(self.queue_summary)
        self.add_folder_btn = button("Add folder", "folder-plus")
        self.add_folder_btn.clicked.connect(self._add_folder)
        self.add_files_btn = button("Add files", "plus")
        self.add_files_btn.clicked.connect(self._add_files)
        self.more_btn = tool("ellipsis", "More actions")
        self.more_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.queue_header = QWidget()
        header = QHBoxLayout(self.queue_header)
        header.setContentsMargins(24, 20, 20, 14)
        header.setSpacing(8)
        header.addLayout(titles, 1)
        header.addWidget(self.add_folder_btn, 0, Qt.AlignmentFlag.AlignBottom)
        header.addWidget(self.add_files_btn, 0, Qt.AlignmentFlag.AlignBottom)
        header.addWidget(self.more_btn, 0, Qt.AlignmentFlag.AlignBottom)

        self.run_bar = RunBar()
        self.run_bar.set_installed_models(self._model_sizes())
        self.run_bar.set_options(self.settings.transcribe_options())
        self.run_bar.changed.connect(self._options_changed)
        self.run_bar.start_clicked.connect(self._start_or_pause)
        self.run_bar.advanced_clicked.connect(self._open_advanced)
        self.run_bar.manage_models_clicked.connect(lambda: self.show_page(PAGE_MODELS))

        page = QWidget()
        page.setObjectName("Page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.queue_header)
        layout.addWidget(self.queue_stack, 1)
        layout.addWidget(self.run_bar)
        return page

    def _build_actions(self) -> None:
        def action(text: str, slot, shortcut=None, target: QWidget | None = None) -> QAction:
            act = QAction(text, self)
            if shortcut:
                act.setShortcut(QKeySequence(shortcut))
            act.triggered.connect(slot)
            (target or self).addAction(act)
            return act

        self.act_add = action("Add files…", self._add_files, QKeySequence.StandardKey.Open)
        self.act_add_dir = action("Add folder…", self._add_folder, "Ctrl+Shift+O")
        self.act_start = action("Transcribe", self._start_or_pause, "Ctrl+R")
        self.act_pause = action("Pause after this one", self.queue.pause)
        self.act_stop = action("Stop", self.queue.stop, "Ctrl+.")
        # Bound to the list only, so Backspace keeps working in text fields elsewhere.
        self.act_remove = action("Remove from queue", self._remove_selected, None, self.queue_view)
        self.act_remove.setShortcuts([QKeySequence(QKeySequence.StandardKey.Delete), QKeySequence("Backspace")])
        self.act_remove.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        self.act_retry_failed = action("Try failed ones again", self._retry_failed)
        self.act_clear = action("Clear finished", self.queue.clear_finished)
        self.act_queue = action("Queue", lambda: self.show_page(PAGE_QUEUE), "Ctrl+1")
        self.act_models = action("Models", lambda: self.show_page(PAGE_MODELS), "Ctrl+2")
        self.act_advanced = action("Advanced options…", self._open_advanced, "Ctrl+Shift+A")
        self.act_settings = action("Settings…", self._open_settings, QKeySequence.StandardKey.Preferences)
        self.act_quit = action("Quit", self.close, QKeySequence.StandardKey.Quit)

        more = QMenu(self)
        more.addAction(self.act_retry_failed)
        more.addSeparator()
        more.addActions([self.act_remove, self.act_clear])
        self.more_btn.setMenu(more)

        # macOS expects a global menu bar; on Windows and Linux the top bar replaces it.
        if sys.platform == "darwin":
            bar = self.menuBar()
            file = bar.addMenu("&File")
            file.addActions([self.act_add, self.act_add_dir])
            file.addSeparator()
            file.addAction(self.act_quit)
            queue_menu = bar.addMenu("&Queue")
            queue_menu.addActions([self.act_start, self.act_pause, self.act_stop])
            queue_menu.addSeparator()
            queue_menu.addActions([self.act_retry_failed, self.act_remove, self.act_clear])
            view = bar.addMenu("&View")
            view.addActions([self.act_queue, self.act_models])
            tools = bar.addMenu("&Tools")
            tools.addActions([self.act_advanced, self.act_settings])
            help_menu = bar.addMenu("&Help")
            help_menu.addAction("About K-Whisper", self._about)

    # --- state ----------------------------------------------------------------------------------

    def show_page(self, page: int) -> None:
        self.pages.setCurrentIndex(page)
        self.top.tabs.button(page).setChecked(True)

    def _toast(self, text: str, msec: int = 3500) -> None:
        on_queue = self.pages.currentIndex() == PAGE_QUEUE
        self.toast.bottom_margin = self.run_bar.height() + 16 if on_queue else 24
        self.toast.show_message(text, msec)

    def _update_state(self) -> None:
        jobs = self.queue.jobs
        counts: dict[JobStatus, int] = {}
        for job in jobs:
            counts[job.status] = counts.get(job.status, 0) + 1
        pending = counts.get(JobStatus.PENDING, 0)
        running = self.queue.running
        current = self.queue.current

        self.queue_heading.setText(f"{len(jobs)} {'recording' if len(jobs) == 1 else 'recordings'}")
        parts = []
        for status, word in ((JobStatus.DONE, "done"), (JobStatus.PENDING, "waiting"), (JobStatus.FAILED, "failed")):
            if n := counts.get(status):
                parts.append(f"{n} {word}")
        self.queue_summary.setText(", ".join(parts))
        self.queue_header.setVisible(bool(jobs))
        self.queue_stack.setCurrentIndex(1 if jobs else 0)

        again, again_selected = self._again_targets()
        self.run_bar.set_state(running, current is not None, pending, len(again), again_selected)
        refresh_icons(self.run_bar)

        selected = bool(self.queue_view.selected_ids())
        self.act_start.setEnabled(self.run_bar.start_btn.isEnabled())
        self.act_pause.setEnabled(running)
        self.act_stop.setEnabled(current is not None)
        self.act_remove.setEnabled(selected)
        self.act_retry_failed.setEnabled(bool(counts.get(JobStatus.FAILED)))
        self.act_clear.setEnabled(any(not j.is_active for j in jobs))

    def _update_empty_state(self) -> None:
        if self.models.installed():
            self.empty.show_ready()
        else:
            self.empty.show_model_missing()

    def _on_backend(self, backend: str) -> None:
        if backend:
            self.backend = backend
        if not resolve_whisper_cli(self.settings):
            self.top.engine.setText("Speech engine missing, see Settings")
        elif not resolve_ffmpeg(self.settings):
            self.top.engine.setText("ffmpeg missing, only WAV, MP3, FLAC and OGG work")
        else:
            self.top.engine.setText(f"Running on {self.backend}" if self.backend else "")

    # --- running --------------------------------------------------------------------------------

    def _sync_pending(self) -> None:
        """Waiting recordings always use the settings in the run bar."""
        pending = [j.id for j in self.queue.jobs if j.status == JobStatus.PENDING]
        if pending:
            self.queue.apply_options(pending, self.run_bar.options())

    def _again_targets(self) -> tuple[list[str], bool]:
        """Finished recordings the Transcribe button does again when none are waiting: the selected ones, else all.
        Also says whether they are the selected ones."""
        if self.queue.current is not None or any(j.status == JobStatus.PENDING for j in self.queue.jobs):
            return [], False
        selected = [j for j in map(self.queue.get, self.queue_view.selected_ids()) if j and not j.is_active]
        if selected:
            return [j.id for j in selected], True
        return [j.id for j in self.queue.jobs if not j.is_active], False

    def _start_or_pause(self) -> None:
        if self.queue.running:
            self.queue.pause()
            self._toast("The queue stops after this recording.")
            return
        self._start(self._again_targets()[0])

    def _start(self, again: list[str]) -> None:
        """Start the waiting recordings and those in ``again``. Finished ones are only reset once nothing can be
        cancelled any more, so cancelling leaves them as they were."""
        if self.queue.current is None and not resolve_whisper_cli(self.settings):
            inform(
                self,
                "Speech engine missing",
                "K-Whisper could not find whisper-cli.",
                "Choose it in Settings under Speech engine.",
            )
            return
        self._sync_pending()
        jobs = [j for j in self.queue.jobs if j.status == JobStatus.PENDING or j.id in again]
        policy = self._existing_files_policy(jobs)
        if policy is None:
            return
        self.queue.on_existing = policy
        if again:
            self._retry(again)
        self._start_queue()

    def _transcribe_again(self, ids: list[str]) -> None:
        if self.queue.running or self.queue.current is not None:
            self._retry(ids)  # the running queue picks them up
        else:
            self._start(ids)

    def _existing_files_policy(self, jobs: list[Job]) -> str | None:
        """What happens to files that already exist ("replace", "number" or "skip"), asking when the settings say
        so. None means the user cancelled."""
        if self.settings.existing_files != "ask":
            return self.settings.existing_files
        existing = self.queue.existing_outputs(jobs, self.run_bar.options())
        if not existing:
            return "number"
        files = [p for paths in existing.values() for p in paths]
        shown = ", ".join(p.name for p in files[:3]) + (f" and {len(files) - 3} more" if len(files) > 3 else "")
        example = f"{files[0].stem}-2{files[0].suffix}"
        them = "it" if len(files) == 1 else "them"
        box = message_box(
            self,
            "Files already exist",
            "1 file already exists." if len(files) == 1 else f"{len(files)} files already exist.",
            f"{shown}\n\nReplace {them} with the new transcription, or keep both and save the new files with a "
            f"number, such as {example}?",
        )
        # With the other alternative on the left, so Cancel and the default sit together on the right; DestructiveRole
        # would set it apart with a wide gap on macOS (see confirm()).
        replace = box.addButton("Replace", QMessageBox.ButtonRole.ActionRole)
        replace.setProperty("variant", "danger")
        repolish(replace)
        keep = box.addButton("Keep both", QMessageBox.ButtonRole.AcceptRole)
        keep.setProperty("variant", "primary")
        repolish(keep)
        skip = box.addButton(
            "Skip this recording" if len(existing) == 1 else "Skip these recordings", QMessageBox.ButtonRole.ActionRole
        )
        cancel = box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(keep)
        box.setEscapeButton(cancel)
        remember = QCheckBox("Do this every time (you can change it in Settings)")
        box.setCheckBox(remember)
        box.exec()
        policy = {replace: "replace", keep: "number", skip: "skip"}.get(box.clickedButton())
        if policy and remember.isChecked():
            self.settings.existing_files = policy
            self.settings.save()
        return policy

    def _start_queue(self) -> None:
        if not self.queue.current:
            self._run_started = time.time()
        self.queue.start()

    def _on_models_changed(self) -> None:
        self._refresh_model_list()
        self._update_empty_state()

    def _model_sizes(self) -> dict[str, int]:
        return {name: self.models.size_of(name) for name in self.models.installed()}

    def _refresh_model_list(self) -> None:
        sizes = self._model_sizes()
        self.run_bar.set_installed_models(sizes)
        # The chosen model can be missing (deleted, or never downloaded); new recordings then use the biggest one.
        if sizes and self.run_bar.options().model not in sizes:
            self.run_bar.set_options(self.run_bar.options().updated(model=max(sizes, key=sizes.__getitem__)))
            self._options_changed()

    def _retry(self, ids: list[str]) -> None:
        self.queue.retry(ids)
        self._sync_pending()

    def _retry_failed(self) -> None:
        self._transcribe_again([j.id for j in self.queue.jobs if j.status == JobStatus.FAILED])

    def _remove_selected(self) -> None:
        self.queue.remove(self.queue_view.selected_ids())

    # --- adding files ---------------------------------------------------------------------------

    def add_paths(self, paths: list[Path]) -> None:
        added = self.queue.add_paths(paths, self.run_bar.options())
        self.show_page(PAGE_QUEUE)
        if not added:
            self._toast("Nothing new to add: no audio or video files, or they are already waiting.")
        else:
            self._toast(f"Added {added} {'recording' if added == 1 else 'recordings'}")

    def _add_files(self) -> None:
        patterns = " ".join(f"*{ext}" for ext in sorted(MEDIA_EXTENSIONS))
        files, _ = QFileDialog.getOpenFileNames(self, "Add recordings", "", f"Audio and video ({patterns})")
        if files:
            self.add_paths([Path(f) for f in files])

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Add a folder of recordings")
        if folder:
            self.add_paths([Path(folder)])

    # --- options --------------------------------------------------------------------------------

    def _use_model(self, filename: str) -> None:
        self.run_bar.set_options(self.run_bar.options().updated(model=filename))
        self._refresh_model_list()
        self._options_changed()
        self._toast(f"New recordings use {model_name(filename)}")

    def _options_changed(self) -> None:
        self.models_page.set_current_model(self.run_bar.options().model)
        self._sync_pending()
        self._save_timer.start()
        self._update_state()
        self._update_empty_state()

    def _persist_settings(self) -> None:
        self.settings.options = self.run_bar.options().to_dict()
        self.settings.save()

    def _open_advanced(self) -> None:
        dialog = AdvancedDialog(self.run_bar.options(), self.settings.custom_presets, self)
        accepted = dialog.exec()
        self.settings.custom_presets = dialog.saved
        if accepted:
            self.run_bar.set_options(dialog.options())
            self._refresh_model_list()
            self._options_changed()
        self._persist_settings()

    # --- job events -----------------------------------------------------------------------------

    def _on_job_finished(self, job_id: str) -> None:
        job = self.queue.get(job_id)
        if job and job.status == JobStatus.FAILED:
            self._toast(f"{job.name} failed. Double-click it to see why.", 6000)

    def _on_all_done(self) -> None:
        # Count only this run; earlier results stay in the queue across sessions.
        recent = [j for j in self.queue.jobs if j.finished >= self._run_started]
        done = sum(1 for j in recent if j.status == JobStatus.DONE)
        failed = sum(1 for j in recent if j.status == JobStatus.FAILED)
        if not done and not failed:
            return
        message = f"Finished: {done} done" + (f", {failed} failed." if failed else ".")
        self._toast(message, 5000)
        # The toast is enough while K-Whisper is in front; the notification is for someone working elsewhere.
        if (
            not self.settings.notify_when_done
            or QApplication.applicationState() == Qt.ApplicationState.ApplicationActive
        ):
            return
        if QSystemTrayIcon.isSystemTrayAvailable():
            if self._tray is None:
                self._tray = QSystemTrayIcon(self.windowIcon() or QIcon(), self)
            self._tray.show()
            self._tray.showMessage(APP_NAME, message)
            # The icon is only a vehicle for the notification; don't leave it in the menu bar or tray.
            QTimer.singleShot(10_000, self._tray.hide)
        QApplication.alert(self)

    # --- context menu ---------------------------------------------------------------------------

    def _open_job(self, job: Job) -> None:
        if job.status == JobStatus.FAILED:
            LogDialog(job, self).exec()
        elif job.outputs:
            reveal(Path(job.outputs[0]))

    def _open_file(self, path: Path) -> None:
        if not path.exists():
            self._toast(f"{path.name} is no longer there. It was moved, renamed or deleted.", 5000)
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _row_action(self, job_id: str, action: str, pos: QPoint) -> None:
        job = self.queue.get(job_id)
        if job is None:
            return
        if action.startswith("open:"):
            self._open_file(Path(job.outputs[int(action.removeprefix("open:"))]))
        elif action == "open-menu":
            menu = QMenu(self)
            for out in map(Path, job.outputs):
                menu.addAction(f"Open {out.suffix.lstrip('.').upper()}", lambda p=out: self._open_file(p))
            menu.exec(pos)
        elif action == "reveal":
            reveal(Path(job.outputs[0]))
        elif action == "log":
            LogDialog(job, self).exec()
        elif action == "retry":
            self._transcribe_again([job.id])
        elif action == "stop":
            self.queue.stop()

    def _queue_menu(self, pos) -> None:
        ids = self.queue_view.selected_ids()
        if not ids:
            return
        jobs = [j for j in (self.queue.get(i) for i in ids) if j]
        first = jobs[0]
        menu = QMenu(self)
        if len(jobs) == 1 and first.outputs:
            for out in map(Path, first.outputs):
                menu.addAction(f"Open {out.suffix.lstrip('.').upper()}", lambda p=out: self._open_file(p))
            menu.addAction(f"Show in {FILE_MANAGER}", lambda: reveal(Path(first.outputs[0])))
            menu.addSeparator()
        if any(not j.is_active for j in jobs):
            menu.addAction("Transcribe again", lambda: self._transcribe_again(ids))
        if any(j is self.queue.current for j in jobs):
            menu.addAction("Stop", self.queue.stop)
        if len(jobs) == 1:
            menu.addAction("Show log", lambda: LogDialog(first, self).exec())
        if len(jobs) == 1 and first.status == JobStatus.PENDING:
            menu.addSeparator()
            menu.addAction("Move up", lambda: self.queue.move(first.id, -1))
            menu.addAction("Move down", lambda: self.queue.move(first.id, 1))
        if any(j is not self.queue.current for j in jobs):
            menu.addSeparator()
            menu.addAction("Remove from queue", lambda: self.queue.remove(ids))
        menu.exec(self.queue_view.viewport().mapToGlobal(pos))

    # --- dialogs --------------------------------------------------------------------------------

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self.backend, self)
        if dialog.exec():
            old_models_dir = self.settings.models_dir
            dialog.apply()
            self.settings.save()
            install(self.settings.theme)
            # Only a changed folder is switched to; one that was unreachable at start stays on the fallback.
            if self.settings.models_dir != old_models_dir:
                self.models.set_models_dir(self.settings.resolved_models_dir())
            self._on_backend("")

    def _about(self) -> None:
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<h3>{APP_NAME} {__version__}</h3>"
            "<p>Subtitles and transcripts made on your own computer with "
            f'<a href="https://github.com/ggml-org/whisper.cpp">whisper.cpp</a> {whisper_cpp_version()}.</p>'
            f"<p>Models folder: {self.models.models_dir}<br>"
            f"Downloaded models: {len(self.models.installed())} ({format_size(self.models.disk_usage())})</p>"
            "<p>Uses Qt (PySide6), FFmpeg (LGPL), Atkinson Hyperlegible (OFL) and Lucide icons (ISC).</p>",
        )

    # --- lifecycle ------------------------------------------------------------------------------

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.toast.isVisible():
            self.toast.reposition()

    def closeEvent(self, event) -> None:
        if self.queue.current is not None:
            details = (
                f"{self.queue.current.name} is being transcribed. It waits in the queue and starts over next time."
            )
            if not confirm(self, APP_NAME, "Stop transcribing and quit?", details, "Quit", destructive=True):
                event.ignore()
                return
            self.queue.shutdown()
        self._persist_settings()
        self.queue.save()
        event.accept()
