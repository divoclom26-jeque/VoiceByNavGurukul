import os
from pathlib import Path
import subprocess
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CardWidget,
    FluentIcon,
    PushButton,
    SubtitleLabel,
    TableWidget,
    TransparentToolButton,
)

from app.core.project_manager import ProjectManager


class ProjectsInterface(QWidget):
    """Projects & Story Library Interface."""

    load_project_requested = Signal(str, str)  # project_dir, target_tab
    play_audio_requested = Signal(str, str)  # audio_path, title

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("projects_interface")
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        card = CardWidget(self)
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(16, 16, 16, 16)
        c_layout.setSpacing(12)

        top_row = QHBoxLayout()
        top_row.addWidget(SubtitleLabel("Projects & Story Library", self))
        top_row.addStretch()

        self.btn_refresh = PushButton(FluentIcon.SYNC, "Refresh", self)
        self.btn_refresh.clicked.connect(self.refresh)
        top_row.addWidget(self.btn_refresh)
        c_layout.addLayout(top_row)

        self.table = TableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Project Name", "Voice", "Blocks", "Updated", "Actions"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(TableWidget.EditTrigger.NoEditTriggers)

        c_layout.addWidget(self.table, stretch=1)
        main_layout.addWidget(card, stretch=1)

    def refresh(self):
        projects = ProjectManager.list_projects()
        self.table.setRowCount(len(projects))

        for row, p in enumerate(projects):
            p_dir = Path(p["path"])
            self.table.setItem(row, 0, QTableWidgetItem(p["name"]))
            self.table.setItem(row, 1, QTableWidgetItem(str(p.get("voice_key", "Default"))))
            self.table.setItem(row, 2, QTableWidgetItem(str(p.get("blocks", 0))))

            date_str = (p.get("updated_at") or "").split("T")[0]
            self.table.setItem(row, 3, QTableWidgetItem(date_str))

            action_w = QWidget()
            a_layout = QHBoxLayout(action_w)
            a_layout.setContentsMargins(4, 2, 4, 2)
            a_layout.setSpacing(6)

            # Check for master audio
            exports_dir = p_dir / "exports"
            master_audio = None
            if exports_dir.is_dir():
                for f in sorted(exports_dir.glob("*_master.*")):
                    if f.suffix in (".mp3", ".wav", ".m4b", ".flac"):
                        master_audio = f
                        break

            if master_audio:
                btn_play = TransparentToolButton(FluentIcon.PLAY, action_w)
                btn_play.clicked.connect(
                    lambda _, a=master_audio, n=p["name"]: self.play_audio_requested.emit(str(a), n)
                )
                a_layout.addWidget(btn_play)

            btn_rev = PushButton(FluentIcon.EDIT, "Review", action_w)
            btn_rev.clicked.connect(lambda _, d=p_dir: self.load_project_requested.emit(str(d), "block_interface"))
            a_layout.addWidget(btn_rev)

            btn_open = TransparentToolButton(FluentIcon.FOLDER, action_w)
            btn_open.clicked.connect(lambda _, d=p_dir: self._open_dir(d))
            a_layout.addWidget(btn_open)

            self.table.setCellWidget(row, 4, action_w)

    def _open_dir(self, folder: Path):
        try:
            if os.name == "posix":
                subprocess.Popen(["xdg-open", str(folder)])
            elif os.name == "nt":
                os.startfile(str(folder))
        except Exception:
            pass
