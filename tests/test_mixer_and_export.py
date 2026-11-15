import os
from pathlib import Path
import subprocess
import pytest

from app.core.audio_pipeline import AudioPipeline
from app.core.project_manager import ProjectManager
from app.utils.atomic_audio import validate_wav_file, write_silence_wav

os.environ["QT_QPA_PLATFORM"] = "offscreen"


def test_mix_background_music_with_autoducking(tmp_path: Path):
    """Test mixing speech WAV with background music and automatic sidechain ducking."""
    pipeline = AudioPipeline()
    speech_wav = tmp_path / "speech.wav"
    music_wav = tmp_path / "music.wav"
    out_mixed = tmp_path / "mixed.wav"

    # 1. Create 3-second speech
    write_silence_wav(speech_wav, duration_seconds=3.0, sample_rate=22050)

    # 2. Create 2-second background music tone (it will loop to fill 3 seconds)
    cmd_tone = [
        str(pipeline.ffmpeg_bin), "-y", "-f", "lavfi", "-i", "sine=frequency=330:duration=2",
        "-c:a", "pcm_s16le", str(music_wav)
    ]
    subprocess.run(cmd_tone, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 3. Mix with auto-ducking
    pipeline.mix_background_music(
        speech_wav=speech_wav,
        music_file=music_wav,
        output_wav=out_mixed,
        music_volume=0.20,
        ducking_ratio=6.0,
        fade_out_sec=1.0,
    )

    assert out_mixed.exists()
    info = validate_wav_file(out_mixed)
    assert 2.8 <= info["duration"] <= 3.2


def test_export_to_m4b_with_chapters(tmp_path: Path):
    """Test exporting to M4B format with chapter markers and metadata."""
    pipeline = AudioPipeline()
    raw_wav = tmp_path / "raw.wav"
    out_m4b = tmp_path / "book.m4b"

    write_silence_wav(raw_wav, duration_seconds=4.0, sample_rate=22050)

    chapters = [
        {"start_ms": 0, "end_ms": 2000, "title": "Chapter 1: The Call"},
        {"start_ms": 2000, "end_ms": 4000, "title": "Chapter 2: The Journey"},
    ]

    metadata = {
        "title": "Adventures in Sound",
        "artist": "NavGurukul AI",
        "album": "Audio Stories Vol 1",
    }

    pipeline.export_to_m4b(
        input_wav=raw_wav,
        output_m4b=out_m4b,
        bitrate="128k",
        metadata=metadata,
        chapters=chapters,
    )

    assert out_m4b.exists()
    assert out_m4b.stat().st_size > 1000


def test_export_to_flac_lossless(tmp_path: Path):
    """Test exporting to FLAC lossless container."""
    pipeline = AudioPipeline()
    raw_wav = tmp_path / "raw.wav"
    out_flac = tmp_path / "master.flac"

    write_silence_wav(raw_wav, duration_seconds=1.5, sample_rate=22050)

    pipeline.export_to_flac(raw_wav, out_flac, metadata={"title": "Studio Master"})
    assert out_flac.exists()
    assert out_flac.stat().st_size > 500


def test_podcast_mixer_widget_offscreen(tmp_path: Path):
    """Test PodcastMixerWidget GUI offscreen instantiation."""
    from PySide6.QtWidgets import QApplication
    from app.ui.components.mixer_widget import PodcastMixerWidget

    app = QApplication.instance() or QApplication([])

    widget = PodcastMixerWidget()
    assert widget is not None
    assert widget.slider_music_vol.value() == 22
    assert widget.slider_ducking.value() == 6

    widget.deleteLater()
    app.processEvents()
