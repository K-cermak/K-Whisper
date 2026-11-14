"""Locations of bundled tools and per-user data."""

import platform
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
EXE_SUFFIX = ".exe" if IS_WINDOWS else ""


def platform_key() -> str:
    system = "macos" if IS_MACOS else "windows" if IS_WINDOWS else "linux"
    arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"
    return f"{system}-{arch}"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def tools_dir() -> Path:
    """Directory holding the ``whisper/`` and ``ffmpeg/`` tool folders."""
    if is_frozen():
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2] / "vendor" / platform_key()


def bundled_whisper_cli() -> Path | None:
    path = tools_dir() / "whisper" / f"whisper-cli{EXE_SUFFIX}"
    return path if path.exists() else None


def bundled_ffmpeg() -> Path | None:
    path = tools_dir() / "ffmpeg" / f"ffmpeg{EXE_SUFFIX}"
    if path.exists():
        return path
    found = shutil.which("ffmpeg")
    return Path(found) if found else None


def whisper_cpp_version() -> str:
    cli = bundled_whisper_cli()
    if cli and (cli.parent / "VERSION").exists():
        return (cli.parent / "VERSION").read_text().strip()
    return "unknown"


def data_dir() -> Path:
    path = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_models_dir() -> Path:
    return data_dir() / "models"
