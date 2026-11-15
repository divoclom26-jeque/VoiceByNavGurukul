from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CaptionLabel,
    CardWidget,
    ComboBox,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    Slider,
    SubtitleLabel,
    SwitchButton,
)

from app.core.audio_pipeline import AudioPipeline
from app.core.project_manager import Project


class MixerInterface(QWidget):
    """Podcast & Ambient Music Studio built with Fluent 2 design."""

    play_audio_requested = Signal(str, str)  # audio_path, title

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("mixer_interface")

        self.project: Optional[Project] = None
        self.pipeline = AudioPipeline()
        self.music_file_path: Optional[Path] = None
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # Header
        self.lbl_head = SubtitleLabel("Podcast & Music Studio", self)
        main_layout.addWidget(self.lbl_head)

        grid = QGridLayout()
        grid.setSpacing(16)

        # 1. Left Card: Music & Ducking
        music_card = CardWidget(self)
        m_layout = QVBoxLayout(music_card)
        m_layout.setContentsMargins(16, 16, 16, 16)
        m_layout.setSpacing(12)

        m_head = SubtitleLabel("🎵 Ambient Music & Auto-Ducking", self)
        m_layout.addWidget(m_head)

        m_layout.addWidget(CaptionLabel("Background Music File:", self))
        file_row = QHBoxLayout()
        self.txt_music = LineEdit(self)
        self.txt_music.setPlaceholderText("Select background music track (.mp3, .wav)...")
        self.btn_browse = PushButton(FluentIcon.FOLDER, "Browse", self)
        self.btn_browse.clicked.connect(self._browse_music)
        file_row.addWidget(self.txt_music)
        file_row.addWidget(self.btn_browse)
        m_layout.addLayout(file_row)

        self.lbl_vol = CaptionLabel("Music Volume: 22%", self)
        self.slider_vol = Slider(Qt.Orientation.Horizontal, self)
        self.slider_vol.setRange(5, 60)
        self.slider_vol.setValue(22)
        self.slider_vol.valueChanged.connect(lambda v: self.lbl_vol.setText(f"Music Volume: {v}%"))
        m_layout.addWidget(self.lbl_vol)
        m_layout.addWidget(self.slider_vol)

        self.lbl_ducking = CaptionLabel("Auto-Ducking Speech Priority: 6.0x", self)
        self.slider_ducking = Slider(Qt.Orientation.Horizontal, self)
        self.slider_ducking.setRange(3, 15)
        self.slider_ducking.setValue(6)
        self.slider_ducking.valueChanged.connect(
            lambda v: self.lbl_ducking.setText(f"Auto-Ducking Speech Priority: {v}.0x")
        )
        m_layout.addWidget(self.lbl_ducking)
        m_layout.addWidget(self.slider_ducking)

        m_layout.addStretch()
        grid.addWidget(music_card, 0, 0)

        # 2. Right Card: Audiobook Metadata
        meta_card = CardWidget(self)
        meta_layout = QVBoxLayout(meta_card)
        meta_layout.setContentsMargins(16, 16, 16, 16)
        meta_layout.setSpacing(10)

        meta_head = SubtitleLabel("📖 Audiobook & Podcast Metadata", self)
        meta_layout.addWidget(meta_head)

        meta_layout.addWidget(CaptionLabel("Book / Episode Title:", self))
        self.txt_title = LineEdit(self)
        meta_layout.addWidget(self.txt_title)

        meta_layout.addWidget(CaptionLabel("Author / Creator:", self))
        self.txt_author = LineEdit(self)
        self.txt_author.setText("Voice Studio Creator")
        meta_layout.addWidget(self.txt_author)

        meta_layout.addWidget(CaptionLabel("Narrator / Speaker:", self))
        self.txt_narrator = LineEdit(self)
        meta_layout.addWidget(self.txt_narrator)

        meta_layout.addWidget(CaptionLabel("Target Container:", self))
        self.combo_format = ComboBox(self)
        self.combo_format.addItems([
            "M4B Audiobook (Chapters + AAC)",
            "MP3 Podcast (ID3 Tags)",
            "FLAC Lossless Master",
            "WAV Studio Wave",
            "🎬 Audiogram Video (1080p MP4)",
            "📜 Synchronized Subtitles (.SRT)",
            "🌐 WebVTT Subtitles (.VTT)",
        ])
        meta_layout.addWidget(self.combo_format)

        # Audiogram Options Container (Visible only when Audiogram Video is selected)
        self.audiogram_box = QWidget(self)
        ag_layout = QVBoxLayout(self.audiogram_box)
        ag_layout.setContentsMargins(0, 4, 0, 0)
        ag_layout.setSpacing(6)

        self.lbl_aspect = CaptionLabel("Video Aspect Ratio:", self.audiogram_box)
        ag_layout.addWidget(self.lbl_aspect)
        self.combo_aspect = ComboBox(self.audiogram_box)
        self.combo_aspect.addItem("1:1 Square (Instagram / Post)", userData="square")
        self.combo_aspect.addItem("9:16 Vertical (Reels / Shorts / TikTok)", userData="vertical")
        self.combo_aspect.addItem("16:9 Landscape (YouTube / Desktop)", userData="landscape")
        ag_layout.addWidget(self.combo_aspect)

        burn_row = QHBoxLayout()
        burn_row.addWidget(CaptionLabel("Burn Subtitles into Video:", self.audiogram_box))
        self.switch_burn_subs = SwitchButton(self.audiogram_box)
        self.switch_burn_subs.setChecked(True)
        burn_row.addWidget(self.switch_burn_subs)
        burn_row.addStretch()
        ag_layout.addLayout(burn_row)

        self.audiogram_box.setVisible(False)
        meta_layout.addWidget(self.audiogram_box)
        self.combo_format.currentIndexChanged.connect(self._on_format_changed)

        grid.addWidget(meta_card, 0, 1)

        # 3. Bottom Row: Studio Mastering FX Card
        fx_card = CardWidget(self)
        fx_layout = QVBoxLayout(fx_card)
        fx_layout.setContentsMargins(16, 14, 16, 14)
        fx_layout.setSpacing(10)

        fx_head = SubtitleLabel("🎚️ Studio Mastering FX Presets", self)
        fx_layout.addWidget(fx_head)

        fx_row = QHBoxLayout()
        fx_row.setSpacing(12)

        preset_col = QVBoxLayout()
        preset_col.addWidget(CaptionLabel("Mastering Preset:", self))
        self.combo_fx_preset = ComboBox(self)
        self.combo_fx_preset.addItem("🎙️ Podcast Warmth", userData="podcast_warmth")
        self.combo_fx_preset.addItem("📻 Broadcast Clarity", userData="broadcast_clarity")
        self.combo_fx_preset.addItem("📖 Audiobook Standard (ACX)", userData="audiobook_acx")
        self.combo_fx_preset.addItem("⚡ Crisp & Clean", userData="crisp_clean")
        self.combo_fx_preset.addItem("🚫 Bypass FX (Raw Voice)", userData="bypass")
        preset_col.addWidget(self.combo_fx_preset)
        fx_row.addLayout(preset_col, stretch=2)

        room_col = QVBoxLayout()
        room_col.addWidget(CaptionLabel("Natural Room Tone:", self))
        self.switch_mixer_room_tone = SwitchButton(self)
        self.switch_mixer_room_tone.setChecked(False)
        self.switch_mixer_room_tone.setToolTip("Subtle acoustic room presence during silence gaps")
        room_col.addWidget(self.switch_mixer_room_tone)
        fx_row.addLayout(room_col, stretch=1)

        fx_layout.addLayout(fx_row)

        self.lbl_fx_desc = CaptionLabel(
            "Rich low-end proximity (+3dB @ 120Hz) with smooth optical compression (-16 LUFS)",
            self,
        )
        self.lbl_fx_desc.setStyleSheet("font-style: italic; color: #555;")
        self.combo_fx_preset.currentIndexChanged.connect(self._update_fx_desc)
        fx_layout.addWidget(self.lbl_fx_desc)

        grid.addWidget(fx_card, 1, 0, 1, 2)
        main_layout.addLayout(grid, stretch=1)

        # Production Action Button
        self.btn_produce = PrimaryPushButton(FluentIcon.MUSIC, "Produce Final Mastered Audio", self)
        self.btn_produce.setFixedHeight(42)
        self.btn_produce.clicked.connect(self._produce_master)
        main_layout.addWidget(self.btn_produce)

    def _on_format_changed(self):
        is_audiogram = "Audiogram" in self.combo_format.currentText()
        self.audiogram_box.setVisible(is_audiogram)

    def _update_fx_desc(self):
        preset_key = self.combo_fx_preset.currentData() or "podcast_warmth"
        preset = self.pipeline.STUDIO_PRESETS.get(preset_key, {})
        desc = preset.get("desc", "")
        target_i = preset.get("target_i", -16.0)
        self.lbl_fx_desc.setText(f"{desc} (Target: {target_i} LUFS)")

    def load_project(self, project: Project):
        self.project = project
        self.lbl_head.setText(f"Podcast & Music Studio: {project.name}")
        self.txt_title.setText(project.name)
        self.txt_narrator.setText(project.voice_key)

    def _browse_music(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Background Music", "", "Audio (*.mp3 *.wav *.ogg *.flac);;All (*)"
        )
        if file_path:
            self.music_file_path = Path(file_path)
            self.txt_music.setText(self.music_file_path.name)

    def _produce_master(self):
        if not self.project:
            InfoBar.warning(title="No Project", content="Please synthesize a story first.", parent=self)
            return

        try:
            # 1. Base speech master with selected Studio FX preset
            fx_key = self.combo_fx_preset.currentData() or "podcast_warmth"
            room_tone = self.switch_mixer_room_tone.isChecked()

            speech_master = self.project.build_master_audio(
                output_format="wav",
                pause_ms=350,
                normalize=True,
                fx_preset=fx_key,
                add_room_tone=room_tone,
            )
            active_track = speech_master

            # 2. Ducking if music provided
            if self.music_file_path and self.music_file_path.is_file():
                mixed_wav = self.project.exports_dir / f"{self.project.name}_podcast_mix.wav"
                self.pipeline.mix_background_music(
                    speech_wav=speech_master,
                    music_file=self.music_file_path,
                    output_wav=mixed_wav,
                    music_volume=self.slider_vol.value() / 100.0,
                    ducking_ratio=float(self.slider_ducking.value()),
                )
                active_track = mixed_wav

            metadata = {
                "title": self.txt_title.text().strip() or self.project.name,
                "artist": self.txt_author.text().strip() or "Voice Studio",
                "album": self.txt_title.text().strip() or self.project.name,
                "composer": self.txt_narrator.text().strip() or self.project.voice_key,
            }

            chapters = []
            cur_ms = 0
            for i, b in enumerate(self.project.blocks):
                dur_ms = int(b.duration * 1000)
                chapters.append({
                    "start_ms": cur_ms,
                    "end_ms": cur_ms + dur_ms,
                    "title": f"Chapter {i+1}: {b.text[:30]}",
                })
                cur_ms += dur_ms + 350

            fmt_text = self.combo_format.currentText()
            final_file = None

            if "Audiogram" in fmt_text:
                aspect = self.combo_aspect.currentData() or "square"
                burn_subs = self.switch_burn_subs.isChecked()
                srt_path = None
                if burn_subs:
                    srt_path = self.project.export_subtitles(format="srt")

                final_file = self.project.exports_dir / f"{self.project.name}_audiogram_{aspect}.mp4"
                self.pipeline.export_audiogram_video(
                    speech_wav=active_track,
                    output_mp4=final_file,
                    title=metadata["title"],
                    author=metadata["artist"],
                    subtitle_srt=srt_path,
                    aspect_ratio=aspect,
                )
                InfoBar.success(
                    title="Audiogram Video Ready! 🎬",
                    content=f"Saved HD video to {final_file.name}",
                    parent=self,
                    position=InfoBarPosition.TOP,
                )
                return

            elif "SRT" in fmt_text:
                final_file = self.project.export_subtitles(format="srt")
                InfoBar.success(
                    title="Synchronized Subtitles Ready! 📜",
                    content=f"Saved SRT file to {final_file.name}",
                    parent=self,
                    position=InfoBarPosition.TOP,
                )
                return

            elif "VTT" in fmt_text:
                final_file = self.project.export_subtitles(format="vtt")
                InfoBar.success(
                    title="WebVTT Subtitles Ready! 🌐",
                    content=f"Saved VTT file to {final_file.name}",
                    parent=self,
                    position=InfoBarPosition.TOP,
                )
                return

            elif "M4B" in fmt_text:
                final_file = self.project.exports_dir / f"{self.project.name}_audiobook.m4b"
                self.pipeline.export_to_m4b(active_track, final_file, metadata=metadata, chapters=chapters)
            elif "MP3" in fmt_text:
                final_file = self.project.exports_dir / f"{self.project.name}_podcast.mp3"
                self.pipeline.export_to_mp3(active_track, final_file, metadata=metadata)
            elif "FLAC" in fmt_text:
                final_file = self.project.exports_dir / f"{self.project.name}_lossless.flac"
                self.pipeline.export_to_flac(active_track, final_file, metadata=metadata)
            else:
                final_file = self.project.exports_dir / f"{self.project.name}_master.wav"
                import shutil
                if active_track != final_file:
                    shutil.copy2(active_track, final_file)

            self.play_audio_requested.emit(str(final_file), f"Master: {final_file.name}")
            InfoBar.success(
                title="Production Master Ready! 🎧",
                content=f"Saved to {final_file.name}",
                parent=self,
                position=InfoBarPosition.TOP,
            )
        except Exception as e:
            InfoBar.error(title="Mastering Error", content=str(e), parent=self)
