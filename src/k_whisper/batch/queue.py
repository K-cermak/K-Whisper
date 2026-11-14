"""Sequential job queue: runs one TranscriptionTask at a time and persists the queue to disk."""

import json
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from k_whisper.batch.job import MEDIA_EXTENSIONS, Job, JobStatus, output_paths
from k_whisper.batch.probe import MediaProbe
from k_whisper.engine.options import TranscribeOptions
from k_whisper.engine.runner import TranscriptionTask
from k_whisper.models.catalog import VAD_MODEL
from k_whisper.models.manager import ModelManager
from k_whisper.paths import bundled_ffmpeg, bundled_whisper_cli, data_dir
from k_whisper.settings import AppSettings
from k_whisper.transcript.formats import export
from k_whisper.transcript.model import Transcript
from k_whisper.transcript.resegment import resegment

MAX_LOG_LINES = 2000


def resolve_whisper_cli(settings: AppSettings) -> Path | None:
    if settings.whisper_cli_path and Path(settings.whisper_cli_path).exists():
        return Path(settings.whisper_cli_path)
    return bundled_whisper_cli()


def resolve_ffmpeg(settings: AppSettings) -> Path | None:
    if settings.ffmpeg_path and Path(settings.ffmpeg_path).exists():
        return Path(settings.ffmpeg_path)
    return bundled_ffmpeg()


def is_media(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS


def collect_media(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files += sorted(p for p in path.rglob("*") if is_media(p))
        elif is_media(path):
            files.append(path)
    return files


class JobQueue(QObject):
    jobs_reset = Signal()
    job_added = Signal(int)
    job_removed = Signal(int)
    job_updated = Signal(str)
    running_changed = Signal(bool)
    segment = Signal(str, str, str, str)  # job id, start, end, text
    log_line = Signal(str, str)  # job id, line
    backend_detected = Signal(str)
    job_started = Signal(str)
    job_finished = Signal(str)
    all_done = Signal()

    def __init__(self, settings: AppSettings, models: ModelManager, state_file: Path | None = None, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.models = models
        self.jobs: list[Job] = []
        self.running = False
        self.current: Job | None = None
        self._task: TranscriptionTask | None = None
        self._waiting_for_vad = False
        # For files that already exist: "replace", "number" (keep both) or "skip". Chosen when the queue is started;
        # never overwriting is the safe default for anything that runs without that choice.
        self.on_existing = "number"
        self._state_file = state_file or data_dir() / "queue.json"
        self._save_timer = QTimer(self, singleShot=True, interval=500)
        self._save_timer.timeout.connect(self.save)
        models.download_finished.connect(self._on_model_download_finished)
        self._probe = MediaProbe(self)
        self._probe.probed.connect(self._on_probed)

    # --- persistence ----------------------------------------------------------------------------

    def load(self) -> None:
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            self.jobs = [Job.from_dict(d) for d in data.get("jobs", [])]
        except OSError, ValueError, TypeError, KeyError:
            self.jobs = []
        self.jobs_reset.emit()
        for job in self.jobs:
            self._probe_duration(job)

    def save(self) -> None:
        data = {"jobs": [j.to_dict() for j in self.jobs]}
        self._state_file.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    def _changed(self, job: Job) -> None:
        self.job_updated.emit(job.id)
        self._save_timer.start()

    # --- editing --------------------------------------------------------------------------------

    def get(self, job_id: str) -> Job | None:
        return next((j for j in self.jobs if j.id == job_id), None)

    def index_of(self, job_id: str) -> int:
        return next((i for i, j in enumerate(self.jobs) if j.id == job_id), -1)

    def add_paths(self, paths: list[Path], opts: TranscribeOptions) -> int:
        """Add the recordings found there; those already waiting or running are not added twice."""
        queued = {j.source for j in self.jobs if j.is_active}
        files = [p for p in collect_media(paths) if str(p) not in queued]
        for path in files:
            job = Job(source=str(path), options=opts.to_dict())
            self.jobs.append(job)
            self.job_added.emit(len(self.jobs) - 1)
            self._probe_duration(job)
        self._save_timer.start()
        return len(files)

    def _probe_duration(self, job: Job) -> None:
        if not job.media_duration and Path(job.source).exists():
            self._probe.ffmpeg = resolve_ffmpeg(self.settings)
            self._probe.request(job.id, Path(job.source))

    def _on_probed(self, job_id: str, duration: float) -> None:
        if job := self.get(job_id):
            job.media_duration = duration
            self._changed(job)

    def remove(self, job_ids: list[str]) -> None:
        for job_id in job_ids:
            if self.current and self.current.id == job_id:
                continue
            idx = self.index_of(job_id)
            if idx >= 0:
                del self.jobs[idx]
                self.job_removed.emit(idx)
        self._save_timer.start()

    def clear_finished(self) -> None:
        self.remove([j.id for j in self.jobs if not j.is_active])

    def move(self, job_id: str, delta: int) -> None:
        idx = self.index_of(job_id)
        new = idx + delta
        if idx < 0 or not 0 <= new < len(self.jobs):
            return
        self.jobs[idx], self.jobs[new] = self.jobs[new], self.jobs[idx]
        self.jobs_reset.emit()
        self._save_timer.start()

    def apply_options(self, job_ids: list[str], opts: TranscribeOptions) -> None:
        for job in self.jobs:
            if job.id in job_ids and job.status == JobStatus.PENDING:
                job.options = opts.to_dict()
                self._changed(job)

    def retry(self, job_ids: list[str]) -> None:
        for job in self.jobs:
            if job.id in job_ids and not job.is_active:
                job.reset()
                self._changed(job)

    # --- running --------------------------------------------------------------------------------

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.running_changed.emit(True)
        if not self.current:
            self._next()

    def pause(self) -> None:
        """Stop after the current job finishes."""
        self.running = False
        self.running_changed.emit(False)

    def stop(self) -> None:
        self.pause()
        if self._task:
            self._task.cancel()

    def shutdown(self) -> None:
        """Before quitting: end the running tool and remove its temporary audio. The job stays running, so the
        saved queue offers it again on the next start."""
        if self._task:
            self._task.discard()

    def _next(self) -> None:
        if not self.running:
            return
        job = next((j for j in self.jobs if j.status == JobStatus.PENDING), None)
        if job is None:
            self.running = False
            self.running_changed.emit(False)
            self.all_done.emit()
            return
        self._run(job)

    def _fail(self, job: Job, message: str) -> None:
        job.status = JobStatus.FAILED
        job.error = message
        job.finished = time.time()
        self._changed(job)
        self.job_finished.emit(job.id)
        QTimer.singleShot(0, self._next)

    def _output_dir(self, source: Path) -> Path:
        if self.settings.output_mode == "folder" and self.settings.output_dir:
            return Path(self.settings.output_dir)
        return source.parent

    def _outputs_for(
        self, job: Job, language: str, opts: TranscribeOptions | None = None, keep_existing: bool = False
    ) -> dict[str, Path]:
        """Output files of a job; names another recording in the queue already wrote get a number instead."""
        source = Path(job.source)
        taken = frozenset(Path(p) for j in self.jobs if j.source != job.source for p in j.outputs)
        template = self.settings.filename_template
        out_dir = self._output_dir(source)
        return output_paths(source, opts or job.opts, out_dir, template, language, taken, keep_existing)

    def _names_known(self, opts: TranscribeOptions) -> bool:
        """With {lang} in the file name the names are only known once the language is detected."""
        return opts.language != "auto" or "{lang}" not in self.settings.filename_template

    def existing_outputs(self, jobs: list[Job], opts: TranscribeOptions) -> dict[str, list[Path]]:
        """Files that transcribing these recordings with these options would overwrite, by job id."""
        if not self._names_known(opts):
            return {}
        found = {}
        for job in jobs:
            if existing := [p for p in self._outputs_for(job, opts.language, opts).values() if p.exists()]:
                found[job.id] = existing
        return found

    def _run(self, job: Job) -> None:
        opts = job.opts
        source = Path(job.source)
        if not source.exists():
            self._fail(job, "The file is no longer there. It was moved, renamed or deleted.")
            return
        cli_path = resolve_whisper_cli(self.settings)
        if not cli_path:
            self._fail(job, "The speech engine (whisper-cli) was not found. Choose it in Settings.")
            return
        if not self.models.is_installed(opts.model):
            name = opts.model.removeprefix("ggml-").removesuffix(".bin")
            self._fail(job, f"The model {name} is not downloaded. Download it on the Models page.")
            return
        if opts.vad and not self.models.vad_model_path():
            if not self._waiting_for_vad:
                self._waiting_for_vad = True
                job.stage = "Downloading silence model"
                self._changed(job)
                self.models.download(VAD_MODEL)
            return

        skip = self.on_existing == "skip" and self._names_known(opts)
        if skip and (existing := [p for p in self._outputs_for(job, opts.language).values() if p.exists()]):
            job.status = JobStatus.SKIPPED
            job.outputs = [str(p) for p in existing]
            self._changed(job)
            QTimer.singleShot(0, self._next)
            return

        job.reset()
        job.status = JobStatus.RUNNING
        job.started = time.time()
        self.current = job
        self._changed(job)
        self.job_started.emit(job.id)

        task = TranscriptionTask(
            source,
            opts,
            cli_path,
            resolve_ffmpeg(self.settings),
            self.models.path_for(opts.model),
            self.models.vad_model_path() if opts.vad else None,
        )
        task.progress.connect(lambda frac, stage: self._on_progress(job, frac, stage))
        task.segment.connect(lambda start, end, text: self._on_segment(job, start, end, text))
        task.log.connect(lambda line: self._on_log(job, line))
        task.language_detected.connect(lambda lang: setattr(job, "language", lang))
        task.backend_detected.connect(self.backend_detected)
        task.finished.connect(lambda transcript, error: self._on_task_finished(job, transcript, error))
        self._task = task
        task.start()

    def _on_model_download_finished(self, filename: str, error: str) -> None:
        if filename != VAD_MODEL.filename or not self._waiting_for_vad:
            return
        self._waiting_for_vad = False
        job = next((j for j in self.jobs if j.status == JobStatus.PENDING), None)
        if job and job.stage:
            job.stage = ""
            self._changed(job)
        if error and job:
            self._fail(job, f"The silence detection model could not be downloaded.\n\n{error}")
        else:
            self._next()

    def _on_progress(self, job: Job, fraction: float, stage: str) -> None:
        job.progress = fraction
        job.stage = stage
        self.job_updated.emit(job.id)

    def _on_segment(self, job: Job, start: str, end: str, text: str) -> None:
        job.last_text = text
        self.segment.emit(job.id, start, end, text)
        self.job_updated.emit(job.id)

    def _on_log(self, job: Job, line: str) -> None:
        job.log.append(line)
        if len(job.log) > MAX_LOG_LINES:
            del job.log[: len(job.log) - MAX_LOG_LINES]
        self.log_line.emit(job.id, line)

    def _on_task_finished(self, job: Job, transcript: Transcript | None, error: str) -> None:
        self._task = None
        self.current = None
        job.finished = time.time()
        if transcript is None:
            job.status = JobStatus.CANCELLED if error == "Cancelled" else JobStatus.FAILED
            job.error = "" if error == "Cancelled" else error
        else:
            try:
                self._write_outputs(job, transcript)
                job.status = JobStatus.DONE
                job.progress = 1.0
                job.stage = ""
            # Whatever goes wrong here must fail this job, not leave it running with the queue stuck behind it.
            except Exception as exc:
                job.status = JobStatus.FAILED
                job.error = f"The result could not be saved.\n\n{exc}"
        self._changed(job)
        self.job_finished.emit(job.id)
        QTimer.singleShot(0, self._next)

    def _write_outputs(self, job: Job, transcript: Transcript) -> None:
        opts = job.opts
        job.language = transcript.language or job.language
        # Names that could not be checked before (they contain the detected language) get a number, unless
        # replacing was chosen: the transcription is done, so skipping now would throw it away.
        outputs = self._outputs_for(job, job.language, keep_existing=self.on_existing != "replace")
        # Subtitle lines are for the subtitle formats; the plain text keeps whisper's own segments.
        cues = resegment(transcript, opts.subtitle_format()) if opts.resegment else transcript
        for fmt, path in outputs.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            export(transcript if fmt == "txt" else cues, fmt, path)
        job.outputs = [str(p) for p in outputs.values()]
