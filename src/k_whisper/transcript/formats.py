"""Subtitle and transcript export: SRT, VTT, TXT, TSV and JSON with word timings."""

import json
from collections.abc import Callable
from pathlib import Path

from k_whisper.transcript.model import Segment, Transcript


def format_timestamp(seconds: float, sep: str = ",", always_hours: bool = True) -> str:
    ms = max(0, round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    if h or always_hours:
        return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"
    return f"{m:02d}:{s:02d}{sep}{ms:03d}"


def parse_timestamp(text: str) -> float:
    """Accepts ``HH:MM:SS,mmm``, ``HH:MM:SS.mmm``, ``MM:SS.mmm`` and plain seconds."""
    text = text.strip().replace(",", ".")
    parts = text.split(":")
    if not 1 <= len(parts) <= 3:
        raise ValueError(f"Invalid timestamp: {text!r}")
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + float(part)
    return seconds


def _cues(transcript: Transcript) -> list[Segment]:
    return [s for s in transcript.segments if s.text.strip()]


def to_srt(transcript: Transcript) -> str:
    blocks = []
    for i, seg in enumerate(_cues(transcript), 1):
        blocks.append(f"{i}\n{format_timestamp(seg.start)} --> {format_timestamp(seg.end)}\n{seg.text.strip()}\n")
    return "\n".join(blocks)


def to_vtt(transcript: Transcript) -> str:
    blocks = ["WEBVTT\n"]
    for seg in _cues(transcript):
        start, end = format_timestamp(seg.start, "."), format_timestamp(seg.end, ".")
        blocks.append(f"{start} --> {end}\n{seg.text.strip()}\n")
    return "\n".join(blocks)


def to_txt(transcript: Transcript) -> str:
    return transcript.plain_text() + "\n"


def to_tsv(transcript: Transcript) -> str:
    lines = ["start\tend\ttext"]
    lines += [f"{round(s.start * 1000)}\t{round(s.end * 1000)}\t{s.plain_text}" for s in _cues(transcript)]
    return "\n".join(lines) + "\n"


def to_json(transcript: Transcript) -> str:
    return json.dumps(transcript.to_dict(), ensure_ascii=False, indent=1)


EXPORTERS: dict[str, tuple[str, Callable[[Transcript], str]]] = {
    "srt": (".srt", to_srt),
    "vtt": (".vtt", to_vtt),
    "txt": (".txt", to_txt),
    "tsv": (".tsv", to_tsv),
    "json": (".json", to_json),
}


def export(transcript: Transcript, fmt: str, path: Path) -> None:
    _, fn = EXPORTERS[fmt]
    path.write_text(fn(transcript), encoding="utf-8")
