"""Provide an LGPL ffmpeg binary in vendor/<platform>/ffmpeg/.

macOS and Linux: a small audio-only build from source (decoders and demuxers only, no external libraries).
Windows: the LGPL static build from BtbN/FFmpeg-Builds (building FFmpeg with MSVC is impractical).

Usage: python scripts/fetch_ffmpeg.py [--jobs N]
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from platform_key import platform_key  # noqa: E402

FFMPEG_VERSION = "9.0.2"
BTBN_BRANCH = "9.0"
SOURCE_URL = f"https://ffmpeg.org/releases/ffmpeg-{FFMPEG_VERSION}.tar.xz"
BTBN_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n{branch}-latest-{target}-lgpl-{branch}.zip"
)

ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = ROOT / "build" / "ffmpeg"

DEMUXERS = [
    "aac",
    "ac3",
    "aiff",
    "amr",
    "asf",
    "avi",
    "caf",
    "dts",
    "eac3",
    "flac",
    "flv",
    "matroska",
    "mov",
    "mp3",
    "mpegps",
    "mpegts",
    "ogg",
    "truehd",
    "w64",
    "wav",
    "wv",
]
DECODERS = [
    "aac",
    "aac_latm",
    "ac3",
    "alac",
    "amrnb",
    "amrwb",
    "dca",
    "eac3",
    "flac",
    "mp1",
    "mp1float",
    "mp2",
    "mp2float",
    "mp3",
    "mp3float",
    "opus",
    "truehd",
    "vorbis",
    "wavpack",
    "wmalossless",
    "wmapro",
    "wmav1",
    "wmav2",
    "pcm_alaw",
    "pcm_f32be",
    "pcm_f32le",
    "pcm_f64le",
    "pcm_mulaw",
    "pcm_s16be",
    "pcm_s16le",
    "pcm_s24be",
    "pcm_s24le",
    "pcm_s32be",
    "pcm_s32le",
    "pcm_u8",
    "adpcm_ima_wav",
    "adpcm_ms",
]
PARSERS = ["aac", "aac_latm", "ac3", "dca", "flac", "mpegaudio", "opus", "vorbis"]
FILTERS = ["abuffer", "abuffersink", "aformat", "anull", "aresample", "null"]


def configure_flags(prefix: Path) -> list[str]:
    flags = [
        f"--prefix={prefix}",
        "--disable-everything",
        "--disable-autodetect",
        "--disable-network",
        "--disable-doc",
        "--disable-ffplay",
        "--disable-ffprobe",
        "--disable-debug",
        "--enable-static",
        "--disable-shared",
        "--enable-small",
        "--enable-protocol=file,pipe",
        "--enable-muxer=wav",
        "--enable-encoder=pcm_s16le",
        "--enable-demuxer=" + ",".join(DEMUXERS),
        "--enable-decoder=" + ",".join(DECODERS),
        "--enable-parser=" + ",".join(PARSERS),
        "--enable-filter=" + ",".join(FILTERS),
        "--enable-swresample",
    ]
    if platform_key().endswith("x64") and not shutil.which("nasm"):
        flags.append("--disable-x86asm")
    if sys.platform == "darwin":
        flags.append("--extra-cflags=-mmacosx-version-min=13.3")
        flags.append("--extra-ldflags=-mmacosx-version-min=13.3")
    return flags


def download(url: str) -> bytes:
    print(f"Downloading {url}", flush=True)
    with urllib.request.urlopen(url) as resp:
        return resp.read()


def build_from_source(dest: Path, jobs: int) -> None:
    src = BUILD_DIR / f"ffmpeg-{FFMPEG_VERSION}"
    if not src.exists():
        BUILD_DIR.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(download(SOURCE_URL)), mode="r:xz") as tar:
            tar.extractall(BUILD_DIR, filter="data")
    prefix = BUILD_DIR / "install"
    flags = configure_flags(prefix)
    subprocess.run(["./configure", *flags], cwd=src, check=True)
    subprocess.run(["make", f"-j{jobs}", "ffmpeg"], cwd=src, check=True)

    shutil.copy2(src / "ffmpeg", dest / "ffmpeg")
    shutil.copy2(src / "COPYING.LGPLv2.1", dest / "LICENSE.txt")
    (dest / "BUILD_INFO.txt").write_text(
        f"FFmpeg {FFMPEG_VERSION} built from {SOURCE_URL}\nconfigure {' '.join(flags)}\n"
    )


def fetch_btbn(dest: Path, plat: str) -> None:
    target = "winarm64" if plat.endswith("arm64") else "win64"
    url = BTBN_URL.format(branch=BTBN_BRANCH, target=target)
    with zipfile.ZipFile(io.BytesIO(download(url))) as zf:
        for name in zf.namelist():
            base = Path(name).name
            if base in ("ffmpeg.exe", "LICENSE.txt"):
                (dest / base).write_bytes(zf.read(name))
    if not (dest / "ffmpeg.exe").exists():
        raise SystemExit("ffmpeg.exe not found in the BtbN archive")
    (dest / "BUILD_INFO.txt").write_text(f"FFmpeg LGPL build from {url}\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    args = parser.parse_args()

    plat = platform_key()
    dest = ROOT / "vendor" / plat / "ffmpeg"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    if plat.startswith("windows"):
        fetch_btbn(dest, plat)
    else:
        build_from_source(dest, args.jobs)
    print(f"ffmpeg installed into {dest}")


if __name__ == "__main__":
    main()
