import json
from pathlib import Path
import tempfile
import numpy as np
import pytest
import soundfile as sf
import wave

from PySide6.QtWidgets import QApplication

from app.clone.dsp import AudioDSP
from app.clone.engine import VoiceCloningEngine
from app.clone.profile import CloneManager, CloneProfile
from app.clone.speaker_encoder import SpeakerEncoder
from app.core.project_manager import Project, ProjectManager, TextBlock
from app.tts.voice_manager import list_local_voices
from app.ui.fluent.clone_dialog import CloneVoiceDialog
from app.ui.fluent.interfaces.studio_interface import StudioInterface
from app.utils.atomic_audio import write_silence_wav


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


def create_mock_speech_wav(path: Path, duration_sec: float = 3.5, sr: int = 22050):
    """Generate a clean synthetic speech-like harmonic signal for testing."""
    t = np.linspace(0, duration_sec, int(sr * duration_sec), endpoint=False)
    # Fundamental pitch 140Hz with speech-like vowel formants
    signal = (
        0.5 * np.sin(2 * np.pi * 140 * t)
        + 0.3 * np.sin(2 * np.pi * 500 * t)
        + 0.2 * np.sin(2 * np.pi * 1800 * t)
        + 0.1 * np.sin(2 * np.pi * 2500 * t)
    )
    # Add silent borders to test VAD
    pad_len = int(sr * 0.4)
    silence = np.zeros(pad_len, dtype=np.float32)
    signal = np.concatenate([silence, signal.astype(np.float32), silence])
    sf.write(str(path), signal, sr, subtype="PCM_16")
    return path


def test_audio_dsp_processing(tmp_path: Path):
    raw_wav = tmp_path / "raw.wav"
    clean_wav = tmp_path / "clean.wav"
    create_mock_speech_wav(raw_wav, duration_sec=3.0, sr=44100)

    meta = AudioDSP.clean_voice_sample(raw_wav, clean_wav, target_sr=22050, min_duration_sec=2.0)
    assert clean_wav.is_file()
    assert meta["sample_rate"] == 22050
    assert meta["duration"] >= 2.0

    # Verify mel spectrogram
    data, sr = sf.read(str(clean_wav), dtype="float32")
    mel = AudioDSP.extract_mel_spectrogram(data, sr=sr, n_mels=80)
    assert mel.shape[0] == 80
    assert mel.shape[1] > 10


def test_speaker_encoder_embeddings():
    encoder = SpeakerEncoder()
    sr = 16000
    t = np.linspace(0, 2.0, sr * 2, endpoint=False)

    # Voice 1 (Male lower pitch ~120Hz)
    audio1 = 0.5 * np.sin(2 * np.pi * 120 * t) + 0.3 * np.sin(2 * np.pi * 600 * t)
    emb1 = encoder.extract_embedding(audio1.astype(np.float32), sr)
    assert len(emb1) == 256
    assert abs(np.linalg.norm(emb1) - 1.0) < 1e-4

    # Voice 2 (Female higher pitch ~240Hz)
    audio2 = 0.5 * np.sin(2 * np.pi * 240 * t) + 0.3 * np.sin(2 * np.pi * 1200 * t)
    emb2 = encoder.extract_embedding(audio2.astype(np.float32), sr)
    assert len(emb2) == 256
    assert abs(np.linalg.norm(emb2) - 1.0) < 1e-4

    # Self similarity is 1.0
    sim_self = SpeakerEncoder.cosine_similarity(emb1, emb1)
    assert abs(sim_self - 1.0) < 1e-4

    # Cross similarity is < 1.0
    sim_cross = SpeakerEncoder.cosine_similarity(emb1, emb2)
    assert sim_cross < 0.99


def test_clone_manager_lifecycle(tmp_path: Path):
    manager = CloneManager(clones_dir=tmp_path / "clones")
    sample_wav = tmp_path / "sample.wav"
    create_mock_speech_wav(sample_wav, duration_sec=3.0)

    # 1. Create Clone Profile
    profile = manager.create_clone(
        name="Vikram Voice",
        reference_audio_path=sample_wav,
        language="hi_IN",
        base_voice_key="hi_IN-pratham-medium",
    )
    assert profile.id.startswith("clone_vikram_voice")
    assert profile.full_reference_path.is_file()
    assert profile.full_embedding_path.is_file()

    # 2. List Clones
    clones = manager.list_clones()
    assert len(clones) == 1
    assert clones[0].name == "Vikram Voice"

    # 3. Retrieve Clone
    retrieved = manager.get_clone(profile.id)
    assert retrieved is not None
    assert retrieved.name == "Vikram Voice"

    # 4. Load Embedding
    emb = manager.load_embedding(profile.id)
    assert emb is not None
    assert len(emb) == 256

    # 5. Delete Clone
    assert manager.delete_clone(profile.id)
    assert len(manager.list_clones()) == 0


def test_voice_cloning_engine_synthesis(tmp_path: Path):
    clones_dir = tmp_path / "clones"
    manager = CloneManager(clones_dir=clones_dir)
    sample_wav = tmp_path / "ref.wav"
    create_mock_speech_wav(sample_wav, duration_sec=3.0)

    profile = manager.create_clone(
        name="Rani Voice",
        reference_audio_path=sample_wav,
        language="hi_IN",
        base_voice_key="hi_IN-priyamvada-medium",
    )

    engine = VoiceCloningEngine(models_dir=tmp_path)
    engine.clone_manager = manager

    out_wav = tmp_path / "cloned_speech.wav"
    res = engine.synthesize_cloned("नमस्ते", profile.id, out_wav)
    assert res.is_file()
    info = sf.info(str(res))
    assert info.duration > 0.2
    assert info.samplerate == 22050


def test_studio_interface_all_formats(qapp):
    studio = StudioInterface()
    assert studio.combo_format.count() == 7
    formats = [studio.combo_format.itemText(i) for i in range(studio.combo_format.count())]
    assert any("WAV" in f for f in formats)
    assert any("MP3" in f for f in formats)
    assert any("FLAC" in f for f in formats)
    assert any("M4B" in f for f in formats)
    assert any("Audiogram" in f for f in formats)
    assert any("SRT" in f for f in formats)
    assert any("VTT" in f for f in formats)

    # Check clone button exists in Studio
    assert hasattr(studio, "btn_clone_voice")


def test_clone_voice_dialog_ui(qapp, tmp_path: Path):
    dlg = CloneVoiceDialog()
    assert dlg.windowTitle() == "Clone AI Voice Profile"
    assert not dlg.btn_save.isEnabled()

    # Mic controls exist
    assert hasattr(dlg, "btn_record")
    assert hasattr(dlg, "btn_play_record")
    assert hasattr(dlg, "lbl_record_timer")
    assert hasattr(dlg, "combo_mics")

    # Script prompt adapts to language
    dlg.combo_lang.setCurrentIndex(0)  # Hindi
    assert "नमस्ते" in dlg.lbl_script_prompt.text()
    dlg.combo_lang.setCurrentIndex(1)  # English
    assert "Hello" in dlg.lbl_script_prompt.text()

    # Feed short sample (< 2.0s)
    short_wav = tmp_path / "short.wav"
    create_mock_speech_wav(short_wav, duration_sec=1.0)
    dlg._validate_and_set_sample(short_wav, from_mic=True)
    assert not dlg.btn_save.isEnabled()
    assert "too short" in dlg.lbl_mic_status.text()

    # Feed valid sample (>= 2.0s)
    sample_wav = tmp_path / "valid_sample.wav"
    create_mock_speech_wav(sample_wav, duration_sec=4.0)

    dlg._validate_and_set_sample(sample_wav, from_mic=True)
    assert dlg.btn_save.isEnabled()
    assert dlg.btn_test.isEnabled()
    assert dlg.btn_play_record.isEnabled()
    assert dlg.selected_sample_path == sample_wav

    # Test tab switching
    dlg._switch_input_method(1)  # File mode
    assert dlg.stacked_input.currentIndex() == 1
    dlg._switch_input_method(0)  # Mic mode
    assert dlg.stacked_input.currentIndex() == 0

    dlg.deleteLater()
    qapp.processEvents()
