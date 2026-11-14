"""The run bar under the queue: model, what to make and language on the left; Advanced options and the button that
starts the work on the right."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from k_whisper.engine.languages import LANGUAGES
from k_whisper.engine.options import MODE_LABELS, TranscribeOptions, advanced_changes, output_mode, with_mode
from k_whisper.models.catalog import describe, format_size, parse_name
from k_whisper.ui.theme import ui_font
from k_whisper.ui.widgets import SearchCombo, Segmented, button, label

MANAGE_MODELS = "__manage__"
FIELD_HEIGHT = 34


def model_name(filename: str) -> str:
    return filename.removeprefix("ggml-").removesuffix(".bin")


def _field(caption: str, widget: QWidget) -> QVBoxLayout:
    box = QVBoxLayout()
    box.setSpacing(5)
    lbl = label(caption, "field")
    lbl.setBuddy(widget)
    box.addWidget(lbl)
    box.addWidget(widget)
    return box


class RunBar(QWidget):
    changed = Signal()
    start_clicked = Signal()
    advanced_clicked = Signal()
    manage_models_clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("RunBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self._opts = TranscribeOptions()
        self._sizes: dict[str, int] = {}
        self._loading = False

        self.model = QComboBox()
        # Room for the usual "large-v3-turbo-q5_0 (574.0 MB)" without cutting it off, measured with the padding
        # and arrow of the stylesheet.
        self.model.ensurePolished()
        self.model.addItem("large-v3-turbo-q5_0 (574.0 MB)")
        self.model.setMinimumWidth(self.model.sizeHint().width())
        self.model.clear()
        self.model.setMaximumWidth(340)
        self.model.setAccessibleName("Model")
        self.model.activated.connect(self._model_activated)
        # Without a downloaded model there is nothing to choose: a button in its place leads to the Models page.
        self.get_model_btn = button("Download a model…", "download")
        self.get_model_btn.setToolTip("Opens the Models page")
        self.get_model_btn.clicked.connect(self.manage_models_clicked)
        self.model_slot = QStackedWidget()
        self.model_slot.addWidget(self.model)
        self.model_slot.addWidget(self.get_model_btn)
        self.mode = Segmented(MODE_LABELS)
        self.mode.setAccessibleName("What to make")
        self.mode.changed.connect(self._mode_changed)
        self.language = SearchCombo("Search languages")
        self.language.setMinimumWidth(185)
        self.language.setMaximumWidth(260)
        self.language.setMaxVisibleItems(18)
        self.language.setAccessibleName("Spoken language")
        self.language.addItem("Detect automatically", "auto")
        for code, name in LANGUAGES:
            self.language.addItem(name, code)
        self.language.currentIndexChanged.connect(self._primary_changed)
        self.translate = QCheckBox("Translate to English")
        self.translate.toggled.connect(self._primary_changed)

        self.start_btn = button("Transcribe", "play", "primary", large=True)
        self.start_btn.clicked.connect(self.start_clicked)
        self.advanced_btn = button("Advanced options", "sliders-horizontal")
        self.advanced_btn.setToolTip("Output formats, subtitle lines, silence, names and terms, hardware")
        self.advanced_btn.clicked.connect(self.advanced_clicked)

        # Same height for combos and the segmented control, so the field captions line up.
        for w in (self.model, self.get_model_btn, self.language, *self.mode.group.buttons(), self.advanced_btn):
            w.setFixedHeight(FIELD_HEIGHT)

        fields = QHBoxLayout()
        fields.setSpacing(20)
        fields.addLayout(_field("Model", self.model_slot), 3)
        fields.addLayout(_field("Make", self.mode))
        fields.addLayout(_field("Spoken language", self.language), 2)
        translate_box = QVBoxLayout()
        translate_box.addStretch(1)
        translate_box.addWidget(self.translate)
        translate_box.addSpacing(8)
        fields.addLayout(translate_box)
        fields.addStretch(0)

        # Wide enough for the longest label, so the column never changes width mid-run.
        metrics = QFontMetrics(ui_font(14, QFont.Weight.Bold))
        labels = ("Transcribe 999 recordings", "Transcribe 99 selected again")
        self.start_btn.setMinimumWidth(max(metrics.horizontalAdvance(t) for t in labels) + 76)
        # Both columns sit on the bottom edge, so the fields line up with the Transcribe button.
        left = QVBoxLayout()
        left.addStretch(1)
        left.addLayout(fields)
        right = QVBoxLayout()
        right.setSpacing(8)
        right.addStretch(1)
        right.addWidget(self.advanced_btn)
        right.addWidget(self.start_btn)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 14, 24, 16)
        layout.setSpacing(28)
        layout.addLayout(left, 1)
        layout.addLayout(right)

    # --- options --------------------------------------------------------------------------------

    def set_installed_models(self, sizes: dict[str, int]) -> None:
        """The downloaded models with their sizes. Without any there is nothing to choose and nothing to start."""
        self._loading = True
        self._sizes = sizes
        self.model.clear()
        if sizes:
            for name in sorted(sizes, key=lambda f: (sizes[f], f)):
                self.model.addItem(f"{model_name(name)} ({format_size(sizes[name])})", name)
                self.model.setItemData(self.model.count() - 1, describe(name), Qt.ItemDataRole.ToolTipRole)
            self.model.insertSeparator(self.model.count())
            self.model.addItem("Download other models…", MANAGE_MODELS)
            self.model.setCurrentIndex(max(0, self.model.findData(self._opts.model)))
        self.model_slot.setCurrentWidget(self.model if sizes else self.get_model_btn)
        self._loading = False

    def _model_activated(self) -> None:
        if self.model.currentData() == MANAGE_MODELS:
            self.model.setCurrentIndex(max(0, self.model.findData(self._opts.model)))
            self.manage_models_clicked.emit()
            return
        self._primary_changed()

    def _mode_changed(self, mode: str) -> None:
        self._opts = with_mode(self._opts, mode)
        self._update_advanced()
        self.changed.emit()

    def _primary_changed(self, *_args) -> None:
        if self._loading:
            return
        model = self.model.currentData()
        self._opts = self._opts.updated(
            model=model if model and model != MANAGE_MODELS else self._opts.model,
            language=self.language.currentData(),
            translate=self.translate.isChecked(),
        )
        self._sync_language_rules()
        self.changed.emit()

    def _sync_language_rules(self) -> None:
        """English-only models cannot hear other languages, Turbo models were not trained to translate (they
        answer in the spoken language), and translating English to English does nothing."""
        family, english_only, _quant = parse_name(self._opts.model)
        can_translate = "turbo" not in family
        self._loading = True
        if english_only:
            self.language.setCurrentIndex(self.language.findData("en"))
            self._opts = self._opts.updated(language="en", translate=False)
        if not can_translate:
            self._opts = self._opts.updated(translate=False)
        self.translate.setChecked(self._opts.translate)
        self.language.setEnabled(not english_only)
        self.language.setToolTip("This model only understands English" if english_only else "")
        self.translate.setEnabled(can_translate and self._opts.language != "en")
        self.translate.setToolTip(
            "Write the subtitles or transcript in English, whatever language is spoken"
            if can_translate
            else "Turbo models cannot translate. Choose large-v3 or medium for that."
        )
        self._loading = False

    def set_options(self, opts: TranscribeOptions) -> None:
        self._loading = True
        self._opts = opts
        if (idx := self.model.findData(opts.model)) >= 0:
            self.model.setCurrentIndex(idx)
        self.mode.set_value(output_mode(opts))
        self.language.setCurrentIndex(max(0, self.language.findData(opts.language)))
        self.translate.setChecked(opts.translate)
        self._loading = False
        self._sync_language_rules()
        self._update_advanced()

    def options(self) -> TranscribeOptions:
        return self._opts

    def _update_advanced(self) -> None:
        changes = len(advanced_changes(self._opts)) + (output_mode(self._opts) is None)
        self.advanced_btn.setText(f"Advanced options ({changes} changed)" if changes else "Advanced options")

    # --- state ----------------------------------------------------------------------------------

    def set_state(self, running: bool, has_current: bool, pending: int, again: int = 0, selected: bool = False) -> None:
        """``again``: finished recordings the button would transcribe again when none are waiting, the selected
        ones if ``selected``."""
        if running:
            self.start_btn.setText("Pause after this one")
            self.start_btn.setProperty("iconName", "pause")
            self.start_btn.setToolTip("Finish the current recording, then stop")
        elif has_current:
            self.start_btn.setText("Continue")
            self.start_btn.setProperty("iconName", "play")
            self.start_btn.setToolTip("")
        elif pending:
            noun = "recording" if pending == 1 else "recordings"
            self.start_btn.setText(f"Transcribe {pending} {noun}")
            self.start_btn.setProperty("iconName", "play")
            self.start_btn.setToolTip("")
        elif again:
            self.start_btn.setText(f"Transcribe {again} selected again" if selected else f"Transcribe {again} again")
            self.start_btn.setProperty("iconName", "rotate-ccw")
            self.start_btn.setToolTip(
                f"Transcribe the selected {'recording' if again == 1 else 'recordings'} again with the settings above"
                if selected
                else "Transcribe the finished recordings again with the settings above. Select rows to choose which."
            )
        else:
            self.start_btn.setText("Transcribe")
            self.start_btn.setProperty("iconName", "play")
            self.start_btn.setToolTip("Add recordings to the queue first")
        can_start = bool(self._sizes) and (pending > 0 or again > 0)
        if not self._sizes and not (running or has_current):
            self.start_btn.setToolTip("Download a model on the Models page first")
        self.start_btn.setEnabled(running or has_current or can_start)
