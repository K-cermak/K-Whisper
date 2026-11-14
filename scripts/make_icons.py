"""Render the application icon from the logo and write PNG/ICO/ICNS variants.

The logo has no background, so the icon puts it on a white tile, as app icons on macOS are expected to look.
The generated files are committed; re-run only when the logo changes:
    uv run python scripts/make_icons.py
"""

import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "packaging" / "icons"
RESOURCES = ROOT / "src" / "k_whisper" / "resources"


def render(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size / 1024
    tile = QRectF(80 * s, 80 * s, 864 * s, 864 * s)
    radius = 196 * s

    # A soft shadow and a hairline keep the white tile visible on white backgrounds.
    if size >= 64:
        for i in range(12, 0, -1):
            shadow = QPainterPath()
            shadow.addRoundedRect(
                tile.adjusted(-i * s, (6 - i) * s, i * s, (14 + i) * s), radius + i * s, radius + i * s
            )
            p.fillPath(shadow, QColor(0, 0, 0, 3))
    path = QPainterPath()
    path.addRoundedRect(tile, radius, radius)
    p.fillPath(path, QColor("#FFFFFF"))
    p.setPen(QColor(0, 0, 0, 28))
    p.drawPath(path)

    inset = 110 * s
    QSvgRenderer(str(RESOURCES / "logo.svg")).render(p, tile.adjusted(inset, inset, -inset, -inset))
    p.end()
    return img


def main() -> None:
    app = QGuiApplication(sys.argv)  # noqa: F841 - needed for QImage text/painting backends
    ICONS.mkdir(parents=True, exist_ok=True)

    render(1024).save(str(ICONS / "icon.png"))
    render(512).save(str(RESOURCES / "icon.png"))
    render(256).save(str(ICONS / "icon.ico"))

    if sys.platform == "darwin":
        with tempfile.TemporaryDirectory() as tmp:
            iconset = Path(tmp) / "icon.iconset"
            iconset.mkdir()
            for base in (16, 32, 128, 256, 512):
                render(base).save(str(iconset / f"icon_{base}x{base}.png"))
                render(base * 2).save(str(iconset / f"icon_{base}x{base}@2x.png"))
            subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(ICONS / "icon.icns")], check=True)
    print("Icons written to", ICONS)


if __name__ == "__main__":
    main()
