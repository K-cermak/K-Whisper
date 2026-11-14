"""Shared helper for build scripts: normalized platform key such as ``macos-arm64``."""

import platform
import sys


def platform_key() -> str:
    if sys.platform == "darwin":
        system = "macos"
    elif sys.platform == "win32":
        system = "windows"
    else:
        system = "linux"

    machine = platform.machine().lower()
    if machine in ("arm64", "aarch64"):
        arch = "arm64"
    elif machine in ("x86_64", "amd64"):
        arch = "x64"
    else:
        raise SystemExit(f"Unsupported architecture: {machine}")
    return f"{system}-{arch}"


if __name__ == "__main__":
    print(platform_key())
