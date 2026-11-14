"""Transcript data model shared by the engine and the exporters. Times are in seconds."""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from k_whisper.transcript.text import is_unspaced

JSON_VERSION = 1


@dataclass
class Word:
    start: float
    end: float
    text: str
    prob: float = 1.0


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def plain_text(self) -> str:
        return " ".join(self.text.split())


@dataclass
class Transcript:
    segments: list[Segment] = field(default_factory=list)
    language: str = ""
    media_path: str = ""
    model: str = ""

    def plain_text(self) -> str:
        return "\n".join(s.plain_text for s in self.segments if s.plain_text)

    def to_dict(self) -> dict:
        return {"version": JSON_VERSION, **asdict(self)}


def _fix_utf8(text: str) -> str:
    # Tokens may hold partial UTF-8 sequences (e.g. Czech diacritics split across tokens); they were
    # decoded with surrogateescape, so joining them and re-encoding restores the original bytes.
    return text.encode("utf-8", "surrogateescape").decode("utf-8", "replace")


def _is_special(token_text: str) -> bool:
    return token_text.startswith("[_") and token_text.endswith("]")


def _words_from_tokens(tokens: list[dict]) -> list[Word]:
    words: list[Word] = []
    parts: list[str] = []
    start = end = 0.0
    probs: list[float] = []

    def flush() -> None:
        text = _fix_utf8("".join(parts)).strip()
        if text:
            words.append(Word(start, max(start, end), text, round(sum(probs) / len(probs), 4)))

    for tok in tokens:
        text = tok.get("text", "")
        if not text or _is_special(text):
            continue
        # whisper-cli leaves out the offsets of tokens it has no timing for.
        offsets = tok.get("offsets") or {"from": end * 1000, "to": end * 1000}
        t0 = offsets["from"] / 1000
        t1 = offsets["to"] / 1000
        new_word = text.startswith(" ") or (parts and (is_unspaced(text[0]) or is_unspaced(parts[-1][-1])))
        if new_word and parts:
            flush()
            parts, probs = [], []
        if not parts:
            start = t0
        parts.append(text)
        probs.append(float(tok.get("p", 1.0)))
        end = t1
    if parts:
        flush()
    return words


def _fit_words(words: list[Word], tokens: list[dict], start: float, end: float) -> list[Word]:
    """Move word times onto the segment's timeline.

    With silence skipping (VAD) whisper-cli maps segment times back to the original recording, but token
    times stay on the shortened audio it actually transcribed. Without VAD both timelines are the same.
    """
    times = [t["offsets"] for t in tokens if "offsets" in t]
    if not words or not times:
        return words
    lo = min(t["from"] for t in times) / 1000
    hi = max(t["to"] for t in times) / 1000
    scale = (end - start) / (hi - lo) if hi > lo else 0.0
    return [
        Word(round(start + (w.start - lo) * scale, 3), round(start + (w.end - lo) * scale, 3), w.text, w.prob)
        for w in words
    ]


def from_whisper_json(path: Path) -> Transcript:
    """Load the ``-ojf`` (full JSON) output of whisper-cli."""
    raw = path.read_bytes().decode("utf-8", "surrogateescape")
    data = json.loads(raw, strict=False)
    segments = []
    for item in data.get("transcription", []):
        text = _fix_utf8(item.get("text", "")).strip()
        if not text:
            continue
        start, end = item["offsets"]["from"] / 1000, item["offsets"]["to"] / 1000
        tokens = item.get("tokens", [])
        words = _fit_words(_words_from_tokens(tokens), tokens, start, end)
        segments.append(Segment(start=start, end=end, text=text, words=words))
    language = data.get("result", {}).get("language", "") or data.get("params", {}).get("language", "")
    return Transcript(segments=segments, language=language)
