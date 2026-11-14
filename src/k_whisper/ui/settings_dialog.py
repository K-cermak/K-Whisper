"""Settings window: where files go, appearance, and where the speech engine and models live."""

from pathlib import Path

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from k_whisper.batch.job import output_base_name
from k_whisper.models.catalog import RECOMMENDED
from k_whisper.paths import bundled_ffmpeg, bundled_whisper_cli, default_models_dir, whisper_cpp_version
from k_whisper.settings import AppSettings
from k_whisper.ui.widgets import (
    align_forms,
    button,
    dialog_footer,
    form_section,
    inform,
    label,
    refresh_icons,
    rule,
)

EXAMPLE = Path("interview.mp4")
EXISTING_FILES_LABELS = {
    "ask": "Ask me",
    "replace": "Replace them",
    "number": "Keep both (the new files get a number)",
    "skip": "Skip the recording",
}


def _path_row(edit: QLineEdit, directory: bool, title: str) -> QWidget:
    w = QWidget()
    row = QHBoxLayout(w)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(8)
    browse = button("Choose…")

    def pick() -> None:
        if directory:
            path = QFileDialog.getExistingDirectory(w, title, edit.text())
        else:
            path, _ = QFileDialog.getOpenFileName(w, title, edit.text())
        if path:
            edit.setText(path)

    browse.clicked.connect(pick)
    row.addWidget(edit, 1)
    row.addWidget(browse)
    return w


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, backend: str, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Settings")
        self.resize(660, 0)

        body = QVBoxLayout()
        body.setContentsMargins(28, 24, 28, 20)
        body.setSpacing(10)
        forms = []

        def section(title: str, note: str = ""):
            forms.append(form_section(body, title, note))
            return forms[-1]

        form = section("Where finished files go")
        self.next_to_source = QRadioButton("Next to each recording")
        self.to_folder = QRadioButton("All in one folder")
        group = QButtonGroup(self)
        group.addButton(self.next_to_source)
        group.addButton(self.to_folder)
        (self.to_folder if settings.output_mode == "folder" else self.next_to_source).setChecked(True)
        self.output_dir = QLineEdit(settings.output_dir)
        self.output_dir.setPlaceholderText("Choose a folder")
        form.addRow(self.next_to_source)
        form.addRow(self.to_folder)
        self.folder_row = _path_row(self.output_dir, True, "Folder for finished files")
        form.addRow(self.folder_row)
        self.to_folder.toggled.connect(self.folder_row.setEnabled)
        self.folder_row.setEnabled(self.to_folder.isChecked())
        self.template = QLineEdit(settings.filename_template)
        form.addRow("File name", self.template)
        self.preview = label("", "small", wrap=True)
        form.addRow("", self.preview)
        self.template.textChanged.connect(self._update_preview)
        self._update_preview()
        self.existing_files = QComboBox()
        for value, text in EXISTING_FILES_LABELS.items():
            self.existing_files.addItem(text, value)
        self.existing_files.setCurrentIndex(max(0, self.existing_files.findData(settings.existing_files)))
        self.existing_files.setMaximumWidth(320)
        form.addRow("If files exist", self.existing_files)

        form = section("Appearance and notifications")
        self.theme = QComboBox()
        for value, text in (("system", "Same as the system"), ("light", "Light"), ("dark", "Dark")):
            self.theme.addItem(text, value)
        self.theme.setCurrentIndex(max(0, self.theme.findData(settings.theme)))
        self.theme.setMaximumWidth(320)
        form.addRow("Theme", self.theme)
        self.notify = QCheckBox("Show a system notification when all recordings are done")
        self.notify.setChecked(settings.notify_when_done)
        form.addRow(self.notify)
        notify_note = label("Only while K-Whisper is in the background, e.g. during long recordings.", "small")
        # Indented to the checkbox text: indicator (16 px) plus its spacing (8 px).
        notify_note.setContentsMargins(24, 0, 0, 0)
        form.addRow(notify_note)

        form = section("Models")
        self.models_dir = QLineEdit(settings.models_dir)
        self.models_dir.setPlaceholderText(str(default_models_dir()))
        form.addRow("Folder", _path_row(self.models_dir, True, "Folder for models"))

        engine_note = f"whisper.cpp {whisper_cpp_version()}" + (f", last run on {backend}" if backend else "")
        form = section("Speech engine", f"{engine_note}. Leave these empty to use the copies included with K-Whisper.")
        self.cli = QLineEdit(settings.whisper_cli_path)
        self.cli.setPlaceholderText(str(bundled_whisper_cli() or "Not included, choose whisper-cli"))
        form.addRow("whisper-cli", _path_row(self.cli, False, "Choose whisper-cli"))
        self.ffmpeg = QLineEdit(settings.ffmpeg_path)
        self.ffmpeg.setPlaceholderText(str(bundled_ffmpeg() or "Not found, choose ffmpeg"))
        form.addRow("ffmpeg", _path_row(self.ffmpeg, False, "Choose ffmpeg"))

        # Show where a path starts (the disk or home folder), not its tail.
        for edit in (self.output_dir, self.models_dir, self.cli, self.ffmpeg):
            edit.setCursorPosition(0)

        align_forms(forms)

        cancel = button("Cancel")
        cancel.clicked.connect(self.reject)
        save = button("Save settings", None, "primary")
        save.setDefault(True)
        save.clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(body)
        layout.addWidget(rule())
        layout.addLayout(dialog_footer([], [cancel, save]))
        refresh_icons(self)

    def _update_preview(self) -> None:
        base = output_base_name(self.template.text().strip() or "{name}", EXAMPLE, "cs", RECOMMENDED)
        self.preview.setText(
            f"For interview.mp4 in Czech this gives {base}.srt. You can use {{name}}, {{lang}}, {{model}} and {{date}}."
        )

    def accept(self) -> None:
        if self.to_folder.isChecked() and not self.output_dir.text().strip():
            inform(
                self, "Choose a folder", "Choose the folder for finished files.", "Or keep them next to each recording."
            )
            return
        models_dir = self.models_dir.text().strip()
        if models_dir and models_dir != self.settings.models_dir:
            try:
                Path(models_dir).mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                inform(self, "Choose another folder", f"Models cannot be kept in {models_dir}.", str(exc))
                return
        super().accept()

    def apply(self) -> None:
        s = self.settings
        s.whisper_cli_path = self.cli.text().strip()
        s.ffmpeg_path = self.ffmpeg.text().strip()
        s.models_dir = self.models_dir.text().strip()
        s.output_mode = "folder" if self.to_folder.isChecked() and self.output_dir.text().strip() else "source"
        s.output_dir = self.output_dir.text().strip()
        s.filename_template = self.template.text().strip() or "{name}"
        s.existing_files = self.existing_files.currentData()
        s.notify_when_done = self.notify.isChecked()
        s.theme = self.theme.currentData()
