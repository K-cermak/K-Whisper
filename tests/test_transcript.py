import json

from k_whisper.transcript.model import Segment, Transcript, Word, from_whisper_json
from k_whisper.transcript.resegment import SubtitleFormat, resegment, split_words, wrap_text
from k_whisper.transcript.text import join_words, text_width


def whisper_json(tmp_path, segments: list[dict]) -> Transcript:
    path = tmp_path / "out.json"
    path.write_text(json.dumps({"result": {"language": "xx"}, "transcription": segments}), encoding="utf-8")
    return from_whisper_json(path)


def token(text: str, start_ms: int, end_ms: int) -> dict:
    return {"text": text, "offsets": {"from": start_ms, "to": end_ms}, "p": 1.0}


def test_from_whisper_json(jfk_json):
    t = from_whisper_json(jfk_json)
    assert t.language == "en"
    assert len(t.segments) == 1
    seg = t.segments[0]
    assert seg.text.startswith("And so, my fellow Americans")
    assert seg.end == 10.5
    words = [w.text for w in seg.words]
    assert words[:4] == ["And", "so,", "my", "fellow"]
    assert not any(w.startswith("[_") for w in words)


def test_split_utf8_tokens_are_joined(tmp_path):
    # "žluťoučký" split in the middle of the multi-byte "ť" (c5 a5) across two tokens.
    raw = "žluťoučký".encode()
    cut = raw.index(b"\xc5\xa5") + 1
    first, second = raw[:cut], raw[cut:]
    tokens = [
        {"text": " ", "offsets": {"from": 0, "to": 0}, "p": 1.0},
        {"text": "@@1@@", "offsets": {"from": 0, "to": 500}, "p": 0.9},
        {"text": "@@2@@", "offsets": {"from": 500, "to": 900}, "p": 0.8},
    ]
    data = {
        "result": {"language": "cs"},
        "transcription": [{"offsets": {"from": 0, "to": 900}, "text": " žluťoučký", "tokens": tokens}],
    }
    payload = json.dumps(data, ensure_ascii=False).encode()
    payload = payload.replace(b"@@1@@", b" " + first).replace(b"@@2@@", second)
    path = tmp_path / "out.json"
    path.write_bytes(payload)

    t = from_whisper_json(path)
    assert t.segments[0].text == "žluťoučký"
    assert [w.text for w in t.segments[0].words] == ["žluťoučký"]


def test_wrap_text_balances_two_lines():
    fmt = SubtitleFormat(max_chars_per_line=20, max_lines=2)
    wrapped = wrap_text("one two three four five six seven", fmt)
    lines = wrapped.split("\n")
    assert len(lines) == 2
    assert all(len(ln) <= 20 for ln in lines)
    assert abs(len(lines[0]) - len(lines[1])) <= 6


def test_split_words_respects_capacity_and_duration():
    words = [Word(i * 0.5, i * 0.5 + 0.4, f"word{i}") for i in range(40)]
    fmt = SubtitleFormat(max_chars_per_line=20, max_lines=2, max_duration=4.0)
    groups = split_words(words, fmt)
    assert sum(len(g) for g in groups) == 40
    for g in groups:
        assert len(" ".join(w.text for w in g)) <= fmt.capacity
        assert g[-1].end - g[0].start <= fmt.max_duration


def test_resegment_jfk(jfk_json):
    fmt = SubtitleFormat(max_chars_per_line=30, max_lines=2)
    cues = resegment(from_whisper_json(jfk_json), fmt).segments
    assert len(cues) >= 2
    for a, b in zip(cues, cues[1:], strict=False):
        assert b.start - a.end >= fmt.min_gap - 1e-6
    for cue in cues:
        assert all(len(ln) <= 30 for ln in cue.text.split("\n"))


def test_resegment_without_words_synthesizes_timing():
    t = Transcript(segments=[Segment(0, 10, "alpha beta gamma delta epsilon zeta eta theta iota kappa")])
    cues = resegment(t, SubtitleFormat(max_chars_per_line=12, max_lines=1)).segments
    assert len(cues) > 1
    assert cues[0].start == 0
    assert cues[-1].end <= 10.0001


def test_word_times_follow_the_segment_when_silence_was_skipped(tmp_path):
    # With VAD whisper-cli maps segment times to the original recording but leaves token times on the
    # shortened audio: here the speech starts at 12 s, the tokens claim 0 s.
    tokens = [token("[_BEG_]", 0, 0), token(" Ask", 0, 1000), token(" not.", 1000, 2000), token("[_TT_1]", 2000, 2000)]
    t = whisper_json(tmp_path, [{"offsets": {"from": 12000, "to": 14000}, "text": " Ask not.", "tokens": tokens}])
    assert [(w.start, w.end) for w in t.segments[0].words] == [(12.0, 13.0), (13.0, 14.0)]


def test_word_times_unchanged_without_silence_skipping(jfk_json):
    words = from_whisper_json(jfk_json).segments[0].words
    raw = json.loads(jfk_json.read_text(encoding="utf-8"))["transcription"][0]["tokens"]
    first = next(tok for tok in raw if tok["text"].strip() == "And")
    assert words[0].start == first["offsets"]["from"] / 1000


def test_japanese_is_split_into_readable_subtitles(tmp_path):
    text = (
        "今日はとても良い天気ですね。私たちは公園に行って、友達と一緒にお弁当を食べました。それから映画館に行きました。"
    )
    tokens = [token(ch, i * 250, i * 250 + 250) for i, ch in enumerate(text)]
    t = whisper_json(tmp_path, [{"offsets": {"from": 0, "to": len(text) * 250}, "text": text, "tokens": tokens}])
    fmt = SubtitleFormat()
    cues = resegment(t, fmt).segments
    assert len(cues) > 1
    assert "".join(c.text.replace("\n", "") for c in cues) == text
    for cue in cues:
        lines = cue.text.split("\n")
        assert len(lines) <= fmt.max_lines and all(text_width(ln) <= fmt.max_chars_per_line for ln in lines)
        assert cue.end - cue.start <= fmt.max_duration


def test_korean_keeps_its_spaces():
    assert join_words(["안녕하세요", "여러분"]) == "안녕하세요 여러분"
    assert join_words(["今日", "は", "Python", "で"]) == "今日はPythonで"
    wrapped = wrap_text("今日はとても良い天気ですね、公園に行きましょう。", SubtitleFormat(max_chars_per_line=20))
    assert wrapped.count("\n") == 1
