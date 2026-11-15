from pathlib import Path
import pytest

from app.tts.base import BaseTTSEngine
from app.tts.piper_engine import PiperTTSEngine
from app.tts.voice_manager import list_local_voices
from app.utils.atomic_audio import InvalidWavError, validate_wav_file, write_silence_wav


def test_base_engine_abstract():
    """Verify that BaseTTSEngine cannot be instantiated directly."""
    with pytest.raises(TypeError):
        BaseTTSEngine()  # type: ignore


def test_atomic_audio_silence(tmp_path: Path):
    """Test generating and validating a silent WAV file."""
    silence_file = tmp_path / "silence.wav"
    write_silence_wav(silence_file, duration_seconds=0.5, sample_rate=22050)

    assert silence_file.exists()
    info = validate_wav_file(silence_file)
    assert info["channels"] == 1
    assert info["framerate"] == 22050
    assert 0.49 <= info["duration"] <= 0.51
    assert info["size_bytes"] > 44


def test_atomic_audio_corrupted_file(tmp_path: Path):
    """Test that a truncated/corrupted WAV raises InvalidWavError."""
    bad_file = tmp_path / "corrupt.wav"
    bad_file.write_bytes(b"RIFF1234WAVEfmt ")  # Less than 44 bytes

    with pytest.raises(InvalidWavError):
        validate_wav_file(bad_file)


def test_piper_engine_validation_missing_model(tmp_path: Path):
    """Test that validating non-existent models raises FileNotFoundError."""
    engine = PiperTTSEngine()
    invalid_config = {
        "model_path": str(tmp_path / "non_existent.onnx"),
        "config_path": str(tmp_path / "non_existent.onnx.json"),
    }
    with pytest.raises(FileNotFoundError):
        engine.validate(invalid_config)


def test_piper_engine_synthesize_real_voice(tmp_path: Path):
    """Test synthesizing a sentence with a real installed local voice."""
    voices = list_local_voices()
    if not voices:
        pytest.skip("No local voice installed, skipping live synthesis test.")

    voice = voices[0]
    engine = PiperTTSEngine()
    out_wav = tmp_path / "output_test.wav"

    text = "Unit testing speech synthesis engine."
    result_path = engine.synthesize_to_wav(text, out_wav, voice)

    assert result_path.exists()
    info = validate_wav_file(result_path)
    assert info["duration"] > 0.5
    assert info["size_bytes"] > 1000


def test_piper_engine_symbol_safeguard(tmp_path: Path):
    """Test that empty or non-alphanumeric text produces a silent WAV safely."""
    voices = list_local_voices()
    if not voices:
        pytest.skip("No local voice installed.")

    voice = voices[0]
    engine = PiperTTSEngine()
    out_wav = tmp_path / "safeguard.wav"

    # Only markdown dividers / punctuation
    text = "--- *** ---"
    result_path = engine.synthesize_to_wav(text, out_wav, voice)

    assert result_path.exists()
    info = validate_wav_file(result_path)
    assert info["duration"] >= 0.2
