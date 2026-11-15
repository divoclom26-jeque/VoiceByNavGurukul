import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QTableWidgetItem,
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
    PrimaryPushButton,
    PushButton,
    SubtitleLabel,
    TableWidget,
    TransparentToolButton,
)

from app.core.project_manager import Project
from app.core.screenplay import CHARACTER_COLORS
from app.tts.piper_engine import PiperTTSEngine
from app.tts.voice_manager import list_local_voices
from app.utils.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)


class CharacterPaletteDialog(QDialog):
    """Modern Fluent 2 Dialog for assigning voices and colors to characters in a screenplay."""

    palette_applied = Signal()

    def __init__(self, project: Project, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Character Voice Palette & Multi-Speaker Studio")
        self.resize(720, 480)
        self.setMinimumSize(600, 380)

        self.preview_player = QMediaPlayer(self)
        self.preview_output = QAudioOutput(self)
        self.preview_player.setAudioOutput(self.preview_output)
        self.preview_output.setVolume(0.9)

        self.available_voices = list_local_voices()
        self.character_widgets: Dict[str, ComboBox] = {}

        self._setup_ui()
        self._load_characters()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # Header
        top_layout = QVBoxLayout()
        top_layout.setSpacing(2)
        lbl_head = SubtitleLabel("🎭 Character Voice Palette & Multi-Speaker Studio", self)
        lbl_sub = CaptionLabel(
            "Assign distinct local voices and accent colors to each character in your story.",
            self,
        )
        top_layout.addWidget(lbl_head)
        top_layout.addWidget(lbl_sub)
        main_layout.addLayout(top_layout)

        # Main Card & Table
        card = CardWidget(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(10)

        self.table = TableWidget(self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([
            "Character",
            "Lines Spoken",
            "Assigned Voice",
            "Preview",
        ])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(TableWidget.EditTrigger.NoEditTriggers)

        card_layout.addWidget(self.table, stretch=1)
        main_layout.addWidget(card, stretch=1)

        # Footer
        footer = QHBoxLayout()
        footer.addStretch()

        self.btn_save = PrimaryPushButton(FluentIcon.SAVE, "Apply to All Dialogue", self)
        self.btn_save.clicked.connect(self._save_palette)
        self.btn_close = PushButton("Close", self)
        self.btn_close.clicked.connect(self.reject)

        footer.addWidget(self.btn_save)
        footer.addWidget(self.btn_close)
        main_layout.addLayout(footer)

    def _load_characters(self):
        palette = self.project.get_character_palette()
        # Also find all speakers present in blocks
        all_speakers = list(palette.keys())
        for b in self.project.blocks:
            if b.speaker_label and b.speaker_label not in all_speakers:
                all_speakers.append(b.speaker_label)

        if not all_speakers:
            all_speakers = ["Narrator"]

        self.table.setRowCount(len(all_speakers))
        self.character_widgets.clear()

        for row, char_name in enumerate(all_speakers):
            char_data = palette.get(char_name, {})
            color = char_data.get("color", CHARACTER_COLORS[row % len(CHARACTER_COLORS)])
            assigned_voice = char_data.get("voice_key") or self.project.voice_key

            # Count lines
            line_count = sum(1 for b in self.project.blocks if b.speaker_label == char_name)

            # Col 0: Character name with color dot
            char_item = QTableWidgetItem(f"●  {char_name}")
            char_item.setForeground(Qt.GlobalColor.black)
            self.table.setItem(row, 0, char_item)

            # Col 1: Line count
            lines_item = QTableWidgetItem(f"{line_count} lines")
            lines_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, lines_item)

            # Col 2: Voice ComboBox
            combo = ComboBox(self)
            for v in self.available_voices:
                lang = v.get("language", "en")
                flag = "🇮🇳" if lang.startswith("hi") else "🇺🇸"
                combo.addItem(f"{flag} {v['name']} ({lang})", userData=v["key"])

            # Set current voice selection
            idx = combo.findData(assigned_voice)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            elif self.available_voices:
                combo.setCurrentIndex(row % len(self.available_voices))

            self.table.setCellWidget(row, 2, combo)
            self.character_widgets[char_name] = combo

            # Col 3: Preview button
            btn_play = TransparentToolButton(FluentIcon.PLAY, self)
            btn_play.setToolTip(f"Test Voice Sample for {char_name}")
            btn_play.clicked.connect(lambda _, c=combo, name=char_name: self._preview_character_voice(name, c.currentData()))
            self.table.setCellWidget(row, 3, btn_play)

    def _preview_character_voice(self, char_name: str, voice_key: str):
        if not voice_key:
            return

        voices = {v["key"]: v for v in self.available_voices}
        if voice_key not in voices:
            return

        voice_cfg = dict(voices[voice_key])
        test_dir = PROJECT_ROOT / "projects" / "_preview"
        test_dir.mkdir(parents=True, exist_ok=True)
        preview_wav = test_dir / f"char_preview_{char_name}.wav"

        sample_text = (
            f"नमस्ते, मैं {char_name} हूँ।"
            if voice_key.startswith("hi")
            else f"Hello, I am {char_name}."
        )

        try:
            engine = PiperTTSEngine()
            engine.synthesize_to_wav(sample_text, preview_wav, voice_cfg)
            self.preview_player.setSource(QUrl.fromLocalFile(str(preview_wav)))
            self.preview_player.play()
            InfoBar.success(
                title=f"Sample Playing: {char_name} 🎧",
                content=f"Using voice {voice_key}",
                parent=self,
                position=InfoBarPosition.TOP,
            )
        except Exception as e:
            logger.error("Preview voice failed: %s", e)
            InfoBar.error(title="Preview Error", content=str(e), parent=self)

    def _save_palette(self):
        """Apply assigned voices to all lines spoken by each character."""
        for char_name, combo in self.character_widgets.items():
            selected_voice = combo.currentData()
            if selected_voice:
                self.project.set_character_voice(
                    character=char_name,
                    voice_key=selected_voice,
                    update_blocks=True,
                )

        self.project.save()
        self.palette_applied.emit()
        InfoBar.success(
            title="Voices Applied 🎉",
            content="Multi-speaker character voices updated across the project.",
            parent=self,
            position=InfoBarPosition.TOP,
        )
        self.accept()
