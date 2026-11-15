from pathlib import Path
from typing import Optional

from PySide6.QtCore import QTime, QUrl, Qt
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    FluentIcon,
    Slider,
    TransparentToolButton,
)

from app.ui.fluent.waveform_widget import WaveformWidget


class FluentAudioPlayerBar(CardWidget):
    """Modern Fluent Audio Player Bar with scrubbable slider, controls, and volume."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.current_file: Optional[Path] = None
        self._user_is_seeking = False

        # Init Qt multimedia
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.85)

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 10, 16, 10)
        main_layout.setSpacing(6)

        # Top row: Track Title & Time
        top_row = QHBoxLayout()
        self.lbl_title = BodyLabel("No audio loaded", self)
        self.lbl_title.setStyleSheet("font-weight: 600;")
        self.lbl_time = CaptionLabel("00:00 / 00:00", self)
        self.lbl_time.setStyleSheet("font-family: monospace; font-weight: 500;")
        top_row.addWidget(self.lbl_title)
        top_row.addStretch()
        top_row.addWidget(self.lbl_time)
        main_layout.addLayout(top_row)

        # Bottom row: Controls + Scrubber + Volume
        controls_row = QHBoxLayout()
        controls_row.setSpacing(12)

        # Buttons
        self.btn_play = TransparentToolButton(FluentIcon.PLAY, self)
        self.btn_play.setEnabled(False)
        self.btn_play.setToolTip("Play / Pause")

        self.btn_stop = TransparentToolButton(FluentIcon.SYNC, self)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setToolTip("Stop")

        controls_row.addWidget(self.btn_play)
        controls_row.addWidget(self.btn_stop)

        # Interactive Visual Waveform Scrubber
        self.waveform = WaveformWidget(self)
        controls_row.addWidget(self.waveform, stretch=1)

        # Volume Controls
        self.lbl_vol_icon = CaptionLabel("🔊", self)
        self.vol_slider = Slider(Qt.Orientation.Horizontal, self)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(85)
        self.vol_slider.setFixedWidth(90)
        controls_row.addWidget(self.lbl_vol_icon)
        controls_row.addWidget(self.vol_slider)

        main_layout.addLayout(controls_row)

    def _connect_signals(self):
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_stop.clicked.connect(self.stop)

        self.vol_slider.valueChanged.connect(lambda v: self.audio_output.setVolume(v / 100.0))

        # Waveform seek signal
        self.waveform.seek_requested.connect(self._on_waveform_seek)

        # Player signals
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)

    def _on_waveform_seek(self, position_ms: int):
        self.player.setPosition(position_ms)
        self._update_time_label(position_ms, self.player.duration())

    def load_audio(self, file_path: str, title: Optional[str] = None):
        path = Path(file_path).resolve()
        if not path.is_file():
            return

        self.current_file = path
        display_title = title or path.name
        self.lbl_title.setText(f"🎧 {display_title}")

        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.btn_play.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self.lbl_time.setText("00:00 / 00:00")
        self.waveform.load_audio(str(path))

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def play(self):
        if self.current_file and self.current_file.is_file():
            self.player.play()

    def pause(self):
        self.player.pause()

    def stop(self):
        self.player.stop()
        self.waveform.set_position(0)
        self.btn_play.setIcon(FluentIcon.PLAY)

    def _on_playback_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.btn_play.setIcon(FluentIcon.PAUSE)
        else:
            self.btn_play.setIcon(FluentIcon.PLAY)

    def _on_duration_changed(self, duration_ms: int):
        self.waveform.set_duration(duration_ms)
        self._update_time_label(self.player.position(), duration_ms)

    def _on_position_changed(self, position_ms: int):
        self.waveform.set_position(position_ms)
        self._update_time_label(position_ms, self.player.duration())

    def _update_time_label(self, pos_ms: int, dur_ms: int):
        cur_time = QTime(0, 0, 0).addMSecs(max(0, pos_ms)).toString("mm:ss")
        total_time = QTime(0, 0, 0).addMSecs(max(0, dur_ms)).toString("mm:ss")
        self.lbl_time.setText(f"{cur_time} / {total_time}")
