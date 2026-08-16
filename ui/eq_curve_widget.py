import math

from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush
from PyQt6.QtCore import Qt, QPointF, pyqtSignal

from esx.audio_dsp import eq_frequency_response

DB_RANGE = 24.0
FREQ_MIN = 20.0
FREQ_MAX = 20000.0
GRID_FREQS = [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000]
NODE_RADIUS = 7
NODE_HIT_RADIUS = 12
NODE_COLORS = [
    QColor(79, 182, 255), QColor(255, 159, 67), QColor(159, 214, 79), QColor(255, 100, 130),
]


class EqCurveWidget(QWidget):
    """Draws the cascaded frequency-response curve of a set of EQBands on a
    log-frequency / dB grid, in the same flat painter style as WaveformWidget.
    Each band's (freq, gain) is shown as a draggable node, FL-Studio-Parametric-
    EQ-style: drag to set freq/gain, scroll the wheel over a node to change Q."""

    bandChanged = pyqtSignal(int)
    bandQChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bands = []
        self._sample_rate = 44100
        self._drag_index = None
        self.setMinimumHeight(140)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMouseTracking(True)

    def set_bands(self, bands, sample_rate: int):
        self._bands = bands
        self._sample_rate = sample_rate if sample_rate > 0 else 44100
        self.update()

    def _x_for_freq(self, freq: float, w: int) -> float:
        freq = max(FREQ_MIN, min(FREQ_MAX, freq))
        t = (math.log10(freq) - math.log10(FREQ_MIN)) / (math.log10(FREQ_MAX) - math.log10(FREQ_MIN))
        return t * w

    def _freq_for_x(self, x: float, w: int) -> float:
        w = max(1, w)
        t = max(0.0, min(1.0, x / w))
        log_f = math.log10(FREQ_MIN) + t * (math.log10(FREQ_MAX) - math.log10(FREQ_MIN))
        return 10.0 ** log_f

    def _y_for_db(self, db: float, h: int) -> float:
        t = (db + DB_RANGE) / (2 * DB_RANGE)
        t = max(0.0, min(1.0, t))
        return h - t * h

    def _db_for_y(self, y: float, h: int) -> float:
        h = max(1, h)
        t = 1.0 - max(0.0, min(1.0, y / h))
        db = t * 2 * DB_RANGE - DB_RANGE
        return max(-DB_RANGE, min(DB_RANGE, db))

    def _node_pos(self, band, w: int, h: int):
        gain_for_y = 0.0 if band.type in ("low_pass", "high_pass") else band.gain_db
        return self._x_for_freq(band.freq, w), self._y_for_db(gain_for_y, h)

    def _node_at(self, pos):
        w, h = self.width(), self.height()
        best_index = None
        best_dist = None
        for i, band in enumerate(self._bands):
            if not band.enabled:
                continue
            x, y = self._node_pos(band, w, h)
            dist = math.hypot(pos.x() - x, pos.y() - y)
            if dist <= NODE_HIT_RADIUS and (best_dist is None or dist < best_dist):
                best_dist = dist
                best_index = i
        return best_index

    def _drag_to(self, index, pos):
        w, h = self.width(), self.height()
        band = self._bands[index]
        band.freq = max(FREQ_MIN, min(FREQ_MAX, self._freq_for_x(pos.x(), w)))
        if band.type not in ("low_pass", "high_pass"):
            band.gain_db = self._db_for_y(pos.y(), h)
        self.update()
        self.bandChanged.emit(index)

    def mousePressEvent(self, event):
        index = self._node_at(event.position())
        if index is not None:
            self._drag_index = index
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self._drag_to(index, event.position())
        event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_index is not None:
            self._drag_to(self._drag_index, event.position())
        else:
            hovering = self._node_at(event.position()) is not None
            self.setCursor(Qt.CursorShape.OpenHandCursor if hovering else Qt.CursorShape.ArrowCursor)
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag_index is not None:
            self._drag_index = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
        event.accept()

    def wheelEvent(self, event):
        index = self._drag_index if self._drag_index is not None else self._node_at(event.position())
        if index is None:
            return
        band = self._bands[index]
        factor = 1.1 if event.angleDelta().y() > 0 else (1.0 / 1.1)
        band.q = max(0.1, min(10.0, band.q * factor))
        self.update()
        self.bandQChanged.emit(index)
        event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), self.palette().base())

        w = max(1, self.width())
        h = max(1, self.height())

        painter.setPen(QPen(QColor(70, 70, 76), 1, Qt.PenStyle.DotLine))
        for freq in GRID_FREQS:
            x = self._x_for_freq(freq, w)
            painter.drawLine(int(x), 0, int(x), h)
        for db in (-18, -12, -6, 0, 6, 12, 18):
            y = self._y_for_db(db, h)
            painter.drawLine(0, int(y), w, int(y))

        painter.setPen(QPen(QColor(120, 120, 120), 1, Qt.PenStyle.DashLine))
        zero_y = self._y_for_db(0.0, h)
        painter.drawLine(0, int(zero_y), w, int(zero_y))

        if not self._bands:
            painter.end()
            return

        freqs, mags = eq_frequency_response(self._bands, self._sample_rate, num_points=max(60, w))
        painter.setPen(QPen(QColor(79, 182, 255), 2))
        points = [
            (self._x_for_freq(f, w), self._y_for_db(db, h))
            for f, db in zip(freqs, mags)
        ]
        for i in range(len(points) - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        for i, band in enumerate(self._bands):
            color = NODE_COLORS[i % len(NODE_COLORS)]
            x, y = self._node_pos(band, w, h)
            if not band.enabled:
                color = QColor(110, 110, 115)
            painter.setPen(QPen(color.darker(140), 2))
            painter.setBrush(QBrush(color))
            painter.drawEllipse(QPointF(x, y), NODE_RADIUS, NODE_RADIUS)
            painter.setPen(QPen(QColor(20, 20, 22)))
            painter.drawText(int(x) - 3, int(y) + 4, str(i + 1))

        painter.end()
