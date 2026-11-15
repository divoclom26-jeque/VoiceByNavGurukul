import logging
from pathlib import Path
from typing import Optional
from PySide6.QtCore import QTime, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
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
    LineEdit,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    SubtitleLabel,
)
import soundfile as sf

from app.clone.dsp import AudioDSP
from app.clone.engine import VoiceCloningEngine
from app.clone.profile import CloneManager
from app.tts.voice_manager import list_local_voices

logger = logging.getLogger(__name__)


class CloneVoiceDialog(QDialog):
    """Modern Fluent 2 Voice Cloning Studio Dialog (100% Offline, Zero-GPU)."""

    voice_cloned = Signal(str)  # Emits clone_id upon successful creation
    preview_requested = Signal(str, str)  # audio_path, title

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Clone AI Voice Profile")
        self.setMinimumWidth(560)
        self.setMinimumHeight(480)

        self.clone_manager = CloneManager()
        self.cloning_engine = VoiceCloningEngine()
        self.selected_sample_path: Optional[Path] = None

        self._setup_ui()
        self._populate_base_voices()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(14)

        # Header
        head_row = QHBoxLayout()
        icon_lbl = SubtitleLabel("🎙️ Clone AI Voice Profile", self)
        head_row.addWidget(icon_lbl)
        head_row.addStretch()
        badge = CaptionLabel("100% Offline · Zero GPU", self)
        badge.setStyleSheet("color: #0284C7; font-weight: 600; background: rgba(2, 132, 199, 0.1); padding: 4px 8px; border-radius: 4px;")
        head_row.addWidget(badge)
        main_layout.addLayout(head_row)

        desc = BodyLabel(
            "Create a personal AI voice from just 5 to 15 seconds of clear speech.\n"
            "Runs purely on your CPU with hardware AVX-512 acceleration. Your voice data remains 100% private.",
            self,
        )
        desc.setStyleSheet("color: #64748B; font-size: 13px;")
        main_layout.addWidget(desc)

        # Settings Card
        settings_card = CardWidget(self)
        card_layout = QVBoxLayout(settings_card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(10)

        card_layout.addWidget(CaptionLabel("Voice Name:", self))
        self.txt_name = LineEdit(self)
        self.txt_name.setPlaceholderText("e.g. My Personal Voice, Rahul Narrator...")
        self.txt_name.setText("My Cloned Voice")
        card_layout.addWidget(self.txt_name)

        row_meta = QHBoxLayout()
        row_meta.setSpacing(12)

        col_lang = QVBoxLayout()
        col_lang.addWidget(CaptionLabel("Primary Language:", self))
        self.combo_lang = ComboBox(self)
        self.combo_lang.addItem("🇮🇳 Hindi (hi_IN)", userData="hi_IN")
        self.combo_lang.addItem("🇺🇸 English (en_US)", userData="en_US")
        col_lang.addWidget(self.combo_lang)
        row_meta.addLayout(col_lang, stretch=1)

        col_base = QVBoxLayout()
        col_base.addWidget(CaptionLabel("Base Acoustic Model:", self))
        self.combo_base_voice = ComboBox(self)
        col_base.addWidget(self.combo_base_voice)
        row_meta.addLayout(col_base, stretch=1)
        card_layout.addLayout(row_meta)

        # Reference Sample Ingestion Card
        card_layout.addSpacing(6)
        card_layout.addWidget(CaptionLabel("Reference Voice Sample (5 - 15 Seconds of Speech):", self))

        file_row = QHBoxLayout()
        self.txt_file = LineEdit(self)
        self.txt_file.setPlaceholderText("Select a clear voice recording (.wav, .mp3, .ogg, .flac)...")
        self.btn_browse = PushButton(FluentIcon.FOLDER, "Browse File", self)
        self.btn_browse.clicked.connect(self._browse_audio)
        file_row.addWidget(self.txt_file, stretch=1)
        file_row.addWidget(self.btn_browse)
        card_layout.addLayout(file_row)

        self.lbl_sample_info = CaptionLabel("No sample selected. Recommended: 5-10s of normal speaking pace.", self)
        self.lbl_sample_info.setStyleSheet("color: #64748B; font-style: italic;")
        card_layout.addWidget(self.lbl_sample_info)

        main_layout.addWidget(settings_card)

        # Progress / Status
        self.progress_bar = ProgressBar(self)
        self.progress_bar.setVisible(False)
        self.lbl_status = CaptionLabel("", self)
        self.lbl_status.setVisible(False)
        main_layout.addWidget(self.lbl_status)
        main_layout.addWidget(self.progress_bar)

        # Bottom Button Row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_test = PushButton(FluentIcon.PLAY, "Test Voice", self)
        self.btn_test.setEnabled(False)
        self.btn_test.clicked.connect(self._test_voice_sample)
        btn_row.addWidget(self.btn_test)

        btn_row.addStretch()

        self.btn_cancel = PushButton("Cancel", self)
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)

        self.btn_save = PrimaryPushButton(FluentIcon.ADD, "Create Voice Profile", self)
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self._create_voice_profile)
        btn_row.addWidget(self.btn_save)

        main_layout.addLayout(btn_row)

    def _populate_base_voices(self):
        self.combo_base_voice.clear()
        voices = list_local_voices(include_clones=False)
        for v in voices:
            flag = "🇮🇳" if v.get("language", "").startswith("hi") else "🇺🇸"
            self.combo_base_voice.addItem(f"{flag} {v['name']}", userData=v["key"])
        if voices:
            self.combo_base_voice.setCurrentIndex(0)

    def _browse_audio(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Reference Voice Audio",
            "",
            "Audio Files (*.wav *.mp3 *.ogg *.flac *.m4a);;All Files (*)",
        )
        if not file_path:
            return

        p = Path(file_path).resolve()
        if not p.is_file():
            return

        self.selected_sample_path = p
        self.txt_file.setText(p.name)

        # Inspect duration
        try:
            info = sf.info(str(p))
            dur = info.duration
            if dur < 2.0:
                self.lbl_sample_info.setText(f"⚠️ Warning: Sample is short ({dur:.1f}s). At least 3-5s recommended.")
                self.lbl_sample_info.setStyleSheet("color: #DC2626; font-weight: 500;")
                self.btn_save.setEnabled(False)
                self.btn_test.setEnabled(False)
            else:
                self.lbl_sample_info.setText(f"✓ Valid Speech Sample: {dur:.1f}s · {info.samplerate} Hz · Ready to clone")
                self.lbl_sample_info.setStyleSheet("color: #16A34A; font-weight: 500;")
                self.btn_save.setEnabled(True)
                self.btn_test.setEnabled(True)
        except Exception as e:
            self.lbl_sample_info.setText(f"❌ Error reading audio: {e}")
            self.lbl_sample_info.setStyleSheet("color: #DC2626;")
            self.btn_save.setEnabled(False)
            self.btn_test.setEnabled(False)

    def _create_voice_profile(self):
        if not self.selected_sample_path or not self.selected_sample_path.is_file():
            InfoBar.warning(title="Missing Sample", content="Please select a voice audio file first.", parent=self)
            return

        name = self.txt_name.text().strip() or "My Cloned Voice"
        lang = self.combo_lang.currentData() or "hi_IN"
        base_voice = self.combo_base_voice.currentData() or "hi_IN-pratham-medium"

        self.btn_save.setEnabled(False)
        self.btn_browse.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.lbl_status.setVisible(True)
        self.progress_bar.setValue(25)
        self.lbl_status.setText("Extracting acoustic speaker embedding on CPU...")

        try:
            profile = self.clone_manager.create_clone(
                name=name,
                reference_audio_path=self.selected_sample_path,
                language=lang,
                base_voice_key=base_voice,
            )
            self.progress_bar.setValue(100)
            self.lbl_status.setText("Voice profile created successfully!")
            self.voice_cloned.emit(profile.id)
            InfoBar.success(
                title="Voice Cloned! ✨",
                content=f"Created '{profile.name}' — available in Studio dropdown.",
                parent=self.parent() or self,
                position=InfoBarPosition.TOP,
            )
            self.accept()
        except Exception as e:
            logger.exception("Voice cloning failed:")
            self.btn_save.setEnabled(True)
            self.btn_browse.setEnabled(True)
            self.progress_bar.setVisible(False)
            self.lbl_status.setVisible(False)
            InfoBar.error(title="Cloning Failed", content=str(e), parent=self)

    def _test_voice_sample(self):
        if not self.selected_sample_path or not self.selected_sample_path.is_file():
            return

        name = self.txt_name.text().strip() or "Test Voice"
        lang = self.combo_lang.currentData() or "hi_IN"
        base_voice = self.combo_base_voice.currentData() or "hi_IN-pratham-medium"

        try:
            # Temporary clone profile for test
            temp_profile = self.clone_manager.create_clone(
                name=f"temp_preview_{int(QTime.currentTime().msecsSinceStartOfDay())}",
                reference_audio_path=self.selected_sample_path,
                language=lang,
                base_voice_key=base_voice,
            )

            test_text = (
                "नमस्ते! यह आपकी क्लोन की गई नई आवाज़ का टेस्ट सैंपल है।"
                if lang.startswith("hi")
                else "Hello! This is a test sample of your newly cloned voice profile."
            )
            test_wav = temp_profile.clone_dir / "preview_test.wav"
            self.cloning_engine.synthesize_cloned(test_text, temp_profile.id, test_wav)

            # Request preview playback
            self.preview_requested.emit(str(test_wav), f"Preview: {name}")

            InfoBar.success(
                title="Voice Preview Ready 🎧",
                content=f"Playing synthesized test in cloned tone.",
                parent=self,
                position=InfoBarPosition.TOP,
            )
        except Exception as e:
            InfoBar.error(title="Preview Failed", content=str(e), parent=self)
