# PyInstaller spec: uv run pyinstaller --noconfirm packaging/k-whisper.spec
# Expects whisper-cli and ffmpeg in vendor/<platform>/ (scripts/build_whispercpp.py, scripts/fetch_ffmpeg.py).

import os
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT / "scripts"))
from platform_key import platform_key  # noqa: E402

sys.path.insert(0, str(ROOT / "src"))
from k_whisper import APP_NAME, __version__  # noqa: E402

PLAT = platform_key()
VENDOR = ROOT / "vendor" / PLAT
ICONS = ROOT / "packaging" / "icons"
BINARY_SUFFIXES = (".dll", ".so", ".dylib", ".exe")

binaries, datas = [], [(str(ROOT / "src" / "k_whisper" / "resources"), "k_whisper/resources")]
for tool in ("whisper", "ffmpeg"):
    folder = VENDOR / tool
    if not folder.is_dir():
        raise SystemExit(f"Missing {folder}; run the scripts in scripts/ first")
    for f in sorted(folder.iterdir()):
        if not f.is_file():
            continue
        is_binary = os.access(f, os.X_OK) or f.suffix in BINARY_SUFFIXES or ".so." in f.name
        (binaries if is_binary else datas).append((str(f), tool))

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.Qt3DCore"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    console=False,
    icon=str(ICONS / ("icon.icns" if PLAT.startswith("macos") else "icon.ico")),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name=APP_NAME, upx=False)

if PLAT.startswith("macos"):
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=str(ICONS / "icon.icns"),
        bundle_identifier="cz.kcermak.kwhisper",
        version=__version__,
        info_plist={
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            "LSMinimumSystemVersion": "13.3",
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,
        },
    )
