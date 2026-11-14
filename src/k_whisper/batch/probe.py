"""Reads media durations with ffmpeg in the background, one file at a time."""

from collections import deque
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Signal

from k_whisper.engine.cli import parse_ffmpeg_duration
from k_whisper.engine.runner import child_environment


class MediaProbe(QObject):
    probed = Signal(str, float)  # key, duration in seconds

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.ffmpeg: Path | None = None
        self._pending: deque[tuple[str, Path]] = deque()
        self._proc: QProcess | None = None
        self._key = ""

    def request(self, key: str, path: Path) -> None:
        if self.ffmpeg is None:
            return
        self._pending.append((key, path))
        if self._proc is None:
            self._next()

    def _next(self) -> None:
        if not self._pending or self.ffmpeg is None:
            self._proc = None
            return
        self._key, path = self._pending.popleft()
        proc = QProcess(self)
        proc.setProcessEnvironment(child_environment())
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        # Without an output file ffmpeg prints the input info (including "Duration:") and exits.
        proc.start(str(self.ffmpeg), ["-hide_banner", "-nostdin", "-i", str(path.resolve())])
        proc.finished.connect(lambda *_: self._done(proc))
        proc.errorOccurred.connect(lambda err: self._done(proc) if err == QProcess.ProcessError.FailedToStart else None)
        self._proc = proc

    def _done(self, proc: QProcess) -> None:
        if proc is not self._proc:
            return
        try:
            output = bytes(proc.readAll().data()).decode("utf-8", "replace")
        except RuntimeError:
            # The probe is being destroyed: QProcess's destructor kills the child and still emits finished.
            return
        duration = next((d for line in output.splitlines() if (d := parse_ffmpeg_duration(line))), None)
        if duration:
            self.probed.emit(self._key, duration)
        proc.deleteLater()
        self._next()
