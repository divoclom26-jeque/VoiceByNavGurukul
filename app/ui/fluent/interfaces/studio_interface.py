from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
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
    PlainTextEdit,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    Slider,
    SubtitleLabel,
    SwitchButton,
)

from app.core.text_processor import TextProcessor
from app.tts import PiperTTSEngine, list_local_voices
from app.ui.workers import SynthesisWorker
from app.utils.paths import PROJECT_ROOT


class StudioInterface(QWidget):
    """Studio Workspace Interface built with Fluent 2 design principles."""

    synthesis_completed = Signal(str, float, str)  # master_path, duration, project_name
    test_voice_requested = Signal(str, str)  # audio_path, title

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("studio_interface")

        self.current_worker: Optional[SynthesisWorker] = None
        self._setup_ui()
        self._populate_voices()
        self._connect_signals()

    def _setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # Left Card: Text & Script Editor
        self.editor_card = CardWidget(self)
        editor_layout = QVBoxLayout(self.editor_card)
        editor_layout.setContentsMargins(16, 16, 16, 16)
        editor_layout.setSpacing(10)

        # Title Row
        title_row = QHBoxLayout()
        lbl_proj = BodyLabel("Project Title:", self)
        lbl_proj.setStyleSheet("font-weight: 600;")
        self.txt_title = LineEdit(self)
        self.txt_title.setText("My Audio Story")
        self.txt_title.setPlaceholderText("Enter project name...")

        self.btn_characters = PushButton(FluentIcon.PEOPLE, "Characters", self)
        self.btn_characters.setToolTip("Configure multi-speaker drama characters & voice palette")
        self.btn_lexicon = PushButton(FluentIcon.DICTIONARY, "Pronunciation", self)
        self.btn_lexicon.setToolTip("Customize phonetic word substitutions & acronyms")
        self.btn_import = PushButton(FluentIcon.FOLDER, "Open File", self)
        self.btn_clear = PushButton(FluentIcon.DELETE, "Clear", self)

        title_row.addWidget(lbl_proj)
        title_row.addWidget(self.txt_title, stretch=1)
        title_row.addWidget(self.btn_characters)
        title_row.addWidget(self.btn_lexicon)
        title_row.addWidget(self.btn_import)
        title_row.addWidget(self.btn_clear)
        editor_layout.addLayout(title_row)

        # Editor
        self.text_edit = PlainTextEdit(self)
        self.text_edit.setPlaceholderText(
            "Write or paste your script or story here...\n\n"
            "Supports Hindi and English. Markdown headers, quotes, and punctuation boundaries are normalized automatically."
        )
        self.text_edit.setPlainText(
            "एक समय की बात है। एक छोटे से गाँव में एक जिज्ञासु बालक रहता था।\n"
            "उसका सपना था कि वह एक दिन पूरी दुनिया की सैर करेगा और नई चीजें सीखेगा।\n"
            "हर शाम वह गाँव के किनारे बैठकर दूर क्षितिज को देखता था।"
        )
        editor_layout.addWidget(self.text_edit, stretch=1)

        # Bottom Metrics
        self.lbl_metrics = CaptionLabel("Words: 0 | Chars: 0 | Est. read: 0s | Blocks: 0", self)
        self.lbl_metrics.setStyleSheet("font-weight: 500;")
        editor_layout.addWidget(self.lbl_metrics)

        main_layout.addWidget(self.editor_card, stretch=3)

        # Right Card: Voice Settings
        self.settings_card = CardWidget(self)
        self.settings_card.setFixedWidth(310)
        settings_layout = QVBoxLayout(self.settings_card)
        settings_layout.setContentsMargins(16, 16, 16, 16)
        settings_layout.setSpacing(12)

        lbl_head = SubtitleLabel("Voice & Engine", self)
        settings_layout.addWidget(lbl_head)

        # Voice Selector
        settings_layout.addWidget(CaptionLabel("Speaker Voice:", self))
        self.combo_voices = ComboBox(self)
        settings_layout.addWidget(self.combo_voices)

        # Test Voice Button
        self.btn_test = PushButton(FluentIcon.PLAY, "Test Voice Sample", self)
        settings_layout.addWidget(self.btn_test)

        settings_layout.addSpacing(6)

        # Speed Slider
        self.lbl_speed = CaptionLabel("Speech Speed: 1.00x", self)
        self.slider_speed = Slider(Qt.Orientation.Horizontal, self)
        self.slider_speed.setRange(50, 200)
        self.slider_speed.setValue(100)
        settings_layout.addWidget(self.lbl_speed)
        settings_layout.addWidget(self.slider_speed)

        # Pause Slider
        self.lbl_pause = CaptionLabel("Sentence Pause: 350 ms", self)
        self.slider_pause = Slider(Qt.Orientation.Horizontal, self)
        self.slider_pause.setRange(100, 1000)
        self.slider_pause.setValue(350)
        settings_layout.addWidget(self.lbl_pause)
        settings_layout.addWidget(self.slider_pause)

        # Format
        settings_layout.addWidget(CaptionLabel("Master Format:", self))
        self.combo_format = ComboBox(self)
        self.combo_format.addItems(["WAV (Lossless)", "MP3 (192 kbps)"])
        settings_layout.addWidget(self.combo_format)

        # Mastering FX Preset
        settings_layout.addWidget(CaptionLabel("Mastering FX Preset:", self))
        self.combo_preset = ComboBox(self)
        self.combo_preset.addItem("⚡ Crisp & Clean (Default)", userData="crisp_clean")
        self.combo_preset.addItem("🎙️ Podcast Warmth", userData="podcast_warmth")
        self.combo_preset.addItem("📻 Broadcast Clarity", userData="broadcast_clarity")
        self.combo_preset.addItem("📖 Audiobook Standard (ACX)", userData="audiobook_acx")
        self.combo_preset.addItem("🚫 Bypass FX (Raw Voice)", userData="bypass")
        settings_layout.addWidget(self.combo_preset)

        # Room Tone Switch
        room_row = QHBoxLayout()
        room_row.addWidget(CaptionLabel("Natural Room Tone:", self))
        self.switch_room_tone = SwitchButton(self)
        self.switch_room_tone.setChecked(False)
        self.switch_room_tone.setToolTip("Adds subtle acoustic room presence during silence to eliminate artificial digital void.")
        room_row.addStretch()
        room_row.addWidget(self.switch_room_tone)
        settings_layout.addLayout(room_row)

        # Loudnorm Switch
        loudnorm_row = QHBoxLayout()
        loudnorm_row.addWidget(CaptionLabel("EBU R128 Loudnorm:", self))
        self.switch_loudnorm = SwitchButton(self)
        self.switch_loudnorm.setChecked(True)
        loudnorm_row.addStretch()
        loudnorm_row.addWidget(self.switch_loudnorm)
        settings_layout.addLayout(loudnorm_row)

        settings_layout.addStretch()

        # Progress Display
        self.progress_bar = ProgressBar(self)
        self.progress_bar.setVisible(False)
        self.lbl_progress = CaptionLabel("", self)
        self.lbl_progress.setVisible(False)
        settings_layout.addWidget(self.lbl_progress)
        settings_layout.addWidget(self.progress_bar)

        # Generate Button
        self.btn_generate = PrimaryPushButton(FluentIcon.MICROPHONE, "Generate Studio Audio", self)
        self.btn_generate.setFixedHeight(40)
        settings_layout.addWidget(self.btn_generate)

        main_layout.addWidget(self.settings_card, stretch=1)

    def _populate_voices(self):
        self.combo_voices.clear()
        voices = list_local_voices()
        sorted_voices = sorted(
            voices,
            key=lambda x: (not x.get("language", "").startswith("hi"), x.get("name", "")),
        )
        for v in sorted_voices:
            lang = v.get("language", "en")
            flag = "🇮🇳" if lang.startswith("hi") else "🇺🇸"
            self.combo_voices.addItem(f"{flag} {v['name']} ({lang})", userData=v["key"])

        if not voices:
            self.combo_voices.addItem("No voice installed (Visit Gallery)", userData=None)
            self.btn_generate.setEnabled(False)
            self.btn_test.setEnabled(False)
        else:
            self.combo_voices.setCurrentIndex(0)
            self.btn_generate.setEnabled(True)
            self.btn_test.setEnabled(True)

    def _connect_signals(self):
        self.text_edit.textChanged.connect(self._update_metrics)
        self.btn_clear.clicked.connect(self.text_edit.clear)
        self.btn_import.clicked.connect(self._import_file)
        self.btn_characters.clicked.connect(self._open_characters_dialog)
        self.btn_lexicon.clicked.connect(self._open_lexicon_dialog)

        self.slider_speed.valueChanged.connect(
            lambda v: self.lbl_speed.setText(f"Speech Speed: {v / 100.0:.2f}x")
        )
        self.slider_pause.valueChanged.connect(
            lambda v: self.lbl_pause.setText(f"Sentence Pause: {v} ms")
        )

        self.btn_test.clicked.connect(self._test_voice)
        self.btn_generate.clicked.connect(self._start_synthesis)

        self._update_metrics()

    def _update_metrics(self):
        text = self.text_edit.toPlainText().strip()
        words = len(text.split()) if text else 0
        chars = len(text)
        est_sec = int((words / 150.0) * 60)
        mins, secs = divmod(est_sec, 60)
        time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
        blocks = TextProcessor.split_into_blocks(text, max_chars=280) if text else []

        from app.core.screenplay import ScreenplayParser

        has_screenplay = ScreenplayParser.has_screenplay_tags(text)
        characters = ScreenplayParser.extract_characters(text) if has_screenplay else []
        char_badge = f" | 🎭 {len(characters)} Characters ({', '.join(characters[:3])})" if characters else ""

        self.lbl_metrics.setText(
            f"Words: {words:,} | Chars: {chars:,} | Est. read: ~{time_str} | Blocks: {len(blocks)}{char_badge}"
        )

    def _open_characters_dialog(self):
        from app.core.project_manager import ProjectManager
        from app.core.screenplay import ScreenplayParser
        from app.ui.fluent.speaker_dialog import CharacterPaletteDialog

        text = self.text_edit.toPlainText().strip()
        if not text:
            InfoBar.warning(
                title="Empty Script",
                content="Please enter text or screenplay dialogue first.",
                parent=self,
            )
            return

        project_name = self.txt_title.text().strip() or "Untitled Story"
        voice_key = self.combo_voices.currentData() or "hi_IN-pratham-medium"
        speed = self.slider_speed.value() / 100.0

        project = ProjectManager.create_project(
            name=project_name,
            text=text,
            voice_key=voice_key,
            speed=speed,
        )

        dlg = CharacterPaletteDialog(project, parent=self.window())
        dlg.exec()

    def _import_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Text File", "", "Text & Markdown (*.txt *.md);;All Files (*)"
        )
        if file_path:
            p = Path(file_path)
            content = p.read_text(encoding="utf-8", errors="replace")
            self.text_edit.setPlainText(content)
            self.txt_title.setText(p.stem.replace("_", " ").title())

    def _open_lexicon_dialog(self):
        from app.ui.fluent.lexicon_dialog import LexiconDialog

        project_name = self.txt_title.text().strip() or "Untitled Story"
        safe_name = "".join(c for c in project_name if c.isalnum() or c in (" ", "-", "_")).strip()
        safe_name = safe_name.replace(" ", "_")
        proj_dir = PROJECT_ROOT / "projects" / safe_name if safe_name else None

        dialog = LexiconDialog(parent=self.window(), project_dir=proj_dir)
        dialog.rules_updated.connect(self._update_metrics)
        dialog.exec()

    def _test_voice(self):
        voice_key = self.combo_voices.currentData()
        if not voice_key:
            return

        voices = {v["key"]: v for v in list_local_voices()}
        if voice_key not in voices:
            return

        voice_cfg = dict(voices[voice_key])
        speed = self.slider_speed.value() / 100.0
        voice_cfg["speed"] = speed

        test_dir = PROJECT_ROOT / "projects" / "_preview"
        test_dir.mkdir(parents=True, exist_ok=True)
        test_wav = test_dir / f"test_{voice_key}.wav"

        sample_text = (
            "नमस्ते! यह आपकी चुनी हुई आवाज़ का नमूना है।"
            if voice_key.startswith("hi")
            else "Hello! This is a real-time sample of the selected voice."
        )

        try:
            engine = PiperTTSEngine()
            engine.synthesize_to_wav(sample_text, test_wav, voice_cfg)
            self.test_voice_requested.emit(str(test_wav), f"Sample: {voice_key}")
            InfoBar.success(
                title="Voice Preview Ready 🎧",
                content=f"Playing sample for {voice_key}",
                parent=self,
                position=InfoBarPosition.TOP,
            )
        except Exception as e:
            InfoBar.error(title="Test Failed", content=str(e), parent=self, position=InfoBarPosition.TOP)

    def _start_synthesis(self):
        text = self.text_edit.toPlainText().strip()
        if not text:
            InfoBar.warning(title="Empty Text", content="Please enter text to synthesize.", parent=self)
            return

        voice_key = self.combo_voices.currentData()
        if not voice_key:
            InfoBar.warning(title="No Voice", content="Please select a valid voice.", parent=self)
            return

        project_name = self.txt_title.text().strip() or "Untitled Story"
        speed = self.slider_speed.value() / 100.0
        pause_ms = self.slider_pause.value()
        fmt = "mp3" if "MP3" in self.combo_format.currentText() else "wav"
        norm = self.switch_loudnorm.isChecked()
        preset_key = self.combo_preset.currentData() or "crisp_clean"
        room_tone = self.switch_room_tone.isChecked()

        self.btn_generate.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.lbl_progress.setVisible(True)
        self.progress_bar.setValue(0)
        self.lbl_progress.setText("Initializing synthesis...")

        self.current_worker = SynthesisWorker(
            project_name=project_name,
            text=text,
            voice_key=voice_key,
            speed=speed,
            pause_ms=pause_ms,
            output_format=fmt,
            normalize=norm,
            fx_preset=preset_key,
            add_room_tone=room_tone,
            parent=self,
        )
        self.current_worker.progress.connect(self._on_progress)
        self.current_worker.finished.connect(self._on_finished)
        self.current_worker.error.connect(self._on_error)
        self.current_worker.start()

    def _on_progress(self, current: int, total: int, msg: str):
        if total > 0:
            self.progress_bar.setValue(int((current / total) * 100))
        self.lbl_progress.setText(msg)

    def _on_finished(self, master_path: str, duration: float, project_name: str):
        self.btn_generate.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.lbl_progress.setVisible(False)
        self.synthesis_completed.emit(master_path, duration, project_name)
        InfoBar.success(
            title="Generation Complete! 🎉",
            content=f"Master audio saved ({duration:.1f}s)",
            parent=self,
            position=InfoBarPosition.TOP,
        )

    def _on_error(self, err_msg: str):
        self.btn_generate.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.lbl_progress.setVisible(False)
        InfoBar.error(title="Synthesis Error", content=err_msg, parent=self, position=InfoBarPosition.TOP)
