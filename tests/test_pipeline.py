from pathlib import Path
import pytest

from app.core.audio_pipeline import AudioPipeline
from app.core.project_manager import ProjectManager
from app.tts.voice_manager import list_local_voices
from app.utils.atomic_audio import validate_wav_file, write_silence_wav


def test_audio_pipeline_concat_fast(tmp_path: Path):
    """Test rapid lossless WAV concatenation with pauses."""
    pipeline = AudioPipeline()
    wav1 = tmp_path / "w1.wav"
    wav2 = tmp_path / "w2.wav"
    out_concat = tmp_path / "concat.wav"

    write_silence_wav(wav1, duration_seconds=0.3, sample_rate=16000)
    write_silence_wav(wav2, duration_seconds=0.4, sample_rate=16000)

    # 300ms pause between 300ms + 400ms = approx 1.0s
    res = pipeline.concatenate_wavs_fast([wav1, wav2], out_concat, pause_ms=300)
    assert res.exists()
    info = validate_wav_file(res)
    assert 0.95 <= info["duration"] <= 1.05


def test_audio_pipeline_loudnorm_and_mp3(tmp_path: Path):
    """Test loudness normalization and MP3 export."""
    pipeline = AudioPipeline()
    raw_wav = tmp_path / "raw.wav"
    norm_wav = tmp_path / "norm.wav"
    mp3_file = tmp_path / "export.mp3"

    write_silence_wav(raw_wav, duration_seconds=0.5, sample_rate=22050)

    pipeline.normalize_loudness(raw_wav, norm_wav)
    assert norm_wav.exists()
    info = validate_wav_file(norm_wav)
    assert info["duration"] > 0

    pipeline.export_to_mp3(norm_wav, mp3_file, metadata={"title": "Test Title"})
    assert mp3_file.exists()
    assert mp3_file.stat().st_size > 500


def test_project_workflow_end_to_end(tmp_path: Path):
    """Test full Project lifecycle: creation, chunking, rendering, and master building."""
    voices = list_local_voices()
    if not voices:
        pytest.skip("No voice model installed.")

    voice_key = voices[0]["key"]

    sample_story = (
        "Once upon a time in a digital studio, an autonomous audio engine was created. "
        "It processed long text effortlessly. "
        "Each block was rendered locally with crystal-clear fidelity. "
        "Finally, all segments joined together into a magnificent audiobook."
    )

    # 1. Create project
    project = ProjectManager.create_project(
        name="Test Audiobook Project",
        text=sample_story,
        voice_key=voice_key,
        max_chars=90,
    )
    assert len(project.blocks) >= 3
    assert project.manifest_path.exists()

    # 2. Synthesize all blocks
    project.synthesize_all()
    for b in project.blocks:
        assert b.status == "completed"
        assert b.duration > 0
        seg_file = project.project_dir / b.audio_file
        assert seg_file.exists()

    # 3. Test single block re-synthesis (Phase 4 capability)
    block_2 = project.blocks[1]
    block_2.text = "It processed long text effortlessly and with incredible speed."
    project.synthesize_block(block_2.id)
    assert block_2.status == "completed"

    # 4. Build master audio WAV and MP3
    master_wav = project.build_master_audio(output_format="wav", pause_ms=250, normalize=True)
    assert master_wav.exists()
    wav_info = validate_wav_file(master_wav)
    assert wav_info["duration"] > 3.0

    master_mp3 = project.build_master_audio(output_format="mp3", pause_ms=250, normalize=False)
    assert master_mp3.exists()
    assert master_mp3.stat().st_size > 1000
