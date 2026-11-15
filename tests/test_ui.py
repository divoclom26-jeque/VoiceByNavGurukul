import os
from pathlib import Path
import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from app.ui.components.block_table import BlockTableWidget
from app.ui.components.editor_widget import EditorWidget
from app.ui.components.player_widget import AudioPlayerWidget
from app.ui.components.project_history import ProjectHistoryWidget
from app.ui.components.voice_gallery import VoiceGalleryWidget
from app.ui.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    app.processEvents()


def test_main_window_instantiation(qapp):
    """Test that MainWindow instantiates without errors in offscreen mode."""
    window = MainWindow()
    assert window is not None
    assert window.windowTitle() != ""
    assert window.stack.count() == 4

    # Check child widgets exist
    assert isinstance(window.editor, EditorWidget)
    assert isinstance(window.player, AudioPlayerWidget)
    assert isinstance(window.page_blocks, BlockTableWidget)
    assert isinstance(window.page_gallery, VoiceGalleryWidget)
    assert isinstance(window.page_projects, ProjectHistoryWidget)

    window.close()
    window.deleteLater()
    qapp.processEvents()


def test_editor_widget_metrics(qapp):
    """Test text metric updates in EditorWidget."""
    editor = EditorWidget()
    editor.set_text("This is a sample sentence with six words.")
    stats_text = editor.lbl_stats.text()
    assert "Words: 8" in stats_text
    assert "Characters: 41" in stats_text
    assert editor.get_project_name() != ""

    editor.deleteLater()
    qapp.processEvents()


def test_player_widget_controls(qapp, tmp_path: Path):
    """Test player widget state transitions."""
    player = AudioPlayerWidget()
    assert not player.btn_play.isEnabled()

    test_wav = tmp_path / "test.wav"
    from app.utils.atomic_audio import write_silence_wav
    write_silence_wav(test_wav, duration_seconds=0.5, sample_rate=16000)

    player.load_audio(str(test_wav), "Test Audio")
    assert player.btn_play.isEnabled()
    assert player.btn_stop.isEnabled()
    assert player.current_file == test_wav

    player.stop()
    player.deleteLater()
    qapp.processEvents()
