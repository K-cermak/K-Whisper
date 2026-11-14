"""Models page: a short list of the models most people need, every variant on request, smallest first."""

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from k_whisper.models.catalog import RECOMMENDED, ModelInfo, describe, format_size
from k_whisper.models.manager import ModelManager
from k_whisper.ui.theme import theme
from k_whisper.ui.widgets import button, capped, confirm, inform, label, refresh_icons, thin_progress, tool

# What a non-specialist needs to know to choose; every other variant is behind "Show every variant".
CURATED = {
    RECOMMENDED: "The best balance of speed and accuracy. Start with this one.",
    "ggml-large-v3-turbo.bin": "The same model at full precision, three times the download.",
    "ggml-large-v3.bin": "Most accurate and slowest. For difficult recordings.",
    "ggml-medium.bin": "Accurate. Slow on older computers.",
    "ggml-small.bin": "Works well on clear speech.",
    "ggml-base.bin": "Fast, but misses more words.",
    "ggml-tiny.bin": "Fastest. Good enough for rough notes.",
}


class ModelRow(QWidget):
    def __init__(self, page: ModelsPage, info: ModelInfo) -> None:
        super().__init__()
        self.setObjectName("ModelRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.page = page
        self.info = info

        title = QHBoxLayout()
        title.setSpacing(8)
        title.addWidget(label(info.name, "name"))
        if info.filename == RECOMMENDED:
            title.addWidget(label("Recommended", "tag"))
        title.addStretch(1)
        note = CURATED.get(info.filename) if not page.show_all.isChecked() else None
        details = label(note or describe(info.filename), "muted")
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addLayout(title)
        text.addWidget(details)

        size = page.manager.size_of(info.filename)
        self.size = label(format_size(size) if size else "", "mono")
        self.size.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.size.setFixedWidth(90)

        self.state = label("", "muted")
        self.progress = thin_progress()
        state_box = QVBoxLayout()
        state_box.setContentsMargins(0, 0, 0, 0)
        state_box.setSpacing(5)
        state_box.addStretch(1)
        state_box.addWidget(self.state)
        state_box.addWidget(self.progress)
        state_box.addStretch(1)
        state = QWidget()
        state.setLayout(state_box)
        state.setFixedWidth(190)

        self.action = button("")
        self.action.setFixedWidth(104)
        self.action.clicked.connect(self._act)
        self.delete_btn = tool("trash-2", f"Delete {info.name} from this computer")
        self.delete_btn.clicked.connect(self._delete)

        # Hidden buttons keep their space, so the columns line up across rows.
        for w in (self.action, self.delete_btn):
            policy = w.sizePolicy()
            policy.setRetainSizeWhenHidden(True)
            w.setSizePolicy(policy)

        row = QHBoxLayout(self)
        row.setContentsMargins(24, 12, 20, 12)
        row.setSpacing(16)
        row.addLayout(text, 1)
        row.addWidget(self.size)
        row.addWidget(state)
        row.addWidget(self.action)
        row.addWidget(self.delete_btn)
        self.update_state()

    def update_state(self, received: int = 0, total: int = 0) -> None:
        t = theme().tokens
        manager = self.page.manager
        filename = self.info.filename
        downloading = filename in manager.downloads
        installed = manager.is_installed(filename) and not downloading
        in_use = installed and filename == self.page.current_model

        self.progress.setVisible(downloading)
        self.delete_btn.setVisible(installed)
        self.action.setVisible(not in_use)
        if downloading:
            self.state.setText(f"Downloading {round(received / total * 100)}%" if total else "Starting download…")
            self.state.setStyleSheet(f"color: {t.ink};")
            self.progress.setValue(round(received / total * 1000) if total else 0)
            self.action.setText("Cancel")
            self.action.setProperty("variant", "quiet")
        elif in_use:
            self.state.setText("Used for new recordings")
            self.state.setStyleSheet(f"color: {t.accent_text}; font-weight: 600;")
        elif installed:
            self.state.setText("Downloaded")
            self.state.setStyleSheet(f"color: {t.done};")
            self.action.setText("Use")
            self.action.setProperty("variant", None)
        else:
            self.state.setText("")
            self.action.setText("Download")
            self.action.setProperty("variant", None)
        self.action.style().unpolish(self.action)
        self.action.style().polish(self.action)

    def _act(self) -> None:
        manager = self.page.manager
        filename = self.info.filename
        if filename in manager.downloads:
            manager.cancel_download(filename)
        elif manager.is_installed(filename):
            self.page.use_requested.emit(filename)
        else:
            manager.download(manager.info_for(filename))
            self.update_state()

    def _delete(self) -> None:
        size = format_size(self.page.manager.size_of(self.info.filename))
        details = f"This frees {size} on this computer. You can download it again later."
        if confirm(self, "Delete model", f"Delete {self.info.name}?", details, "Delete", destructive=True):
            self.page.manager.delete(self.info.filename)


class ModelsPage(QWidget):
    use_requested = Signal(str)

    def __init__(self, manager: ModelManager, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Page")
        self.manager = manager
        self.rows: dict[str, ModelRow] = {}
        self.current_model = ""

        # The tab already says "Models"; the heading states what is on this computer instead.
        self.heading = label("", "title")
        intro = label(
            "Bigger models recognize more words but take longer. Compressed (quantized) versions store the same "
            "model with less precise numbers: two to three times smaller and faster, and almost as accurate. "
            "Q5 is the smallest, Q8 stays closer to the original.",
            "muted",
            wrap=True,
        )
        self.show_all = QCheckBox("Show every variant, including more compressed and English-only versions")
        self.show_all.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.show_all.toggled.connect(self._populate)

        self.list = QListWidget()
        self.list.setObjectName("Models")
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.usage = label("", "small")
        import_btn = button("Import a model file…", "file-up", "quiet")
        import_btn.setToolTip("Add a GGML model, for example one fine-tuned for your language")
        import_btn.clicked.connect(self._import)
        folder_btn = button("Open models folder", "folder-open", "quiet")
        folder_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.manager.models_dir))))
        footer = QHBoxLayout()
        footer.setContentsMargins(24, 10, 20, 14)
        footer.addWidget(self.usage, 1)
        footer.addWidget(import_btn)
        footer.addWidget(folder_btn)

        header = QVBoxLayout()
        header.setContentsMargins(24, 20, 24, 14)
        header.setSpacing(6)
        header.addWidget(self.heading)
        header.addLayout(capped(intro, 760))
        header.addSpacing(6)
        header.addWidget(self.show_all)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(header)
        layout.addWidget(self.list, 1)
        layout.addLayout(footer)

        manager.catalog_changed.connect(self._populate)
        manager.installed_changed.connect(self._populate)
        manager.download_progress.connect(self._on_progress)
        manager.download_finished.connect(self._on_finished)
        theme().changed.connect(self._populate)
        self._populate()
        self._refreshed = False

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._refreshed:
            self._refreshed = True
            self.manager.refresh_catalog()

    def set_current_model(self, filename: str) -> None:
        self.current_model = filename
        for row in self.rows.values():
            row.update_state()

    def _models(self) -> list[ModelInfo]:
        installed = set(self.manager.installed())
        known = {m.filename for m in self.manager.catalog}
        models = [self.manager.info_for(f) for f in installed if f not in known]
        if self.show_all.isChecked():
            models += self.manager.catalog
        else:
            models += [m for m in self.manager.catalog if m.filename in CURATED or m.filename in installed]
        return sorted(models, key=lambda m: (self.manager.size_of(m.filename), m.filename))

    def _populate(self) -> None:
        self.list.clear()
        self.rows = {}
        t = theme().tokens
        for info in self._models():
            row = ModelRow(self, info)
            row.setStyleSheet(f"QWidget#ModelRow {{ border-bottom: 1px solid {t.rule}; background: {t.sheet}; }}")
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, row.sizeHint().height()))
            self.list.addItem(item)
            self.list.setItemWidget(item, row)
            self.rows[info.filename] = row
        refresh_icons(self)
        for row in self.rows.values():
            row.update_state()
        count = len(self.manager.installed())
        self.heading.setText(
            "No models downloaded yet" if not count else f"{count} {'model' if count == 1 else 'models'} downloaded"
        )
        self.usage.setText(f"{format_size(self.manager.disk_usage())} of disk space used by models")
        self.usage.setToolTip(str(self.manager.models_dir))

    def select(self, filename: str) -> None:
        if row := self.rows.get(filename):
            for i in range(self.list.count()):
                if self.list.itemWidget(self.list.item(i)) is row:
                    self.list.scrollToItem(self.list.item(i))

    def _on_progress(self, filename: str, received: int, total: int) -> None:
        if row := self.rows.get(filename):
            row.update_state(received, total)

    def _on_finished(self, filename: str, error: str) -> None:
        if row := self.rows.get(filename):
            row.update_state()
        if error and error != "Cancelled":
            name = filename.removeprefix("ggml-").removesuffix(".bin")
            inform(self, "Download failed", f"{name} could not be downloaded.", error)

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import a model file", "", "GGML models (*.bin);;All files (*)")
        if path:
            self.manager.import_model(Path(path))
            self.usage.setText(f"Importing {Path(path).name}…")
