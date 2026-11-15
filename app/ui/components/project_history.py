import os
from pathlib import Path
import subprocess
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.project_manager import Project, ProjectManager


class ProjectHistoryWidget(QFrame):
    """View and manage generated audiobook/voiceover projects."""

    load_project_requested = Signal(str)  # project_dir
    play_audio_requested = Signal(str, str)  # audio_path, title

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setProperty("class", "card-panel")
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Header
        top_bar = QHBoxLayout()
        lbl_heading = QLabel("Project History")
        lbl_heading.setProperty("class", "heading")
        top_bar.addWidget(lbl_heading)
        top_bar.addStretch()

        self.btn_refresh = QPushButton("🔄 Refresh")
        self.btn_refresh.setProperty("class", "btn-secondary")
        self.btn_refresh.clicked.connect(self.refresh)
        top_bar.addWidget(self.btn_refresh)
        layout.addLayout(top_bar)

        # Projects Table
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Project Name", "Voice", "Blocks", "Updated", "Actions"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        layout.addWidget(self.table, stretch=1)

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

            # Action Buttons container
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(2, 2, 2, 2)
            action_layout.setSpacing(6)

            # Check for master audio in exports
            exports_dir = p_dir / "exports"
            master_audio = None
            if exports_dir.is_dir():
                for f in sorted(exports_dir.glob("*_master.*")):
                    if f.suffix in (".mp3", ".wav", ".m4b"):
                        master_audio = f
                        break

            if master_audio:
                btn_play = QPushButton("▶ Play")
                btn_play.setProperty("class", "btn-secondary")
                btn_play.clicked.connect(lambda _, a=master_audio, n=p["name"]: self.play_audio_requested.emit(str(a), n))
                action_layout.addWidget(btn_play)

            btn_review = QPushButton("🔍 Review Blocks")
            btn_review.setProperty("class", "btn-secondary")
            btn_review.clicked.connect(lambda _, d=p_dir: self.load_project_requested.emit(str(d)))
            action_layout.addWidget(btn_review)

            btn_open = QPushButton("📂 Folder")
            btn_open.setProperty("class", "btn-secondary")
            btn_open.clicked.connect(lambda _, d=p_dir: self._open_folder(d))
            action_layout.addWidget(btn_open)

            self.table.setCellWidget(row, 4, action_widget)

    def _open_folder(self, folder: Path):
        try:
            if os.name == "posix":
                subprocess.Popen(["xdg-open", str(folder)])
            elif os.name == "nt":
                os.startfile(str(folder))
        except Exception as e:
            QMessageBox.warning(self, "Open Folder", f"Could not open directory: {e}")
