import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.text_processor import TextProcessor
from app.tts import PiperTTSEngine, list_local_voices
from app.ui.components.block_table import BlockTableWidget
from app.ui.components.editor_widget import EditorWidget
from app.ui.components.player_widget import AudioPlayerWidget
from app.ui.components.project_history import ProjectHistoryWidget
from app.ui.components.voice_gallery import VoiceGalleryWidget
from app.ui.workers import SynthesisWorker
from app.utils.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main Application Window for Local Voice Engine Studio."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Voice Studio AI — Local & Offline Audio Production")
        self.resize(1180, 780)
        self.setMinimumSize(960, 640)

        self.current_worker: Optional[SynthesisWorker] = None

        self._setup_ui()
        self._load_stylesheet()
        self._populate_voices()
        self._connect_signals()

    def _load_stylesheet(self):
        qss_path = Path(__file__).parent / "styles.qss"
        if qss_path.is_file():
            self.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    def _setup_ui(self):
        central_widget = QWidget()
        central_widget.setObjectName("CentralWidget")
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Left Sidebar
        sidebar = self._build_sidebar()
        main_layout.addWidget(sidebar)

        # 2. Right Stacked Pages
        self.stack = QStackedWidget()
        self.page_studio = self._build_studio_page()
        self.page_blocks = BlockTableWidget()
        self.page_gallery = VoiceGalleryWidget()
        self.page_projects = ProjectHistoryWidget()

        self.stack.addWidget(self.page_studio)    # index 0
        self.stack.addWidget(self.page_blocks)    # index 1
        self.stack.addWidget(self.page_gallery)   # index 2
        self.stack.addWidget(self.page_projects)  # index 3

        main_layout.addWidget(self.stack, stretch=1)

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(210)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 20, 14, 20)
        layout.setSpacing(8)

        # App Brand
        lbl_title = QLabel("🎙️ Voice Studio")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #89b4fa;")
        lbl_sub = QLabel("Local AI Audio Engine")
        lbl_sub.setStyleSheet("font-size: 11px; color: #6c7086; margin-bottom: 12px;")
        layout.addWidget(lbl_title)
        layout.addWidget(lbl_sub)

        # Nav Buttons Group
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        self.btn_nav_studio = QPushButton("📝 Studio Workspace")
        self.btn_nav_studio.setCheckable(True)
        self.btn_nav_studio.setChecked(True)
        self.btn_nav_studio.setProperty("class", "nav-btn")
        self.nav_group.addButton(self.btn_nav_studio, 0)

        self.btn_nav_blocks = QPushButton("🔍 Block Review")
        self.btn_nav_blocks.setCheckable(True)
        self.btn_nav_blocks.setProperty("class", "nav-btn")
        self.nav_group.addButton(self.btn_nav_blocks, 1)

        self.btn_nav_gallery = QPushButton("🌐 Voice Gallery")
        self.btn_nav_gallery.setCheckable(True)
        self.btn_nav_gallery.setProperty("class", "nav-btn")
        self.nav_group.addButton(self.btn_nav_gallery, 2)

        self.btn_nav_projects = QPushButton("📚 Projects & History")
        self.btn_nav_projects.setCheckable(True)
        self.btn_nav_projects.setProperty("class", "nav-btn")
        self.nav_group.addButton(self.btn_nav_projects, 3)

        layout.addWidget(self.btn_nav_studio)
        layout.addWidget(self.btn_nav_blocks)
        layout.addWidget(self.btn_nav_gallery)
        layout.addWidget(self.btn_nav_projects)

        layout.addStretch()

        # Engine Status Pill
        status_box = QFrame()
        status_box.setStyleSheet("background-color: #11111b; border-radius: 8px; padding: 10px;")
        s_layout = QVBoxLayout(status_box)
        s_layout.setContentsMargins(6, 6, 6, 6)
        s_layout.setSpacing(4)
        lbl_eng = QLabel("Engine: Piper ONNX")
        lbl_eng.setStyleSheet("color: #a6adc8; font-size: 11px; font-weight: 600;")
        lbl_mode = QLabel("● 100% Offline / Local")
        lbl_mode.setStyleSheet("color: #a6e3a1; font-size: 11px;")
        s_layout.addWidget(lbl_eng)
        s_layout.addWidget(lbl_mode)
        layout.addWidget(status_box)

        return sidebar

    def _build_studio_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Top area: Split between Editor (Left) and Controls (Right)
        top_split = QHBoxLayout()
        top_split.setSpacing(12)

        # Editor
        self.editor = EditorWidget()
        top_split.addWidget(self.editor, stretch=3)

        # Settings Card Panel (Right)
        settings_panel = self._build_settings_panel()
        top_split.addWidget(settings_panel, stretch=1)

        layout.addLayout(top_split, stretch=1)

        # Progress Area
        self.progress_frame = QFrame()
        self.progress_frame.setProperty("class", "card-panel")
        self.progress_frame.setVisible(False)
        p_layout = QVBoxLayout(self.progress_frame)
        p_layout.setContentsMargins(12, 10, 12, 10)
        p_layout.setSpacing(6)

        p_top = QHBoxLayout()
        self.lbl_progress_status = QLabel("Synthesizing audio blocks...")
        self.lbl_progress_status.setStyleSheet("font-weight: 600; color: #89b4fa;")
        self.btn_cancel = QPushButton("✖ Cancel")
        self.btn_cancel.setProperty("class", "btn-danger")
        self.btn_cancel.setFixedWidth(90)
        p_top.addWidget(self.lbl_progress_status)
        p_top.addStretch()
        p_top.addWidget(self.btn_cancel)
        p_layout.addLayout(p_top)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        p_layout.addWidget(self.progress_bar)

        layout.addWidget(self.progress_frame)

        # Audio Player (Bottom)
        self.player = AudioPlayerWidget()
        layout.addWidget(self.player)

        return page

    def _build_settings_panel(self) -> QWidget:
        panel = QFrame()
        panel.setProperty("class", "card-panel")
        panel.setFixedWidth(290)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        lbl_header = QLabel("Voice & Audio Settings")
        lbl_header.setProperty("class", "heading")
        layout.addWidget(lbl_header)

        # Voice Selector
        lbl_v = QLabel("Speaker Voice:")
        lbl_v.setStyleSheet("color: #a6adc8; font-weight: 500;")
        self.combo_voices = QComboBox()
        layout.addWidget(lbl_v)
        layout.addWidget(self.combo_voices)

        # Test Voice Button
        self.btn_test_voice = QPushButton("🔊 Test Voice Sample")
        self.btn_test_voice.setProperty("class", "btn-secondary")
        layout.addWidget(self.btn_test_voice)

        layout.addSpacing(6)

        # Speed Slider
        self.lbl_speed_val = QLabel("Speed: 1.0x")
        self.lbl_speed_val.setStyleSheet("color: #a6adc8; font-weight: 500;")
        self.slider_speed = QSlider(Qt.Orientation.Horizontal)
        self.slider_speed.setRange(50, 200)
        self.slider_speed.setValue(100)
        layout.addWidget(self.lbl_speed_val)
        layout.addWidget(self.slider_speed)

        # Pause Between Chunks Slider
        self.lbl_pause_val = QLabel("Inter-sentence Pause: 350 ms")
        self.lbl_pause_val.setStyleSheet("color: #a6adc8; font-weight: 500;")
        self.slider_pause = QSlider(Qt.Orientation.Horizontal)
        self.slider_pause.setRange(100, 1000)
        self.slider_pause.setValue(350)
        layout.addWidget(self.lbl_pause_val)
        layout.addWidget(self.slider_pause)

        # Export Format
        lbl_fmt = QLabel("Export Format:")
        lbl_fmt.setStyleSheet("color: #a6adc8; font-weight: 500;")
        self.combo_format = QComboBox()
        self.combo_format.addItems(["WAV (Lossless)", "MP3 (192 kbps)"])
        layout.addWidget(lbl_fmt)
        layout.addWidget(self.combo_format)

        # Normalization Checkbox
        self.chk_loudnorm = QCheckBox("Loudness Normalization (EBU R128)")
        self.chk_loudnorm.setChecked(True)
        self.chk_loudnorm.setStyleSheet("color: #cdd6f4;")
        layout.addWidget(self.chk_loudnorm)

        layout.addStretch()

        # Big Generate Studio Audio Button
        self.btn_generate = QPushButton("✨ Generate Studio Audio")
        self.btn_generate.setProperty("class", "btn-primary")
        self.btn_generate.setFixedHeight(44)
        layout.addWidget(self.btn_generate)

        return panel

    def _populate_voices(self):
        self.combo_voices.clear()
        voices = list_local_voices()
        for v in voices:
            lang = v.get("language", "en")
            flag = "🇮🇳" if lang.startswith("hi") else "🇺🇸"
            self.combo_voices.addItem(f"{flag} {v['name']} ({lang})", v["key"])

        if not voices:
            self.combo_voices.addItem("No voice installed (Visit Gallery)", None)
            self.btn_generate.setEnabled(False)
            self.btn_test_voice.setEnabled(False)
        else:
            self.btn_generate.setEnabled(True)
            self.btn_test_voice.setEnabled(True)

    def _connect_signals(self):
        # Nav buttons
        self.nav_group.idClicked.connect(self.stack.setCurrentIndex)

        # Sliders
        self.slider_speed.valueChanged.connect(
            lambda v: self.lbl_speed_val.setText(f"Speed: {v / 100.0:.2f}x")
        )
        self.slider_pause.valueChanged.connect(
            lambda v: self.lbl_pause_val.setText(f"Inter-sentence Pause: {v} ms")
        )

        # Actions
        self.btn_generate.clicked.connect(self._on_start_synthesis)
        self.btn_cancel.clicked.connect(self._on_cancel_synthesis)
        self.btn_test_voice.clicked.connect(self._on_test_voice)
        self.editor.btn_preview_chunks.clicked.connect(self._preview_chunks)

        # Voice gallery signal
        self.page_gallery.voice_installed.connect(lambda _: self._populate_voices())

        # Block review signals
        self.page_blocks.play_block_requested.connect(
            lambda path, title: (self.player.load_audio(path, title), self.player.play())
        )

        # Projects history signals
        self.page_projects.play_audio_requested.connect(
            lambda path, title: (self.player.load_audio(path, title), self.player.play())
        )
        self.page_projects.load_project_requested.connect(self._on_load_project_from_history)

    def _preview_chunks(self):
        text = self.editor.get_text()
        if not text:
            QMessageBox.information(self, "Preview Chunks", "Please enter some text in the editor first.")
            return

        blocks = TextProcessor.split_into_blocks(text, max_chars=280)
        sample = "\n\n".join([f"[{i+1}] ({len(b)} chars): {b}" for i, b in enumerate(blocks[:8])])
        if len(blocks) > 8:
            sample += f"\n\n... and {len(blocks) - 8} more blocks."

        msg = f"Your text will be safely divided into {len(blocks)} blocks:\n\n{sample}"
        QMessageBox.information(self, "Chunking Breakdown", msg)

    def _on_test_voice(self):
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
        test_wav = test_dir / f"sample_{voice_key}.wav"

        # Test text
        sample_text = (
            "नमस्ते! यह आपकी आवाज़ का नमूना है।"
            if voice_key.startswith("hi")
            else "Hello! This is a test sample of the selected voice."
        )

        try:
            engine = PiperTTSEngine()
            engine.synthesize_to_wav(sample_text, test_wav, voice_cfg)
            self.player.load_audio(str(test_wav), f"Sample: {voice_key}")
            self.player.play()
        except Exception as e:
            QMessageBox.critical(self, "Voice Test Failed", str(e))

    def _on_start_synthesis(self):
        text = self.editor.get_text()
        if not text:
            QMessageBox.warning(self, "Empty Text", "Please enter or paste text before generating audio.")
            return

        voice_key = self.combo_voices.currentData()
        if not voice_key:
            QMessageBox.warning(self, "No Voice", "Please select a valid voice model.")
            return

        project_name = self.editor.get_project_name()
        speed = self.slider_speed.value() / 100.0
        pause_ms = self.slider_pause.value()
        fmt = "mp3" if "MP3" in self.combo_format.currentText() else "wav"
        norm = self.chk_loudnorm.isChecked()

        # UI state during generation
        self.btn_generate.setEnabled(False)
        self.btn_test_voice.setEnabled(False)
        self.progress_frame.setVisible(True)
        self.progress_bar.setValue(0)
        self.lbl_progress_status.setText("Initializing synthesis pipeline...")

        # Start QThread worker
        self.current_worker = SynthesisWorker(
            project_name=project_name,
            text=text,
            voice_key=voice_key,
            speed=speed,
            pause_ms=pause_ms,
            output_format=fmt,
            normalize=norm,
            parent=self,
        )
        self.current_worker.progress.connect(self._on_worker_progress)
        self.current_worker.finished.connect(self._on_worker_finished)
        self.current_worker.error.connect(self._on_worker_error)
        self.current_worker.cancelled.connect(self._on_worker_cancelled)
        self.current_worker.start()

    def _on_worker_progress(self, current: int, total: int, status: str):
        if total > 0:
            pct = int((current / total) * 100)
            self.progress_bar.setValue(pct)
        self.lbl_progress_status.setText(status)

    def _on_worker_finished(self, master_path: str, duration: float, project_name: str):
        self.btn_generate.setEnabled(True)
        self.btn_test_voice.setEnabled(True)
        self.progress_frame.setVisible(False)

        # Load into player and auto-play
        self.player.load_audio(master_path, f"{project_name} ({duration:.1f}s)")
        self.player.play()

        # Load project into Block Review table
        try:
            from app.core.project_manager import Project, ProjectManager
            from app.utils.paths import PROJECTS_DIR
            slug = ProjectManager.slugify(project_name)
            p_dir = PROJECTS_DIR / slug
            if p_dir.is_dir():
                proj = Project.load(p_dir)
                self.page_blocks.load_project(proj)
        except Exception as e:
            logger.warning(f"Could not load project into blocks page: {e}")

        # Refresh project history tab
        self.page_projects.refresh()

        QMessageBox.information(
            self,
            "Generation Complete! 🎉",
            f"Successfully produced master audio for '{project_name}'!\n\n"
            f"Duration: {duration:.1f} seconds\n"
            f"Saved to: {master_path}\n\n"
            "Tip: You can now review each block individually in the 'Block Review' tab!",
        )

    def _on_load_project_from_history(self, project_dir_str: str):
        try:
            from app.core.project_manager import Project
            p_dir = Path(project_dir_str)
            proj = Project.load(p_dir)
            self.page_blocks.load_project(proj)
            self.editor.set_project_name(proj.name)
            # Reconstruct text in editor
            all_text = "\n\n".join(b.text for b in proj.blocks)
            self.editor.set_text(all_text)
            self.btn_nav_blocks.setChecked(True)
            self.stack.setCurrentIndex(1)
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Could not load project: {e}")

    def _on_worker_error(self, err_msg: str):
        self.btn_generate.setEnabled(True)
        self.btn_test_voice.setEnabled(True)
        self.progress_frame.setVisible(False)
        QMessageBox.critical(self, "Synthesis Error", f"Failed to synthesize audio:\n\n{err_msg}")

    def _on_cancel_synthesis(self):
        if self.current_worker and self.current_worker.isRunning():
            self.lbl_progress_status.setText("Cancelling synthesis...")
            self.current_worker.cancel()

    def _on_worker_cancelled(self):
        self.btn_generate.setEnabled(True)
        self.btn_test_voice.setEnabled(True)
        self.progress_frame.setVisible(False)
        QMessageBox.information(self, "Cancelled", "Synthesis was cancelled by user.")
