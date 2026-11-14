"""Application settings persisted with QSettings (stored as one JSON blob for easy defaults/migration)."""

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from PySide6.QtCore import QSettings

from k_whisper.engine.options import TranscribeOptions
from k_whisper.paths import default_models_dir

SETTINGS_KEY = "settings/v1"
# What happens when a recording's files already exist; "ask" decides when the queue is started.
EXISTING_FILES = ("ask", "replace", "number", "skip")


@dataclass
class AppSettings:
    models_dir: str = ""
    whisper_cli_path: str = ""
    ffmpeg_path: str = ""

    output_mode: str = "source"  # "source" = next to the input file, "folder" = output_dir
    output_dir: str = ""
    filename_template: str = "{name}"
    existing_files: str = "ask"
    notify_when_done: bool = True

    options: dict = field(default_factory=lambda: TranscribeOptions().to_dict())
    custom_presets: dict[str, dict] = field(default_factory=dict)
    theme: str = "system"  # "system", "light" or "dark"

    def transcribe_options(self) -> TranscribeOptions:
        return TranscribeOptions.from_dict(self.options)

    def resolved_models_dir(self) -> Path:
        return Path(self.models_dir) if self.models_dir else default_models_dir()

    @classmethod
    def load(cls) -> AppSettings:
        raw = QSettings().value(SETTINGS_KEY, "")
        try:
            data = json.loads(raw) if raw else {}
        except TypeError, ValueError:
            data = {}
        if data.get("skip_existing") and "existing_files" not in data:
            data["existing_files"] = "skip"
        known = {f.name for f in fields(cls)}
        settings = cls(**{k: v for k, v in data.items() if k in known})
        if settings.existing_files not in EXISTING_FILES:
            settings.existing_files = "ask"
        return settings

    def save(self) -> None:
        QSettings().setValue(SETTINGS_KEY, json.dumps(asdict(self)))
