"""Runs one transcription: ffmpeg (decode to 16 kHz WAV) followed by whisper-cli, via QProcess."""

import shutil
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from k_whisper.engine import cli
from k_whisper.engine.options import TranscribeOptions
from k_whisper.paths import is_frozen
from k_whisper.transcript.formats import parse_timestamp
from k_whisper.transcript.model import Transcript, from_whisper_json

NATIVE_AUDIO = {".wav", ".mp3", ".flac", ".ogg"}
DECODE_SHARE = 0.05
LOG_TAIL = 30


class LineBuffer:
    """Splits a byte stream into decoded lines; also splits on CR because ffmpeg uses it for status."""

    def __init__(self) -> None:
        self._buf = b""

    def feed(self, data: bytes) -> list[str]:
        self._buf += data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        *lines, self._buf = self._buf.split(b"\n")
        return [ln.decode("utf-8", "replace") for ln in lines]

    def flush(self) -> list[str]:
        rest, self._buf = self._buf, b""
        return [rest.decode("utf-8", "replace")] if rest else []


def child_environment() -> QProcessEnvironment:
    env = QProcessEnvironment.systemEnvironment()
    # The PyInstaller bootloader points LD_LIBRARY_PATH at the bundle; child tools must not inherit it.
    if is_frozen() and sys.platform.startswith("linux"):
        if env.contains("LD_LIBRARY_PATH_ORIG"):
            env.insert("LD_LIBRARY_PATH", env.value("LD_LIBRARY_PATH_ORIG"))
        else:
            env.remove("LD_LIBRARY_PATH")
    return env


class TranscriptionTask(QObject):
    progress = Signal(float, str)
    segment = Signal(str, str, str)  # start, end, text
    log = Signal(str)
    language_detected = Signal(str)
    backend_detected = Signal(str)
    # Transcript (or None on failure) and an error message ("" on success, "Cancelled" when cancelled).
    finished = Signal(object, str)

    def __init__(
        self,
        source: Path,
        opts: TranscribeOptions,
        whisper_cli: Path,
        ffmpeg: Path | None,
        model_path: Path,
        vad_model_path: Path | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        # Absolute paths: the child processes run with the tool's folder as working directory.
        self.source = source.resolve()
        self.opts = opts
        self.whisper_cli = whisper_cli.resolve()
        self.ffmpeg = ffmpeg.resolve() if ffmpeg else None
        self.model_path = model_path.resolve()
        self.vad_model_path = vad_model_path.resolve() if vad_model_path else None

        self._tmp: Path | None = None
        self._proc: QProcess | None = None
        self._out = LineBuffer()
        self._err = LineBuffer()
        self._tail: list[str] = []
        self._duration = 0.0
        self._backend = ""
        self._cancelled = False
        self._done = False

    def start(self) -> None:
        self._tmp = Path(tempfile.mkdtemp(prefix="kwhisper-"))
        if not self.opts.use_gpu:
            # whisper.cpp logs nothing about the backend when the GPU is switched off.
            self._backend = "CPU"
            self.backend_detected.emit("CPU")
        if self.ffmpeg:
            self._start_ffmpeg()
        elif self.source.suffix.lower() in NATIVE_AUDIO:
            self._start_whisper(self.source)
        else:
            self._finish(None, "ffmpeg is missing, so only WAV, MP3, FLAC and OGG files can be read.")

    def cancel(self) -> None:
        self._cancelled = True
        if self._proc and self._proc.state() != QProcess.ProcessState.NotRunning:
            self._proc.kill()
        elif not self._done:
            self._finish(None, "Cancelled")

    def _new_process(self, program: Path, args: list[str], on_out, on_err, on_done) -> None:
        self._out, self._err, self._tail = LineBuffer(), LineBuffer(), []
        proc = QProcess(self)
        proc.setProgram(str(program))
        proc.setArguments(args)
        proc.setWorkingDirectory(str(program.parent))
        proc.setProcessEnvironment(child_environment())
        proc.readyReadStandardOutput.connect(
            lambda: [on_out(ln) for ln in self._out.feed(bytes(proc.readAllStandardOutput().data()))]
        )
        proc.readyReadStandardError.connect(
            lambda: [on_err(ln) for ln in self._err.feed(bytes(proc.readAllStandardError().data()))]
        )
        proc.finished.connect(on_done)
        proc.errorOccurred.connect(self._on_process_error)
        self._proc = proc
        self.log.emit("$ " + " ".join([program.name, *args]))
        proc.start()

    def _on_process_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart and not self._done:
            program = Path(self._proc.program()).name if self._proc else "a helper program"
            self._finish(None, f"{program} could not be started. Check the speech engine in Settings.")

    def _remember(self, line: str) -> None:
        if line.strip():
            self.log.emit(line)
            self._tail = [*self._tail[-LOG_TAIL + 1 :], line]

    def _error_summary(self) -> str:
        # whisper-cli prints its whole usage text after an argument error; the error lines matter.
        errors = [ln for ln in self._tail if "error" in ln.lower() or "failed" in ln.lower()]
        return "\n".join((errors or self._tail)[-8:])

    # --- ffmpeg ---------------------------------------------------------------------------------

    def _start_ffmpeg(self) -> None:
        assert self.ffmpeg and self._tmp
        self.progress.emit(0.0, "Decoding audio")
        wav = self._tmp / "audio.wav"
        self._new_process(
            self.ffmpeg,
            cli.ffmpeg_args(self.source, wav),
            self._on_ffmpeg_out,
            self._on_ffmpeg_err,
            lambda code, status: self._on_ffmpeg_done(code, status, wav),
        )

    def _on_ffmpeg_out(self, line: str) -> None:
        t = cli.parse_ffmpeg_out_time(line)
        if t is not None and self._duration > 0:
            self.progress.emit(DECODE_SHARE * min(1.0, t / self._duration), "Decoding audio")

    def _on_ffmpeg_err(self, line: str) -> None:
        duration = cli.parse_ffmpeg_duration(line)
        if duration and not self._duration:
            self._duration = duration
        self._remember(line)

    def _on_ffmpeg_done(self, code: int, status: QProcess.ExitStatus, wav: Path) -> None:
        if self._done:
            return
        for line in self._err.flush():
            self._remember(line)
        if self._cancelled:
            self._finish(None, "Cancelled")
        elif code != 0 or status != QProcess.ExitStatus.NormalExit or not wav.exists():
            self._finish(None, "The audio in this file could not be read.\n\n" + self._error_summary())
        else:
            self._start_whisper(wav)

    # --- whisper-cli ----------------------------------------------------------------------------

    def _start_whisper(self, audio: Path) -> None:
        assert self._tmp
        self.progress.emit(DECODE_SHARE, "Transcribing")
        out_base = self._tmp / "result"
        args = cli.whisper_args(self.opts, self.model_path, audio, out_base, self.vad_model_path)
        self._new_process(
            self.whisper_cli,
            args,
            self._on_whisper_out,
            self._on_whisper_err,
            lambda code, status: self._on_whisper_done(code, status, out_base.with_suffix(".json")),
        )

    def _whisper_progress(self, fraction: float) -> None:
        self.progress.emit(DECODE_SHARE + (1 - DECODE_SHARE) * min(1.0, fraction), "Transcribing")

    def _on_whisper_out(self, line: str) -> None:
        seg = cli.parse_whisper_segment(line)
        if not seg:
            return
        start, end, text = seg
        self.segment.emit(start, end, text)
        if self._duration > 0:
            self._whisper_progress(parse_timestamp(end) / self._duration)

    def _on_whisper_err(self, line: str) -> None:
        if (pct := cli.parse_whisper_progress(line)) is not None:
            self._whisper_progress(pct / 100)
            return
        if lang := cli.parse_detected_language(line):
            self.language_detected.emit(lang)
        # The VAD model always runs on the CPU and logs "no GPU found" after the speech model's backend.
        if not self._backend and (backend := cli.parse_backend(line)):
            self._backend = backend
            self.backend_detected.emit(backend)
        self._remember(line)

    def _on_whisper_done(self, code: int, status: QProcess.ExitStatus, json_path: Path) -> None:
        if self._done:
            return
        for line in self._err.flush():
            self._remember(line)
        if self._cancelled:
            self._finish(None, "Cancelled")
            return
        if code != 0 or status != QProcess.ExitStatus.NormalExit or not json_path.exists():
            self._finish(None, f"The speech engine stopped with an error (code {code}).\n\n" + self._error_summary())
            return
        try:
            transcript = from_whisper_json(json_path)
        except (OSError, ValueError, KeyError) as exc:
            self._finish(None, f"The speech engine's result could not be read.\n\n{exc}")
            return
        transcript.media_path = str(self.source)
        transcript.model = self.model_path.name
        self.progress.emit(1.0, "Done")
        self._finish(transcript, "")

    def discard(self) -> None:
        """Kill the running tool and delete the temporary audio without reporting back (used when quitting)."""
        self._done = True
        if self._proc and self._proc.state() != QProcess.ProcessState.NotRunning:
            self._proc.kill()
            self._proc.waitForFinished(3000)
        if self._tmp:
            shutil.rmtree(self._tmp, ignore_errors=True)
            self._tmp = None

    def _finish(self, transcript: Transcript | None, error: str) -> None:
        self._done = True
        if self._tmp:
            shutil.rmtree(self._tmp, ignore_errors=True)
            self._tmp = None
        self.finished.emit(transcript, error)
        # Not right away: we may be inside the signal of a process whose connection would be dropped.
        QTimer.singleShot(0, self._release_processes)

    def _release_processes(self) -> None:
        """The process signals go to lambdas that hold this task; without them the task can be freed."""
        for proc in self.findChildren(QProcess):
            proc.readyReadStandardOutput.disconnect()
            proc.readyReadStandardError.disconnect()
            proc.finished.disconnect()
            proc.errorOccurred.disconnect()
