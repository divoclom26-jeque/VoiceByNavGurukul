from pathlib import Path
from typing import Optional

from PySide6.QtCore import QTime, QUrl, Qt
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)


class AudioPlayerWidget(QFrame):
    """Audio player bar with waveform/progress slider, play/pause, seek, and volume control."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("PlayerWidget")
        self.setProperty("class", "card-panel")

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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # Top row: Title and time label
        top_row = QHBoxLayout()
        self.lbl_title = QLabel("No audio loaded")
        self.lbl_title.setStyleSheet("font-weight: 600; color: #cdd6f4;")
        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setStyleSheet("color: #a6adc8; font-family: monospace;")
        top_row.addWidget(self.lbl_title)
        top_row.addStretch()
        top_row.addWidget(self.lbl_time)
        layout.addLayout(top_row)

        # Middle row: Seek Slider
        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setEnabled(False)
        layout.addWidget(self.seek_slider)

        # Bottom row: Control buttons + Volume
        controls_row = QHBoxLayout()
        controls_row.setSpacing(10)

        self.btn_play = QPushButton("▶ Play")
        self.btn_play.setProperty("class", "btn-primary")
        self.btn_play.setEnabled(False)
        self.btn_play.setFixedWidth(90)

        self.btn_stop = QPushButton("⏹ Stop")
        self.btn_stop.setProperty("class", "btn-secondary")
        self.btn_stop.setEnabled(False)
        self.btn_stop.setFixedWidth(80)

        controls_row.addWidget(self.btn_play)
        controls_row.addWidget(self.btn_stop)
        controls_row.addStretch()

        # Volume control
        lbl_vol = QLabel("🔊")
        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(85)
        self.vol_slider.setFixedWidth(90)
        controls_row.addWidget(lbl_vol)
        controls_row.addWidget(self.vol_slider)

        layout.addLayout(controls_row)

    def _connect_signals(self):
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_stop.clicked.connect(self.stop)

        self.vol_slider.valueChanged.connect(lambda v: self.audio_output.setVolume(v / 100.0))

        # Player signals
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)

        # Seek slider signals
        self.seek_slider.sliderPressed.connect(self._on_slider_pressed)
        self.seek_slider.sliderMoved.connect(self._on_slider_moved)
        self.seek_slider.sliderReleased.connect(self._on_slider_released)

    def load_audio(self, file_path: str, title: Optional[str] = None):
        """Load an audio file into the player."""
        path = Path(file_path).resolve()
        if not path.is_file():
            return

        self.current_file = path
        display_title = title or path.name
        self.lbl_title.setText(f"🎧 {display_title}")

        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.btn_play.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self.seek_slider.setEnabled(True)
        self.seek_slider.setValue(0)
        self.lbl_time.setText("00:00 / 00:00")

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
        self.seek_slider.setValue(0)
        self.btn_play.setText("▶ Play")

    def _on_playback_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.btn_play.setText("⏸ Pause")
        else:
            self.btn_play.setText("▶ Play")

    def _on_duration_changed(self, duration_ms: int):
        self.seek_slider.setRange(0, duration_ms)
        self._update_time_label(self.player.position(), duration_ms)

    def _on_position_changed(self, position_ms: int):
        if not self._user_is_seeking:
            self.seek_slider.setValue(position_ms)
        self._update_time_label(position_ms, self.player.duration())

    def _on_slider_pressed(self):
        self._user_is_seeking = True

    def _on_slider_moved(self, position_ms: int):
        self._update_time_label(position_ms, self.player.duration())

    def _on_slider_released(self):
        self._user_is_seeking = False
        self.player.setPosition(self.seek_slider.value())

    def _update_time_label(self, pos_ms: int, dur_ms: int):
        cur_time = QTime(0, 0, 0).addMSecs(max(0, pos_ms)).toString("mm:ss")
        total_time = QTime(0, 0, 0).addMSecs(max(0, dur_ms)).toString("mm:ss")
        self.lbl_time.setText(f"{cur_time} / {total_time}")
