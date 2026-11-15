import os
from pathlib import Path
import pytest

from PySide6.QtWidgets import QApplication
from app.core.audio_pipeline import AudioPipeline
from app.core.project_manager import ProjectManager
from app.tts.voice_manager import list_local_voices
from app.ui.fluent.interfaces.mixer_interface import MixerInterface
from app.utils.atomic_audio import validate_wav_file, write_silence_wav

os.environ["QT_QPA_PLATFORM"] = "offscreen"


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_audio_pipeline_presets_exist():
    pipeline = AudioPipeline()
    assert "podcast_warmth" in pipeline.STUDIO_PRESETS
    assert "broadcast_clarity" in pipeline.STUDIO_PRESETS
    assert "audiobook_acx" in pipeline.STUDIO_PRESETS
    assert "crisp_clean" in pipeline.STUDIO_PRESETS
    assert "bypass" in pipeline.STUDIO_PRESETS


def test_apply_studio_fx_presets(tmp_path: Path):
    pipeline = AudioPipeline()
    input_wav = tmp_path / "test_input.wav"
    write_silence_wav(input_wav, duration_seconds=1.5, sample_rate=22050)

    # 1. Podcast Warmth
    out_warmth = tmp_path / "out_warmth.wav"
    pipeline.apply_studio_fx_preset(input_wav, out_warmth, preset_key="podcast_warmth")
    assert out_warmth.is_file()
    info = validate_wav_file(out_warmth)
    assert info["duration"] == pytest.approx(1.5, abs=0.1)

    # 2. Broadcast Clarity
    out_clarity = tmp_path / "out_clarity.wav"
    pipeline.apply_studio_fx_preset(input_wav, out_clarity, preset_key="broadcast_clarity")
    assert out_clarity.is_file()

    # 3. Audiobook ACX
    out_acx = tmp_path / "out_acx.wav"
    pipeline.apply_studio_fx_preset(input_wav, out_acx, preset_key="audiobook_acx")
    assert out_acx.is_file()


def test_apply_studio_fx_with_room_tone(tmp_path: Path):
    pipeline = AudioPipeline()
    input_wav = tmp_path / "speech_tone.wav"
    write_silence_wav(input_wav, duration_seconds=1.0, sample_rate=22050)

    out_room = tmp_path / "out_room.wav"
    pipeline.apply_studio_fx_preset(
        input_wav,
        out_room,
        preset_key="podcast_warmth",
        add_room_tone=True,
    )
    assert out_room.is_file()
    info = validate_wav_file(out_room)
    assert info["duration"] == pytest.approx(1.0, abs=0.1)


def test_project_build_master_with_fx_preset(tmp_path: Path):
    voices = list_local_voices()
    if not voices:
        pytest.skip("No voice model installed.")

    project = ProjectManager.create_project(
        name="Mastering FX Test",
        text="Testing studio mastering presets for broadcast.",
        voice_key=voices[0]["key"],
        max_chars=60,
    )
    project.synthesize_all()

    master_wav = project.build_master_audio(
        output_format="wav",
        fx_preset="broadcast_clarity",
        add_room_tone=True,
    )
    assert master_wav.is_file()
    info = validate_wav_file(master_wav)
    assert info["duration"] > 1.0


def test_mixer_interface_fx_controls(qapp, tmp_path: Path):
    voices = list_local_voices()
    if not voices:
        pytest.skip("No voice model installed.")

    project = ProjectManager.create_project(
        name="Mixer UI Test",
        text="Audio project for mixer interface.",
        voice_key=voices[0]["key"],
        max_chars=60,
    )

    mixer = MixerInterface()
    mixer.load_project(project)

    assert hasattr(mixer, "combo_fx_preset")
    assert hasattr(mixer, "switch_mixer_room_tone")
    assert mixer.combo_fx_preset.count() >= 5

    # Switch preset to Audiobook ACX
    idx = mixer.combo_fx_preset.findData("audiobook_acx")
    assert idx >= 0
    mixer.combo_fx_preset.setCurrentIndex(idx)
    assert "ACX" in mixer.lbl_fx_desc.text()

    mixer.close()
