"""Download the UI assets into src/k_whisper/resources/ (committed to the repo):
Lucide icons and the Atkinson Hyperlegible fonts.

Re-run after adding a name to ICONS:  uv run python scripts/fetch_ui_assets.py
"""

import urllib.request
from pathlib import Path

LUCIDE_VERSION = "1.43.0"
BASE = f"https://unpkg.com/lucide-static@{LUCIDE_VERSION}"
GOOGLE_FONTS_COMMIT = "95f4904fc8bcf26d3420fe315560c96417c6dec7"
FONTS_BASE = f"https://raw.githubusercontent.com/google/fonts/{GOOGLE_FONTS_COMMIT}/ofl"
FONTS = {
    "AtkinsonHyperlegibleNext.ttf": "atkinsonhyperlegiblenext/AtkinsonHyperlegibleNext[wght].ttf",
    "AtkinsonHyperlegibleMono.ttf": "atkinsonhyperlegiblemono/AtkinsonHyperlegibleMono[wght].ttf",
    "OFL.txt": "atkinsonhyperlegiblenext/OFL.txt",
}

ICONS = [
    "audio-lines",
    "check",
    "chevron-down",
    "circle-stop",
    "download",
    "ellipsis",
    "file-up",
    "folder-open",
    "folder-plus",
    "pause",
    "play",
    "plus",
    "rotate-ccw",
    "settings",
    "sliders-horizontal",
    "trash-2",
]

RESOURCES = Path(__file__).resolve().parent.parent / "src" / "k_whisper" / "resources"


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url) as resp:
        return resp.read()


def main() -> None:
    icons = RESOURCES / "icons"
    icons.mkdir(parents=True, exist_ok=True)
    for old in icons.glob("*.svg"):
        old.unlink()
    for name in ICONS:
        (icons / f"{name}.svg").write_bytes(fetch(f"{BASE}/icons/{name}.svg"))
    (icons / "LICENSE").write_bytes(fetch(f"{BASE}/LICENSE"))

    fonts = RESOURCES / "fonts"
    fonts.mkdir(parents=True, exist_ok=True)
    for target, source in FONTS.items():
        (fonts / target).write_bytes(fetch(f"{FONTS_BASE}/{source}"))
    print(f"{len(ICONS)} icons and {len(FONTS) - 1} fonts written to {RESOURCES}")


if __name__ == "__main__":
    main()
