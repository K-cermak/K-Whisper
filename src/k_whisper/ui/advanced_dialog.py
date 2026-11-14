"""Advanced options window: everything that is not model, output mode or language."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from k_whisper.engine.cli import auto_threads
from k_whisper.engine.options import OUTPUT_FORMATS, TranscribeOptions, output_mode, with_mode
from k_whisper.ui.widgets import (
    align_forms,
    button,
    confirm,
    dialog_footer,
    form_section,
    label,
    refresh_icons,
    rule,
)

FORMAT_LABELS = {
    "srt": "SRT subtitles",
    "vtt": "WebVTT subtitles (for web video)",
    "txt": "Plain text",
    "tsv": "Table with start, end and text (TSV)",
    "json": "JSON with the timing of every word (for further processing)",
}


def _spin(lo: int, hi: int, suffix: str = "", special: str = "") -> QSpinBox:
    box = QSpinBox()
    box.setRange(lo, hi)
    box.setFixedWidth(120)
    if suffix:
        box.setSuffix(suffix)
    if special:
        box.setSpecialValueText(special)
    return box


def _dspin(lo: float, hi: float, step: float, decimals: int = 2, suffix: str = "") -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(lo, hi)
    box.setSingleStep(step)
    box.setDecimals(decimals)
    box.setFixedWidth(120)
    if suffix:
        box.setSuffix(suffix)
    return box


class AdvancedDialog(QDialog):
    def __init__(self, opts: TranscribeOptions, saved: dict[str, dict], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Advanced options")
        self.resize(620, 760)
        self.saved = saved
        self._base = opts
        self._forms: list[QFormLayout] = []

        body = QWidget()
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setContentsMargins(28, 24, 28, 24)
        self.body_layout.setSpacing(10)
        intro = label(
            "These apply to the recordings you transcribe from now on. Most recordings need none of them.",
            "muted",
            wrap=True,
        )
        self.body_layout.addWidget(intro)
        self._build_setups()
        self._build_output()
        self._build_cues()
        self._build_prompt()
        self._build_silence()
        self._build_decoding()
        self._build_hardware()
        self.body_layout.addStretch(1)
        align_forms(self._forms)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        reset = button("Reset to defaults", "rotate-ccw", "quiet")
        reset.clicked.connect(lambda: self.set_options(self._defaults()))
        cancel = button("Cancel")
        cancel.clicked.connect(self.reject)
        self.apply_btn = apply = button("Use these settings", None, "primary")
        apply.setDefault(True)
        apply.clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(scroll, 1)
        layout.addWidget(rule())
        layout.addLayout(dialog_footer([reset], [cancel, apply]))
        self.set_options(opts)
        refresh_icons(self)

    # --- construction ---------------------------------------------------------------------------

    def _section(self, title: str, note: str = "") -> QFormLayout:
        self._forms.append(form_section(self.body_layout, title, note))
        return self._forms[-1]

    def _build_setups(self) -> None:
        form = self._section(
            "Saved setups", "Keep all of these, together with the model and language, under a name to load later."
        )
        row = QHBoxLayout()
        self.setups = QComboBox()
        self.setups.setMinimumWidth(200)
        self.setups.setAccessibleName("Saved setups")
        load = button("Load")
        load.clicked.connect(self._load_setup)
        save = button("Save current…")
        save.clicked.connect(self._save_setup)
        self.delete_setup = button("Delete", None, "quiet")
        self.delete_setup.clicked.connect(self._delete_setup)
        row.addWidget(self.setups, 1)
        row.addWidget(load)
        row.addWidget(save)
        row.addWidget(self.delete_setup)
        form.addRow(row)
        self._fill_setups()

    def _build_output(self) -> None:
        form = self._section("Output files", "Overrides the Subtitles, Transcript and Both choice in the main window.")
        self.formats = {fmt: QCheckBox(FORMAT_LABELS[fmt]) for fmt in OUTPUT_FORMATS}
        for cb in self.formats.values():
            cb.toggled.connect(self._check_formats)
            form.addRow(cb)
        self.formats_error = label("Choose at least one kind of file.", "error")
        self.formats_error.hide()
        form.addRow(self.formats_error)

    def _build_cues(self) -> None:
        form = self._section("Subtitle lines", "How recognized speech is split into subtitles that are easy to read.")
        self.resegment = QCheckBox("Split into readable subtitles (recommended)")
        form.addRow(self.resegment)
        self.max_chars = _spin(10, 200, " characters")
        form.addRow("Longest line", self.max_chars)
        self.max_lines = _spin(1, 4, " lines")
        form.addRow("Lines per subtitle", self.max_lines)
        self.max_duration = _dspin(1, 30, 0.5, 1, " s")
        form.addRow("Longest subtitle", self.max_duration)
        self.min_duration = _dspin(0, 5, 0.1, 1, " s")
        form.addRow("Shortest subtitle", self.min_duration)
        self.min_gap = _dspin(0, 1, 0.01, 2, " s")
        form.addRow("Gap between subtitles", self.min_gap)
        fields = (self.max_chars, self.max_lines, self.max_duration, self.min_duration, self.min_gap)
        self.resegment.toggled.connect(lambda on: [f.setEnabled(on) for f in fields])

    def _build_prompt(self) -> None:
        form = self._section(
            "Names and terms", "Write names, places or jargon as they should be spelled. Helps with rare words."
        )
        self.prompt = QLineEdit()
        self.prompt.setPlaceholderText("e.g. Brno, Masaryk University, PySide")
        form.addRow(self.prompt)
        self.carry_prompt = QCheckBox("Keep using them through long recordings")
        form.addRow(self.carry_prompt)

    def _build_silence(self) -> None:
        form = self._section(
            "Silence", "Skipping silence stops invented text in quiet passages. Needs a small extra download."
        )
        self.vad = QCheckBox("Skip silent parts")
        form.addRow(self.vad)
        self.vad_threshold = _dspin(0.05, 0.95, 0.05)
        form.addRow("Speech sensitivity", self.vad_threshold)
        self.vad_min_speech = _spin(0, 5000, " ms")
        form.addRow("Shortest speech", self.vad_min_speech)
        self.vad_min_silence = _spin(0, 5000, " ms")
        form.addRow("Shortest pause", self.vad_min_silence)
        fields = (self.vad_threshold, self.vad_min_speech, self.vad_min_silence)
        self.vad.toggled.connect(lambda on: [f.setEnabled(on) for f in fields])

    def _build_decoding(self) -> None:
        form = self._section("Decoding", "Lower beam size is faster; higher can be slightly more accurate.")
        self.beam_size = _spin(1, 16)
        form.addRow("Beam size", self.beam_size)
        self.best_of = _spin(1, 16)
        form.addRow("Candidates", self.best_of)
        self.temperature = _dspin(0, 1, 0.1)
        form.addRow("Temperature", self.temperature)
        self.no_speech = _dspin(0, 1, 0.05)
        form.addRow("No-speech threshold", self.no_speech)
        self.temperature_fallback = QCheckBox("Retry with more randomness when decoding fails")
        form.addRow(self.temperature_fallback)
        self.suppress_nst = QCheckBox("Leave out sounds like [music] or (laughs)")
        form.addRow(self.suppress_nst)

    def _build_hardware(self) -> None:
        form = self._section("Hardware")
        self.use_gpu = QCheckBox("Use the graphics card (Metal or Vulkan) when available")
        form.addRow(self.use_gpu)
        self.gpu_device = _spin(0, 16)
        form.addRow("Graphics card number", self.gpu_device)
        self.flash_attn = QCheckBox("Flash attention (faster on most graphics cards)")
        form.addRow(self.flash_attn)
        self.threads = _spin(0, 64, special=f"Automatic ({auto_threads()})")
        form.addRow("Processor threads", self.threads)
        self.use_gpu.toggled.connect(self.gpu_device.setEnabled)

    def _check_formats(self) -> None:
        ok = any(cb.isChecked() for cb in self.formats.values())
        self.formats_error.setVisible(not ok)
        self.apply_btn.setEnabled(ok)

    # --- saved setups ---------------------------------------------------------------------------

    def _fill_setups(self, select: str | None = None) -> None:
        self.setups.clear()
        for name in sorted(self.saved):
            self.setups.addItem(name)
        if not self.saved:
            self.setups.addItem("No saved setups")
        self.setups.setEnabled(bool(self.saved))
        self.delete_setup.setEnabled(bool(self.saved))
        if select:
            self.setups.setCurrentText(select)

    def _load_setup(self) -> None:
        name = self.setups.currentText()
        if name in self.saved:
            self.set_options(TranscribeOptions.from_dict(self.saved[name]))

    def _save_setup(self) -> None:
        name, ok = QInputDialog.getText(self, "Save setup", "Name for this setup:")
        name = name.strip()
        if ok and name:
            self.saved[name] = self.options().to_dict()
            self._fill_setups(name)

    def _delete_setup(self) -> None:
        name = self.setups.currentText()
        question = f"Delete the saved setup “{name}”?"
        if name in self.saved and confirm(self, "Delete setup", question, "", "Delete", destructive=True):
            del self.saved[name]
            self._fill_setups()

    # --- values ---------------------------------------------------------------------------------

    def _defaults(self) -> TranscribeOptions:
        """Defaults for everything but the main window's choices: model, language and what to make."""
        base = self._base
        defaults = TranscribeOptions(model=base.model, language=base.language, translate=base.translate)
        mode = output_mode(base)
        return with_mode(defaults, mode) if mode else defaults

    def set_options(self, o: TranscribeOptions) -> None:
        self._base = o
        for fmt, cb in self.formats.items():
            cb.setChecked(fmt in o.formats)
        self.resegment.setChecked(o.resegment)
        self.max_chars.setValue(o.max_chars_per_line)
        self.max_lines.setValue(o.max_lines)
        self.max_duration.setValue(o.max_duration)
        self.min_duration.setValue(o.min_duration)
        self.min_gap.setValue(o.min_gap)
        self.prompt.setText(o.prompt)
        self.carry_prompt.setChecked(o.carry_prompt)
        self.vad.setChecked(o.vad)
        self.vad_threshold.setValue(o.vad_threshold)
        self.vad_min_speech.setValue(o.vad_min_speech_ms)
        self.vad_min_silence.setValue(o.vad_min_silence_ms)
        self.beam_size.setValue(o.beam_size)
        self.best_of.setValue(o.best_of)
        self.temperature.setValue(o.temperature)
        self.no_speech.setValue(o.no_speech_threshold)
        self.temperature_fallback.setChecked(o.temperature_fallback)
        self.suppress_nst.setChecked(o.suppress_non_speech)
        self.use_gpu.setChecked(o.use_gpu)
        self.gpu_device.setValue(o.gpu_device)
        self.flash_attn.setChecked(o.flash_attn)
        self.threads.setValue(o.threads)
        # toggled is not emitted when the state does not change; sync the dependent fields explicitly.
        for cb in (self.resegment, self.vad, self.use_gpu):
            cb.toggled.emit(cb.isChecked())
        self._check_formats()

    def options(self) -> TranscribeOptions:
        return self._base.updated(
            formats=[fmt for fmt, cb in self.formats.items() if cb.isChecked()],
            resegment=self.resegment.isChecked(),
            max_chars_per_line=self.max_chars.value(),
            max_lines=self.max_lines.value(),
            max_duration=self.max_duration.value(),
            min_duration=self.min_duration.value(),
            min_gap=self.min_gap.value(),
            prompt=self.prompt.text(),
            carry_prompt=self.carry_prompt.isChecked(),
            vad=self.vad.isChecked(),
            vad_threshold=self.vad_threshold.value(),
            vad_min_speech_ms=self.vad_min_speech.value(),
            vad_min_silence_ms=self.vad_min_silence.value(),
            beam_size=self.beam_size.value(),
            best_of=self.best_of.value(),
            temperature=self.temperature.value(),
            no_speech_threshold=self.no_speech.value(),
            temperature_fallback=self.temperature_fallback.isChecked(),
            suppress_non_speech=self.suppress_nst.isChecked(),
            use_gpu=self.use_gpu.isChecked(),
            gpu_device=self.gpu_device.value(),
            flash_attn=self.flash_attn.isChecked(),
            threads=self.threads.value(),
        )
