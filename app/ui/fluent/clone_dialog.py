import logging
from pathlib import Path
import re
import tempfile
from typing import List, Optional

import numpy as np

from PySide6.QtCore import QTime, QTimer, QUrl, Qt, Signal
from PySide6.QtMultimedia import (
    QAudioDevice,
    QAudioInput,
    QAudioOutput,
    QMediaCaptureSession,
    QMediaDevices,
    QMediaFormat,
    QMediaPlayer,
    QMediaRecorder,
)
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QStackedWidget,
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
    SegmentedWidget,
    Slider,
    SmoothScrollArea,
    SubtitleLabel,
    ToolButton,
)
import soundfile as sf

from app.clone.dsp import AudioDSP
from app.clone.engine import VoiceCloningEngine
from app.clone.profile import CloneManager
from app.tts.voice_manager import list_local_voices

logger = logging.getLogger(__name__)


class CloneVoiceDialog(QDialog):
    """Modern Fluent 2 Voice Cloning Studio Dialog.
    
    Supports:
    1. Direct in-app microphone recording (5-15 seconds) with live timer & instant playback.
    2. File upload (.wav, .mp3, .flac, .ogg, .m4a).
    3. 100% offline, zero-GPU acoustic biometric profile creation.
    """

    voice_cloned = Signal(str)  # Emits clone_id upon successful creation
    preview_requested = Signal(str, str)  # audio_path, title

    MAX_RECORDING_SECONDS = 15.0
    MIN_RECORDING_SECONDS = 2.0

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Clone AI Voice Profile")
        self.setFixedSize(620, 560)
        self.setSizeGripEnabled(False)

        self.clone_manager = CloneManager()
        self.cloning_engine = VoiceCloningEngine()
        
        self.selected_sample_path: Optional[Path] = None
        self.recorded_sample_path: Optional[Path] = None
        self.file_sample_path: Optional[Path] = None

        # Temp directory for mic recording
        self.temp_rec_dir = Path(tempfile.gettempdir()) / "voice_engine_recordings"
        self.temp_rec_dir.mkdir(parents=True, exist_ok=True)
        self.recorded_sample_path = self.temp_rec_dir / "mic_voice_sample.wav"

        # Recording state
        self._is_recording: bool = False
        self._audio_devices: List[QAudioDevice] = []

        # Audio capture session & recorder
        self._init_recording_engine()

        # Audio playback preview player
        self._init_playback_engine()

        self._setup_ui()
        self._populate_audio_devices()
        self._populate_base_voices()
        self._update_script_prompt()

    def _init_recording_engine(self):
        """Setup QtMultimedia capture session for direct microphone recording."""
        self.capture_session = QMediaCaptureSession(self)
        self.audio_input = QAudioInput(self)
        self.capture_session.setAudioInput(self.audio_input)

        self.recorder = QMediaRecorder(self)
        self.capture_session.setRecorder(self.recorder)

        # High-quality lossless Wave PCM format
        media_format = QMediaFormat()
        media_format.setFileFormat(QMediaFormat.FileFormat.Wave)
        media_format.setAudioCodec(QMediaFormat.AudioCodec.Wave)
        self.recorder.setMediaFormat(media_format)
        self.recorder.setQuality(QMediaRecorder.Quality.HighQuality)

        self.recorder.recorderStateChanged.connect(self._on_recorder_state_changed)
        self.recorder.durationChanged.connect(self._on_recorder_duration_changed)
        self.recorder.errorOccurred.connect(self._on_recorder_error)

    def _init_playback_engine(self):
        """Setup playback engine for previewing recorded sample."""
        self.preview_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.preview_player.setAudioOutput(self.audio_output)
        self.preview_player.playbackStateChanged.connect(self._on_playback_state_changed)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 16, 20, 16)
        main_layout.setSpacing(10)

        # Header (Compact)
        head_row = QHBoxLayout()
        icon_lbl = SubtitleLabel("🎙️ Clone AI Voice Profile", self)
        head_row.addWidget(icon_lbl)
        head_row.addStretch()
        badge = CaptionLabel("100% Offline · Zero GPU", self)
        badge.setStyleSheet(
            "color: #0284C7; font-weight: 600; background: rgba(2, 132, 199, 0.1); padding: 4px 8px; border-radius: 4px;"
        )
        head_row.addWidget(badge)
        main_layout.addLayout(head_row)

        desc = CaptionLabel(
            "Record 5-15s from your mic or upload an audio sample. Runs on CPU with hardware AVX-512 acceleration.",
            self,
        )
        desc.setStyleSheet("color: #64748B;")
        main_layout.addWidget(desc)

        # Voice Settings Card
        settings_card = CardWidget(self)
        card_layout = QVBoxLayout(settings_card)
        card_layout.setContentsMargins(14, 10, 14, 10)
        card_layout.setSpacing(8)

        # Row 1: Profile Name & Language
        row_name_lang = QHBoxLayout()
        row_name_lang.setSpacing(12)

        col_name = QVBoxLayout()
        col_name.setSpacing(3)
        col_name.addWidget(CaptionLabel("Voice Profile Name:", self))
        self.txt_name = LineEdit(self)
        self.txt_name.setPlaceholderText("e.g. My Cloned Voice")
        self.txt_name.setText("My Cloned Voice")
        col_name.addWidget(self.txt_name)
        row_name_lang.addLayout(col_name, stretch=3)

        col_lang = QVBoxLayout()
        col_lang.setSpacing(3)
        col_lang.addWidget(CaptionLabel("Primary Language:", self))
        self.combo_lang = ComboBox(self)
        self.combo_lang.addItem("🇮🇳 Hindi (hi_IN)", userData="hi_IN")
        self.combo_lang.addItem("🇺🇸 English (en_US)", userData="en_US")
        self.combo_lang.currentIndexChanged.connect(self._on_language_changed)
        col_lang.addWidget(self.combo_lang)
        row_name_lang.addLayout(col_lang, stretch=2)

        card_layout.addLayout(row_name_lang)

        # Row 2: Base Acoustic Model & Pitch Shift Slider
        row_base_pitch = QHBoxLayout()
        row_base_pitch.setSpacing(12)

        col_base = QVBoxLayout()
        col_base.setSpacing(3)
        col_base.addWidget(CaptionLabel("Base Acoustic Model:", self))
        self.combo_base_voice = ComboBox(self)
        col_base.addWidget(self.combo_base_voice)
        row_base_pitch.addLayout(col_base, stretch=3)

        col_pitch = QVBoxLayout()
        col_pitch.setSpacing(3)
        pitch_header = QHBoxLayout()
        pitch_header.addWidget(CaptionLabel("Acoustic Pitch Shift:", self))
        pitch_header.addStretch()
        self.lbl_pitch_val = CaptionLabel("Auto-Match (0.0 st)", self)
        self.lbl_pitch_val.setStyleSheet("color: #0284C7; font-weight: 600;")
        pitch_header.addWidget(self.lbl_pitch_val)
        col_pitch.addLayout(pitch_header)

        self.slider_pitch = Slider(Qt.Orientation.Horizontal, self)
        self.slider_pitch.setRange(-12, 12)
        self.slider_pitch.setValue(0)
        self.slider_pitch.valueChanged.connect(self._on_pitch_slider_changed)
        col_pitch.addWidget(self.slider_pitch)
        row_base_pitch.addLayout(col_pitch, stretch=3)

        card_layout.addLayout(row_base_pitch)
        main_layout.addWidget(settings_card)

        # Ingestion Mode Selection Card (Record vs Upload)
        input_card = CardWidget(self)
        input_layout = QVBoxLayout(input_card)
        input_layout.setContentsMargins(14, 10, 14, 10)
        input_layout.setSpacing(8)

        # Navigation Segmented Tabs
        self.seg_input_method = SegmentedWidget(self)
        self.seg_input_method.addItem("mic", "🎙️ Record Voice (Direct Mic)", onClick=lambda: self._switch_input_method(0))
        self.seg_input_method.addItem("file", "📁 Upload Audio File", onClick=lambda: self._switch_input_method(1))
        input_layout.addWidget(self.seg_input_method)

        # Stacked Pages
        self.stacked_input = QStackedWidget(self)

        # --- Page 0: Direct Mic Recording ---
        page_mic = QWidget(self)
        layout_mic = QVBoxLayout(page_mic)
        layout_mic.setContentsMargins(0, 4, 0, 0)
        layout_mic.setSpacing(6)

        # Mic Device Row
        row_dev = QHBoxLayout()
        row_dev.addWidget(CaptionLabel("Microphone:", self))
        self.combo_mics = ComboBox(self)
        self.combo_mics.currentIndexChanged.connect(self._on_mic_device_selected)
        row_dev.addWidget(self.combo_mics, stretch=1)
        self.btn_refresh_mics = ToolButton(FluentIcon.SYNC, self)
        self.btn_refresh_mics.setFixedSize(32, 32)
        self.btn_refresh_mics.setToolTip("Refresh Microphone Devices")
        self.btn_refresh_mics.clicked.connect(self._populate_audio_devices)
        row_dev.addWidget(self.btn_refresh_mics)
        layout_mic.addLayout(row_dev)

        # Script Prompt Box (Clean banner)
        self.box_prompt = QWidget(page_mic)
        self.box_prompt.setStyleSheet(
            "QWidget { background-color: rgba(2, 132, 199, 0.06); border: 1px solid rgba(2, 132, 199, 0.25); border-radius: 6px; }"
        )
        box_prompt_layout = QVBoxLayout(self.box_prompt)
        box_prompt_layout.setContentsMargins(8, 6, 8, 6)
        box_prompt_layout.setSpacing(2)

        prompt_header = CaptionLabel("📖 Suggested Reading Text (Speak clearly into your mic):", self.box_prompt)
        prompt_header.setStyleSheet("color: #0284C7; font-weight: 600; border: none; background: transparent;")
        box_prompt_layout.addWidget(prompt_header)

        self.lbl_script_prompt = BodyLabel("", self.box_prompt)
        self.lbl_script_prompt.setStyleSheet("color: #1E293B; font-size: 13px; font-weight: 500; border: none; background: transparent;")
        self.lbl_script_prompt.setWordWrap(True)
        box_prompt_layout.addWidget(self.lbl_script_prompt)
        layout_mic.addWidget(self.box_prompt)

        # Recording Actions Row
        rec_controls = QHBoxLayout()
        rec_controls.setSpacing(8)

        self.btn_record = PrimaryPushButton(FluentIcon.MICROPHONE, "Start Recording", page_mic)
        self.btn_record.setFixedHeight(34)
        self.btn_record.clicked.connect(self._toggle_record)
        rec_controls.addWidget(self.btn_record)

        self.btn_play_record = PushButton(FluentIcon.PLAY, "Listen to Recording", page_mic)
        self.btn_play_record.setFixedHeight(34)
        self.btn_play_record.setEnabled(False)
        self.btn_play_record.clicked.connect(self._toggle_playback_recording)
        rec_controls.addWidget(self.btn_play_record)

        rec_controls.addStretch()

        self.lbl_record_timer = CaptionLabel("00:00 / 00:15", page_mic)
        self.lbl_record_timer.setStyleSheet("font-size: 13px; font-weight: 600; color: #475569;")
        rec_controls.addWidget(self.lbl_record_timer)
        layout_mic.addLayout(rec_controls)

        # Recording Progress Bar (0 to 15s)
        self.record_progress = ProgressBar(page_mic)
        self.record_progress.setRange(0, 100)
        self.record_progress.setValue(0)
        layout_mic.addWidget(self.record_progress)

        self.lbl_mic_status = CaptionLabel("Click 'Start Recording' and read the suggested sentence (5-10s).", page_mic)
        self.lbl_mic_status.setStyleSheet("color: #64748B; font-style: italic;")
        layout_mic.addWidget(self.lbl_mic_status)

        self.stacked_input.addWidget(page_mic)

        # --- Page 1: File Upload ---
        page_file = QWidget(self)
        layout_file = QVBoxLayout(page_file)
        layout_file.setContentsMargins(0, 8, 0, 0)
        layout_file.setSpacing(8)

        layout_file.addWidget(CaptionLabel("Select an Audio File (5 - 15 Seconds of Speech):", page_file))
        file_row = QHBoxLayout()
        self.txt_file = LineEdit(page_file)
        self.txt_file.setPlaceholderText("Select a voice recording (.wav, .mp3, .ogg, .flac, .m4a)...")
        self.btn_browse = PushButton(FluentIcon.FOLDER, "Browse File", page_file)
        self.btn_browse.clicked.connect(self._browse_audio)
        file_row.addWidget(self.txt_file, stretch=1)
        file_row.addWidget(self.btn_browse)
        layout_file.addLayout(file_row)

        self.lbl_file_info = CaptionLabel("Recommended: 5-10s of natural speech with minimal background noise.", page_file)
        self.lbl_file_info.setStyleSheet("color: #64748B; font-style: italic;")
        layout_file.addWidget(self.lbl_file_info)

        self.stacked_input.addWidget(page_file)
        input_layout.addWidget(self.stacked_input)
        main_layout.addWidget(input_card)

        self.seg_input_method.setCurrentItem("mic")
        self.stacked_input.setCurrentIndex(0)

        # Cloning Execution Progress
        self.clone_progress = ProgressBar(self)
        self.clone_progress.setVisible(False)
        self.lbl_clone_status = CaptionLabel("", self)
        self.lbl_clone_status.setVisible(False)
        main_layout.addWidget(self.lbl_clone_status)
        main_layout.addWidget(self.clone_progress)

        # Bottom Action Bar
        footer_widget = QWidget(self)
        footer_layout = QHBoxLayout(footer_widget)
        footer_layout.setContentsMargins(0, 4, 0, 0)
        footer_layout.setSpacing(10)

        self.btn_test = PushButton(FluentIcon.PLAY, "Test Voice", footer_widget)
        self.btn_test.setFixedHeight(36)
        self.btn_test.setEnabled(False)
        self.btn_test.clicked.connect(self._test_voice_sample)
        footer_layout.addWidget(self.btn_test)

        footer_layout.addStretch()

        self.btn_cancel = PushButton("Cancel", footer_widget)
        self.btn_cancel.setFixedHeight(36)
        self.btn_cancel.clicked.connect(self.reject)
        footer_layout.addWidget(self.btn_cancel)

        self.btn_save = PrimaryPushButton(FluentIcon.ADD, "Create Voice Profile", footer_widget)
        self.btn_save.setFixedHeight(36)
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self._create_voice_profile)
        footer_layout.addWidget(self.btn_save)

        main_layout.addWidget(footer_widget)

    def _clean_mic_name(self, name: str) -> str:
        """Strip redundant ALSA / chipset boilerplate for clean, readable display."""
        s = re.sub(r"^[0-9A-Za-z\s]+On-Package High Definition Audio\s*\(HD Audio\)\s*", "Built-in ", name)
        s = re.sub(r"^[0-9A-Za-z\s]+High Definition Audio\s*", "Built-in ", s)
        return s.strip()

    def _on_recorder_error(self, error, error_string):
        logger.error(f"Recorder error: {error} - {error_string}")
        self.lbl_mic_status.setText(f"❌ Recording error: {error_string or 'Device error'}")
        self.lbl_mic_status.setStyleSheet("color: #DC2626;")

    def _populate_audio_devices(self):
        """Find and list available microphone input devices."""
        self.combo_mics.clear()
        self._audio_devices = QMediaDevices.audioInputs()
        default_index = 0
        for i, dev in enumerate(self._audio_devices):
            full_desc = dev.description()
            clean_desc = self._clean_mic_name(full_desc)
            if dev.isDefault():
                clean_desc += " (Default)"
                default_index = i
            self.combo_mics.addItem(clean_desc, userData=dev.id().data().decode("utf-8", "ignore"))

        if self._audio_devices:
            self.combo_mics.setCurrentIndex(default_index)
            self.audio_input.setDevice(self._audio_devices[default_index])
            self.btn_record.setEnabled(True)
        else:
            self.combo_mics.addItem("No microphone detected")
            self.btn_record.setEnabled(False)

    def _on_mic_device_selected(self, idx: int):
        if 0 <= idx < len(self._audio_devices):
            self.audio_input.setDevice(self._audio_devices[idx])

    def _populate_base_voices(self):
        self.combo_base_voice.clear()
        voices = list_local_voices(include_clones=False)
        for v in voices:
            flag = "🇮🇳" if v.get("language", "").startswith("hi") else "🇺🇸"
            self.combo_base_voice.addItem(f"{flag} {v['name']}", userData=v["key"])
        if voices:
            self.combo_base_voice.setCurrentIndex(0)

    def _on_language_changed(self):
        self._update_script_prompt()

    def _update_script_prompt(self):
        lang = self.combo_lang.currentData() or "hi_IN"
        if lang.startswith("hi"):
            self.lbl_script_prompt.setText(
                "\"नमस्ते! मेरा नाम [आपका नाम] है। मैं इस AI वॉइस स्टूडियो में अपनी आवाज़ क्लोन करने के लिए यह ऑडियो रिकॉर्ड कर रहा हूँ।\""
            )
        else:
            self.lbl_script_prompt.setText(
                "\"Hello! My name is [Your Name], and I am recording this speech sample to clone my custom AI voice profile.\""
            )

    def _switch_input_method(self, idx: int):
        self.stacked_input.setCurrentIndex(idx)
        if idx == 0:
            # Mic mode
            if self.recorded_sample_path and self.recorded_sample_path.is_file():
                self._validate_and_set_sample(self.recorded_sample_path, from_mic=True)
            else:
                self.selected_sample_path = None
                self.btn_save.setEnabled(False)
                self.btn_test.setEnabled(False)
        else:
            # File mode
            if self.file_sample_path and self.file_sample_path.is_file():
                self._validate_and_set_sample(self.file_sample_path, from_mic=False)
            else:
                self.selected_sample_path = None
                self.btn_save.setEnabled(False)
                self.btn_test.setEnabled(False)

    # ---------------------------------------------------------
    # In-App Microphone Recording Handlers
    # ---------------------------------------------------------
    def _toggle_record(self):
        if self._is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        # Stop preview player if playing
        if self.preview_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.preview_player.stop()

        # Remove previous temporary recording file if exists
        if self.recorded_sample_path and self.recorded_sample_path.exists():
            try:
                self.recorded_sample_path.unlink()
            except Exception:
                pass

        # Set device & output location
        device_idx = self.combo_mics.currentIndex()
        if 0 <= device_idx < len(self._audio_devices):
            self.audio_input.setDevice(self._audio_devices[device_idx])

        self.recorder.setOutputLocation(QUrl.fromLocalFile(str(self.recorded_sample_path)))
        self.recorder.record()
        self._is_recording = True

        self.btn_record.setText("⏹️ Stop Recording")
        self.btn_record.setIcon(FluentIcon.CANCEL)
        self.btn_record.setStyleSheet("background-color: #DC2626; color: white; font-weight: bold;")
        self.lbl_mic_status.setText("● Recording in progress... Speak clearly now into your microphone")
        self.lbl_mic_status.setStyleSheet("color: #DC2626; font-weight: 600;")
        self.btn_play_record.setEnabled(False)
        self.btn_save.setEnabled(False)
        self.btn_test.setEnabled(False)
        self.record_progress.setValue(0)
        self.lbl_record_timer.setText("00:00 / 00:15")

    def _stop_recording(self):
        if not self._is_recording:
            return
        self.recorder.stop()

    def _on_recorder_state_changed(self, state):
        if state == QMediaRecorder.RecorderState.StoppedState:
            self._is_recording = False
            self.btn_record.setText("🔄 Record Again")
            self.btn_record.setIcon(FluentIcon.MICROPHONE)
            self.btn_record.setStyleSheet("")

            if self.recorded_sample_path and self.recorded_sample_path.exists():
                self._validate_and_set_sample(self.recorded_sample_path, from_mic=True)
            else:
                self.lbl_mic_status.setText("❌ Recording failed or file was not saved.")
                self.lbl_mic_status.setStyleSheet("color: #DC2626;")
                self.btn_save.setEnabled(False)
                self.btn_test.setEnabled(False)

    def _on_recorder_duration_changed(self, duration_ms: int):
        if not self._is_recording:
            return
        sec = duration_ms / 1000.0
        pct = min(100, int((sec / self.MAX_RECORDING_SECONDS) * 100))
        self.record_progress.setValue(pct)
        self.lbl_record_timer.setText(f"{int(sec):02d}:{int((sec*10)%10):01d}s / {int(self.MAX_RECORDING_SECONDS)}:00s")

        # Auto stop at maximum duration
        if sec >= self.MAX_RECORDING_SECONDS:
            self._stop_recording()

    # ---------------------------------------------------------
    # Playback Preview of Recorded Audio
    # ---------------------------------------------------------
    def _toggle_playback_recording(self):
        if not self.recorded_sample_path or not self.recorded_sample_path.exists():
            return

        if self.preview_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.preview_player.stop()
            self.btn_play_record.setText("Listen to Recording")
            self.btn_play_record.setIcon(FluentIcon.PLAY)
        else:
            self.preview_player.setSource(QUrl.fromLocalFile(str(self.recorded_sample_path)))
            self.preview_player.play()
            self.btn_play_record.setText("Stop Playback")
            self.btn_play_record.setIcon(FluentIcon.PAUSE)

    def _on_playback_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.StoppedState:
            self.btn_play_record.setText("Listen to Recording")
            self.btn_play_record.setIcon(FluentIcon.PLAY)

    # ---------------------------------------------------------
    # File Browse & Validation
    # ---------------------------------------------------------
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

        self.file_sample_path = p
        self.txt_file.setText(p.name)
        self._validate_and_set_sample(p, from_mic=False)

    def _on_pitch_slider_changed(self, val: int):
        self.lbl_pitch_val.setText(f"{val:+.1f} st")

    def _validate_and_set_sample(self, path: Path, from_mic: bool = True):
        try:
            data, sr = sf.read(str(path), dtype="float32")
            if data.ndim > 1:
                data = np.mean(data, axis=1)
            dur = len(data) / float(sr)
            if dur < self.MIN_RECORDING_SECONDS:
                msg = f"⚠️ Audio is too short ({dur:.1f}s). Please provide at least 3-5 seconds of speech."
                if from_mic:
                    self.lbl_mic_status.setText(msg)
                    self.lbl_mic_status.setStyleSheet("color: #DC2626; font-weight: 500;")
                    self.btn_play_record.setEnabled(False)
                else:
                    self.lbl_file_info.setText(msg)
                    self.lbl_file_info.setStyleSheet("color: #DC2626; font-weight: 500;")
                self.selected_sample_path = None
                self.btn_save.setEnabled(False)
                self.btn_test.setEnabled(False)
            else:
                import math
                user_f0 = AudioDSP.estimate_median_f0(data, sr)

                # Auto-select the closest natural base voice model
                cur_lang = self.combo_lang.currentData() or "hi_IN"
                if cur_lang.startswith("hi"):
                    best_base = "hi_IN-priyamvada-medium" if user_f0 > 175.0 else "hi_IN-pratham-medium"
                    for i in range(self.combo_base_voice.count()):
                        if self.combo_base_voice.itemData(i) == best_base:
                            self.combo_base_voice.setCurrentIndex(i)
                            break

                base_key = self.combo_base_voice.currentData() or "hi_IN-pratham-medium"
                base_f0_map = {
                    "hi_IN-pratham-medium": 107.0,
                    "hi_IN-priyamvada-medium": 220.0,
                    "en_US-lessac-medium": 140.0,
                    "en_US-ryan-medium": 115.0,
                    "en_US-amy-medium": 215.0,
                }
                nominal_f0 = base_f0_map.get(base_key, 120.0)
                auto_shift = int(round(12.0 * math.log2(user_f0 / nominal_f0)))
                auto_shift = max(-12, min(12, auto_shift))
                self.slider_pitch.setValue(auto_shift)
                self.lbl_pitch_val.setText(f"{auto_shift:+.1f} st (Auto-detected: {user_f0:.0f} Hz)")

                msg = f"✓ Speech ready: {dur:.1f}s · Pitch: {user_f0:.0f} Hz · Shift: {auto_shift:+.1f} st"
                if from_mic:
                    self.lbl_mic_status.setText(msg)
                    self.lbl_mic_status.setStyleSheet("color: #16A34A; font-weight: 600;")
                    self.btn_play_record.setEnabled(True)
                else:
                    self.lbl_file_info.setText(msg)
                    self.lbl_file_info.setStyleSheet("color: #16A34A; font-weight: 600;")
                self.selected_sample_path = path
                self.btn_save.setEnabled(True)
                self.btn_test.setEnabled(True)
        except Exception as e:
            err_msg = f"❌ Error reading audio: {e}"
            if from_mic:
                self.lbl_mic_status.setText(err_msg)
                self.lbl_mic_status.setStyleSheet("color: #DC2626;")
            else:
                self.lbl_file_info.setText(err_msg)
                self.lbl_file_info.setStyleSheet("color: #DC2626;")
            self.selected_sample_path = None
            self.btn_save.setEnabled(False)
            self.btn_test.setEnabled(False)

    # ---------------------------------------------------------
    # Profile Creation & Testing
    # ---------------------------------------------------------
    def _create_voice_profile(self):
        if not self.selected_sample_path or not self.selected_sample_path.is_file():
            InfoBar.warning(title="Missing Sample", content="Please record or select a voice audio file first.", parent=self)
            return

        name = self.txt_name.text().strip() or "My Cloned Voice"
        lang = self.combo_lang.currentData() or "hi_IN"
        base_voice = self.combo_base_voice.currentData() or "hi_IN-pratham-medium"
        pitch_shift = float(self.slider_pitch.value())

        self.btn_save.setEnabled(False)
        self.btn_record.setEnabled(False)
        self.btn_browse.setEnabled(False)
        self.clone_progress.setVisible(True)
        self.lbl_clone_status.setVisible(True)
        self.clone_progress.setValue(25)
        self.lbl_clone_status.setText("Extracting acoustic speaker embedding on CPU...")

        try:
            profile = self.clone_manager.create_clone(
                name=name,
                reference_audio_path=self.selected_sample_path,
                language=lang,
                base_voice_key=base_voice,
                pitch_shift=pitch_shift,
            )
            self.clone_progress.setValue(100)
            self.lbl_clone_status.setText("Voice profile created successfully!")
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
            self.btn_record.setEnabled(True)
            self.btn_browse.setEnabled(True)
            self.clone_progress.setVisible(False)
            self.lbl_clone_status.setVisible(False)
            InfoBar.error(title="Cloning Failed", content=str(e), parent=self)

    def _test_voice_sample(self):
        if not self.selected_sample_path or not self.selected_sample_path.is_file():
            return

        name = self.txt_name.text().strip() or "Test Voice"
        lang = self.combo_lang.currentData() or "hi_IN"
        base_voice = self.combo_base_voice.currentData() or "hi_IN-pratham-medium"
        pitch_shift = float(self.slider_pitch.value())

        try:
            temp_profile = self.clone_manager.create_clone(
                name=f"temp_preview_{int(QTime.currentTime().msecsSinceStartOfDay())}",
                reference_audio_path=self.selected_sample_path,
                language=lang,
                base_voice_key=base_voice,
                pitch_shift=pitch_shift,
            )

            test_text = (
                "नमस्ते! यह आपकी क्लोन की गई नई आवाज़ का टेस्ट सैंपल है।"
                if lang.startswith("hi")
                else "Hello! This is a test sample of your newly cloned voice profile."
            )
            test_wav = temp_profile.clone_dir / "preview_test.wav"
            self.cloning_engine.synthesize_cloned(test_text, temp_profile.id, test_wav)

            self.preview_requested.emit(str(test_wav), f"Preview: {name}")

            # Also play directly in dialog preview player for instant feedback
            self.preview_player.setSource(QUrl.fromLocalFile(str(test_wav)))
            self.preview_player.play()

            InfoBar.success(
                title="Voice Preview Ready 🎧",
                content=f"Playing synthesized test in cloned tone.",
                parent=self,
                position=InfoBarPosition.TOP,
            )
        except Exception as e:
            InfoBar.error(title="Preview Failed", content=str(e), parent=self)

    def closeEvent(self, event):
        if self._is_recording:
            self._stop_recording()
        if self.preview_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.preview_player.stop()
        super().closeEvent(event)
