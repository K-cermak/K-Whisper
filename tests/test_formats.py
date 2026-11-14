import json

import pytest

from k_whisper.transcript.formats import (
    format_timestamp,
    parse_timestamp,
    to_json,
    to_srt,
    to_tsv,
    to_txt,
    to_vtt,
)
from k_whisper.transcript.model import Segment, Transcript, Word

T = Transcript(segments=[Segment(0.5, 2.25, "Hello there,\nfriend."), Segment(3725.004, 3726.0, "Ahoj")])


def test_timestamps():
    assert format_timestamp(3725.004) == "01:02:05,004"
    assert format_timestamp(1.5, ".") == "00:00:01.500"
    assert parse_timestamp("01:02:05,004") == pytest.approx(3725.004)
    assert parse_timestamp("02:05.5") == pytest.approx(125.5)
    with pytest.raises(ValueError):
        parse_timestamp("a:b")


def test_srt():
    assert to_srt(T) == (
        "1\n00:00:00,500 --> 00:00:02,250\nHello there,\nfriend.\n\n2\n01:02:05,004 --> 01:02:06,000\nAhoj\n"
    )


def test_vtt():
    out = to_vtt(T)
    assert out.startswith("WEBVTT\n\n00:00:00.500 --> 00:00:02.250\nHello there,\nfriend.\n")


def test_txt_and_tsv():
    assert to_txt(T) == "Hello there, friend.\nAhoj\n"
    assert to_tsv(T).splitlines()[1] == "500\t2250\tHello there, friend."


def test_json_keeps_word_timings():
    t = Transcript(segments=[Segment(0.0, 1.0, "Ahoj světe", [Word(0.0, 0.4, "Ahoj"), Word(0.5, 1.0, "světe")])])
    data = json.loads(to_json(t))
    assert data["version"] == 1
    assert data["segments"][0]["words"][1] == {"start": 0.5, "end": 1.0, "text": "světe", "prob": 1.0}
