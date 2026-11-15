from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from app.core.audio_pipeline import AudioPipeline
from app.core.project_manager import Project


class PodcastMixerWidget(QFrame):
    """Audio post-processing, background music auto-ducking, and audiobook metadata mastering."""

    play_audio_requested = Signal(str, str)  # audio_path, title

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setProperty("class", "card-panel")

        self.project: Optional[Project] = None
        self.pipeline = AudioPipeline()
        self.music_file_path: Optional[Path] = None
        self.cover_image_path: Optional[Path] = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(12)

        # Header
        top_bar = QHBoxLayout()
        lbl_heading = QLabel("Podcast & Music Studio (Post-Processing)")
        lbl_heading.setProperty("class", "heading")
        top_bar.addWidget(lbl_heading)
        top_bar.addStretch()
        self.lbl_project_status = QLabel("No Project Loaded")
        self.lbl_project_status.setStyleSheet("color: #a6adc8; font-weight: bold;")
        top_bar.addWidget(self.lbl_project_status)
        main_layout.addLayout(top_bar)

        # Grid: Left = Background Music & Ducking | Right = Metadata & Cover Art
        grid = QGridLayout()
        grid.setSpacing(14)

        # 1. Left Panel: Background Music & Auto-Ducking
        music_box = QFrame()
        music_box.setProperty("class", "card-panel")
        m_layout = QVBoxLayout(music_box)
        m_layout.setSpacing(10)

        lbl_m_head = QLabel("🎵 Ambient Music & Auto-Ducking")
        lbl_m_head.setStyleSheet("font-weight: bold; color: #89b4fa; font-size: 14px;")
        m_layout.addWidget(lbl_m_head)

        # Music File Picker
        file_row = QHBoxLayout()
        self.txt_music_path = QLineEdit()
        self.txt_music_path.setPlaceholderText("Select background music track (.mp3, .wav)...")
        self.txt_music_path.setReadOnly(True)
        self.btn_browse_music = QPushButton("📂 Browse")
        self.btn_browse_music.setProperty("class", "btn-secondary")
        file_row.addWidget(self.txt_music_path)
        file_row.addWidget(self.btn_browse_music)
        m_layout.addLayout(file_row)

        # Music Volume Slider
        self.lbl_music_vol = QLabel("Music Volume: 22%")
        self.lbl_music_vol.setStyleSheet("color: #a6adc8;")
        self.slider_music_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_music_vol.setRange(5, 60)
        self.slider_music_vol.setValue(22)
        m_layout.addWidget(self.lbl_music_vol)
        m_layout.addWidget(self.slider_music_vol)

        # Ducking Intensity (Ratio)
        self.lbl_ducking_ratio = QLabel("Auto-Ducking Intensity: 6.0x (Speech priority)")
        self.lbl_ducking_ratio.setStyleSheet("color: #a6adc8;")
        self.slider_ducking = QSlider(Qt.Orientation.Horizontal)
        self.slider_ducking.setRange(2, 16)
        self.slider_ducking.setValue(6)
        m_layout.addWidget(self.lbl_ducking_ratio)
        m_layout.addWidget(self.slider_ducking)

        # Music Fade Out
        self.lbl_fade_out = QLabel("End Music Fade-Out: 2.0s")
        self.lbl_fade_out.setStyleSheet("color: #a6adc8;")
        self.slider_fade = QSlider(Qt.Orientation.Horizontal)
        self.slider_fade.setRange(10, 50)
        self.slider_fade.setValue(20)
        m_layout.addWidget(self.lbl_fade_out)
        m_layout.addWidget(self.slider_fade)

        m_layout.addStretch()
        grid.addWidget(music_box, 0, 0)

        # 2. Right Panel: Metadata & Cover Art
        meta_box = QFrame()
        meta_box.setProperty("class", "card-panel")
        meta_layout = QVBoxLayout(meta_box)
        meta_layout.setSpacing(8)

        lbl_meta_head = QLabel("📖 Audiobook & Podcast Metadata")
        lbl_meta_head.setStyleSheet("font-weight: bold; color: #89b4fa; font-size: 14px;")
        meta_layout.addWidget(lbl_meta_head)

        # Inputs
        self.txt_title = QLineEdit()
        self.txt_title.setPlaceholderText("Title (e.g. The Cosmic Journey - Chapter 1)")
        meta_layout.addWidget(QLabel("Title:"))
        meta_layout.addWidget(self.txt_title)

        self.txt_author = QLineEdit()
        self.txt_author.setPlaceholderText("Author / Creator")
        meta_layout.addWidget(QLabel("Author / Creator:"))
        meta_layout.addWidget(self.txt_author)

        self.txt_narrator = QLineEdit()
        self.txt_narrator.setPlaceholderText("Narrator / Speaker")
        meta_layout.addWidget(QLabel("Narrator:"))
        meta_layout.addWidget(self.txt_narrator)

        # Cover Image Picker
        cover_row = QHBoxLayout()
        self.txt_cover_path = QLineEdit()
        self.txt_cover_path.setPlaceholderText("Cover Image (.jpg, .png)...")
        self.txt_cover_path.setReadOnly(True)
        self.btn_browse_cover = QPushButton("🖼 Cover")
        self.btn_browse_cover.setProperty("class", "btn-secondary")
        cover_row.addWidget(self.txt_cover_path)
        cover_row.addWidget(self.btn_browse_cover)
        meta_layout.addWidget(QLabel("Cover Art:"))
        meta_layout.addLayout(cover_row)

        grid.addWidget(meta_box, 0, 1)
        main_layout.addLayout(grid, stretch=1)

        # Bottom Bar: Output Format & Master Export Button
        bottom_box = QFrame()
        bottom_box.setProperty("class", "card-panel")
        b_layout = QHBoxLayout(bottom_box)
        b_layout.setSpacing(12)

        lbl_exp = QLabel("Master Output Format:")
        lbl_exp.setStyleSheet("font-weight: bold; color: #cdd6f4;")
        self.combo_format = QComboBox()
        self.combo_format.addItems([
            "M4B Audiobook (.m4b) [Chapters + AAC + Cover Art]",
            "Podcast MP3 (.mp3) [ID3 Tags + Cover Art]",
            "Lossless Archive (.wav)",
            "Lossless FLAC (.flac)",
        ])

        self.btn_render_master = QPushButton("🚀 Produce Final Mastered Audio")
        self.btn_render_master.setProperty("class", "btn-primary")
        self.btn_render_master.setFixedHeight(40)

        b_layout.addWidget(lbl_exp)
        b_layout.addWidget(self.combo_format, stretch=1)
        b_layout.addWidget(self.btn_render_master)
        main_layout.addWidget(bottom_box)

    def _connect_signals(self):
        self.btn_browse_music.clicked.connect(self._browse_music)
        self.btn_browse_cover.clicked.connect(self._browse_cover)

        self.slider_music_vol.valueChanged.connect(
            lambda v: self.lbl_music_vol.setText(f"Music Volume: {v}%")
        )
        self.slider_ducking.valueChanged.connect(
            lambda v: self.lbl_ducking_ratio.setText(f"Auto-Ducking Intensity: {v}.0x (Speech priority)")
        )
        self.slider_fade.valueChanged.connect(
            lambda v: self.lbl_fade_out.setText(f"End Music Fade-Out: {v / 10.0:.1f}s")
        )

        self.btn_render_master.clicked.connect(self._on_produce_master)

    def load_project(self, project: Project):
        self.project = project
        self.lbl_project_status.setText(f"Project: {project.name}")
        self.txt_title.setText(project.name)
        if not self.txt_author.text():
            self.txt_author.setText("Author")
        if not self.txt_narrator.text():
            self.txt_narrator.setText(project.voice_key)

    def _browse_music(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Background Music File",
            "",
            "Audio Files (*.mp3 *.wav *.ogg *.flac *.m4a);;All Files (*)",
        )
        if file_path:
            self.music_file_path = Path(file_path)
            self.txt_music_path.setText(self.music_file_path.name)

    def _browse_cover(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Cover Image",
            "",
            "Images (*.jpg *.jpeg *.png *.webp);;All Files (*)",
        )
        if file_path:
            self.cover_image_path = Path(file_path)
            self.txt_cover_path.setText(self.cover_image_path.name)

    def _on_produce_master(self):
        if not self.project:
            QMessageBox.warning(self, "No Project", "Please load a project first from Projects or Studio.")
            return

        # Check completed segments
        completed_blocks = [b for b in self.project.blocks if b.status == "completed" and b.audio_file]
        if not completed_blocks:
            QMessageBox.warning(self, "Incomplete Project", "Please synthesize speech blocks before producing final master.")
            return

        # 1. First build the master speech WAV
        try:
            speech_master = self.project.build_master_audio(output_format="wav", pause_ms=350, normalize=True)
        except Exception as e:
            QMessageBox.critical(self, "Master Error", f"Failed building speech track: {e}")
            return

        active_track = speech_master

        # 2. If background music is chosen, apply real-time auto-ducking
        if self.music_file_path and self.music_file_path.is_file():
            mixed_wav = self.project.exports_dir / f"{self.project.name}_podcast_mix.wav"
            vol = self.slider_music_vol.value() / 100.0
            ratio = float(self.slider_ducking.value())
            fade = self.slider_fade.value() / 10.0

            try:
                self.pipeline.mix_background_music(
                    speech_wav=speech_master,
                    music_file=self.music_file_path,
                    output_wav=mixed_wav,
                    music_volume=vol,
                    ducking_ratio=ratio,
                    fade_out_sec=fade,
                )
                active_track = mixed_wav
            except Exception as e:
                QMessageBox.critical(self, "Music Mixing Error", f"Failed mixing background music: {e}")
                return

        # 3. Metadata dictionary
        metadata = {
            "title": self.txt_title.text().strip() or self.project.name,
            "artist": self.txt_author.text().strip() or "Voice Studio",
            "album": self.txt_title.text().strip() or self.project.name,
            "composer": self.txt_narrator.text().strip() or self.project.voice_key,
            "comment": "Produced with Local Voice Engine Studio",
        }

        # 4. Chapters generation from blocks
        chapters = []
        cur_ms = 0
        for i, b in enumerate(self.project.blocks):
            dur_ms = int(b.duration * 1000)
            chapters.append({
                "start_ms": cur_ms,
                "end_ms": cur_ms + dur_ms,
                "title": f"Chapter {i+1}: {b.text[:30]}..." if len(b.text) > 30 else f"Chapter {i+1}: {b.text}",
            })
            cur_ms += dur_ms + 350

        # 5. Export to target format
        fmt_selection = self.combo_format.currentText()
        exports_dir = self.project.exports_dir

        try:
            final_file = None
            if "M4B" in fmt_selection:
                final_file = exports_dir / f"{self.project.name}_audiobook.m4b"
                self.pipeline.export_to_m4b(
                    input_wav=active_track,
                    output_m4b=final_file,
                    bitrate="128k",
                    metadata=metadata,
                    chapters=chapters,
                    cover_image=self.cover_image_path,
                )
            elif "MP3" in fmt_selection:
                final_file = exports_dir / f"{self.project.name}_podcast.mp3"
                self.pipeline.export_to_mp3(
                    input_wav=active_track,
                    output_mp3=final_file,
                    bitrate="192k",
                    metadata=metadata,
                    cover_image=self.cover_image_path,
                )
            elif "FLAC" in fmt_selection:
                final_file = exports_dir / f"{self.project.name}_lossless.flac"
                self.pipeline.export_to_flac(
                    input_wav=active_track,
                    output_flac=final_file,
                    metadata=metadata,
                )
            else:  # WAV
                final_file = exports_dir / f"{self.project.name}_production_master.wav"
                import shutil
                shutil.copy2(active_track, final_file)

            # Play final track
            self.play_audio_requested.emit(str(final_file), f"Master: {final_file.name}")

            QMessageBox.information(
                self,
                "Production Master Ready! 🎧",
                f"Your production-grade audio has been successfully mastered!\n\n"
                f"File: {final_file.name}\n"
                f"Location: {final_file.parent}\n"
                f"Format: {final_file.suffix.upper()}",
            )

        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Could not export mastered audio: {e}")
