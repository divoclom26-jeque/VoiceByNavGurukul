import logging
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Optional

from PySide6.QtCore import QTime, QUrl, Qt
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    Slider,
    TransparentToolButton,
)

from app.ui.fluent.waveform_widget import WaveformWidget

logger = logging.getLogger(__name__)


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

        # Download & Folder Action Buttons
        self.btn_download = TransparentToolButton(FluentIcon.DOWNLOAD, self)
        self.btn_download.setEnabled(False)
        self.btn_download.setToolTip("Save / Download Audio File As...")
        controls_row.addWidget(self.btn_download)

        self.btn_open_folder = TransparentToolButton(FluentIcon.FOLDER, self)
        self.btn_open_folder.setEnabled(False)
        self.btn_open_folder.setToolTip("Open Containing Folder in File Manager")
        controls_row.addWidget(self.btn_open_folder)

        main_layout.addLayout(controls_row)

    def _connect_signals(self):
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_stop.clicked.connect(self.stop)
        self.btn_download.clicked.connect(self._on_download_clicked)
        self.btn_open_folder.clicked.connect(self._on_open_folder_clicked)

        self.vol_slider.valueChanged.connect(lambda v: self.audio_output.setVolume(v / 100.0))

        # Waveform seek signal
        self.waveform.seek_requested.connect(self._on_waveform_seek)

        # Player signals
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)

    def _on_download_clicked(self):
        if not self.current_file or not self.current_file.is_file():
            return

        ext = self.current_file.suffix.lower()
        filter_str = f"Audio File (*{ext});;All Files (*)"
        dest_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Audio File As",
            self.current_file.name,
            filter_str,
        )
        if dest_path:
            try:
                shutil.copy2(self.current_file, dest_path)
                InfoBar.success(
                    title="Download Complete! 💾",
                    content=f"Saved to {Path(dest_path).name}",
                    parent=self.window(),
                    position=InfoBarPosition.TOP,
                )
            except Exception as e:
                InfoBar.error(title="Save Failed", content=str(e), parent=self.window())

    def _on_open_folder_clicked(self):
        if not self.current_file or not self.current_file.is_file():
            return
        folder = self.current_file.parent
        try:
            if sys.platform.startswith("linux"):
                subprocess.Popen(["xdg-open", str(folder)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            elif sys.platform == "win32":
                import os
                os.startfile(str(folder))
        except Exception as e:
            logger.error("Failed to open file manager: %s", e)

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
        self.btn_download.setEnabled(True)
        self.btn_open_folder.setEnabled(True)
        self.lbl_time.setText("00:00 / 00:00")
        self.waveform.load_audio(str(path))
        self.lbl_time.setText("00:00 / 00:00")
        self.waveform.load_audio(str(path))

    def seek_seconds(self, seconds: float):
        """Seek player to exact timestamp in seconds."""
        pos_ms = int(max(0.0, seconds) * 1000)
        self.player.setPosition(pos_ms)
        self.waveform.set_position(pos_ms)
        self._update_time_label(pos_ms, self.player.duration())

    def seek_and_play(self, seconds: float):
        """Seek to timestamp and commence playback."""
        self.seek_seconds(seconds)
        self.play()

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
