import logging
from pathlib import Path
from typing import Optional

import numpy as np
from PySide6.QtCore import QPoint, QRectF, QTime, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget
from qfluentwidgets import isDarkTheme
import soundfile as sf

logger = logging.getLogger(__name__)


class WaveformWidget(QWidget):
    """High-performance Interactive Audio Waveform & Scrubber Widget."""

    seek_requested = Signal(int)  # target position in milliseconds
    hover_changed = Signal(int, bool)  # target_ms, is_hovering

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedHeight(50)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.peaks: np.ndarray = np.array([], dtype=np.float32)
        self.duration_ms: int = 0
        self.position_ms: int = 0

        self.is_dragging: bool = False
        self.hover_x: int = -1
        self.hover_ms: int = -1
        self.is_hovering: bool = False

    def load_audio(self, audio_path: str, duration_ms: Optional[int] = None):
        """Extract peak amplitudes from audio file for waveform display."""
        path = Path(audio_path).resolve()
        if not path.is_file():
            self.peaks = np.array([], dtype=np.float32)
            self.duration_ms = 0
            self.update()
            return

        try:
            data, sr = sf.read(str(path), dtype="float32")
            if data.ndim > 1:
                data = data.mean(axis=1)

            total_samples = len(data)
            if total_samples == 0:
                self.peaks = np.zeros(120, dtype=np.float32)
            else:
                num_bins = 140
                bin_size = max(1, total_samples // num_bins)
                peaks_list = []
                for i in range(num_bins):
                    s = i * bin_size
                    e = min(total_samples, (i + 1) * bin_size)
                    val = float(np.max(np.abs(data[s:e]))) if s < e else 0.0
                    peaks_list.append(val)

                peaks_arr = np.array(peaks_list, dtype=np.float32)
                max_v = np.max(peaks_arr)
                if max_v > 0:
                    peaks_arr = peaks_arr / max_v
                self.peaks = peaks_arr

            calc_dur_ms = int((total_samples / float(sr)) * 1000)
            self.duration_ms = duration_ms if duration_ms and duration_ms > 0 else calc_dur_ms
            self.position_ms = 0
            self.update()
        except Exception as e:
            logger.error("Error extracting waveform peaks: %s", e)
            self.peaks = np.array([], dtype=np.float32)
            self.duration_ms = duration_ms or 0
            self.update()

    def set_position(self, position_ms: int):
        """Update current playback playhead position."""
        if not self.is_dragging:
            self.position_ms = max(0, min(self.duration_ms, position_ms))
            self.update()

    def set_duration(self, duration_ms: int):
        """Update total audio duration in milliseconds."""
        self.duration_ms = max(0, duration_ms)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        mid_y = h / 2.0
        dark = isDarkTheme()

        # Background container pill
        bg_color = QColor(255, 255, 255, 180) if not dark else QColor(30, 30, 30, 180)
        border_color = QColor(220, 225, 230) if not dark else QColor(55, 55, 55)

        painter.setPen(QPen(border_color, 1))
        painter.setBrush(bg_color)
        painter.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), 6, 6)

        # If no peaks loaded, show placeholder guide
        if len(self.peaks) == 0:
            painter.setPen(QPen(QColor(180, 185, 195) if not dark else QColor(90, 95, 105), 1, Qt.PenStyle.DashLine))
            painter.drawLine(15, int(mid_y), w - 15, int(mid_y))
            painter.setPen(QColor(140, 145, 155) if not dark else QColor(130, 135, 145))
            painter.setFont(QFont("Segoe UI", 9))
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "Waveform visualizer ready — synthesize or load audio")
            return

        # Calculate progress ratio
        progress = 0.0
        if self.duration_ms > 0:
            progress = max(0.0, min(1.0, self.position_ms / float(self.duration_ms)))
        playhead_x = 10 + progress * (w - 20)

        # Colors for waveform bars
        unplayed_color = QColor(190, 198, 208) if not dark else QColor(70, 78, 90)
        played_color = QColor(0, 120, 212) if not dark else QColor(96, 205, 255)

        num_bars = len(self.peaks)
        avail_width = w - 20
        bar_width = max(2.0, (avail_width / float(num_bars)) * 0.7)
        gap = (avail_width - (num_bars * bar_width)) / max(1, num_bars - 1)

        # Draw waveform bars
        for i, peak in enumerate(self.peaks):
            bx = 10 + i * (bar_width + gap)
            bar_h = max(3.0, peak * (h - 16))

            # Color depending on whether it is past playhead
            is_past = (bx + bar_width) <= playhead_x
            bar_color = played_color if is_past else unplayed_color

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bar_color)
            painter.drawRoundedRect(
                QRectF(bx, mid_y - (bar_h / 2.0), bar_width, bar_h),
                bar_width / 2.0,
                bar_width / 2.0,
            )

        # Draw Hover Line and Timecode Pill if mouse is hovering
        if self.is_hovering and 10 <= self.hover_x <= w - 10:
            painter.setPen(QPen(QColor(160, 165, 175), 1, Qt.PenStyle.DashLine))
            painter.drawLine(self.hover_x, 6, self.hover_x, h - 6)

            # Floating time pill
            time_str = QTime(0, 0, 0).addMSecs(max(0, self.hover_ms)).toString("mm:ss")
            pill_w = 46
            pill_h = 18
            pill_x = min(w - pill_w - 6, max(6, self.hover_x - (pill_w // 2)))
            pill_y = 4

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(20, 20, 25, 220) if not dark else QColor(240, 240, 245, 220))
            painter.drawRoundedRect(QRectF(pill_x, pill_y, pill_w, pill_h), 4, 4)

            painter.setPen(QColor(255, 255, 255) if not dark else QColor(20, 20, 25))
            f = QFont("Segoe UI", 8)
            f.setBold(True)
            painter.setFont(f)
            painter.drawText(QRectF(pill_x, pill_y, pill_w, pill_h), Qt.AlignmentFlag.AlignCenter, time_str)

        # Draw Playhead Cursor
        cursor_color = QColor(0, 95, 184) if not dark else QColor(56, 189, 248)
        painter.setPen(QPen(cursor_color, 2))
        painter.drawLine(int(playhead_x), 4, int(playhead_x), h - 4)

        # Top and bottom playhead cap handles
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(cursor_color)
        painter.drawEllipse(QRectF(playhead_x - 3.5, 3, 7, 7))
        painter.drawEllipse(QRectF(playhead_x - 3.5, h - 10, 7, 7))

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self.duration_ms > 0:
            self.is_dragging = True
            self._handle_seek(event.position().x())

    def mouseMoveEvent(self, event: QMouseEvent):
        w = self.width()
        x = event.position().x()
        self.hover_x = int(x)
        self.is_hovering = True

        if self.duration_ms > 0:
            frac = max(0.0, min(1.0, (x - 10) / float(max(1, w - 20))))
            self.hover_ms = int(frac * self.duration_ms)
            self.hover_changed.emit(self.hover_ms, True)

            if self.is_dragging:
                self._handle_seek(x)
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self.is_dragging:
            self.is_dragging = False
            self._handle_seek(event.position().x())

    def leaveEvent(self, event):
        self.is_hovering = False
        self.is_dragging = False
        self.hover_changed.emit(0, False)
        self.update()

    def _handle_seek(self, x_pos: float):
        w = self.width()
        frac = max(0.0, min(1.0, (x_pos - 10) / float(max(1, w - 20))))
        target_ms = int(frac * self.duration_ms)
        self.position_ms = target_ms
        self.seek_requested.emit(target_ms)
        self.update()
