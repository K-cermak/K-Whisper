"""Build whisper-cli from a pinned whisper.cpp tag into vendor/<platform>/whisper/.

Usage: python scripts/build_whispercpp.py [--no-vulkan] [--windows-arm64-cross] [--jobs N]
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from platform_key import platform_key  # noqa: E402

WHISPER_CPP_TAG = "v1.9.5"
REPO_URL = "https://github.com/ggml-org/whisper.cpp.git"

ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = ROOT / "build" / "whispercpp"
HOST_TOOLCHAIN = BUILD_DIR / "host-toolchain.cmake"

# The Vulkan shader generator runs during the build, so a cross build also compiles it for the host. Left to
# itself ggml picks the first of cl, gcc, clang on PATH; on GitHub's Windows runners that is MinGW's gcc, and
# its program then fails to start (0xc0000139) against another libstdc++ DLL on PATH. clang is what the arm64
# build itself uses.
HOST_TOOLCHAIN_TEXT = """\
set(CMAKE_BUILD_TYPE Release)
set(CMAKE_C_COMPILER clang)
set(CMAKE_CXX_COMPILER clang++)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE NEVER)
"""


def run(cmd: list[str], **kwargs) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, **kwargs)


def cmake_options(plat: str, vulkan: bool, src: Path, cross: bool) -> list[str]:
    opts = [
        "-DCMAKE_BUILD_TYPE=Release",
        "-DWHISPER_BUILD_EXAMPLES=ON",
        "-DWHISPER_BUILD_TESTS=OFF",
        "-DWHISPER_BUILD_SERVER=OFF",
        "-DWHISPER_SDL2=OFF",
        "-DWHISPER_CURL=OFF",
        "-DGGML_NATIVE=OFF",
        # OpenMP would add a runtime dependency (libgomp / vcomp140) we would have to ship.
        "-DGGML_OPENMP=OFF",
    ]
    if plat.startswith("macos"):
        opts += [
            "-DBUILD_SHARED_LIBS=OFF",
            "-DGGML_METAL=ON",
            "-DGGML_METAL_EMBED_LIBRARY=ON",
            "-DCMAKE_OSX_DEPLOYMENT_TARGET=13.3",
        ]
    else:
        # Backends as runtime-loaded modules: a missing Vulkan loader or an old CPU
        # makes ggml skip that backend instead of whisper-cli failing to start.
        opts += [
            "-DBUILD_SHARED_LIBS=ON",
            "-DGGML_BACKEND_DL=ON",
            f"-DGGML_VULKAN={'ON' if vulkan else 'OFF'}",
            "-DCMAKE_BUILD_WITH_INSTALL_RPATH=ON",
            "-DCMAKE_INSTALL_RPATH=$ORIGIN",
        ]
        if plat.endswith("x64"):
            opts.append("-DGGML_CPU_ALL_VARIANTS=ON")
        if plat.startswith("windows"):
            opts.append("-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded")
    if cross:
        # Same approach as llama.cpp releases: clang targeting arm64 on an x64 host, so the Vulkan
        # shader generator can still run natively during the build.
        opts += ["-G", "Ninja Multi-Config", f"-DCMAKE_TOOLCHAIN_FILE={src / 'cmake' / 'arm64-windows-llvm.cmake'}"]
        if vulkan:
            opts.append(f"-DGGML_VULKAN_SHADERS_GEN_TOOLCHAIN={HOST_TOOLCHAIN.as_posix()}")
    return opts


def collect_outputs(build: Path, dest: Path, plat: str) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    exe = "whisper-cli.exe" if plat.startswith("windows") else "whisper-cli"
    patterns = [exe]
    if plat.startswith("windows"):
        patterns.append("*.dll")
    elif plat.startswith("linux"):
        patterns.append("*.so*")

    found_exe = False
    for pattern in patterns:
        for path in build.rglob(pattern):
            if not path.exists() or "CMakeFiles" in path.parts:
                continue
            # Dereference SONAME symlinks (libwhisper.so.1 -> ...): PyInstaller and zip archives handle
            # plain files more reliably, and the libraries are small.
            shutil.copy2(path.resolve(), dest / path.name)
            found_exe |= path.name == exe
    if not found_exe:
        raise SystemExit(f"{exe} not found in {build}")

    (dest / "VERSION").write_text(WHISPER_CPP_TAG + "\n")
    print(f"Installed into {dest}:")
    for p in sorted(dest.iterdir()):
        print("  ", p.name)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-vulkan", action="store_true", help="CPU-only build on Windows/Linux")
    parser.add_argument(
        "--windows-arm64-cross", action="store_true", help="cross-compile for Windows arm64 on an x64 host"
    )
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    args = parser.parse_args()

    plat = "windows-arm64" if args.windows_arm64_cross else platform_key()
    src = BUILD_DIR / f"src-{WHISPER_CPP_TAG}"
    build = BUILD_DIR / f"build-{plat}"
    dest = ROOT / "vendor" / plat / "whisper"

    if not src.exists():
        src.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--depth", "1", "--branch", WHISPER_CPP_TAG, REPO_URL, str(src)])

    if args.windows_arm64_cross:
        HOST_TOOLCHAIN.write_text(HOST_TOOLCHAIN_TEXT)
    options = cmake_options(plat, not args.no_vulkan, src, args.windows_arm64_cross)
    run(["cmake", "-S", str(src), "-B", str(build), *options])
    # No --target: with GGML_BACKEND_DL the backend modules are not link dependencies of whisper-cli.
    run(["cmake", "--build", str(build), "--config", "Release", "--parallel", str(args.jobs)])
    collect_outputs(build, dest, plat)


if __name__ == "__main__":
    main()
