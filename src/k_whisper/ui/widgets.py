"""Small building blocks shared by all windows: buttons, dialog forms, segmented control, searchable drop-down,
toast, empty queue."""

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QSize, QSortFilterProxyModel, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from k_whisper.ui.theme import icon, pixmap, repolish, theme


def label(text: str, role: str | None = None, wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    if role:
        lbl.setProperty("role", role)
    lbl.setWordWrap(wrap)
    return lbl


def rule() -> QFrame:
    line = QFrame()
    line.setObjectName("Rule")
    return line


def thin_progress() -> QProgressBar:
    bar = QProgressBar()
    bar.setObjectName("Thin")
    bar.setTextVisible(False)
    bar.setRange(0, 1000)
    return bar


class Button(QPushButton):
    """Push button with a readable gap between icon and text (Qt leaves about 2 px)."""

    def setText(self, text: str) -> None:  # noqa: N802 - Qt API
        super().setText(f" {text}" if self.property("iconName") and text else text)


def button(text: str, icon_name: str | None = None, variant: str | None = None, large: bool = False) -> Button:
    b = Button()
    if variant:
        b.setProperty("variant", variant)
    if large:
        b.setProperty("large", True)
    if icon_name:
        b.setProperty("iconName", icon_name)
        b.setIconSize(QSize(16, 16))
    b.setText(text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    # Keyboard focus only: a mouse click should not leave a focus outline behind.
    b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    return b


def tool(icon_name: str, tooltip: str) -> QToolButton:
    b = QToolButton()
    b.setProperty("variant", "quiet")
    b.setProperty("iconName", icon_name)
    b.setToolTip(tooltip)
    b.setAccessibleName(tooltip)
    b.setIconSize(QSize(18, 18))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    return b


def message_box(parent: QWidget | None, title: str, headline: str, details: str = "") -> QMessageBox:
    """A message without the style's icon (Fusion's look dated) and with a short headline: Qt sets the main text in
    bold on macOS, so everything else goes into the details."""
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(headline)
    box.setInformativeText(details)
    # Qt sizes the box to the headline, which squeezes the details into a narrow column.
    for name in ("qt_msgbox_label", "qt_msgbox_informativelabel"):
        if text := box.findChild(QLabel, name):
            text.setMinimumWidth(320)
    return box


def confirm(
    parent: QWidget | None, title: str, headline: str, details: str, action: str, destructive: bool = False
) -> bool:
    """Ask before ``action``, a verb such as "Delete". A destructive action is never the default button.

    It keeps the accept role even when destructive: on macOS Qt sets a destructive-role button 28 px apart from
    Cancel, an old Aqua rule that today's alerts no longer follow.
    """
    box = message_box(parent, title, headline, details)
    act = box.addButton(action, QMessageBox.ButtonRole.AcceptRole)
    act.setProperty("variant", "danger" if destructive else "primary")
    repolish(act)
    cancel = box.addButton(QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(cancel if destructive else act)
    box.setEscapeButton(cancel)
    box.exec()
    return box.clickedButton() is act


def inform(parent: QWidget | None, title: str, headline: str, details: str = "") -> None:
    box = message_box(parent, title, headline, details)
    ok = box.addButton(QMessageBox.StandardButton.Ok)
    ok.setProperty("variant", "primary")
    repolish(ok)
    box.exec()


def capped(widget: QWidget, width: int, center: bool = False) -> QHBoxLayout:
    """A wrapping label at most ``width`` wide. Inside a horizontal box it gets the height for the width it really
    has; a vertical box asks for the height at its full width, which clips the lines that wrap."""
    widget.setMaximumWidth(width)
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    # Stretch 0 on the spacers: they only get what is left once the label has reached its width.
    if center:
        row.addStretch(0)
    row.addWidget(widget, 1)
    row.addStretch(0)
    return row


def form_section(body: QVBoxLayout, title: str, note: str = "") -> QFormLayout:
    """Append a heading, an optional note and a form to a dialog's body."""
    if body.count():
        body.addSpacing(14)
    body.addWidget(label(title, "heading"))
    if note:
        body.addWidget(label(note, "muted", wrap=True))
    form = QFormLayout()
    form.setContentsMargins(0, 4, 0, 0)
    form.setHorizontalSpacing(16)
    form.setVerticalSpacing(9)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    body.addLayout(form)
    return form


def align_forms(forms: list[QFormLayout]) -> None:
    """Each form sizes its own label column; one shared width makes the fields of all sections line up."""
    labels = []
    for form in forms:
        for row in range(form.rowCount()):
            item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
            if item and item.widget():
                labels.append(item.widget())
    width = max((w.sizeHint().width() for w in labels), default=0)
    for w in labels:
        w.setMinimumWidth(width)


def dialog_footer(left: list[QWidget], right: list[QWidget]) -> QHBoxLayout:
    """Bottom row of a dialog: secondary actions on the left, Cancel and the default action equally wide on the
    right."""
    row = QHBoxLayout()
    row.setContentsMargins(28, 14, 28, 16)
    row.setSpacing(8)
    for w in left:
        row.addWidget(w)
    row.addStretch(1)
    width = max(96, *(b.sizeHint().width() for b in right))
    for b in right:
        b.setMinimumWidth(width)
        row.addWidget(b)
    return row


def refresh_icons(root: QWidget) -> None:
    """(Re)tint every button that declares an ``iconName`` property, e.g. after a theme change."""
    t = theme().tokens
    for b in [root, *root.findChildren(QPushButton), *root.findChildren(QToolButton)]:
        name = b.property("iconName")
        if not name or not isinstance(b, QPushButton | QToolButton):
            continue
        if b.property("variant") == "primary":
            color = t.on_accent
        elif b.property("variant") == "quiet":
            color = t.graphite
        else:
            color = t.ink
        b.setIcon(icon(name, color))


class Segmented(QWidget):
    """Adjacent exclusive buttons sharing one outline (a real segmented control, not separate pills)."""

    changed = Signal(str)

    def __init__(self, options: dict[str, str], parent=None) -> None:
        super().__init__(parent)
        self.group = QButtonGroup(self)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        keys = list(options)
        for i, key in enumerate(keys):
            b = QPushButton(options[key])
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            b.setProperty("key", key)
            b.setProperty("segment", "first" if i == 0 else "last" if i == len(keys) - 1 else "middle")
            self.group.addButton(b)
            layout.addWidget(b)
        self.group.buttonClicked.connect(lambda b: self.changed.emit(b.property("key")))

    def value(self) -> str | None:
        b = self.group.checkedButton()
        return b.property("key") if b else None

    def set_value(self, key: str | None) -> None:
        # Exclusive groups cannot be cleared directly; toggling exclusivity allows "no selection" (custom).
        self.group.setExclusive(False)
        for b in self.group.buttons():
            b.setChecked(b.property("key") == key)
        self.group.setExclusive(True)


class SearchCombo(QComboBox):
    """Drop-down whose list opens with a search field above it, for long lists such as the spoken languages.

    It stays a plain QComboBox to its users: the popup only filters the combo's own model and sets the current index.
    """

    def __init__(self, placeholder: str, parent=None) -> None:
        super().__init__(parent)
        self.popup = QFrame(self, Qt.WindowType.Popup)
        self.popup.setObjectName("SearchPopup")
        self.search = QLineEdit()
        self.search.setPlaceholderText(placeholder)
        self.search.setAccessibleName(placeholder)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model())
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.list = QListView()
        self.list.setModel(self.proxy)
        self.list.setUniformItemSizes(True)
        self.list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.clicked.connect(self._choose)
        self.search.textChanged.connect(self._filter)
        self.search.installEventFilter(self)
        layout = QVBoxLayout(self.popup)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        layout.addWidget(self.search)
        layout.addWidget(self.list)

    def showPopup(self) -> None:  # noqa: N802 - Qt API
        self.search.clear()
        self._filter("")
        if self.currentIndex() >= 0:
            current = self.proxy.mapFromSource(self.model().index(self.currentIndex(), 0))
            self.list.setCurrentIndex(current)
            self.list.scrollTo(current, QAbstractItemView.ScrollHint.PositionAtCenter)
        # The height stays the same while typing, so the list does not jump under the pointer.
        rows = min(self.maxVisibleItems(), self.count())
        self.list.setFixedHeight(rows * max(self.list.sizeHintForRow(0), 24) + 2 * self.list.frameWidth())
        self.popup.setFixedWidth(max(self.width(), 240))
        self.popup.adjustSize()
        below = self.mapToGlobal(QPoint(0, self.height() + 2))
        screen = self.screen().availableGeometry()
        if below.y() + self.popup.height() > screen.bottom():
            below = self.mapToGlobal(QPoint(0, -self.popup.height() - 2))
        self.popup.move(below)
        self.popup.show()
        self.search.setFocus()

    def hidePopup(self) -> None:  # noqa: N802 - Qt API
        self.popup.hide()

    def _filter(self, text: str) -> None:
        self.proxy.setFilterFixedString(text.strip())
        if text.strip() and self.proxy.rowCount():
            self.list.setCurrentIndex(self.proxy.index(0, 0))

    def _choose(self, index) -> None:
        row = self.proxy.mapToSource(index).row()
        self.popup.hide()
        self.setCurrentIndex(row)
        self.activated.emit(row)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt API
        if obj is self.search and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
                # Typing stays in the search field while the arrows move through the list.
                QCoreApplication.sendEvent(self.list, event)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self.list.currentIndex().isValid():
                    self._choose(self.list.currentIndex())
                return True
            if key == Qt.Key.Key_Escape:
                self.popup.hide()
                return True
        return super().eventFilter(obj, event)


class Toast(QLabel):
    """Transient message floating at the bottom of its parent widget."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setWordWrap(True)
        self.setMaximumWidth(520)
        self.hide()
        self._timer = QTimer(self, singleShot=True)
        self._timer.timeout.connect(self.hide)
        self.bottom_margin = 24

    def show_message(self, text: str, msec: int = 3500) -> None:
        self.setText(text)
        self.adjustSize()
        self.reposition()
        self.raise_()
        self.show()
        self._timer.start(msec)

    def reposition(self) -> None:
        parent = self.parentWidget()
        self.move((parent.width() - self.width()) // 2, parent.height() - self.height() - self.bottom_margin)


class EmptyQueue(QWidget):
    """What the queue shows before any recording is added: a drop zone for files and folders.

    Without a downloaded model the first step is the Models page, so that is where it points then.
    """

    files_dropped = Signal(list)
    choose_files = Signal()
    choose_folder = Signal()
    show_models = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("EmptyQueue")
        self.setAcceptDrops(True)

        self.mark = QLabel()
        self.title = label("", "title")
        self.body = label("", "muted", wrap=True)
        for lbl in (self.mark, self.title, self.body):
            lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.models_btn = button("Open Models", None, "primary", large=True)
        self.models_btn.clicked.connect(self.show_models)
        self.files_btn = button("Choose files…", "plus")
        self.folder_btn = button("Choose a folder…", "folder-plus")
        self.files_btn.clicked.connect(self.choose_files)
        self.folder_btn.clicked.connect(self.choose_folder)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch(1)
        for b in (self.models_btn, self.files_btn, self.folder_btn):
            row.addWidget(b)
        row.addStretch(1)

        self.zone = QFrame()
        self.zone.setObjectName("DropZone")
        center = Qt.AlignmentFlag.AlignHCenter
        inner = QVBoxLayout(self.zone)
        inner.setContentsMargins(32, 32, 32, 32)
        inner.setSpacing(10)
        inner.addStretch(2)
        inner.addWidget(self.mark, 0, center)
        inner.addSpacing(4)
        inner.addWidget(self.title, 0, center)
        inner.addLayout(capped(self.body, 480, center=True))
        inner.addSpacing(10)
        inner.addLayout(row)
        inner.addStretch(3)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(self.zone)
        theme().changed.connect(self._paint_mark)
        self._paint_mark()
        self.show_ready()

    def _paint_mark(self) -> None:
        self.mark.setPixmap(pixmap("audio-lines", theme().tokens.faint, 40))

    def _set(self, title: str, body: str, *, model_missing: bool = False) -> None:
        self.title.setText(title)
        self.body.setText(body)
        self.models_btn.setVisible(model_missing)
        self.files_btn.setVisible(not model_missing)
        self.folder_btn.setVisible(not model_missing)

    def show_ready(self) -> None:
        self._set(
            "Drop recordings here",
            "Interviews, lectures, podcasts or videos. Each one gets its subtitles or transcript saved "
            "next to it. Folders are searched for audio and video files.",
        )

    def show_model_missing(self) -> None:
        self._set(
            "First, download a speech model",
            "Transcription needs a speech model. Download one on the Models page, in the tabs at the top of the "
            "window.",
            model_missing=True,
        )

    def _set_dropping(self, dropping: bool) -> None:
        self.zone.setProperty("dropping", dropping)
        repolish(self.zone)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_dropping(True)

    def dragLeaveEvent(self, _event) -> None:
        self._set_dropping(False)

    def dropEvent(self, event) -> None:
        self._set_dropping(False)
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
