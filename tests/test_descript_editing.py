import os
from pathlib import Path
import pytest

from PySide6.QtWidgets import QApplication
from app.core.project_manager import ProjectManager, TextBlock
from app.tts.voice_manager import list_local_voices
from app.ui.fluent.block_edit_dialog import FluentBlockEditDialog
from app.ui.fluent.player_bar import FluentAudioPlayerBar
from app.utils.atomic_audio import validate_wav_file

os.environ["QT_QPA_PLATFORM"] = "offscreen"


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_instant_retake_block(tmp_path: Path):
    voices = list_local_voices()
    if not voices:
        pytest.skip("No voice model installed.")

    voice_key = voices[0]["key"]
    text = "First sentence here. Second sentence with error. Third sentence concludes."
    project = ProjectManager.create_project(
        name="Retake Test",
        text=text,
        voice_key=voice_key,
        max_chars=40,
    )
    assert len(project.blocks) >= 3

    # Initial synthesis
    project.synthesize_all()
    orig_master = project.build_master_audio(normalize=False)
    orig_dur = validate_wav_file(orig_master)["duration"]

    # Target block 2 for Instant Re-take with longer text
    retaken = project.retake_block(
        block_id=2,
        new_text="Second sentence has now been replaced with a much longer elaborate explanation.",
        rebuild_master=True,
    )

    assert retaken.status == "completed"
    assert retaken.duration > 0
    new_master = project.exports_dir / f"{project.name}_master.wav"
    assert new_master.is_file()
    new_dur = validate_wav_file(new_master)["duration"]
    assert new_dur > orig_dur  # Master audio duration increased


def test_cut_block_audio_and_text(tmp_path: Path):
    voices = list_local_voices()
    if not voices:
        pytest.skip("No voice model installed.")

    voice_key = voices[0]["key"]
    text = "Sentence one will stay. Sentence two must be deleted. Sentence three remains."
    project = ProjectManager.create_project(
        name="Cut Block Test",
        text=text,
        voice_key=voice_key,
        max_chars=40,
    )
    project.synthesize_all()
    orig_master = project.build_master_audio(normalize=False)
    orig_dur = validate_wav_file(orig_master)["duration"]
    orig_block_count = len(project.blocks)

    # Cut Block 2 (Delete text = Delete audio)
    success = project.delete_block(2, rebuild_master=True)
    assert success is True
    assert len(project.blocks) == orig_block_count - 1

    # Check block IDs re-indexed 1..N
    assert project.blocks[0].id == 1
    assert project.blocks[1].id == 2

    new_master = project.exports_dir / f"{project.name}_master.wav"
    new_dur = validate_wav_file(new_master)["duration"]
    assert new_dur < orig_dur  # Master audio duration shrunk


def test_add_and_split_block(tmp_path: Path):
    voices = list_local_voices()
    if not voices:
        pytest.skip("No voice model installed.")

    voice_key = voices[0]["key"]
    text = "Introduction block here.\n\nConclusion block here."
    project = ProjectManager.create_project(
        name="Add Split Test",
        text=text,
        voice_key=voice_key,
        max_chars=25,
    )
    assert len(project.blocks) == 2
    project.synthesize_all()
    project.build_master_audio(normalize=False)

    # Add block in between (after block 1)
    new_b = project.add_block("Middle inserted sentence.", after_block_id=1, synthesize_now=True)
    assert new_b.id == 2
    assert len(project.blocks) == 3
    assert project.blocks[2].id == 3

    # Split block 1
    full_text = project.blocks[0].text
    split_pos = len(full_text) // 2
    b1, b2 = project.split_block(1, split_pos, synthesize_now=True)
    assert b1.id == 1
    assert b2.id == 2
    assert len(project.blocks) == 4


def test_update_timings_and_custom_pause(tmp_path: Path):
    voices = list_local_voices()
    if not voices:
        pytest.skip("No voice model installed.")

    voice_key = voices[0]["key"]
    text = "Block A content here.\n\nBlock B content here."
    project = ProjectManager.create_project(
        name="Timings Test",
        text=text,
        voice_key=voice_key,
        max_chars=25,
    )
    assert len(project.blocks) == 2
    project.synthesize_all()

    # Set custom pause after block 1 to 500ms
    project.blocks[0].pause_after_ms = 500
    project.build_master_audio(pause_ms=200, normalize=False)

    b0 = project.blocks[0]
    b1 = project.blocks[1]

    assert b0.start_time == 0.0
    assert b0.end_time == pytest.approx(b0.duration, abs=0.01)
    # Block 1 starts at b0.end_time + 0.5s pause
    assert b1.start_time == pytest.approx(b0.end_time + 0.5, abs=0.01)


def test_fluent_block_edit_dialog_offscreen(qapp, tmp_path: Path):
    voices = list_local_voices()
    if not voices:
        pytest.skip("No voice model installed.")

    voice_key = voices[0]["key"]
    project = ProjectManager.create_project(
        name="Dialog Test",
        text="Sample dialog text for testing.",
        voice_key=voice_key,
        max_chars=50,
    )
    block = project.blocks[0]

    dlg = FluentBlockEditDialog(project, block)
    assert dlg.windowTitle() == f"Edit & Re-Take Block #{block.id}"
    assert dlg.txt_content.toPlainText() == block.text
    assert dlg.slider_speed.value() == 100
    assert dlg.slider_pause.value() == 350
    dlg.close()


def test_player_bar_seek_seconds(qapp, tmp_path: Path):
    player_bar = FluentAudioPlayerBar()
    assert hasattr(player_bar, "seek_seconds")
    assert hasattr(player_bar, "seek_and_play")

    player_bar.waveform.set_duration(10000)
    player_bar.seek_seconds(5.5)
    assert player_bar.waveform.position_ms == 5500
    player_bar.close()
