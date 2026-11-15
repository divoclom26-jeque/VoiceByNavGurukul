import json
from pathlib import Path
import pytest

from PySide6.QtWidgets import QApplication
from app.core.lexicon import LexiconManager
from app.core.text_processor import TextProcessor
from app.ui.fluent.lexicon_dialog import LexiconDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_lexicon_manager_default_entries(tmp_path, monkeypatch):
    test_global_path = tmp_path / "models" / "lexicon.json"
    monkeypatch.setattr("app.core.lexicon.GLOBAL_LEXICON_PATH", test_global_path)

    entries = LexiconManager.load_global_lexicon()
    assert "NavGurukul" in entries
    assert entries["NavGurukul"]["replacement"] == "नवगुरुकुल"
    assert test_global_path.exists()


def test_lexicon_manager_add_and_remove(tmp_path, monkeypatch):
    test_global_path = tmp_path / "models" / "lexicon.json"
    monkeypatch.setattr("app.core.lexicon.GLOBAL_LEXICON_PATH", test_global_path)

    # Add entry
    LexiconManager.add_entry(
        word="K8s",
        replacement="कुबरनेटीज",
        whole_word=True,
        case_sensitive=False,
        notes="Kubernetes abbreviation",
        is_global=True,
    )

    entries = LexiconManager.load_global_lexicon()
    assert "K8s" in entries
    assert entries["K8s"]["replacement"] == "कुबरनेटीज"

    # Remove entry
    removed = LexiconManager.remove_entry("K8s", is_global=True)
    assert removed is True
    assert "K8s" not in LexiconManager.load_global_lexicon()


def test_lexicon_project_override(tmp_path, monkeypatch):
    test_global_path = tmp_path / "models" / "lexicon.json"
    monkeypatch.setattr("app.core.lexicon.GLOBAL_LEXICON_PATH", test_global_path)

    proj_dir = tmp_path / "projects" / "MyStory"
    proj_dir.mkdir(parents=True, exist_ok=True)

    # Add project-specific rule
    LexiconManager.add_entry(
        word="Protagonist",
        replacement="मुख्य पात्र",
        is_global=False,
        project_dir=proj_dir,
    )

    combined = LexiconManager.get_combined_lexicon(project_dir=proj_dir)
    assert "Protagonist" in combined
    assert combined["Protagonist"]["replacement"] == "मुख्य पात्र"
    assert "NavGurukul" in combined  # Global entry still present


def test_lexicon_substitution_word_boundary_and_case(tmp_path, monkeypatch):
    test_global_path = tmp_path / "models" / "lexicon.json"
    monkeypatch.setattr("app.core.lexicon.GLOBAL_LEXICON_PATH", test_global_path)

    LexiconManager.save_global_lexicon({
        "AI": {
            "replacement": "ए-आई",
            "whole_word": True,
            "case_sensitive": True,
        },
        "SQL": {
            "replacement": "सीक्वेल",
            "whole_word": True,
            "case_sensitive": False,
        },
    })

    # "AI" should match, but "FAIL" or "pain" should NOT match due to whole_word boundary
    text = "We use AI to study SQL. Do not FAIL or feel pain. Write in sql."
    result = LexiconManager.apply_lexicon(text)

    assert "ए-आई" in result
    assert "सीक्वेल" in result
    assert "FAIL" in result  # Not replaced
    assert "pain" in result  # Not replaced


def test_text_processor_applies_lexicon(tmp_path, monkeypatch):
    test_global_path = tmp_path / "models" / "lexicon.json"
    monkeypatch.setattr("app.core.lexicon.GLOBAL_LEXICON_PATH", test_global_path)

    LexiconManager.save_global_lexicon({
        "NavGurukul": {
            "replacement": "नवगुरुकुल",
            "whole_word": True,
            "case_sensitive": False,
        }
    })

    raw_text = "Welcome to NavGurukul! We empower youth with education."
    cleaned = TextProcessor.clean_text_for_speech(raw_text)
    assert "नवगुरुकुल" in cleaned
    assert "NavGurukul" not in cleaned

    blocks = TextProcessor.split_into_blocks(raw_text)
    assert len(blocks) > 0
    assert "नवगुरुकुल" in blocks[0]


def test_ssml_pause_tag_normalization():
    text = "Sentence one.<break time=\"500ms\"/>Sentence two. [pause: 300ms] Sentence three."
    result = LexiconManager.apply_lexicon(text)
    assert "<break" not in result
    assert "[pause" not in result
    assert "Sentence one. ... Sentence two. ... Sentence three." == result


def test_lexicon_dialog_ui(qapp, tmp_path, monkeypatch):
    test_global_path = tmp_path / "models" / "lexicon.json"
    monkeypatch.setattr("app.core.lexicon.GLOBAL_LEXICON_PATH", test_global_path)

    proj_dir = tmp_path / "projects" / "TestProj"
    proj_dir.mkdir(parents=True, exist_ok=True)

    dialog = LexiconDialog(project_dir=proj_dir)
    assert dialog.windowTitle() == "Pronunciation & Phonetic Dictionary"
    assert dialog.table.columnCount() == 6
    assert dialog.table.rowCount() >= 5  # default global entries

    # Add a new rule via UI fields
    dialog.txt_word.setText("API")
    dialog.txt_replacement.setText("ए-पी-आई")
    dialog.btn_add.click()

    assert "API" in LexiconManager.load_global_lexicon()
    dialog.close()
