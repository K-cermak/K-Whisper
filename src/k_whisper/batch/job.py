"""A single batch job and helpers for naming its output files."""

import re
import time
import uuid
from dataclasses import asdict, dataclass, field, fields
from enum import StrEnum
from pathlib import Path

from k_whisper.engine.options import TranscribeOptions
from k_whisper.models.catalog import parse_name
from k_whisper.transcript.formats import EXPORTERS

MEDIA_EXTENSIONS = {
    ".wav",
    ".w64",
    ".mp3",
    ".mp2",
    ".m4a",
    ".m4b",
    ".aac",
    ".ac3",
    ".eac3",
    ".dts",
    ".flac",
    ".ogg",
    ".oga",
    ".opus",
    ".wma",
    ".wv",
    ".aiff",
    ".aif",
    ".caf",
    ".amr",
    ".mka",
    ".weba",
    ".mp4",
    ".m4v",
    ".mkv",
    ".mov",
    ".avi",
    ".webm",
    ".wmv",
    ".flv",
    ".mpg",
    ".mpeg",
    ".vob",
    ".ts",
    ".mts",
    ".m2ts",
    ".3gp",
    ".3g2",
}


class JobStatus(StrEnum):
    PENDING = "Pending"
    RUNNING = "Running"
    DONE = "Done"
    FAILED = "Failed"
    CANCELLED = "Cancelled"
    SKIPPED = "Skipped"


@dataclass
class Job:
    source: str
    options: dict
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0
    stage: str = ""
    error: str = ""
    language: str = ""
    outputs: list[str] = field(default_factory=list)
    created: float = field(default_factory=time.time)
    started: float = 0.0
    finished: float = 0.0
    media_duration: float = 0.0
    log: list[str] = field(default_factory=list, repr=False)
    last_text: str = field(default="", repr=False)  # most recent recognized line, for the live caption

    @property
    def name(self) -> str:
        return Path(self.source).name

    @property
    def opts(self) -> TranscribeOptions:
        return TranscribeOptions.from_dict(self.options)

    @property
    def is_active(self) -> bool:
        return self.status in (JobStatus.PENDING, JobStatus.RUNNING)

    def eta_seconds(self) -> float | None:
        if self.status != JobStatus.RUNNING or self.progress <= 0.06 or not self.started:
            return None
        elapsed = time.time() - self.started
        return elapsed * (1 - self.progress) / self.progress

    def reset(self) -> None:
        self.status = JobStatus.PENDING
        self.progress = 0.0
        self.stage = self.error = ""
        self.outputs = []
        self.started = self.finished = 0.0
        self.log = []
        self.last_text = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        data.pop("log")
        data.pop("last_text")
        return data

    @classmethod
    def from_dict(cls, data: dict) -> Job:
        known = {f.name for f in fields(cls)}
        job = cls(**{k: v for k, v in data.items() if k in known})
        job.status = JobStatus(job.status)
        if job.status == JobStatus.RUNNING:
            job.reset()
        return job


_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def output_base_name(template: str, source: Path, language: str, model: str) -> str:
    family, english, quant = parse_name(model)
    values = {
        "name": source.stem,
        "lang": language or "auto",
        "model": family + (".en" if english else "") + (f"-{quant}" if quant else ""),
        "date": time.strftime("%Y-%m-%d"),
    }
    try:
        name = template.format(**values)
    except KeyError, IndexError, ValueError, AttributeError, TypeError:
        name = source.stem
    return _UNSAFE.sub("_", name).strip() or source.stem


def output_paths(
    source: Path,
    opts: TranscribeOptions,
    out_dir: Path,
    template: str,
    language: str,
    taken: frozenset[Path] = frozenset(),
    keep_existing: bool = False,
) -> dict[str, Path]:
    """Output files per format; "-2", "-3"… is added to the name while any of them is in ``taken`` or, with
    ``keep_existing``, already exists."""
    base = output_base_name(template, source, language, opts.model)
    name, n = base, 2
    while True:
        paths = {fmt: out_dir / (name + EXPORTERS[fmt][0]) for fmt in opts.formats if fmt in EXPORTERS}
        if taken.isdisjoint(paths.values()) and not (keep_existing and any(p.exists() for p in paths.values())):
            return paths
        name, n = f"{base}-{n}", n + 1
