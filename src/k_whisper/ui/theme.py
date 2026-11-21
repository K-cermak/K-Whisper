"""Design tokens, fonts, the application stylesheet and tinted Lucide icons (see docs/DESIGN.md)."""

from dataclasses import dataclass
from functools import cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QObject, QRectF, QStandardPaths, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

RESOURCES = Path(__file__).resolve().parent.parent / "resources"
ICON_DIR = RESOURCES / "icons"
MODES = ("system", "light", "dark")

UI_FAMILY = "Atkinson Hyperlegible Next"
MONO_FAMILY = "Atkinson Hyperlegible Mono"
FALLBACK_MONO = ["Menlo", "Consolas", "DejaVu Sans Mono", "monospace"]


@dataclass(frozen=True)
class Tokens:
    dark: bool
    desk: str  # window background
    sheet: str  # lists, inputs, run bar
    sheet_alt: str  # pressed and hovered surfaces
    ink: str
    graphite: str
    faint: str
    rule: str
    rule_strong: str
    accent: str  # signal blue: the Transcribe action, progress, selection, focus
    accent_hover: str
    accent_soft: str
    accent_text: str  # accent used as text or thin lines on a sheet
    on_accent: str
    band: str  # live caption band
    band_text: str
    band_progress: str
    done: str
    failed: str


LIGHT = Tokens(
    dark=False,
    desk="#E9ECEF",
    sheet="#FFFFFF",
    sheet_alt="#F2F4F6",
    ink="#1E2328",
    graphite="#5D6670",
    faint="#828B95",
    rule="#D3D8DD",
    rule_strong="#B8C0C8",
    accent="#1F5FAD",
    accent_hover="#194F92",
    accent_soft="#E4EDF9",
    accent_text="#1F5FAD",
    on_accent="#FFFFFF",
    band="#16191C",
    band_text="#F4F2EA",
    band_progress="#5B9BE8",
    done="#2E7A4E",
    failed="#B83A2B",
)

DARK = Tokens(
    dark=True,
    desk="#1D2125",
    sheet="#262B30",
    sheet_alt="#2E343A",
    ink="#E8EBEE",
    graphite="#A2ABB4",
    faint="#78818A",
    rule="#3A4047",
    rule_strong="#4C545C",
    accent="#3A73C0",
    # Darker on hover: a lighter blue would drop white text below 4.5:1.
    accent_hover="#3166AE",
    accent_soft="#233B5C",
    accent_text="#7FB0EE",
    on_accent="#FFFFFF",
    band="#101315",
    band_text="#F4F2EA",
    band_progress="#5B9BE8",
    done="#6FCF97",
    failed="#F08A7E",
)


def load_fonts() -> None:
    for name in ("AtkinsonHyperlegibleNext.ttf", "AtkinsonHyperlegibleMono.ttf"):
        QFontDatabase.addApplicationFont(str(RESOURCES / "fonts" / name))


def mono_font(pixel_size: int = 12) -> QFont:
    font = QFont()
    font.setFamilies([MONO_FAMILY, *FALLBACK_MONO])
    font.setPixelSize(pixel_size)
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


def ui_font(pixel_size: int = 13, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont(UI_FAMILY)
    font.setPixelSize(pixel_size)
    font.setWeight(weight)
    return font


@cache
def _svg(name: str) -> str:
    return (ICON_DIR / f"{name}.svg").read_text(encoding="utf-8")


@cache
def _pixmap(name: str, color: str, size: int, ratio: float) -> QPixmap:
    data = _svg(name).replace("currentColor", color)
    renderer = QSvgRenderer(QByteArray(data.encode()))
    pm = QPixmap(round(size * ratio), round(size * ratio))
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    renderer.render(painter, QRectF(0, 0, pm.width(), pm.height()))
    painter.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def pixmap(name: str, color: str, size: int = 18) -> QPixmap:
    app = QGuiApplication.instance()
    ratio = app.devicePixelRatio() if isinstance(app, QGuiApplication) else 2.0
    return _pixmap(name, color, size, max(2.0, ratio))


def logo(size: int) -> QPixmap:
    """The K-Whisper bird without a background; on dark surfaces its body is lighter to stay visible."""
    renderer = QSvgRenderer(str(RESOURCES / ("logo-dark.svg" if theme().tokens.dark else "logo.svg")))
    app = QGuiApplication.instance()
    ratio = max(2.0, app.devicePixelRatio() if isinstance(app, QGuiApplication) else 2.0)
    pm = QPixmap(round(size * ratio), round(size * ratio))
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    renderer.render(painter, QRectF(0, 0, pm.width(), pm.height()))
    painter.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def icon(name: str, color: str | None = None) -> QIcon:
    t = theme().tokens
    result = QIcon()
    for size in (16, 18, 20, 24):
        result.addPixmap(pixmap(name, color or t.graphite, size), QIcon.Mode.Normal)
        result.addPixmap(pixmap(name, t.faint, size), QIcon.Mode.Disabled)
    return result


def _write_indicator(name: str, color: str, folder: Path) -> str:
    path = folder / f"{name}-{color.lstrip('#')}.svg"
    if not path.exists():
        path.write_text(_svg(name).replace("currentColor", color).replace('stroke-width="2"', 'stroke-width="3"'))
    return path.as_posix()


def stylesheet(t: Tokens, assets: Path) -> str:
    chevron = _write_indicator("chevron-down", t.graphite, assets)
    check = _write_indicator("check", t.on_accent, assets)
    return f"""
* {{ font-family: "{UI_FAMILY}"; }}
QWidget {{ color: {t.ink}; font-size: 13px; }}
QMainWindow, QDialog, QWidget#Page {{ background: {t.desk}; }}
QToolTip {{ background: {t.ink}; color: {t.sheet}; border: none; padding: 5px 8px; }}

QWidget#TopBar {{ background: {t.desk}; border-bottom: 1px solid {t.rule}; }}
QLabel#Wordmark {{ font-size: 15px; font-weight: 700; }}
QToolButton#Tab {{
    background: transparent; border: none; border-bottom: 2px solid transparent;
    padding: 12px 1px 10px 1px; color: {t.graphite}; font-size: 14px;
}}
QToolButton#Tab:hover {{ color: {t.ink}; }}
QToolButton#Tab:checked {{ color: {t.ink}; border-bottom-color: {t.accent}; font-weight: 600; }}

QWidget#RunBar {{ background: {t.sheet}; border-top: 1px solid {t.rule}; }}
QLabel[role="title"] {{ font-size: 22px; font-weight: 700; }}
QLabel[role="heading"] {{ font-size: 15px; font-weight: 600; }}
QLabel[role="muted"] {{ color: {t.graphite}; }}
QLabel[role="small"] {{ color: {t.graphite}; font-size: 12px; }}
QLabel[role="field"] {{ color: {t.graphite}; }}
QLabel[role="error"] {{ color: {t.failed}; }}
QLabel[role="name"] {{ font-size: 14px; font-weight: 600; }}
QLabel[role="tag"] {{
    color: {t.graphite}; font-size: 12px; font-weight: 600;
    border: 1px solid {t.rule_strong}; border-radius: 4px; padding: 0 6px;
}}
/* setFont() loses to the stylesheet's font-family, so monospace text is styled here too. */
QLabel[role="mono"] {{ font-family: "{MONO_FAMILY}"; font-size: 13px; color: {t.graphite}; }}

QPushButton {{
    background: {t.sheet}; border: 1px solid {t.rule_strong}; border-radius: 6px; padding: 6px 12px;
}}
QPushButton:hover {{ border-color: {t.graphite}; }}
QPushButton:pressed {{ background: {t.sheet_alt}; }}
QPushButton:focus {{ border-color: {t.accent}; }}
QPushButton:disabled {{ color: {t.faint}; border-color: {t.rule}; background: transparent; }}
QPushButton::menu-indicator {{
    image: url("{chevron}"); width: 12px; height: 12px; subcontrol-position: right center; right: 8px;
}}
QPushButton[menu="true"] {{ padding-right: 26px; }}
QPushButton[variant="primary"] {{
    background: {t.accent}; border: 1px solid {t.accent}; color: {t.on_accent}; font-weight: 600;
}}
/* Only the one action of a page is large (Transcribe, the first model download); dialog buttons stay level. */
QPushButton[variant="primary"][large="true"] {{ font-size: 14px; font-weight: 700; padding: 9px 20px; }}
QPushButton[variant="primary"]:hover {{ background: {t.accent_hover}; border-color: {t.accent_hover}; }}
QPushButton[variant="primary"]:focus {{ border: 2px solid {t.ink}; }}
QPushButton[variant="primary"]:disabled {{
    background: {t.sheet_alt}; border-color: {t.rule}; color: {t.faint};
}}
/* Status colors only appear as text, so a destructive button is an ordinary one with red text. */
QPushButton[variant="danger"] {{ color: {t.failed}; font-weight: 600; }}
QPushButton[variant="quiet"], QToolButton[variant="quiet"] {{
    background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 6px 8px;
    color: {t.graphite};
}}
QPushButton[variant="quiet"]:hover, QToolButton[variant="quiet"]:hover {{ color: {t.ink}; background: {t.sheet_alt}; }}
QPushButton[variant="quiet"]:focus, QToolButton[variant="quiet"]:focus {{ border-color: {t.accent}; }}
QToolButton[variant="quiet"]::menu-indicator {{ image: none; width: 0; }}

QPushButton[segment] {{
    background: {t.sheet}; border: 1px solid {t.rule_strong}; border-radius: 0; padding: 6px 14px; color: {t.graphite};
}}
QPushButton[segment="first"] {{ border-top-left-radius: 6px; border-bottom-left-radius: 6px; }}
QPushButton[segment="last"] {{ border-top-right-radius: 6px; border-bottom-right-radius: 6px; }}
QPushButton[segment="middle"], QPushButton[segment="last"] {{ border-left: none; }}
QPushButton[segment]:hover {{ color: {t.ink}; }}
QPushButton[segment]:focus {{ color: {t.accent_text}; }}
QPushButton[segment]:checked {{ background: {t.accent_soft}; color: {t.accent_text}; font-weight: 600; }}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit {{
    background: {t.sheet}; border: 1px solid {t.rule_strong}; border-radius: 6px; padding: 5px 8px;
    selection-background-color: {t.accent}; selection-color: {t.on_accent};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {{
    border-color: {t.accent};
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    color: {t.faint}; background: {t.desk}; border-color: {t.rule};
}}
/* combobox-popup: 0 drops the list below the field; Fusion's default popup covers the field and ignores
   maxVisibleItems, so the hundred spoken languages filled the whole screen height. */
QComboBox {{ padding-right: 26px; combobox-popup: 0; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ image: url("{chevron}"); width: 14px; height: 14px; }}
QComboBox QAbstractItemView {{
    background: {t.sheet}; border: 1px solid {t.rule_strong}; padding: 4px; outline: none;
    selection-background-color: {t.accent_soft}; selection-color: {t.ink};
}}
/* Arrows hidden via QSS: QAbstractSpinBox.NoButtons combined with a stylesheet collapses the editor to 1 px. */
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border; width: 0px; height: 0px; border: none;
}}

QCheckBox, QRadioButton {{ spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px; height: 16px; border: 1.5px solid {t.graphite}; background: {t.sheet};
}}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 10px; }}
QCheckBox::indicator:checked {{ background: {t.accent}; border-color: {t.accent}; image: url("{check}"); }}
/* A thick border draws the dot; the content box shrinks so the outer size stays 20 px (the 1.5 px border of the
   unchecked state takes 2 px each side), otherwise the radio jumps by a pixel when it is chosen. */
QRadioButton::indicator:checked {{ width: 10px; height: 10px; background: {t.sheet}; border: 5px solid {t.accent}; }}
QCheckBox::indicator:focus, QRadioButton::indicator:focus {{ border-color: {t.accent}; }}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{ border-color: {t.rule_strong}; }}
QCheckBox:disabled, QRadioButton:disabled {{ color: {t.faint}; }}

QListView#Queue, QListWidget#Models {{
    background: {t.sheet}; border: none; border-top: 1px solid {t.rule}; border-bottom: 1px solid {t.rule};
    outline: none;
}}
QListView#Queue[dropping="true"] {{ border: 2px solid {t.accent}; }}
QFrame#DropZone {{ border: 2px dashed {t.rule_strong}; border-radius: 10px; }}
QFrame#DropZone[dropping="true"] {{ background: {t.accent_soft}; border-color: {t.accent}; }}
QPlainTextEdit#Console {{
    background: {t.sheet}; border: 1px solid {t.rule}; border-radius: 0; padding: 8px;
    font-family: "{MONO_FAMILY}"; font-size: 12px;
}}
QProgressBar#Thin {{
    background: {t.rule}; border: none; border-radius: 2px; min-height: 4px; max-height: 4px;
}}
QProgressBar#Thin::chunk {{ background: {t.accent}; border-radius: 2px; }}

QFrame#SearchPopup {{ background: {t.sheet}; border: 1px solid {t.rule_strong}; }}
QFrame#SearchPopup QListView {{ background: {t.sheet}; border: none; outline: none; }}
QFrame#SearchPopup QListView::item {{ padding: 4px 6px; border-radius: 4px; }}
QFrame#SearchPopup QListView::item:hover {{ background: {t.sheet_alt}; }}
QFrame#SearchPopup QListView::item:selected {{ background: {t.accent_soft}; color: {t.ink}; }}

QMenu {{ background: {t.sheet}; border: 1px solid {t.rule_strong}; padding: 4px; }}
QMenu::item {{ padding: 6px 24px 6px 10px; border-radius: 4px; }}
QMenu::item:selected {{ background: {t.accent_soft}; }}
QMenu::item:disabled {{ color: {t.faint}; }}
QMenu::separator {{ height: 1px; background: {t.rule}; margin: 4px 6px; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background: {t.rule_strong}; border-radius: 3px; min-height: 30px; min-width: 30px; }}
QScrollBar::handle:hover {{ background: {t.faint}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
    background: none; border: none; width: 0; height: 0;
}}

QLabel#Toast {{ background: {t.ink}; color: {t.sheet}; border-radius: 6px; padding: 9px 14px; }}
QFrame#Rule {{ background: {t.rule}; border: none; max-height: 1px; min-height: 1px; }}
"""


def _palette(t: Tokens) -> QPalette:
    p = QPalette()
    role = QPalette.ColorRole
    for r, c in (
        (role.Window, t.desk),
        (role.WindowText, t.ink),
        (role.Base, t.sheet),
        (role.AlternateBase, t.sheet_alt),
        (role.Text, t.ink),
        (role.Button, t.sheet),
        (role.ButtonText, t.ink),
        (role.Highlight, t.accent),
        (role.HighlightedText, t.on_accent),
        (role.ToolTipBase, t.ink),
        (role.ToolTipText, t.sheet),
        (role.PlaceholderText, t.faint),
        (role.Mid, t.rule_strong),
        (role.Midlight, t.rule),
        (role.Dark, t.rule_strong),
        (role.Light, t.sheet),
        (role.Link, t.accent_text),
    ):
        p.setColor(r, QColor(c))
    for r in (role.Text, role.WindowText, role.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, r, QColor(t.faint))
    return p


class ThemeManager(QObject):
    changed = Signal()

    def __init__(self, mode: str = "system") -> None:
        super().__init__()
        self.mode = mode if mode in MODES else "system"
        self.tokens = self._resolve()
        app = QGuiApplication.instance()
        if isinstance(app, QGuiApplication):
            app.styleHints().colorSchemeChanged.connect(lambda _scheme: self.apply())

    def _resolve(self) -> Tokens:
        if self.mode == "light":
            return LIGHT
        if self.mode == "dark":
            return DARK
        app = QGuiApplication.instance()
        if isinstance(app, QGuiApplication):
            return DARK if app.styleHints().colorScheme() == Qt.ColorScheme.Dark else LIGHT
        return LIGHT

    def set_mode(self, mode: str) -> None:
        self.mode = mode if mode in MODES else "system"
        self.apply()

    def apply(self) -> None:
        self.tokens = self._resolve()
        app = QApplication.instance()
        if not isinstance(app, QApplication):
            return
        assets = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)) / "theme"
        assets.mkdir(parents=True, exist_ok=True)
        app.setStyle("Fusion")
        app.setPalette(_palette(self.tokens))
        app.setFont(ui_font())
        app.setStyleSheet(stylesheet(self.tokens, assets))
        self.changed.emit()


_manager: ThemeManager | None = None


def theme() -> ThemeManager:
    global _manager
    if _manager is None:
        _manager = ThemeManager()
    return _manager


def install(mode: str) -> ThemeManager:
    load_fonts()
    manager = theme()
    manager.set_mode(mode)
    return manager


def repolish(widget) -> None:
    """Re-evaluate the stylesheet after changing a dynamic property used in a selector."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
