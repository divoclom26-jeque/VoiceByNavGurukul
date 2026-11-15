import os
from pathlib import Path
import pytest

from PySide6.QtWidgets import QApplication
from app.core.project_manager import ProjectManager
from app.core.screenplay import ScreenplayParser
from app.tts.voice_manager import list_local_voices
from app.ui.fluent.speaker_dialog import CharacterPaletteDialog

os.environ["QT_QPA_PLATFORM"] = "offscreen"


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_has_screenplay_tags():
    screenplay_text = """
    [Narrator]: Once upon a time in a ancient kingdom.
    [Vikram]: What brings you here Rani?
    [Rani]: I have come to warn you.
    """
    assert ScreenplayParser.has_screenplay_tags(screenplay_text) is True

    plain_screenplay = """
    Narrator: It was a stormy night.
    Vikram: Listen carefully!
    """
    assert ScreenplayParser.has_screenplay_tags(plain_screenplay) is True

    regular_text = """
    This is an ordinary story without any character tags.
    Every day the sun rises and sets over the mountains.
    """
    assert ScreenplayParser.has_screenplay_tags(regular_text) is False


def test_parse_screenplay_and_extract_characters():
    script = """
    [Narrator]: The journey begins at dawn.
    [Vikram]: Are you ready Rani?
    We have a long path ahead.
    [Rani]: Yes, my bag is packed.
    """
    turns = ScreenplayParser.parse_screenplay(script)
    assert len(turns) == 3
    assert turns[0]["speaker"] == "Narrator"
    assert "journey begins" in turns[0]["text"]
    assert turns[1]["speaker"] == "Vikram"
    assert "Are you ready" in turns[1]["text"]
    assert "long path" in turns[1]["text"]  # multi-line turn continuation
    assert turns[2]["speaker"] == "Rani"
    assert "bag is packed" in turns[2]["text"]

    chars = ScreenplayParser.extract_characters(script)
    assert chars == ["Narrator", "Vikram", "Rani"]


def test_generate_character_palette():
    voices = list_local_voices()
    if not voices:
        pytest.skip("No voice model installed.")

    characters = ["Vikram", "Rani", "Narrator"]
    palette = ScreenplayParser.generate_character_palette(characters, voices)

    assert "Vikram" in palette
    assert "Rani" in palette
    assert "Narrator" in palette

    # Rani should be paired with female voice if female voice is present
    has_priyamvada = any("priyamvada" in v.get("key", "").lower() for v in voices)
    if has_priyamvada:
        assert "priyamvada" in palette["Rani"]["voice_key"].lower()

    # Vikram should be paired with male voice if male voice is present
    has_pratham = any("pratham" in v.get("key", "").lower() for v in voices)
    if has_pratham:
        assert "pratham" in palette["Vikram"]["voice_key"].lower()

    # Colors should be distinct
    colors = [palette[c]["color"] for c in characters]
    assert len(set(colors)) == len(characters)


def test_multi_speaker_project_creation(tmp_path: Path):
    voices = list_local_voices()
    if not voices:
        pytest.skip("No voice model installed.")

    script = """
    [Narrator]: A lone traveler arrives in town.
    [Vikram]: Greetings friend.
    [Rani]: Welcome to our village.
    """
    project = ProjectManager.create_project(
        name="Screenplay Drama",
        text=script,
        voice_key=voices[0]["key"],
        max_chars=60,
    )

    assert project.metadata.get("is_screenplay") is True
    assert "characters" in project.metadata
    assert len(project.blocks) == 3

    assert project.blocks[0].speaker_label == "Narrator"
    assert project.blocks[1].speaker_label == "Vikram"
    assert project.blocks[2].speaker_label == "Rani"

    # Block voice_key set from palette
    palette = project.get_character_palette()
    assert project.blocks[1].voice_key == palette["Vikram"]["voice_key"]
    assert project.blocks[2].voice_key == palette["Rani"]["voice_key"]

    # Synthesize project
    project.synthesize_all()
    assert all(b.status == "completed" for b in project.blocks)


def test_update_character_voice(tmp_path: Path):
    voices = list_local_voices()
    if len(voices) < 2:
        pytest.skip("Need at least 2 voices to test voice switching.")

    script = "[Vikram]: Line one. [Vikram]: Line two."
    project = ProjectManager.create_project(
        name="Update Char Voice",
        text=script,
        voice_key=voices[0]["key"],
        max_chars=30,
    )
    new_v = voices[1]["key"]

    # Switch Vikram's voice
    project.set_character_voice("Vikram", new_v, update_blocks=True)

    assert project.get_character_palette()["Vikram"]["voice_key"] == new_v
    for b in project.blocks:
        if b.speaker_label == "Vikram":
            assert b.voice_key == new_v
            assert b.status == "pending"


def test_character_palette_dialog_offscreen(qapp, tmp_path: Path):
    voices = list_local_voices()
    if not voices:
        pytest.skip("No voice model installed.")

    script = "[Host]: Welcome everyone. [Guest]: Thank you for having me."
    project = ProjectManager.create_project(
        name="Dialog Test",
        text=script,
        voice_key=voices[0]["key"],
        max_chars=40,
    )

    dlg = CharacterPaletteDialog(project)
    assert dlg.windowTitle() == "Character Voice Palette & Multi-Speaker Studio"
    assert dlg.table.rowCount() == 2
    dlg.close()
