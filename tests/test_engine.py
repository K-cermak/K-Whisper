from pathlib import Path

from k_whisper.engine import cli
from k_whisper.engine.options import TranscribeOptions, advanced_changes, output_mode, with_mode
from k_whisper.engine.runner import LineBuffer


def test_whisper_args_defaults():
    args = cli.whisper_args(TranscribeOptions(threads=3), Path("m.bin"), Path("a.wav"), Path("out"))
    assert args[:6] == ["-m", "m.bin", "-f", "a.wav", "-of", "out"]
    assert "-ojf" in args and "-pp" in args
    assert args[args.index("-t") + 1] == "3"
    assert args[args.index("-l") + 1] == "auto"
    for flag in ("-tr", "-ng", "--vad", "-nfa", "--prompt", "-nf"):
        assert flag not in args


def test_whisper_args_options():
    opts = TranscribeOptions(
        language="cs",
        translate=True,
        prompt="  Brno, Praha ",
        carry_prompt=True,
        vad=True,
        use_gpu=False,
        flash_attn=False,
        temperature_fallback=False,
    )
    args = cli.whisper_args(opts, Path("m"), Path("a"), Path("o"), Path("vad.bin"))
    assert args[args.index("-l") + 1] == "cs"
    assert args[args.index("--prompt") + 1] == "Brno, Praha"
    assert {"-tr", "--carry-initial-prompt", "--vad", "-ng", "-nfa", "-nf"} <= set(args)
    assert args[args.index("-vm") + 1] == "vad.bin"


def test_vad_requires_model():
    args = cli.whisper_args(TranscribeOptions(vad=True), Path("m"), Path("a"), Path("o"), None)
    assert "--vad" not in args


def test_parsers():
    assert cli.parse_whisper_progress("whisper_print_progress_callback: progress =  45%") == 45
    assert cli.parse_whisper_segment("[00:00:01.000 --> 00:00:02.500]   Hello") == (
        "00:00:01.000",
        "00:00:02.500",
        "Hello",
    )
    assert cli.parse_detected_language("whisper_full_with_state: auto-detected language: cs (p = 0.9)") == "cs"
    assert cli.parse_ffmpeg_duration("  Duration: 01:02:03.50, start: 0.000000") == 3723.5
    assert cli.parse_ffmpeg_out_time("out_time_us=2500000") == 2.5
    assert cli.parse_backend("whisper_backend_init_gpu: using MTL0 backend") == "Metal"
    assert cli.parse_backend("ggml_vulkan: Found 1 Vulkan devices:") == "Vulkan"
    assert cli.parse_backend("random line") is None


def test_line_buffer_handles_partial_utf8_and_cr():
    buf = LineBuffer()
    data = "žluť\rnext\npart".encode()
    assert buf.feed(data[:3]) == []
    assert buf.feed(data[3:]) == ["žluť", "next"]
    assert buf.flush() == ["part"]


def test_options_roundtrip_ignores_unknown_keys():
    opts = TranscribeOptions(language="de", formats=["vtt"])
    data = {**opts.to_dict(), "removed_option": 1}
    assert TranscribeOptions.from_dict(data) == opts


def test_output_modes():
    opts = TranscribeOptions()
    assert output_mode(opts) == "subtitles"
    assert output_mode(with_mode(opts, "transcript")) == "transcript"
    both = with_mode(opts, "both")
    assert set(both.formats) == {"srt", "txt"} and both.resegment
    assert output_mode(opts.updated(formats=["vtt"])) is None


def test_advanced_changes_ignore_primary_options():
    opts = TranscribeOptions(model="ggml-tiny.bin", language="cs", translate=True, formats=["txt"])
    assert advanced_changes(opts) == []
    assert advanced_changes(opts.updated(vad=False, beam_size=1)) == ["beam_size", "vad"]
