import json
from pathlib import Path
import subprocess
import tempfile
import pytest

from PySide6.QtWidgets import QApplication
from app.core.audio_pipeline import AudioPipeline
from app.core.project_manager import Project, ProjectManager, TextBlock
from app.core.subtitles import SubtitleGenerator
from app.ui.fluent.interfaces.block_interface import BlockInterface
from app.ui.fluent.interfaces.mixer_interface import MixerInterface
from app.utils.atomic_audio import write_silence_wav


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


def test_subtitle_timestamp_formatting():
    # 0 seconds
    assert SubtitleGenerator.format_timestamp_srt(0.0) == "00:00:00,000"
    assert SubtitleGenerator.format_timestamp_vtt(0.0) == "00:00:00.000"

    # 1.5 seconds
    assert SubtitleGenerator.format_timestamp_srt(1.5) == "00:00:01,500"
    assert SubtitleGenerator.format_timestamp_vtt(1.5) == "00:00:01.500"

    # 1 hour, 2 minutes, 3 seconds, 456 millis
    t = 3600 + 120 + 3 + 0.456
    assert SubtitleGenerator.format_timestamp_srt(t) == "01:02:03,456"
    assert SubtitleGenerator.format_timestamp_vtt(t) == "01:02:03.456"


def test_subtitle_generator_srt_and_vtt():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        srt_file = p / "test.srt"
        vtt_file = p / "test.vtt"

        blocks = [
            TextBlock(
                id=1,
                text="पहला वाक्य। First sentence.",
                status="completed",
                duration=2.5,
                start_time=0.0,
                end_time=2.5,
                speaker_label="Rani",
            ),
            TextBlock(
                id=2,
                text="दूसरा वाक्य। Second sentence.",
                status="completed",
                duration=3.0,
                start_time=2.85,
                end_time=5.85,
                speaker_label="Aman",
            ),
            TextBlock(
                id=3,
                text="Incomplete block",
                status="pending",
                duration=0.0,
            ),
        ]

        # Generate SRT
        res_srt = SubtitleGenerator.generate_srt(blocks, srt_file, include_speaker=True)
        assert res_srt.is_file()
        srt_content = res_srt.read_text(encoding="utf-8")
        assert "1\n00:00:00,000 --> 00:00:02,500\n[Rani]: पहला वाक्य।" in srt_content
        assert "2\n00:00:02,850 --> 00:00:05,850\n[Aman]: दूसरा वाक्य।" in srt_content
        assert "Incomplete block" not in srt_content

        # Generate VTT
        res_vtt = SubtitleGenerator.generate_vtt(blocks, vtt_file, include_speaker=True)
        assert res_vtt.is_file()
        vtt_content = res_vtt.read_text(encoding="utf-8")
        assert vtt_content.startswith("WEBVTT\n")
        assert "00:00:00.000 --> 00:00:02.500\n<v Rani>पहला वाक्य।" in vtt_content
        assert "00:00:02.850 --> 00:00:05.850\n<v Aman>दूसरा वाक्य।" in vtt_content


def test_export_subtitles_from_project():
    with tempfile.TemporaryDirectory() as td:
        proj_dir = Path(td) / "TestProject"
        proj = Project(
            name="SubProj",
            project_dir=proj_dir,
            voice_key="hi_IN-priyamvada-low",
            blocks=[
                TextBlock(id=1, text="नमस्ते दोस्तों।", status="completed", duration=1.5, audio_file="b1.wav"),
                TextBlock(id=2, text="Voice Engine में आपका स्वागत है।", status="completed", duration=2.0, audio_file="b2.wav"),
            ],
        )

        srt_path = proj.export_subtitles(format="srt")
        assert srt_path.is_file()
        assert srt_path.suffix == ".srt"
        content_srt = srt_path.read_text(encoding="utf-8")
        assert "नमस्ते दोस्तों।" in content_srt

        vtt_path = proj.export_subtitles(format="vtt")
        assert vtt_path.is_file()
        assert vtt_path.suffix == ".vtt"
        content_vtt = vtt_path.read_text(encoding="utf-8")
        assert content_vtt.startswith("WEBVTT")


def test_audiogram_video_generation():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        wav_path = p / "speech.wav"
        srt_path = p / "sub.srt"
        mp4_square = p / "square.mp4"
        mp4_vertical = p / "vertical.mp4"

        # Create 1.5s sine wave
        cmd_tone = [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "sine=frequency=440:duration=1.5",
            "-c:a", "pcm_s16le", str(wav_path)
        ]
        subprocess.run(cmd_tone, check=True, capture_output=True)

        srt_path.write_text("1\n00:00:00,000 --> 00:00:01,500\nपरीक्षण ऑडियो\n\n", encoding="utf-8")

        pipeline = AudioPipeline()

        # 1. Square audiogram with burned Hindi subtitles
        res_sq = pipeline.export_audiogram_video(
            speech_wav=wav_path,
            output_mp4=mp4_square,
            title="मेरी ऑडियो कहानी",
            author="Voice Engine Studio",
            subtitle_srt=srt_path,
            aspect_ratio="square",
        )
        assert res_sq.is_file()
        assert res_sq.stat().st_size > 10000

        # Verify video stream with ffprobe
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,codec_name",
            "-of", "json",
            str(res_sq),
        ]
        probe_res = subprocess.run(probe_cmd, capture_output=True, text=True)
        assert probe_res.returncode == 0
        v_info = json.loads(probe_res.stdout)["streams"][0]
        assert v_info["width"] == 1080
        assert v_info["height"] == 1080
        assert v_info["codec_name"] == "h264"

        # 2. Vertical 9:16 audiogram without subtitles
        res_vert = pipeline.export_audiogram_video(
            speech_wav=wav_path,
            output_mp4=mp4_vertical,
            title="Shorts Reel",
            author="AI Creator",
            subtitle_srt=None,
            aspect_ratio="vertical",
        )
        assert res_vert.is_file()
        assert res_vert.stat().st_size > 10000

        probe_vert = subprocess.run([
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json",
            str(res_vert),
        ], capture_output=True, text=True)
        v_vert = json.loads(probe_vert.stdout)["streams"][0]
        assert v_vert["width"] == 1080
        assert v_vert["height"] == 1920


def test_mixer_audiogram_ui_controls(qapp):
    mixer = MixerInterface()
    
    # Verify formats are present
    formats = [mixer.combo_format.itemText(i) for i in range(mixer.combo_format.count())]
    assert any("Audiogram" in f for f in formats)
    assert any("SRT" in f for f in formats)
    assert any("VTT" in f for f in formats)

    # Audiogram box visibility toggle
    assert mixer.audiogram_box.isHidden()
    
    # Select Audiogram
    ag_idx = next(i for i, f in enumerate(formats) if "Audiogram" in f)
    mixer.combo_format.setCurrentIndex(ag_idx)
    assert not mixer.audiogram_box.isHidden()

    # Select WAV
    wav_idx = next(i for i, f in enumerate(formats) if "WAV" in f)
    mixer.combo_format.setCurrentIndex(wav_idx)
    assert mixer.audiogram_box.isHidden()


def test_block_interface_subtitles_button(qapp):
    block_ui = BlockInterface()
    assert hasattr(block_ui, "btn_subtitles")
    assert block_ui.btn_subtitles.text() == "Subtitles"
