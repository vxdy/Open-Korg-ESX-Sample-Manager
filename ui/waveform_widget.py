import numpy as np
from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush
from PyQt6.QtCore import Qt, pyqtSignal

from ui.i18n import tr

MARKER_HIT_PX = 7


class WaveformWidget(QWidget):
    """Draws a peak-envelope waveform for big-endian 16-bit mono PCM data,
    with optional start/end/loop-start markers. When set_editable(True), the
    start/end markers can be dragged left/right with the mouse to change the
    selection; selectionChanged is emitted (in frames) while dragging."""

    selectionChanged = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._samples = None
        self._start = None
        self._end = None
        self._loop_start = None
        self._editable = False
        self._drag_target = None  # 'start' or 'end' while a drag is in progress
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMouseTracking(True)

    def set_editable(self, editable: bool):
        self._editable = editable
        if not editable:
            self._drag_target = None
            self.unsetCursor()

    def set_audio(self, pcm_bytes: bytes, start_frame=None, end_frame=None, loop_start_frame=None):
        if pcm_bytes:
            self._samples = np.frombuffer(pcm_bytes, dtype='>i2').astype(np.float32)
        else:
            self._samples = None
        self._start = start_frame
        self._end = end_frame
        self._loop_start = loop_start_frame
        self.update()

    def set_selection(self, start_frame, end_frame):
        self._start = start_frame
        self._end = end_frame
        self.update()

    def set_loop_start(self, loop_start_frame):
        self._loop_start = loop_start_frame
        self.update()

    def clear(self):
        self._samples = None
        self._start = self._end = self._loop_start = None
        self.update()

    def _num_frames(self) -> int:
        return len(self._samples) if self._samples is not None else 0

    def _x_for_frame(self, frame) -> float:
        n = self._num_frames()
        w = max(1, self.width())
        if frame is None or n <= 0:
            return 0.0
        return max(0, min(frame, n)) / n * w

    def _frame_for_x(self, x: float) -> int:
        n = self._num_frames()
        w = max(1, self.width())
        if n <= 0:
            return 0
        t = max(0.0, min(1.0, x / w))
        return int(round(t * n))

    def _marker_at(self, x: float):
        """Returns 'start' or 'end' if x is within the hit radius of that
        marker, preferring whichever is closer when both are near."""
        if self._num_frames() <= 0:
            return None
        candidates = []
        if self._start is not None:
            candidates.append(('start', abs(x - self._x_for_frame(self._start))))
        if self._end is not None:
            candidates.append(('end', abs(x - self._x_for_frame(self._end))))
        candidates = [c for c in candidates if c[1] <= MARKER_HIT_PX]
        if not candidates:
            return None
        return min(candidates, key=lambda c: c[1])[0]

    def mousePressEvent(self, event):
        if not self._editable or self._num_frames() <= 0:
            return
        target = self._marker_at(event.position().x())
        if target is not None:
            self._drag_target = target
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        event.accept()

    def mouseMoveEvent(self, event):
        if not self._editable or self._num_frames() <= 0:
            return
        x = event.position().x()
        if self._drag_target is not None:
            n = self._num_frames()
            frame = self._frame_for_x(x)
            if self._drag_target == 'start':
                upper = self._end if self._end is not None else n - 1
                self._start = max(0, min(frame, upper))
            else:
                lower = self._start if self._start is not None else 0
                self._end = min(n - 1, max(frame, lower))
            self.update()
            self.selectionChanged.emit(self._start, self._end)
        else:
            hovering = self._marker_at(x) is not None
            self.setCursor(Qt.CursorShape.SizeHorCursor if hovering else Qt.CursorShape.ArrowCursor)
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag_target is not None:
            self._drag_target = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
        event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillRect(self.rect(), self.palette().base())

        if self._samples is None or len(self._samples) == 0:
            painter.setPen(QColor(150, 150, 150))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, tr("common.no_audio_data"))
            painter.end()
            return

        w = max(1, self.width())
        h = max(1, self.height())
        mid = h / 2.0
        n = len(self._samples)
        samples_per_pixel = n / w

        if self._editable and self._start is not None and self._end is not None:
            x1 = self._x_for_frame(self._start)
            x2 = self._x_for_frame(self._end)
            painter.fillRect(int(min(x1, x2)), 0, max(1, int(abs(x2 - x1))), h, QColor(79, 182, 255, 35))

        painter.setPen(QPen(QColor(0, 150, 220), 1))
        for x in range(w):
            start_idx = int(x * samples_per_pixel)
            end_idx = int((x + 1) * samples_per_pixel)
            end_idx = min(max(end_idx, start_idx + 1), n)
            if start_idx >= n:
                break
            chunk = self._samples[start_idx:end_idx]
            peak_min = float(chunk.min())
            peak_max = float(chunk.max())
            y_top = mid - (peak_max / 32768.0) * mid
            y_bottom = mid - (peak_min / 32768.0) * mid
            painter.drawLine(x, int(y_top), x, int(max(y_bottom, y_top + 1)))

        painter.setPen(QPen(QColor(120, 120, 120), 1, Qt.PenStyle.DashLine))
        painter.drawLine(0, int(mid), w, int(mid))

        marker_width = 2 if self._editable else 1
        self._draw_marker(painter, n, w, h, self._start, QColor(0, 200, 0), marker_width)
        self._draw_marker(painter, n, w, h, self._end, QColor(220, 40, 40), marker_width)
        self._draw_marker(painter, n, w, h, self._loop_start, QColor(220, 200, 0), 1)

        if self._editable:
            self._draw_handle(painter, w, h, self._start, QColor(0, 200, 0))
            self._draw_handle(painter, w, h, self._end, QColor(220, 40, 40))

        painter.end()

    @staticmethod
    def _draw_marker(painter, n, w, h, frame, color, width=1):
        if frame is None or n <= 0:
            return
        x = int(max(0, min(frame, n)) / n * w)
        painter.setPen(QPen(color, width))
        painter.drawLine(x, 0, x, h)

    def _draw_handle(self, painter, w, h, frame, color):
        if frame is None:
            return
        x = self._x_for_frame(frame)
        painter.setPen(QPen(color.darker(150), 1))
        painter.setBrush(QBrush(color))
        painter.drawRect(int(x) - 4, 0, 8, 10)
        painter.drawRect(int(x) - 4, h - 10, 8, 10)
