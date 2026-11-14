"""Transcription parameters and built-in presets."""

from dataclasses import asdict, dataclass, field, fields

from k_whisper.transcript.resegment import SubtitleFormat

OUTPUT_FORMATS = ("srt", "vtt", "txt", "tsv", "json")


@dataclass
class TranscribeOptions:
    model: str = "ggml-large-v3-turbo-q5_0.bin"
    language: str = "auto"
    translate: bool = False
    prompt: str = ""
    carry_prompt: bool = False

    threads: int = 0  # 0 = automatic
    beam_size: int = 5
    best_of: int = 5
    temperature: float = 0.0
    temperature_fallback: bool = True
    no_speech_threshold: float = 0.6
    suppress_non_speech: bool = False

    vad: bool = False
    vad_threshold: float = 0.5
    vad_min_speech_ms: int = 250
    vad_min_silence_ms: int = 100

    use_gpu: bool = True
    gpu_device: int = 0
    flash_attn: bool = True

    formats: list[str] = field(default_factory=lambda: ["srt"])
    resegment: bool = True
    max_chars_per_line: int = 42
    max_lines: int = 2
    max_duration: float = 7.0
    min_duration: float = 1.0
    min_gap: float = 0.08

    def subtitle_format(self) -> SubtitleFormat:
        return SubtitleFormat(
            max_chars_per_line=self.max_chars_per_line,
            max_lines=self.max_lines,
            max_duration=self.max_duration,
            min_duration=self.min_duration,
            min_gap=self.min_gap,
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> TranscribeOptions:
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def updated(self, **changes) -> TranscribeOptions:
        return TranscribeOptions.from_dict({**self.to_dict(), **changes})


# What the user wants to get out of a recording; each mode fixes the output formats and cue splitting.
OUTPUT_MODES: dict[str, dict] = {
    "subtitles": {"formats": ["srt"], "resegment": True},
    "transcript": {"formats": ["txt"], "resegment": False},
    "both": {"formats": ["srt", "txt"], "resegment": True},
}
MODE_LABELS = {"subtitles": "Subtitles", "transcript": "Transcript", "both": "Both"}

# Shown in the run bar; everything else is an advanced option.
PRIMARY_FIELDS = {"model", "language", "translate", "formats", "resegment"}


def output_mode(opts: TranscribeOptions) -> str | None:
    """The mode matching the options, or None when the formats were customized."""
    for mode, values in OUTPUT_MODES.items():
        if set(opts.formats) == set(values["formats"]) and opts.resegment == values["resegment"]:
            return mode
    return None


def with_mode(opts: TranscribeOptions, mode: str) -> TranscribeOptions:
    return opts.updated(**OUTPUT_MODES[mode])


def advanced_changes(opts: TranscribeOptions) -> list[str]:
    """Names of advanced options that differ from the defaults."""
    defaults = TranscribeOptions().to_dict()
    current = opts.to_dict()
    return [k for k in current if k not in PRIMARY_FIELDS and current[k] != defaults[k]]
