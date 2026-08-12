import numpy as np
from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtGui import QPainter, QPen, QColor
from PyQt6.QtCore import Qt


class WaveformWidget(QWidget):
    """Draws a peak-envelope waveform for big-endian 16-bit mono PCM data,
    with optional start/end/loop-start markers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._samples = None
        self._start = None
        self._end = None
        self._loop_start = None
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def set_audio(self, pcm_bytes: bytes, start_frame=None, end_frame=None, loop_start_frame=None):
        if pcm_bytes:
            self._samples = np.frombuffer(pcm_bytes, dtype='>i2').astype(np.float32)
        else:
            self._samples = None
        self._start = start_frame
        self._end = end_frame
        self._loop_start = loop_start_frame
        self.update()

    def set_loop_start(self, loop_start_frame):
        self._loop_start = loop_start_frame
        self.update()

    def clear(self):
        self._samples = None
        self._start = self._end = self._loop_start = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillRect(self.rect(), self.palette().base())

        if self._samples is None or len(self._samples) == 0:
            painter.setPen(QColor(150, 150, 150))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No audio data")
            painter.end()
            return

        w = max(1, self.width())
        h = max(1, self.height())
        mid = h / 2.0
        n = len(self._samples)
        samples_per_pixel = n / w

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

        self._draw_marker(painter, n, w, h, self._start, QColor(0, 200, 0))
        self._draw_marker(painter, n, w, h, self._end, QColor(220, 40, 40))
        self._draw_marker(painter, n, w, h, self._loop_start, QColor(220, 200, 0))
        painter.end()

    @staticmethod
    def _draw_marker(painter, n, w, h, frame, color):
        if frame is None or n <= 0:
            return
        x = int(max(0, min(frame, n)) / n * w)
        painter.setPen(QPen(color, 1))
        painter.drawLine(x, 0, x, h)
