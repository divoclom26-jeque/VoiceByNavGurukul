import os
from pathlib import Path
import wave
import numpy as np
import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from app.core.audio_pipeline import AudioPipeline
from app.ui.fluent.waveform_widget import WaveformWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    app.processEvents()


def test_waveform_widget_empty_state(qapp):
    """Test WaveformWidget with no audio loaded."""
    w = WaveformWidget()
    assert len(w.peaks) == 0
    assert w.duration_ms == 0
    assert w.position_ms == 0
    w.deleteLater()
    qapp.processEvents()


def test_waveform_widget_load_audio_and_peaks(qapp, tmp_path: Path):
    """Test WaveformWidget peak extraction and normalization."""
    test_wav = tmp_path / "waveform_sample.wav"
    sr = 22050
    # Generate 1.0 second sine wave at 440Hz
    t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
    sine = (np.sin(2 * np.pi * 440 * t) * 32000).astype(np.int16)

    with wave.open(str(test_wav), "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sr)
        f.writeframes(sine.tobytes())

    w = WaveformWidget()
    w.resize(300, 50)
    w.load_audio(str(test_wav))

    assert len(w.peaks) > 0
    assert w.duration_ms >= 900
    assert np.max(w.peaks) <= 1.0
    assert np.min(w.peaks) >= 0.0

    # Test seek position updates
    w.set_position(500)
    assert w.position_ms == 500

    # Test mouse click seeking
    seeks = []
    w.seek_requested.connect(lambda pos: seeks.append(pos))

    # Click at 50% width
    click_ev = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPoint(150, 25),
        QPoint(150, 25),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    w.mousePressEvent(click_ev)
    assert len(seeks) == 1
    assert 400 <= seeks[0] <= 600

    w.deleteLater()
    qapp.processEvents()


def test_micro_fades_dsp():
    """Test apply_micro_fades smoothly ramps up start and ramps down end."""
    sr = 22050
    # Constant amplitude buffer of 10,000
    raw_samples = (np.ones(1000, dtype=np.int16) * 10000).tobytes()

    faded_bytes = AudioPipeline.apply_micro_fades(
        raw_samples, n_channels=1, sample_width=2, framerate=sr, fade_ms=15
    )
    faded_arr = np.frombuffer(faded_bytes, dtype=np.int16)

    # First sample should be ramped to near 0
    assert abs(faded_arr[0]) < 100
    # Middle sample should remain original 10,000
    assert faded_arr[500] == 10000
    # Last sample should be ramped to near 0
    assert abs(faded_arr[-1]) < 100


def test_concatenate_with_micro_crossfades(tmp_path: Path):
    """Test fast concatenation with seamless micro fades."""
    pipeline = AudioPipeline()
    sr = 22050

    wav1 = tmp_path / "part1.wav"
    wav2 = tmp_path / "part2.wav"
    out_master = tmp_path / "concatenated_master.wav"

    for p in [wav1, wav2]:
        with wave.open(str(p), "w") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(sr)
            # 0.2s of audio
            f.writeframes(b"\x20\x20" * int(sr * 0.2))

    res = pipeline.concatenate_wavs_fast([wav1, wav2], out_master, pause_ms=100, fade_ms=15)
    assert res.is_file()
    assert res.stat().st_size > 0

    with wave.open(str(res), "rb") as wf:
        total_frames = wf.getnframes()
        # 0.2s + 0.1s pause + 0.2s = 0.5s approx
        expected_frames = int(sr * 0.5)
        assert abs(total_frames - expected_frames) < sr * 0.05
