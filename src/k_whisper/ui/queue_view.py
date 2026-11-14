"""The queue: one sheet of rows with aligned columns; the running file shows a live caption band and a row under
the pointer offers its next step as buttons."""

import sys
from pathlib import Path

from PySide6.QtCore import (
    QAbstractListModel,
    QEvent,
    QModelIndex,
    QPersistentModelIndex,
    QPoint,
    QPointF,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QAbstractItemView, QListView, QStyle, QStyledItemDelegate

from k_whisper.batch.job import Job, JobStatus
from k_whisper.batch.queue import JobQueue
from k_whisper.ui.theme import mono_font, repolish, theme, ui_font

ROW_HEIGHT = 58
BAND_HEIGHT = 46
PAD = 24
DURATION_W = 84
STATUS_W = 200
ACTION_H = 28
FILE_MANAGER = {"darwin": "Finder", "win32": "Explorer"}.get(sys.platform, "file manager")

STATUS_TEXT = {
    JobStatus.PENDING: "Waiting",
    JobStatus.DONE: "Done",
    JobStatus.FAILED: "Failed",
    JobStatus.CANCELLED: "Stopped",
    JobStatus.SKIPPED: "Skipped",
}


def format_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def format_remaining(seconds: float) -> str:
    if seconds < 60:
        return "less than a minute left"
    minutes = round(seconds / 60)
    return f"about {minutes} min left" if minutes < 90 else f"about {minutes / 60:.1f} h left"


def format_took(seconds: float) -> str:
    return f"took {max(1, round(seconds))} s" if seconds < 60 else f"took {format_duration(seconds)}"


def short_path(folder: Path) -> str:
    home = Path.home()
    try:
        return "~/" + folder.relative_to(home).as_posix() if folder != home else "~"
    except ValueError:
        return str(folder)


def job_details(job: Job) -> str:
    """Second line under the file name."""
    match job.status:
        case JobStatus.FAILED:
            return job.error.splitlines()[0] if job.error else "Failed without a message. See the log."
        case JobStatus.DONE:
            if not job.outputs:
                return "Finished without writing files"
            names = ", ".join(Path(p).suffix.lstrip(".").upper() for p in job.outputs)
            folder = Path(job.outputs[0]).parent
            where = "next to the recording" if folder == Path(job.source).parent else f"in {short_path(folder)}"
            return f"Saved {names} {where}"
        case JobStatus.SKIPPED:
            return "Its files already exist, so it was not transcribed again"
        case JobStatus.CANCELLED:
            return "Stopped before it finished"
        case _:
            return short_path(Path(job.source).parent)


def job_status(job: Job) -> tuple[str, str]:
    """Status column: main text and a smaller second line."""
    if job.status == JobStatus.RUNNING:
        eta = job.eta_seconds()
        sub = format_remaining(eta) if eta is not None else job.stage or "Starting"
        return f"Transcribing {job.progress * 100:.0f}%", sub
    if job.status == JobStatus.DONE:
        took = format_took(job.finished - job.started) if job.started and job.finished else ""
        return "Done", took
    if job.status == JobStatus.PENDING:
        return STATUS_TEXT[job.status], job.stage
    return STATUS_TEXT[job.status], ""


def row_actions(job: Job) -> list[tuple[str, str]]:
    """Buttons of a row under the pointer, as (action, text): the usual next step for its status."""
    if job.status in (JobStatus.DONE, JobStatus.SKIPPED) and job.outputs:
        if len(job.outputs) > 2:
            opens = [("open-menu", "Open…")]
        else:
            opens = [(f"open:{i}", f"Open {Path(p).suffix.lstrip('.').upper()}") for i, p in enumerate(job.outputs)]
        return [*opens, ("reveal", f"Show in {FILE_MANAGER}")]
    if job.status == JobStatus.FAILED:
        return [("log", "Show log"), ("retry", "Transcribe again")]
    if job.status == JobStatus.CANCELLED:
        return [("retry", "Transcribe again")]
    if job.status == JobStatus.RUNNING:
        return [("stop", "Stop")]
    return []


def _columns(r: QRectF) -> tuple[float, float]:
    status_x = r.right() - PAD - STATUS_W
    return status_x, status_x - 20 - DURATION_W


def action_rects(r: QRectF, job: Job) -> list[tuple[str, str, QRectF]]:
    """Where the row's buttons go: right-aligned in the name column, so duration and status stay readable."""
    metrics = QFontMetrics(ui_font(13))
    x = _columns(r)[1] - 8
    top = r.top() + (ROW_HEIGHT - ACTION_H) / 2
    rects = []
    for key, text in reversed(row_actions(job)):
        width = metrics.horizontalAdvance(text) + 24
        x -= width
        rects.append((key, text, QRectF(x, top, width, ACTION_H)))
        x -= 6
    return rects[::-1]


class JobListModel(QAbstractListModel):
    def __init__(self, queue: JobQueue, parent=None) -> None:
        super().__init__(parent)
        self.queue = queue
        queue.jobs_reset.connect(self._reset)
        queue.job_added.connect(self._added)
        queue.job_removed.connect(self._removed)
        queue.job_updated.connect(self._updated)

    def _reset(self) -> None:
        self.beginResetModel()
        self.endResetModel()

    def _added(self, row: int) -> None:
        # The queue already appended the job; announce it after the fact.
        self.beginInsertRows(QModelIndex(), row, row)
        self.endInsertRows()

    def _removed(self, row: int) -> None:
        self.beginRemoveRows(QModelIndex(), row, row)
        self.endRemoveRows()

    def _updated(self, job_id: str) -> None:
        row = self.queue.index_of(job_id)
        if row >= 0:
            # SizeHintRole: the running row grows to make room for the caption band.
            self.dataChanged.emit(self.index(row), self.index(row), [Qt.ItemDataRole.SizeHintRole])

    def refresh_running(self) -> None:
        for row, job in enumerate(self.queue.jobs):
            if job.status == JobStatus.RUNNING:
                self.dataChanged.emit(self.index(row), self.index(row))

    def job(self, row: int) -> Job:
        return self.queue.jobs[row]

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self.queue.jobs)

    def data(self, index: QModelIndex | QPersistentModelIndex, role=Qt.ItemDataRole.DisplayRole):
        # The queue mutates its list before notifying us, so a stale row can briefly be out of range.
        if not index.isValid() or index.row() >= len(self.queue.jobs):
            return None
        job = self.job(index.row())
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole):
            if role == Qt.ItemDataRole.DisplayRole:
                return job.name
            return f"{job.name}, {job_status(job)[0]}. {job_details(job)}"
        if role == Qt.ItemDataRole.ToolTipRole:
            lines = [job.source, *job.outputs]
            if job.error:
                lines += ["", job.error]
            return "\n".join(lines)
        if role == Qt.ItemDataRole.UserRole:
            return job
        if role == Qt.ItemDataRole.SizeHintRole:
            extra = BAND_HEIGHT + 10 if job.status == JobStatus.RUNNING else 0
            return QSize(0, ROW_HEIGHT + extra)
        return None


class JobRowDelegate(QStyledItemDelegate):
    def __init__(self, view: QueueView) -> None:
        super().__init__(view)
        self.view = view

    def sizeHint(self, option, index) -> QSize:
        hint = index.data(Qt.ItemDataRole.SizeHintRole)
        return QSize(option.rect.width(), hint.height() if hint else ROW_HEIGHT)

    def paint(self, painter: QPainter, option, index) -> None:
        job: Job | None = index.data(Qt.ItemDataRole.UserRole)
        if job is None:
            return
        t = theme().tokens
        r = QRectF(option.rect)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = index.row() == self.view.hover_row
        actions = action_rects(r, job) if hovered else []
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        if selected:
            painter.fillRect(r, QColor(t.accent_soft))
            painter.fillRect(QRectF(r.left(), r.top(), 3, r.height()), QColor(t.accent))
        elif hovered:
            painter.fillRect(r, QColor(t.sheet_alt))

        status_x, duration_x = _columns(r)
        name_right = actions[0][2].left() - 16 if actions else duration_x - 20
        name_w = name_right - (r.left() + PAD)
        top = r.top() + 11

        name_font = ui_font(14, QFont.Weight.DemiBold)
        small = ui_font(12)
        painter.setFont(name_font)
        painter.setPen(QColor(t.ink))
        name = QFontMetrics(name_font).elidedText(job.name, Qt.TextElideMode.ElideMiddle, int(name_w))
        painter.drawText(QRectF(r.left() + PAD, top, name_w, 20), Qt.AlignmentFlag.AlignVCenter, name)
        painter.setFont(small)
        painter.setPen(QColor(t.failed if job.status == JobStatus.FAILED else t.graphite))
        details = QFontMetrics(small).elidedText(job_details(job), Qt.TextElideMode.ElideMiddle, int(name_w))
        painter.drawText(QRectF(r.left() + PAD, top + 20, name_w, 18), Qt.AlignmentFlag.AlignVCenter, details)

        if job.media_duration:
            painter.setFont(mono_font(13))
            painter.setPen(QColor(t.graphite))
            painter.drawText(
                QRectF(duration_x, top, DURATION_W, 20),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                format_duration(job.media_duration),
            )

        main, sub = job_status(job)
        running = job.status == JobStatus.RUNNING
        colors = {JobStatus.DONE: t.done, JobStatus.FAILED: t.failed, JobStatus.RUNNING: t.ink}
        color = colors.get(job.status, t.graphite)
        painter.setFont(ui_font(13, QFont.Weight.DemiBold if running else QFont.Weight.Normal))
        painter.setPen(QColor(color))
        painter.drawText(QRectF(status_x, top, STATUS_W, 20), Qt.AlignmentFlag.AlignVCenter, main)
        if sub:
            painter.setFont(small)
            painter.setPen(QColor(t.graphite))
            painter.drawText(QRectF(status_x, top + 20, STATUS_W, 18), Qt.AlignmentFlag.AlignVCenter, sub)

        if running:
            band = QRectF(r.left() + PAD, r.top() + ROW_HEIGHT - 2, r.width() - 2 * PAD, BAND_HEIGHT)
            self._paint_band(painter, band, job)
        for key, text, rect in actions:
            self._paint_action(painter, rect, text, key == self.view.hover_action)

        painter.setPen(QColor(t.rule))
        painter.drawLine(r.bottomLeft(), r.bottomRight())
        painter.restore()

    def _paint_action(self, painter: QPainter, rect: QRectF, text: str, hot: bool) -> None:
        t = theme().tokens
        painter.setPen(QPen(QColor(t.graphite if hot else t.rule_strong), 1))
        painter.setBrush(QColor(t.sheet))
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
        painter.setFont(ui_font(13))
        painter.setPen(QColor(t.ink))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    def _paint_band(self, painter: QPainter, band: QRectF, job: Job) -> None:
        t = theme().tokens
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(t.band))
        painter.drawRoundedRect(band, 4, 4)
        progress = QRectF(band.left(), band.bottom() - 3, band.width() * min(1.0, job.progress), 3)
        painter.fillRect(progress, QColor(t.band_progress))

        text = job.last_text or ("Reading the audio…" if job.progress < 0.05 else "Listening…")
        font = ui_font(16, QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor(t.band_text if job.last_text else t.faint))
        inner = band.adjusted(18, 0, -18, -3)
        # Like a real subtitle: centered, and when too long keep the end, which is the newest speech.
        shown = QFontMetrics(font).elidedText(text, Qt.TextElideMode.ElideLeft, int(inner.width()))
        painter.drawText(inner, Qt.AlignmentFlag.AlignCenter, shown)


class QueueView(QListView):
    files_dropped = Signal(list)
    action_triggered = Signal(str, str, QPoint)  # job id, action, global position for a menu

    def __init__(self, model: JobListModel, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Queue")
        self.hover_row = -1
        self.hover_action = ""
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setModel(model)
        self.setItemDelegate(JobRowDelegate(self))
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.setAccessibleName("Recordings in the queue")
        theme().changed.connect(self.viewport().update)

    def selected_ids(self) -> list[str]:
        model: JobListModel = self.model()  # type: ignore[assignment]
        rows = sorted({i.row() for i in self.selectionModel().selectedRows()})
        return [model.job(r).id for r in rows if r < model.rowCount()]

    def _action_at(self, pos: QPoint) -> tuple[Job, str, QRectF] | None:
        index = self.indexAt(pos)
        if not index.isValid():
            return None
        job: Job = index.data(Qt.ItemDataRole.UserRole)
        for key, _text, rect in action_rects(QRectF(self.visualRect(index)), job):
            if rect.contains(QPointF(pos)):
                return job, key, rect
        return None

    def _set_hover(self, row: int, action: str) -> None:
        if (row, action) == (self.hover_row, self.hover_action):
            return
        self.hover_row, self.hover_action = row, action
        if action:
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.viewport().unsetCursor()
        self.viewport().update()

    def mouseMoveEvent(self, event) -> None:
        pos = event.position().toPoint()
        index = self.indexAt(pos)
        hit = self._action_at(pos)
        self._set_hover(index.row() if index.isValid() else -1, hit[1] if hit else "")
        super().mouseMoveEvent(event)

    def viewportEvent(self, event) -> bool:
        # The view's own leaveEvent does not fire when the pointer leaves the viewport.
        if event.type() == QEvent.Type.Leave:
            self._set_hover(-1, "")
        return super().viewportEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and (hit := self._action_at(event.position().toPoint())):
            job, key, rect = hit
            self.action_triggered.emit(job.id, key, self.viewport().mapToGlobal(rect.bottomLeft().toPoint()))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if self._action_at(event.position().toPoint()):
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _set_dropping(self, dropping: bool) -> None:
        self.setProperty("dropping", dropping)
        repolish(self)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_dropping(True)
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event) -> None:
        self._set_dropping(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        self._set_dropping(False)
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)
