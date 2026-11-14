"""Build whisper-cli and ffmpeg command lines; parse their output."""

import os
import re
from pathlib import Path

from k_whisper.engine.options import TranscribeOptions


def auto_threads() -> int:
    return max(1, min(os.cpu_count() or 4, 8))


def whisper_args(
    opts: TranscribeOptions,
    model_path: Path,
    audio_path: Path,
    output_base: Path,
    vad_model_path: Path | None = None,
) -> list[str]:
    args = [
        "-m",
        str(model_path),
        "-f",
        str(audio_path),
        "-of",
        str(output_base),
        "-ojf",
        "-pp",
        "-l",
        opts.language or "auto",
        "-t",
        str(opts.threads or auto_threads()),
        "-bs",
        str(opts.beam_size),
        "-bo",
        str(opts.best_of),
        "-tp",
        f"{opts.temperature:g}",
        "-nth",
        f"{opts.no_speech_threshold:g}",
    ]
    if opts.translate:
        args.append("-tr")
    if not opts.temperature_fallback:
        args.append("-nf")
    if opts.prompt.strip():
        args += ["--prompt", opts.prompt.strip()]
        if opts.carry_prompt:
            args.append("--carry-initial-prompt")
    if opts.suppress_non_speech:
        args.append("-sns")
    if opts.vad and vad_model_path:
        args += [
            "--vad",
            "-vm",
            str(vad_model_path),
            "-vt",
            f"{opts.vad_threshold:g}",
            "-vspd",
            str(opts.vad_min_speech_ms),
            "-vsd",
            str(opts.vad_min_silence_ms),
        ]
    if not opts.use_gpu:
        args.append("-ng")
    elif opts.gpu_device:
        args += ["-dev", str(opts.gpu_device)]
    if not opts.flash_attn:
        args.append("-nfa")
    return args


def ffmpeg_args(source: Path, wav_path: Path) -> list[str]:
    return [
        "-hide_banner",
        "-nostdin",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-sn",
        "-dn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        "-progress",
        "pipe:1",
        "-nostats",
        str(wav_path),
    ]


_PROGRESS = re.compile(r"progress\s*=\s*(\d+)%")
_SEGMENT = re.compile(r"^\[(\d+:\d\d:\d\d\.\d{3}) --> (\d+:\d\d:\d\d\.\d{3})\]\s*(.*)$")
_LANGUAGE = re.compile(r"auto-detected language:\s*(\w+)")
_DURATION = re.compile(r"Duration:\s*(\d+):(\d\d):(\d\d(?:\.\d+)?)")
_OUT_TIME = re.compile(r"^out_time_us=(\d+)")


def parse_whisper_progress(line: str) -> int | None:
    m = _PROGRESS.search(line)
    return int(m.group(1)) if m else None


def parse_whisper_segment(line: str) -> tuple[str, str, str] | None:
    m = _SEGMENT.match(line.strip())
    return (m.group(1), m.group(2), m.group(3).strip()) if m else None


def parse_detected_language(line: str) -> str | None:
    m = _LANGUAGE.search(line)
    return m.group(1) if m else None


def parse_ffmpeg_duration(line: str) -> float | None:
    m = _DURATION.search(line)
    if not m:
        return None
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def parse_ffmpeg_out_time(line: str) -> float | None:
    m = _OUT_TIME.match(line.strip())
    return int(m.group(1)) / 1_000_000 if m else None


def parse_backend(line: str) -> str | None:
    """Return a human readable backend name from whisper.cpp init logs."""
    if "using MTL" in line or "using Metal" in line:
        return "Metal"
    if "ggml_vulkan: Found" in line or "using Vulkan" in line:
        return "Vulkan"
    if "using CUDA" in line:
        return "CUDA"
    if "no GPU found" in line:
        return "CPU"
    return None
