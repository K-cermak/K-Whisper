"""Model storage: resumable downloads with checksum verification, deletion and import."""

import hashlib
import json
import shutil
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from k_whisper import APP_NAME, __version__
from k_whisper.models.catalog import BUILTIN_CATALOG, VAD_MODEL, ModelInfo, parse_tree, tree_url

CHUNK = 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _request(url: str) -> QNetworkRequest:
    req = QNetworkRequest(QUrl(url))
    req.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, f"{APP_NAME}/{__version__}")
    return req


class Download(QObject):
    # qint64: a Qt int is 32-bit, and the large models (3.1 GB) overflowed it.
    progress = Signal("qint64", "qint64")  # received, total
    finished = Signal(str)  # error message, "" on success
    _verified = Signal(str)

    def __init__(self, nam: QNetworkAccessManager, info: ModelInfo, target: Path, parent=None) -> None:
        super().__init__(parent)
        # The checksum is computed in a Python thread; relaying through this object queues the result to the
        # GUI thread, where everything listening to finished must run.
        self._verified.connect(self.finished)
        self.info = info
        self.target = target
        self.part = target.with_name(target.name + ".part")
        self._nam = nam
        self._reply: QNetworkReply | None = None
        self._fh = None
        self._offset = 0
        self._cancelled = False
        self._error = ""

    def start(self) -> None:
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self._offset = self.part.stat().st_size if self.part.exists() else 0
        req = _request(self.info.url)
        if self._offset:
            req.setRawHeader(b"Range", f"bytes={self._offset}-".encode())
        self._reply = self._nam.get(req)
        self._reply.readyRead.connect(self._on_ready_read)
        self._reply.downloadProgress.connect(self._on_progress)
        self._reply.finished.connect(self._on_finished)

    def cancel(self) -> None:
        self._cancelled = True
        if self._reply:
            self._reply.abort()

    def _status(self) -> int:
        if self._reply is None:
            return 0
        return self._reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) or 0

    def _open(self) -> bool:
        status = self._status()
        if status not in (200, 206):
            # Error pages, and the 416 for a .part that is already complete, must not end up in the model file.
            return False
        if self._offset and status != 206:
            # Server ignored the Range header and sends the whole file again.
            self._offset = 0
        self._fh = self.part.open("ab" if self._offset else "wb")
        return True

    def _write(self, data: bytes) -> None:
        try:
            if self._fh is None and not self._open():
                return
            self._fh.write(data)
        except OSError as exc:
            self._error = f"The model could not be saved. {exc}"
            if self._reply:
                self._reply.abort()

    def _on_ready_read(self) -> None:
        self._write(bytes(self._reply.readAll().data()))

    def _on_progress(self, received: int, total: int) -> None:
        total = total + self._offset if total > 0 else self.info.size
        self.progress.emit(received + self._offset, total)

    def _on_finished(self) -> None:
        reply = self._reply
        error = reply.error()
        status = self._status()
        data = bytes(reply.readAll().data())
        if not self._cancelled and not self._error and (data or error == QNetworkReply.NetworkError.NoError):
            self._write(data)
        if self._fh:
            try:
                self._fh.close()
            except OSError as exc:
                self._error = self._error or f"The model could not be saved. {exc}"
            self._fh = None
        reply.deleteLater()
        self._reply = None
        if self._cancelled:
            self.finished.emit("Cancelled")
        elif self._error:
            self.finished.emit(self._error)
        # 416 = the .part file is already complete from an earlier attempt.
        elif error != QNetworkReply.NetworkError.NoError and status != 416:
            self.finished.emit(f"Download failed: {reply.errorString()}")
        else:
            threading.Thread(target=self._verify, daemon=True).start()

    def _verify(self) -> None:
        try:
            damaged = (self.info.size and self.part.stat().st_size != self.info.size) or (
                self.info.sha256 and sha256_file(self.part) != self.info.sha256
            )
            if damaged:
                self.part.unlink(missing_ok=True)
                self._verified.emit("The downloaded file was damaged, so it was deleted. Please try again.")
                return
            self.part.replace(self.target)
        except OSError as exc:
            self._verified.emit(f"The model could not be saved. {exc}")
            return
        self._verified.emit("")


class ModelManager(QObject):
    catalog_changed = Signal()
    installed_changed = Signal()
    download_progress = Signal(str, "qint64", "qint64")  # filename, received, total
    download_finished = Signal(str, str)  # filename, error
    _imported = Signal(str, str)

    def __init__(self, models_dir: Path, parent=None) -> None:
        super().__init__(parent)
        # Queued from the import thread to the GUI thread, like Download._verified.
        self._imported.connect(self._on_imported)
        self.models_dir = models_dir
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.catalog: list[ModelInfo] = self._load_cached_catalog() or list(BUILTIN_CATALOG)
        self.downloads: dict[str, Download] = {}
        self._nam = QNetworkAccessManager(self)

    @property
    def _cache_file(self) -> Path:
        return self.models_dir / ".catalog.json"

    def set_models_dir(self, path: Path) -> None:
        self.models_dir = path
        path.mkdir(parents=True, exist_ok=True)
        self.installed_changed.emit()

    def _load_cached_catalog(self) -> list[ModelInfo]:
        try:
            return parse_tree(json.loads(self._cache_file.read_text()))
        except OSError, ValueError:
            return []

    def refresh_catalog(self) -> None:
        reply = self._nam.get(_request(tree_url()))

        def done() -> None:
            if reply.error() == QNetworkReply.NetworkError.NoError:
                data = bytes(reply.readAll().data())
                try:
                    models = parse_tree(json.loads(data))
                except ValueError:
                    models = []
                if models:
                    self.catalog = models
                    self._cache_file.write_bytes(data)
                    self.catalog_changed.emit()
            reply.deleteLater()

        reply.finished.connect(done)

    def path_for(self, filename: str) -> Path:
        return self.models_dir / filename

    def installed(self) -> list[str]:
        return sorted(p.name for p in self.models_dir.glob("*.bin") if p.name != VAD_MODEL.filename)

    def is_installed(self, filename: str) -> bool:
        return self.path_for(filename).exists()

    def size_of(self, filename: str) -> int:
        """Size on disk once downloaded (the only size an imported model has), else the download size."""
        path = self.path_for(filename)
        return path.stat().st_size if path.exists() else self.info_for(filename).size

    def info_for(self, filename: str) -> ModelInfo:
        if filename == VAD_MODEL.filename:
            return VAD_MODEL
        for info in self.catalog:
            if info.filename == filename:
                return info
        return ModelInfo(filename, 0)

    def download(self, info: ModelInfo) -> None:
        if info.filename in self.downloads:
            return
        dl = Download(self._nam, info, self.path_for(info.filename), self)
        dl.progress.connect(lambda r, t: self.download_progress.emit(info.filename, r, t))
        dl.finished.connect(lambda err: self._on_download_finished(info.filename, err))
        self.downloads[info.filename] = dl
        dl.start()

    def cancel_download(self, filename: str) -> None:
        if dl := self.downloads.get(filename):
            dl.cancel()

    def _on_download_finished(self, filename: str, error: str) -> None:
        # The finished Download stays a child of the manager: deleteLater() on it crashes PySide when the
        # manager is destroyed before the deferred delete runs. Downloads are few, so this costs nothing.
        self.downloads.pop(filename, None)
        self.download_finished.emit(filename, error)
        if not error:
            self.installed_changed.emit()

    def delete(self, filename: str) -> None:
        self.path_for(filename).unlink(missing_ok=True)
        self.path_for(filename + ".part").unlink(missing_ok=True)
        self.installed_changed.emit()

    def import_model(self, source: Path) -> None:
        """Copy a custom GGML model into the models folder in a background thread.

        The copy is named ggml-*.bin, the names the models folder is listed by.
        """
        stem = source.stem if source.stem.startswith("ggml-") else f"ggml-{source.stem}"
        target = self.path_for(f"{stem}.bin")
        # Copied under a temporary name, so a copy cut short (e.g. by quitting) never looks like a model.
        part = target.with_name(target.name + ".part")

        def copy() -> None:
            try:
                shutil.copyfile(source, part)
                part.replace(target)
            except OSError as exc:
                part.unlink(missing_ok=True)
                self._imported.emit(target.name, f"Import failed: {exc}")
                return
            self._imported.emit(target.name, "")

        threading.Thread(target=copy, daemon=True).start()

    def _on_imported(self, filename: str, error: str) -> None:
        self.download_finished.emit(filename, error)
        if not error:
            self.installed_changed.emit()

    def vad_model_path(self) -> Path | None:
        path = self.path_for(VAD_MODEL.filename)
        return path if path.exists() else None

    def disk_usage(self) -> int:
        return sum(p.stat().st_size for p in self.models_dir.glob("*.bin"))
