import logging
from pathlib import Path
from typing import Optional

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import (
    FluentIcon,
    FluentWindow,
    NavigationItemPosition,
    Theme,
    isDarkTheme,
    setTheme,
)

from app.core.project_manager import Project
from app.ui.fluent.interfaces.block_interface import BlockInterface
from app.ui.fluent.interfaces.gallery_interface import GalleryInterface
from app.ui.fluent.interfaces.mixer_interface import MixerInterface
from app.ui.fluent.interfaces.projects_interface import ProjectsInterface
from app.ui.fluent.interfaces.studio_interface import StudioInterface
from app.ui.fluent.player_bar import FluentAudioPlayerBar
from app.utils.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)


class FluentMainWindow(FluentWindow):
    """Modern Windows 11 / macOS Fluent 2 Main Window for Voice Studio AI."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        # 1. Apply Modern Light Fluent theme by default
        setTheme(Theme.LIGHT)

        # 2. Window Configuration
        self.setWindowTitle("Voice Studio AI — Fluent Studio")
        self.resize(1260, 840)
        self.setMinimumSize(960, 640)

        icon_path = PROJECT_ROOT / "assets" / "icon.png"
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))

        # 3. Create Sub-Interfaces
        self.studio_interface = StudioInterface(self)
        self.block_interface = BlockInterface(self)
        self.mixer_interface = MixerInterface(self)
        self.gallery_interface = GalleryInterface(self)
        self.projects_interface = ProjectsInterface(self)

        # 4. Integrate Persistent Bottom Player Bar into Content Area
        self.widgetLayout.removeWidget(self.stackedWidget)

        right_container_vbox = QVBoxLayout()
        right_container_vbox.setContentsMargins(0, 48, 14, 14)
        right_container_vbox.setSpacing(10)
        right_container_vbox.addWidget(self.stackedWidget, stretch=1)

        self.player_bar = FluentAudioPlayerBar(self)
        right_container_vbox.addWidget(self.player_bar, stretch=0)

        self.widgetLayout.setContentsMargins(0, 0, 0, 0)
        self.widgetLayout.addLayout(right_container_vbox)

        # 5. Add Navigation Items
        self.addSubInterface(self.studio_interface, FluentIcon.MICROPHONE, "Studio")
        self.addSubInterface(self.block_interface, FluentIcon.EDIT, "Blocks & Dialogue")
        self.addSubInterface(self.mixer_interface, FluentIcon.MUSIC, "Mixer & Podcast")
        self.addSubInterface(self.gallery_interface, FluentIcon.GLOBE, "Voice Gallery")
        self.addSubInterface(
            self.projects_interface,
            FluentIcon.FOLDER,
            "Projects Library",
            position=NavigationItemPosition.BOTTOM,
        )

        # 6. Add Pronunciation Lexicon and Theme Toggle in Sidebar
        self.navigationInterface.addItem(
            routeKey="lexicon_dialog",
            icon=FluentIcon.DICTIONARY,
            text="Pronunciation",
            onClick=self._open_lexicon_dialog,
            selectable=False,
            position=NavigationItemPosition.BOTTOM,
            tooltip="Manage phonetic pronunciation rules & acronyms",
        )

        self.theme_btn = self.navigationInterface.addItem(
            routeKey="theme_toggle",
            icon=FluentIcon.CONSTRACT,
            text="Dark Mode" if not isDarkTheme() else "Light Mode",
            onClick=self._toggle_theme,
            selectable=False,
            position=NavigationItemPosition.BOTTOM,
            tooltip="Switch between Light and Dark Theme",
        )

        # 7. Connect Inter-Component Signals
        self._connect_signals()

    def _open_lexicon_dialog(self):
        """Open the Lexicon & Pronunciation Dictionary Dialog."""
        from app.ui.fluent.lexicon_dialog import LexiconDialog

        dialog = LexiconDialog(parent=self)
        dialog.exec()

    def _toggle_theme(self):
        """Toggle dynamically between Modern Light and Dark theme."""
        if isDarkTheme():
            setTheme(Theme.LIGHT)
            self.theme_btn.setText("Dark Mode")
            self.theme_btn.setIcon(FluentIcon.CONSTRACT)
        else:
            setTheme(Theme.DARK)
            self.theme_btn.setText("Light Mode")
            self.theme_btn.setIcon(FluentIcon.BRIGHTNESS)

    def _connect_signals(self):
        # Studio synthesis completed -> load into player & pass to block/mixer views
        self.studio_interface.synthesis_completed.connect(self._on_synthesis_completed)
        self.studio_interface.test_voice_requested.connect(
            lambda audio_path, title: (
                self.player_bar.load_audio(audio_path, title=title),
                self.player_bar.play(),
            )
        )

        # Block interface playback & Descript-style seek/repack
        self.block_interface.play_audio_requested.connect(
            lambda audio_path, title: (
                self.player_bar.load_audio(audio_path, title=title),
                self.player_bar.play(),
            )
        )
        self.block_interface.seek_master_requested.connect(self._on_seek_master_requested)
        self.block_interface.master_repacked.connect(self._on_master_repacked)

        # Mixer interface playback
        self.mixer_interface.play_audio_requested.connect(
            lambda audio_path, title: (
                self.player_bar.load_audio(audio_path, title=title),
                self.player_bar.play(),
            )
        )

        # Projects library interactions
        self.projects_interface.play_audio_requested.connect(
            lambda audio_path, title: (
                self.player_bar.load_audio(audio_path, title=title),
                self.player_bar.play(),
            )
        )
        self.projects_interface.load_project_requested.connect(self._on_load_project_from_library)

        # Voice gallery newly installed voice -> refresh studio dropdown
        self.gallery_interface.voice_installed.connect(self._on_voice_installed)

    def _on_synthesis_completed(self, master_path: str, duration: float, project_name: str):
        # Load and start playing master audio
        self.player_bar.load_audio(master_path, title=f"Master: {project_name}")
        self.player_bar.play()

        # Update block & mixer interfaces with the newly synthesized project
        project_dir = Path(master_path).parent.parent
        if (project_dir / "manifest.json").is_file():
            try:
                proj = Project.load(project_dir)
                self.block_interface.load_project(proj)
                self.mixer_interface.load_project(proj)
            except Exception as e:
                logger.error("Failed to load synthesized project into sub-interfaces: %s", e)

        # Refresh project library
        self.projects_interface.refresh()

    def _on_load_project_from_library(self, project_dir: str, target_tab: str):
        try:
            proj = Project.load(Path(project_dir))
            self.block_interface.load_project(proj)
            self.mixer_interface.load_project(proj)

            if target_tab == "mixer":
                self.switchTo(self.mixer_interface)
            else:
                self.switchTo(self.block_interface)
        except Exception as e:
            logger.error("Error loading project %s: %s", project_dir, e)

    def _on_seek_master_requested(self, start_time: float):
        if self.block_interface.project:
            master_wav = (
                self.block_interface.project.exports_dir
                / f"{self.block_interface.project.name}_master.wav"
            )
            if master_wav.is_file():
                if not self.player_bar.current_file or self.player_bar.current_file != master_wav:
                    self.player_bar.load_audio(
                        str(master_wav), title=f"Master: {self.block_interface.project.name}"
                    )
                self.player_bar.seek_and_play(start_time)

    def _on_master_repacked(self, master_path: str, duration: float):
        proj_name = self.block_interface.project.name if self.block_interface.project else "Master"
        self.player_bar.load_audio(master_path, title=f"Master: {proj_name}")
        self.projects_interface.refresh()

    def _on_voice_installed(self, voice_key: str):
        self.studio_interface._populate_voices()

    def closeEvent(self, event):
        if hasattr(self, "player_bar"):
            self.player_bar.stop()
        super().closeEvent(event)
