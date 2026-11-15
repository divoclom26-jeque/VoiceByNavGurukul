import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    ComboBox,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    Slider,
    SubtitleLabel,
    TransparentPushButton,
)

from app.core.project_manager import Project, TextBlock
from app.tts.base import BaseTTSEngine
from app.tts.kokoro_engine import KokoroTTSEngine
from app.tts.piper_engine import PiperTTSEngine
from app.tts.voice_manager import list_local_voices
from app.utils.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)


class FluentBlockEditDialog(QDialog):
    """Modern Fluent 2 Dialog for Descript-style selective block editing, speed/pause tuning, and instant re-takes."""

    block_updated = Signal(int)  # block_id
    block_deleted = Signal(int)  # block_id

    def __init__(self, project: Project, block: TextBlock, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.project = project
        self.block = block
        self.setWindowTitle(f"Edit & Re-Take Block #{block.id}")
        self.resize(650, 520)
        self.setMinimumSize(560, 440)

        # Local audio preview player
        self.preview_player = QMediaPlayer(self)
        self.preview_output = QAudioOutput(self)
        self.preview_player.setAudioOutput(self.preview_output)
        self.preview_output.setVolume(0.9)

        self._setup_ui()
        self._load_block_data()
        self._connect_signals()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # Header
        top_row = QHBoxLayout()
        lbl_head = SubtitleLabel(f"⚡ Edit & Re-Take Block #{self.block.id}", self)
        top_row.addWidget(lbl_head)
        top_row.addStretch()

        dur_text = f"Duration: {self.block.duration:.2f}s" if self.block.duration > 0 else "Status: Pending"
        self.lbl_status = CaptionLabel(dur_text, self)
        self.lbl_status.setStyleSheet("font-weight: 600;")
        top_row.addWidget(self.lbl_status)
        main_layout.addLayout(top_row)

        # Main Card
        card = CardWidget(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)

        # Text Editor
        card_layout.addWidget(BodyLabel("Script / Sentence Text:", self))
        self.txt_content = PlainTextEdit(self)
        self.txt_content.setPlaceholderText("Enter sentence or dialogue...")
        card_layout.addWidget(self.txt_content, stretch=1)

        self.lbl_text_metrics = CaptionLabel("Words: 0 | Chars: 0", self)
        card_layout.addWidget(self.lbl_text_metrics)

        # Voice Override Row
        voice_row = QHBoxLayout()
        voice_row.addWidget(CaptionLabel("Speaker / Voice:", self))
        self.combo_voice = ComboBox(self)
        self.combo_voice.addItem("Default (Project Voice)", userData=None)
        voices = list_local_voices()
        for v in voices:
            lang = v.get("language", "en")
            flag = "🇮🇳" if lang.startswith("hi") else "🇺🇸"
            self.combo_voice.addItem(f"{flag} {v['name']} ({lang})", userData=v["key"])
        voice_row.addWidget(self.combo_voice, stretch=1)
        card_layout.addLayout(voice_row)

        # Sliders Row (Speed & Pause)
        sliders_row = QHBoxLayout()
        sliders_row.setSpacing(16)

        # Speed slider
        speed_col = QVBoxLayout()
        self.lbl_speed = CaptionLabel("Speech Speed: 1.00x", self)
        self.slider_speed = Slider(Qt.Orientation.Horizontal, self)
        self.slider_speed.setRange(50, 200)
        self.slider_speed.setValue(100)
        speed_col.addWidget(self.lbl_speed)
        speed_col.addWidget(self.slider_speed)
        sliders_row.addLayout(speed_col, stretch=1)

        # Pause slider
        pause_col = QVBoxLayout()
        self.lbl_pause = CaptionLabel("Silence After: 350 ms", self)
        self.slider_pause = Slider(Qt.Orientation.Horizontal, self)
        self.slider_pause.setRange(100, 2000)
        self.slider_pause.setValue(350)
        pause_col.addWidget(self.lbl_pause)
        pause_col.addWidget(self.slider_pause)
        sliders_row.addLayout(pause_col, stretch=1)

        card_layout.addLayout(sliders_row)
        main_layout.addWidget(card, stretch=1)

        # Footer Actions
        footer = QHBoxLayout()
        footer.setSpacing(10)

        self.btn_delete = TransparentPushButton(FluentIcon.DELETE, "Cut Block", self)
        self.btn_delete.setStyleSheet("color: #d32f2f; font-weight: 500;")
        footer.addWidget(self.btn_delete)

        footer.addStretch()

        self.btn_preview = PushButton(FluentIcon.PLAY, "Preview Re-Take", self)
        self.btn_save = PrimaryPushButton(FluentIcon.SAVE, "Apply to Master", self)
        self.btn_close = PushButton("Close", self)

        footer.addWidget(self.btn_preview)
        footer.addWidget(self.btn_save)
        footer.addWidget(self.btn_close)
        main_layout.addLayout(footer)

    def _load_block_data(self):
        self.txt_content.setPlainText(self.block.text)

        # Voice
        if self.block.voice_key:
            idx = self.combo_voice.findData(self.block.voice_key)
            if idx >= 0:
                self.combo_voice.setCurrentIndex(idx)
        else:
            self.combo_voice.setCurrentIndex(0)

        # Speed
        speed = self.block.speed or self.project.speed or 1.0
        self.slider_speed.setValue(int(speed * 100))
        self.lbl_speed.setText(f"Speech Speed: {speed:.2f}x")

        # Pause
        p_ms = self.block.pause_after_ms or 350
        self.slider_pause.setValue(p_ms)
        self.lbl_pause.setText(f"Silence After: {p_ms} ms")

        self._update_text_metrics()

    def _connect_signals(self):
        self.txt_content.textChanged.connect(self._update_text_metrics)
        self.slider_speed.valueChanged.connect(
            lambda v: self.lbl_speed.setText(f"Speech Speed: {v / 100.0:.2f}x")
        )
        self.slider_pause.valueChanged.connect(
            lambda v: self.lbl_pause.setText(f"Silence After: {v} ms")
        )

        self.btn_preview.clicked.connect(self._preview_retake)
        self.btn_save.clicked.connect(self._save_and_apply)
        self.btn_delete.clicked.connect(self._confirm_delete)
        self.btn_close.clicked.connect(self.reject)

    def _update_text_metrics(self):
        txt = self.txt_content.toPlainText().strip()
        words = len(txt.split()) if txt else 0
        chars = len(txt)
        self.lbl_text_metrics.setText(f"Words: {words} | Characters: {chars}")

    def _preview_retake(self):
        """Synthesize a quick isolated preview of the edited sentence."""
        text = self.txt_content.toPlainText().strip()
        if not text:
            InfoBar.warning(title="Empty Text", content="Text cannot be empty.", parent=self)
            return

        voice_key = self.combo_voice.currentData() or self.project.voice_key
        speed = self.slider_speed.value() / 100.0

        temp_dir = PROJECT_ROOT / "projects" / "_preview"
        temp_dir.mkdir(parents=True, exist_ok=True)
        preview_wav = temp_dir / f"retake_preview_{self.block.id}.wav"

        try:
            # Build engine config
            dummy_b = TextBlock(id=self.block.id, text=text, voice_key=voice_key, speed=speed)
            cfg = self.project.get_voice_config_for_block(dummy_b)
            engine = KokoroTTSEngine() if cfg.get("engine") == "kokoro" else PiperTTSEngine()
            engine.synthesize_to_wav(text, preview_wav, cfg)

            self.preview_player.setSource(QUrl.fromLocalFile(str(preview_wav)))
            self.preview_player.play()
            InfoBar.success(
                title="Preview Playing 🎧",
                content="Listening to sentence re-take",
                parent=self,
                position=InfoBarPosition.TOP,
            )
        except Exception as e:
            logger.error("Preview retake failed: %s", e)
            InfoBar.error(title="Preview Failed", content=str(e), parent=self)

    def _save_and_apply(self):
        """Save changes, execute instant re-take, and update master audio."""
        text = self.txt_content.toPlainText().strip()
        if not text:
            InfoBar.warning(title="Empty Text", content="Text cannot be empty.", parent=self)
            return

        voice_key = self.combo_voice.currentData()
        speed = self.slider_speed.value() / 100.0
        pause_ms = self.slider_pause.value()

        try:
            self.project.retake_block(
                block_id=self.block.id,
                new_text=text,
                voice_key=voice_key,
                speed=speed,
                pause_after_ms=pause_ms,
                rebuild_master=True,
            )
            self.block_updated.emit(self.block.id)
            self.accept()
        except Exception as e:
            logger.error("Failed to save and apply retake: %s", e)
            InfoBar.error(title="Re-Take Failed", content=str(e), parent=self)

    def _confirm_delete(self):
        """Cut block (Cut text = Cut audio)."""
        res = QMessageBox.question(
            self,
            "Cut Audio Block",
            f"Are you sure you want to cut Block #{self.block.id}? "
            "Its text and audio segment will be removed from the master project.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if res == QMessageBox.StandardButton.Yes:
            block_id = self.block.id
            if self.project.delete_block(block_id, rebuild_master=True):
                self.block_deleted.emit(block_id)
                self.accept()
            else:
                InfoBar.error(title="Delete Failed", content="Could not delete block.", parent=self)
