"""Turn whisper segments into readable subtitle cues (line length, line count, duration limits)."""

from dataclasses import dataclass, replace

from k_whisper.transcript.model import Segment, Transcript, Word
from k_whisper.transcript.text import join_words, text_pieces, text_width

SENTENCE_END = (".", "?", "!", "…", "。", "？", "！")
CLAUSE_END = SENTENCE_END + (",", ";", ":", "–", "—", "、", "，", "；", "：")


@dataclass(frozen=True)
class SubtitleFormat:
    max_chars_per_line: int = 42
    max_lines: int = 2
    max_duration: float = 7.0
    min_duration: float = 1.0
    min_gap: float = 0.08

    @property
    def capacity(self) -> int:
        return self.max_chars_per_line * self.max_lines


def _text_len(words: list[Word]) -> int:
    return text_width(join_words([w.text for w in words]))


def _synthesize_words(seg: Segment) -> list[Word]:
    """Spread the segment duration over its words proportionally to their length."""
    tokens = text_pieces(seg.plain_text)
    if not tokens:
        return []
    total = sum(len(t) for t in tokens)
    words, t = [], seg.start
    for tok in tokens:
        dt = seg.duration * len(tok) / total
        words.append(Word(t, t + dt, tok))
        t += dt
    return words


def _best_break(cur: list[Word], capacity: int) -> int:
    for i in range(len(cur) - 1, 0, -1):
        if cur[i - 1].text.endswith(CLAUSE_END) and _text_len(cur[:i]) >= capacity * 0.4:
            return i
    return len(cur)


def split_words(words: list[Word], fmt: SubtitleFormat) -> list[list[Word]]:
    groups: list[list[Word]] = []
    cur: list[Word] = []
    for w in words:
        candidate = [*cur, w]
        too_long = _text_len(candidate) > fmt.capacity
        too_slow = w.end - candidate[0].start > fmt.max_duration
        if cur and (too_long or too_slow):
            cut = _best_break(cur, fmt.capacity)
            groups.append(cur[:cut])
            cur = [*cur[cut:], w]
        else:
            cur = candidate
        if w.text.endswith(SENTENCE_END) and _text_len(cur) >= fmt.capacity * 0.35:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


def wrap_text(text: str, fmt: SubtitleFormat) -> str:
    return wrap_words(text_pieces(text), fmt)


def wrap_words(words: list[str], fmt: SubtitleFormat) -> str:
    text = join_words(words)
    if text_width(text) <= fmt.max_chars_per_line or fmt.max_lines <= 1 or len(words) < 2:
        return text
    if fmt.max_lines == 2:
        # Balanced two-line split looks better than greedy wrapping (which leaves a short orphan line).
        best = min(
            range(1, len(words)),
            key=lambda i: max(text_width(join_words(words[:i])), text_width(join_words(words[i:]))),
        )
        return join_words(words[:best]) + "\n" + join_words(words[best:])
    lines: list[str] = []
    line: list[str] = []
    for word in words:
        if line and text_width(join_words([*line, word])) > fmt.max_chars_per_line:
            lines.append(join_words(line))
            line = []
        line.append(word)
    lines.append(join_words(line))
    return "\n".join(lines)


def fix_timing(segments: list[Segment], fmt: SubtitleFormat) -> None:
    for i, seg in enumerate(segments):
        nxt = segments[i + 1] if i + 1 < len(segments) else None
        limit = nxt.start - fmt.min_gap if nxt else float("inf")
        if seg.duration < fmt.min_duration:
            seg.end = min(seg.start + fmt.min_duration, max(seg.end, limit))
        if nxt and seg.end > limit:
            seg.end = max(seg.start + 0.1, limit)
        seg.start = round(seg.start, 3)
        seg.end = round(seg.end, 3)


def resegment(transcript: Transcript, fmt: SubtitleFormat) -> Transcript:
    cues: list[Segment] = []
    for seg in transcript.segments:
        words = seg.words or _synthesize_words(seg)
        if not words:
            continue
        for group in split_words(words, fmt):
            text = wrap_words([w.text for w in group], fmt)
            cues.append(Segment(group[0].start, max(group[-1].end, group[0].start), text, list(group)))
    fix_timing(cues, fmt)
    return replace(transcript, segments=cues)
