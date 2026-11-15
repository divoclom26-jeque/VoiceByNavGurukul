import os
from pathlib import Path
import pytest

from app.core.project_manager import ProjectManager, TextBlock
from app.tts.kokoro_engine import KokoroTTSEngine
from app.tts.voice_manager import list_local_voices
from app.utils.atomic_audio import validate_wav_file

os.environ["QT_QPA_PLATFORM"] = "offscreen"


def test_kokoro_engine_interface():
    """Verify KokoroTTSEngine conforms to BaseTTSEngine interface."""
    engine = KokoroTTSEngine()
    assert engine.engine_name == "kokoro"
    assert hasattr(engine, "synthesize_to_wav")
    assert hasattr(engine, "validate")
    # Should validate missing model correctly
    with pytest.raises(FileNotFoundError):
        engine.validate({"model_path": "/invalid/path.onnx", "voices_path": "/invalid/voices.bin"})


def test_block_editing_and_repack(tmp_path: Path):
    """Test updating a single block and re-stitching the master audio."""
    voices = list_local_voices()
    if not voices:
        pytest.skip("No voice model installed.")

    voice_key = voices[0]["key"]

    text = "Block one is first. Block two has a typo. Block three is the conclusion."
    project = ProjectManager.create_project(
        name="Review Test Project",
        text=text,
        voice_key=voice_key,
        max_chars=40,
    )

    assert len(project.blocks) >= 3

    # Initial synthesis of all blocks
    project.synthesize_all()
    orig_durations = [b.duration for b in project.blocks]

    # Target block 2 for editing
    target = project.blocks[1]
    project.update_block_text(target.id, "Block two has been corrected with fresh words.")
    assert target.status == "pending"

    # Re-synthesize ONLY block 2
    updated_block = project.synthesize_block(target.id)
    assert updated_block.status == "completed"
    assert updated_block.duration > 0

    # Fast re-pack master audio
    master_file = project.build_master_audio(output_format="wav", pause_ms=200, normalize=False)
    assert master_file.exists()
    info = validate_wav_file(master_file)
    assert info["duration"] > 1.5


def test_per_block_multi_voice_assignment(tmp_path: Path):
    """Test assigning different voices to different blocks (e.g. dialogue)."""
    voices = list_local_voices()
    if len(voices) < 2:
        pytest.skip("Need at least 2 installed voices for multi-voice assignment test.")

    v1 = voices[0]["key"]
    v2 = voices[1]["key"]

    text = "Narrator says hello. Character answers back."
    project = ProjectManager.create_project(
        name="Dialogue Test",
        text=text,
        voice_key=v1,
        max_chars=30,
    )

    # Assign Voice 1 to Block 1, and Voice 2 to Block 2
    project.assign_block_voice(1, voice_key=v1, speaker_label="Narrator")
    project.assign_block_voice(2, voice_key=v2, speaker_label="Character")

    cfg1 = project.get_voice_config_for_block(project.blocks[0])
    cfg2 = project.get_voice_config_for_block(project.blocks[1])

    assert cfg1["key"] == v1
    assert cfg2["key"] == v2

    # Synthesize both with their distinct voices
    project.synthesize_all()
    assert project.blocks[0].status == "completed"
    assert project.blocks[1].status == "completed"


def test_block_table_widget_offscreen(tmp_path: Path):
    """Test BlockTableWidget UI logic offscreen."""
    from PySide6.QtWidgets import QApplication
    from app.ui.components.block_table import BlockTableWidget

    app = QApplication.instance() or QApplication([])

    voices = list_local_voices()
    if not voices:
        pytest.skip("No voice model installed.")

    project = ProjectManager.create_project(
        name="Widget Test",
        text="First sentence. Second sentence.",
        voice_key=voices[0]["key"],
        max_chars=25,
    )

    table_widget = BlockTableWidget()
    table_widget.load_project(project)

    assert table_widget.table.rowCount() == len(project.blocks)
    assert table_widget.project == project

    table_widget.deleteLater()
    app.processEvents()
