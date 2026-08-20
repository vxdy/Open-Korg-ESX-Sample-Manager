import math

import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QSizePolicy, QVBoxLayout, QHBoxLayout, QPushButton, QSlider, QLabel, QScrollBar
)
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush, QPolygonF
from PyQt6.QtCore import Qt, pyqtSignal, QPointF

from ui.i18n import tr

MARKER_HIT_PX = 7


class WaveformWidget(QWidget):
    """Draws a peak-envelope waveform for big-endian 16-bit mono PCM data,
    with optional start/end/loop-start markers. When set_editable(True), the
    start/end markers can be dragged left/right with the mouse to change the
    selection; selectionChanged is emitted (in frames) while dragging.

    Supports zooming (mouse wheel or set_zoom()) and panning (set_pan_frac())
    into the visible portion of the waveform, and an optional beat/step grid
    (see set_step_grid()) derived from the sample's stretch-step count."""

    selectionChanged = pyqtSignal(int, int)
    viewChanged = pyqtSignal()

    MIN_ZOOM = 1.0
    STEP_PIXEL_THRESHOLD = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self._samples = None
        self._start = None
        self._end = None
        self._loop_start = None
        self._editable = False
        self._drag_target = None  # 'start' or 'end' while a drag is in progress
        self._zoom = self.MIN_ZOOM
        self._view_start_frac = 0.0
        self._total_steps = 0
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
        self._zoom = self.MIN_ZOOM
        self._view_start_frac = 0.0
        self.update()
        self.viewChanged.emit()

    def set_selection(self, start_frame, end_frame):
        self._start = start_frame
        self._end = end_frame
        self.update()

    def set_loop_start(self, loop_start_frame):
        self._loop_start = loop_start_frame
        self.update()

    def set_step_grid(self, total_steps: int):
        """Sets the number of equal steps the sample is divided into for the
        beat/step grid overlay (e.g. the sample's stretch-step count). Every
        4th step is drawn as a beat line; every 4th beat (16 steps) is drawn
        as a bar line in a distinct color. Pass 0 to disable the grid."""
        self._total_steps = max(0, int(total_steps or 0))
        self.update()

    def clear(self):
        self._samples = None
        self._start = self._end = self._loop_start = None
        self._zoom = self.MIN_ZOOM
        self._view_start_frac = 0.0
        self._total_steps = 0
        self.update()
        self.viewChanged.emit()

    def _num_frames(self) -> int:
        return len(self._samples) if self._samples is not None else 0

    def zoom(self) -> float:
        return self._zoom

    def view_start_frac(self) -> float:
        return self._view_start_frac

    def visible_frac(self) -> float:
        return 1.0 / self._zoom if self._zoom > 0 else 1.0

    def max_zoom(self) -> float:
        n = self._num_frames()
        if n <= 0:
            return self.MIN_ZOOM
        return min(5000.0, max(self.MIN_ZOOM, n / 16.0))

    def _clamp_start_frac(self, frac, zoom=None) -> float:
        zoom = zoom if zoom is not None else self._zoom
        visible_frac = 1.0 / zoom if zoom > 0 else 1.0
        max_start = max(0.0, 1.0 - visible_frac)
        return max(0.0, min(frac, max_start))

    def set_zoom(self, zoom: float, anchor_frac: float = None):
        """Sets the zoom level (1.0 = whole sample fits the widget width).
        anchor_frac (0..1, fraction of the widget's current width) stays
        fixed on-screen while zooming, so wheel-zooming under the cursor
        feels natural. Defaults to the center of the view."""
        n = self._num_frames()
        if n <= 0:
            self._zoom = self.MIN_ZOOM
            self._view_start_frac = 0.0
            self.update()
            self.viewChanged.emit()
            return
        new_zoom = max(self.MIN_ZOOM, min(zoom, self.max_zoom()))
        if anchor_frac is None:
            anchor_frac = 0.5
        anchor_frac = max(0.0, min(1.0, anchor_frac))
        old_vs, old_ve = self._visible_range()
        anchor_frame = old_vs + anchor_frac * (old_ve - old_vs)
        self._zoom = new_zoom
        new_span = n / new_zoom
        new_start = anchor_frame - anchor_frac * new_span
        self._view_start_frac = self._clamp_start_frac(new_start / n, new_zoom)
        self.update()
        self.viewChanged.emit()

    def set_pan_frac(self, frac: float):
        self._view_start_frac = self._clamp_start_frac(frac)
        self.update()
        self.viewChanged.emit()

    def _visible_range(self):
        """Returns (start_frame, end_frame) of the currently visible window."""
        n = self._num_frames()
        if n <= 0:
            return 0, 0
        span = min(n, max(1, int(round(n / self._zoom))))
        start = int(round(self._view_start_frac * n))
        start = max(0, min(start, n - span))
        return start, start + span

    def _x_for_frame(self, frame) -> float:
        n = self._num_frames()
        w = max(1, self.width())
        if frame is None or n <= 0:
            return 0.0
        vs, ve = self._visible_range()
        span = max(1, ve - vs)
        return (max(0, min(frame, n)) - vs) / span * w

    def _frame_for_x(self, x: float) -> int:
        n = self._num_frames()
        w = max(1, self.width())
        if n <= 0:
            return 0
        vs, ve = self._visible_range()
        span = ve - vs
        t = max(0.0, min(1.0, x / w))
        return int(round(vs + t * span))

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

    def wheelEvent(self, event):
        if self._num_frames() <= 0 or self.max_zoom() <= self.MIN_ZOOM:
            event.ignore()
            return
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return
        factor = 1.25 if delta > 0 else 0.8
        anchor_frac = max(0.0, min(1.0, event.position().x() / max(1, self.width())))
        self.set_zoom(self._zoom * factor, anchor_frac)
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
        vs, ve = self._visible_range()
        span = max(1, ve - vs)
        samples_per_pixel = span / w

        if self._editable and self._start is not None and self._end is not None:
            x1 = self._x_for_frame(self._start)
            x2 = self._x_for_frame(self._end)
            painter.fillRect(int(min(x1, x2)), 0, max(1, int(abs(x2 - x1))), h, QColor(79, 182, 255, 35))

        self._draw_grid(painter, n, w, h, vs, ve, span)

        if samples_per_pixel >= 1.0:
            painter.setPen(QPen(QColor(0, 150, 220), 1))
            for x in range(w):
                start_idx = vs + int(x * samples_per_pixel)
                end_idx = vs + int((x + 1) * samples_per_pixel)
                end_idx = min(max(end_idx, start_idx + 1), n)
                start_idx = min(start_idx, n - 1)
                if start_idx >= n or start_idx < 0:
                    continue
                chunk = self._samples[start_idx:end_idx]
                peak_min = float(chunk.min())
                peak_max = float(chunk.max())
                y_top = mid - (peak_max / 32768.0) * mid
                y_bottom = mid - (peak_min / 32768.0) * mid
                painter.drawLine(x, int(y_top), x, int(max(y_bottom, y_top + 1)))
        else:
            # Zoomed in past native sample resolution: draw the actual
            # connected sample points instead of blocky per-pixel columns.
            idx0 = max(0, vs - 1)
            idx1 = min(n, ve + 2)
            if idx1 - idx0 >= 2:
                xs = (np.arange(idx0, idx1, dtype=np.float64) - vs) / span * w
                ys = mid - (self._samples[idx0:idx1].astype(np.float64) / 32768.0) * mid
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                painter.setPen(QPen(QColor(0, 150, 220), 1.5))
                painter.drawPolyline(QPolygonF([QPointF(float(x_), float(y_)) for x_, y_ in zip(xs, ys)]))
                if w / max(1, idx1 - idx0) >= 5:
                    painter.setPen(QPen(QColor(0, 150, 220), 1))
                    painter.setBrush(QBrush(QColor(0, 150, 220)))
                    for x_, y_ in zip(xs, ys):
                        painter.drawEllipse(QPointF(float(x_), float(y_)), 2.0, 2.0)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

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

    def _draw_grid(self, painter, n, w, h, vs, ve, span):
        """Draws a step/beat/bar grid, if a step count has been set via
        set_step_grid(). Every step is a thin dotted line, every 4th step
        (a beat) a solid light line, and every 4th beat (a bar, i.e. every
        16th step) a bold line in a distinct color - so the sample's
        length/structure stays readable at a glance."""
        if not self._total_steps or n <= 0:
            return
        frames_per_step = n / self._total_steps
        if frames_per_step <= 0:
            return
        px_per_step = frames_per_step / span * w
        show_steps = px_per_step >= self.STEP_PIXEL_THRESHOLD

        first = max(0, int(vs / frames_per_step) - 1)
        last = min(self._total_steps, int(ve / frames_per_step) + 2)
        for i in range(first, last + 1):
            is_bar = i % 16 == 0
            is_beat = i % 4 == 0
            if not is_beat and not show_steps:
                continue
            frame = i * frames_per_step
            x = int(round(self._x_for_frame(frame)))
            if x < -1 or x > w + 1:
                continue
            if is_bar:
                painter.setPen(QPen(QColor(255, 140, 0, 230), 2))
            elif is_beat:
                painter.setPen(QPen(QColor(200, 200, 200, 170), 1))
            else:
                painter.setPen(QPen(QColor(120, 120, 120, 100), 1, Qt.PenStyle.DotLine))
            painter.drawLine(x, 0, x, h)

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


class WaveformZoomPanel(QWidget):
    """A WaveformWidget plus zoom controls (buttons/slider/mouse wheel) and
    a horizontal scrollbar for panning once zoomed in. Exposes the same
    set_audio/set_selection/set_editable/clear/selectionChanged surface as
    WaveformWidget so it's a drop-in replacement."""

    selectionChanged = pyqtSignal(int, int)

    ZOOM_SLIDER_MAX = 1000
    PAN_SCALE = 10000

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.waveform = WaveformWidget()
        self.waveform.selectionChanged.connect(self.selectionChanged)
        self.waveform.viewChanged.connect(self._update_controls)
        layout.addWidget(self.waveform, 1)

        # Scrollbar + zoom row live in a fixed-height strip below the
        # waveform (Qt's Fixed size policy is a hard floor and ceiling), so
        # under vertical space pressure it's the waveform that shrinks -
        # these controls can never be squeezed onto/over the plot area.
        controls = QWidget()
        controls.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(4)
        layout.addWidget(controls, 0)

        self._scrollbar = QScrollBar(Qt.Orientation.Horizontal)
        self._scrollbar.setRange(0, 0)
        self._scrollbar.setFixedHeight(self._scrollbar.sizeHint().height())
        self._scrollbar.valueChanged.connect(self._on_scrollbar_changed)
        controls_layout.addWidget(self._scrollbar)

        zoom_row = QHBoxLayout()
        zoom_row.setSpacing(6)

        self._zoom_out_btn = QPushButton("−")
        self._zoom_out_btn.setFixedWidth(28)
        self._zoom_out_btn.setToolTip(tr("tab_samples.zoom_out_tooltip"))
        self._zoom_out_btn.clicked.connect(lambda: self._step_zoom(0.8))
        zoom_row.addWidget(self._zoom_out_btn)

        self._zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self._zoom_slider.setRange(0, self.ZOOM_SLIDER_MAX)
        self._zoom_slider.setValue(0)
        self._zoom_slider.valueChanged.connect(self._on_slider_changed)
        zoom_row.addWidget(self._zoom_slider, 1)

        self._zoom_in_btn = QPushButton("+")
        self._zoom_in_btn.setFixedWidth(28)
        self._zoom_in_btn.setToolTip(tr("tab_samples.zoom_in_tooltip"))
        self._zoom_in_btn.clicked.connect(lambda: self._step_zoom(1.25))
        zoom_row.addWidget(self._zoom_in_btn)

        self._zoom_label = QLabel("100%")
        self._zoom_label.setFixedWidth(52)
        zoom_row.addWidget(self._zoom_label)

        self._zoom_fit_btn = QPushButton(tr("tab_samples.zoom_fit"))
        self._zoom_fit_btn.setToolTip(tr("tab_samples.zoom_fit_tooltip"))
        self._zoom_fit_btn.clicked.connect(self._reset_zoom)
        zoom_row.addWidget(self._zoom_fit_btn)

        controls_layout.addLayout(zoom_row)
        self._update_controls()

    def set_editable(self, editable: bool):
        self.waveform.set_editable(editable)

    def set_audio(self, pcm_bytes, start_frame=None, end_frame=None, loop_start_frame=None):
        self.waveform.set_audio(pcm_bytes, start_frame, end_frame, loop_start_frame)
        self._update_controls()

    def set_selection(self, start_frame, end_frame):
        self.waveform.set_selection(start_frame, end_frame)

    def set_loop_start(self, loop_start_frame):
        self.waveform.set_loop_start(loop_start_frame)

    def set_step_grid(self, total_steps: int):
        self.waveform.set_step_grid(total_steps)

    def clear(self):
        self.waveform.clear()
        self._update_controls()

    def _step_zoom(self, factor):
        self.waveform.set_zoom(self.waveform.zoom() * factor, anchor_frac=0.5)

    def _reset_zoom(self):
        self.waveform.set_zoom(WaveformWidget.MIN_ZOOM, anchor_frac=0.0)

    def _on_slider_changed(self, value):
        max_zoom = self.waveform.max_zoom()
        if max_zoom <= WaveformWidget.MIN_ZOOM:
            return
        ratio = value / self.ZOOM_SLIDER_MAX
        zoom = WaveformWidget.MIN_ZOOM * (max_zoom / WaveformWidget.MIN_ZOOM) ** ratio
        self.waveform.set_zoom(zoom, anchor_frac=0.5)

    def _on_scrollbar_changed(self, value):
        frac = value / self.PAN_SCALE
        self.waveform.set_pan_frac(frac)

    def _update_controls(self):
        max_zoom = self.waveform.max_zoom()
        zoom = self.waveform.zoom()
        has_audio = self.waveform._num_frames() > 0
        can_zoom = has_audio and max_zoom > WaveformWidget.MIN_ZOOM + 1e-9

        self._zoom_slider.setEnabled(can_zoom)
        self._zoom_in_btn.setEnabled(can_zoom)
        self._zoom_out_btn.setEnabled(can_zoom and zoom > WaveformWidget.MIN_ZOOM + 1e-9)
        self._zoom_fit_btn.setEnabled(can_zoom and zoom > WaveformWidget.MIN_ZOOM + 1e-9)

        if can_zoom:
            log_ratio = math.log(max(zoom, WaveformWidget.MIN_ZOOM) / WaveformWidget.MIN_ZOOM)
            log_ratio /= math.log(max_zoom / WaveformWidget.MIN_ZOOM)
            slider_val = int(round(log_ratio * self.ZOOM_SLIDER_MAX))
        else:
            slider_val = 0
        self._zoom_slider.blockSignals(True)
        self._zoom_slider.setValue(max(0, min(self.ZOOM_SLIDER_MAX, slider_val)))
        self._zoom_slider.blockSignals(False)

        self._zoom_label.setText(f"{zoom * 100:.0f}%")

        visible_frac = self.waveform.visible_frac()
        self._scrollbar.blockSignals(True)
        self._scrollbar.setEnabled(can_zoom and zoom > WaveformWidget.MIN_ZOOM + 1e-9)
        if not has_audio or visible_frac >= 1.0:
            self._scrollbar.setRange(0, 0)
        else:
            page = max(1, int(round(visible_frac * self.PAN_SCALE)))
            self._scrollbar.setPageStep(page)
            self._scrollbar.setRange(0, self.PAN_SCALE - page)
            value = int(round(self.waveform.view_start_frac() * self.PAN_SCALE))
            self._scrollbar.setValue(max(0, min(value, self.PAN_SCALE - page)))
        self._scrollbar.blockSignals(False)
