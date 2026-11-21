"""Render the application icon from the logo and write PNG/ICO/ICNS variants.

The logo (the bird, padded to a square viewBox) has no background, so the icon puts it on a white tile,
as app icons on macOS are expected to look.

On macOS it also writes an Icon Composer icon (AppIcon.icon) with a dark variant and compiles it with Xcode's
actool into Assets.car. Without it, macOS 26 darkens the classic icon itself in dark mode, eyes included.

The generated files are committed; re-run only when the logo changes:
    uv run python scripts/make_icons.py
"""

import json
import shutil
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
sys.path.insert(0, str(ROOT / "src"))
from k_whisper.ui.theme import DARK  # noqa: E402

# The bird takes the same share of the tile in both icon formats: 672 px of 864.
BIRD_SHARE = 672 / 864


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

    inset = 96 * s
    QSvgRenderer(str(RESOURCES / "logo.svg")).render(p, tile.adjusted(inset, inset, -inset, -inset))
    p.end()
    return img


def render_layer(svg: str, size: int = 1024) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    box = size * BIRD_SHARE
    offset = (size - box) / 2
    QSvgRenderer(str(RESOURCES / svg)).render(p, QRectF(offset, offset, box, box))
    p.end()
    return img


def srgb(hex_color: str) -> str:
    c = QColor(hex_color)
    return f"srgb:{c.redF():.5f},{c.greenF():.5f},{c.blueF():.5f},1.00000"


def write_icon_composer() -> None:
    """AppIcon.icon: the bird on a white tile, in dark mode the lightened bird on the app's dark sheet colour."""
    bundle = ICONS / "AppIcon.icon"
    shutil.rmtree(bundle, ignore_errors=True)
    (bundle / "Assets").mkdir(parents=True)
    render_layer("logo.svg").save(str(bundle / "Assets" / "bird.png"))
    render_layer("logo-dark.svg").save(str(bundle / "Assets" / "bird-dark.png"))
    spec = {
        "fill-specializations": [
            {"value": {"solid": srgb("#FFFFFF")}},
            {"appearance": "dark", "value": {"solid": srgb(DARK.sheet)}},
        ],
        "groups": [
            {
                "layers": [
                    {
                        "image-name-specializations": [
                            {"value": "bird.png"},
                            {"appearance": "dark", "value": "bird-dark.png"},
                        ],
                        "name": "bird",
                    }
                ],
                "shadow": {"kind": "neutral", "opacity": 0.3},
                "translucency": {"enabled": False, "value": 0.5},
            }
        ],
        "supported-platforms": {"squares": ["macOS"]},
    }
    (bundle / "icon.json").write_text(json.dumps(spec, indent=2) + "\n")

    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            ["xcrun", "actool", str(bundle), "--compile", tmp, "--platform", "macosx",
             "--minimum-deployment-target", "13.3", "--app-icon", "AppIcon",
             "--output-partial-info-plist", str(Path(tmp) / "partial.plist")],
            check=True, stdout=subprocess.DEVNULL,
        )  # fmt: skip
        shutil.copy(Path(tmp) / "Assets.car", ICONS / "Assets.car")


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
        write_icon_composer()
    print("Icons written to", ICONS)


if __name__ == "__main__":
    main()
