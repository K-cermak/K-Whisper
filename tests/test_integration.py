"""End-to-end transcription with the real whisper-cli; skipped unless built and test assets fetched."""

from pathlib import Path

import pytest

from k_whisper.engine.options import TranscribeOptions
from k_whisper.engine.runner import TranscriptionTask
from k_whisper.paths import bundled_ffmpeg, bundled_whisper_cli
from k_whisper.transcript.resegment import resegment

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "test-assets" / "ggml-tiny.bin"
AUDIO = ROOT / "test-assets" / "jfk.wav"

pytestmark = pytest.mark.skipif(
    not (bundled_whisper_cli() and MODEL.exists() and AUDIO.exists()),
    reason="needs scripts/build_whispercpp.py and scripts/fetch_test_assets.py",
)


def test_transcribe_jfk(qtbot):
    cli = bundled_whisper_cli()
    assert cli
    task = TranscriptionTask(AUDIO, TranscribeOptions(language="en"), cli, bundled_ffmpeg(), MODEL)
    with qtbot.waitSignal(task.finished, timeout=120_000) as blocker:
        task.start()
    transcript, error = blocker.args
    assert error == ""
    assert "ask not what your country" in transcript.plain_text().lower()
    assert len(resegment(transcript, TranscribeOptions().subtitle_format()).segments) > 1
