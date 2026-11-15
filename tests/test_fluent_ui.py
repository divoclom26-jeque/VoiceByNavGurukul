import os
from pathlib import Path
import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication

from app.core.project_manager import Project, TextBlock
from app.ui.fluent.interfaces.block_interface import BlockInterface
from app.ui.fluent.interfaces.gallery_interface import GalleryInterface
from app.ui.fluent.interfaces.mixer_interface import MixerInterface
from app.ui.fluent.interfaces.projects_interface import ProjectsInterface
from app.ui.fluent.interfaces.studio_interface import StudioInterface
from app.ui.fluent.player_bar import FluentAudioPlayerBar
from app.ui.fluent.window import FluentMainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    app.processEvents()


def test_fluent_audio_player_bar(qapp, tmp_path: Path):
    """Test FluentAudioPlayerBar controls and audio loading."""
    player = FluentAudioPlayerBar()
    assert player is not None
    assert player.lbl_title.text() == "No audio loaded"
    assert not player.btn_play.isEnabled()

    # Create dummy wav
    import wave
    test_wav = tmp_path / "fluent_test.wav"
    with wave.open(str(test_wav), "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(22050)
        f.writeframes(b"\x00\x00" * 2205)  # 0.1s

    player.load_audio(str(test_wav), title="Test Audio")
    assert "Test Audio" in player.lbl_title.text()
    assert player.btn_play.isEnabled()
    assert player.btn_stop.isEnabled()

    player.stop()
    player.deleteLater()
    qapp.processEvents()


def test_fluent_studio_interface_metrics(qapp):
    """Test StudioInterface word count and character count metrics."""
    studio = StudioInterface()
    assert studio.objectName() == "studio_interface"

    studio.text_edit.setPlainText("Ek baar ki baat hai, ek bada sher tha.")
    stats_text = studio.lbl_metrics.text()
    assert "Words:" in stats_text
    assert "Chars:" in stats_text

    studio.deleteLater()
    qapp.processEvents()


def test_fluent_block_interface(qapp, tmp_path: Path):
    """Test BlockInterface project loading and table population."""
    block_ui = BlockInterface()
    assert block_ui.objectName() == "block_interface"

    proj = Project(
        project_dir=tmp_path / "proj1",
        name="TestStory",
        voice_key="en_US-lessac-low",
        blocks=[
            TextBlock(id=1, text="First dialogue block.", status="completed", duration=1.5),
            TextBlock(id=2, text="Second block question?", status="pending"),
        ],
    )

    block_ui.load_project(proj)
    assert block_ui.table.rowCount() == 2
    assert "TestStory" in block_ui.lbl_head.text()

    block_ui.deleteLater()
    qapp.processEvents()


def test_fluent_mixer_interface(qapp, tmp_path: Path):
    """Test MixerInterface metadata binding."""
    mixer_ui = MixerInterface()
    assert mixer_ui.objectName() == "mixer_interface"

    proj = Project(
        project_dir=tmp_path / "proj2",
        name="PodcastEpisode1",
        voice_key="hi_IN-pratham-medium",
        blocks=[TextBlock(id=1, text="Namaste dosto.", status="completed", duration=1.0)],
    )

    mixer_ui.load_project(proj)
    assert mixer_ui.txt_title.text() == "PodcastEpisode1"
    assert mixer_ui.txt_narrator.text() == "hi_IN-pratham-medium"

    mixer_ui.deleteLater()
    qapp.processEvents()


def test_fluent_gallery_and_projects(qapp):
    """Test Voice Gallery and Projects library instantiation."""
    gallery = GalleryInterface()
    assert gallery.objectName() == "gallery_interface"
    assert gallery.table is not None

    projects = ProjectsInterface()
    assert projects.objectName() == "projects_interface"
    assert projects.table is not None

    gallery.deleteLater()
    projects.deleteLater()
    qapp.processEvents()


def test_fluent_main_window_full_integration(qapp, tmp_path: Path):
    """Test FluentMainWindow creation, navigation, and signal flows."""
    window = FluentMainWindow()
    assert window is not None
    assert "Fluent Studio" in window.windowTitle()
    assert window.stackedWidget.count() >= 5

    # Check child interfaces
    assert isinstance(window.studio_interface, StudioInterface)
    assert isinstance(window.block_interface, BlockInterface)
    assert isinstance(window.mixer_interface, MixerInterface)
    assert isinstance(window.gallery_interface, GalleryInterface)
    assert isinstance(window.projects_interface, ProjectsInterface)
    assert isinstance(window.player_bar, FluentAudioPlayerBar)

    # Test tab switching
    window.switchTo(window.block_interface)
    assert window.stackedWidget.currentWidget() == window.block_interface

    window.switchTo(window.mixer_interface)
    assert window.stackedWidget.currentWidget() == window.mixer_interface

    window.switchTo(window.studio_interface)
    assert window.stackedWidget.currentWidget() == window.studio_interface

    # Test theme toggle
    from qfluentwidgets import isDarkTheme
    assert not isDarkTheme()
    assert window.theme_btn.text() == "Dark Mode"
    window._toggle_theme()
    assert isDarkTheme()
    assert window.theme_btn.text() == "Light Mode"
    window._toggle_theme()
    assert not isDarkTheme()

    # Test synthesis completed signal flow
    dummy_wav = tmp_path / "output_master.wav"
    import wave
    with wave.open(str(dummy_wav), "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(22050)
        f.writeframes(b"\x00\x00" * 100)

    window._on_synthesis_completed(str(dummy_wav), 0.1, "Demo Story")
    assert "Demo Story" in window.player_bar.lbl_title.text()

    window.close()
    window.deleteLater()
    qapp.processEvents()
