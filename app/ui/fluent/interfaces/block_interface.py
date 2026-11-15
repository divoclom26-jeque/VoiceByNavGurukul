from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    ComboBox,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    PrimaryPushButton,
    PushButton,
    SearchLineEdit,
    SubtitleLabel,
    TableWidget,
    TransparentToolButton,
)

from app.core.project_manager import Project, TextBlock
from app.tts.voice_manager import list_local_voices
from app.ui.components.block_table import BlockEditDialog


class BlockInterface(QWidget):
    """Fluent Block Review & Dialogue Studio Interface."""

    play_audio_requested = Signal(str, str)  # audio_path, title

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("block_interface")

        self.project: Optional[Project] = None
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        card = CardWidget(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)

        # Header Row
        top_row = QHBoxLayout()
        self.lbl_head = SubtitleLabel("Block Review & Dialogue Studio", self)
        top_row.addWidget(self.lbl_head)
        top_row.addStretch()

        self.search_bar = SearchLineEdit(self)
        self.search_bar.setPlaceholderText("Filter blocks by text...")
        self.search_bar.setFixedWidth(240)
        self.search_bar.textChanged.connect(self.refresh)
        top_row.addWidget(self.search_bar)

        self.btn_repack = PrimaryPushButton(FluentIcon.SYNC, "Fast Re-Pack Master", self)
        self.btn_repack.clicked.connect(self._repack_master)
        top_row.addWidget(self.btn_repack)

        card_layout.addLayout(top_row)

        # Fluent Table
        self.table = TableWidget(self)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["#", "Status", "Text Segment", "Voice", "Duration", "Actions"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(TableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._on_double_click)

        card_layout.addWidget(self.table, stretch=1)
        main_layout.addWidget(card, stretch=1)

    def load_project(self, project: Project):
        self.project = project
        self.lbl_head.setText(f"Block Review: {project.name} ({len(project.blocks)} blocks)")
        self.refresh()

    def refresh(self):
        if not self.project:
            self.table.setRowCount(0)
            return

        query = self.search_bar.text().lower().strip()
        filtered = [b for b in self.project.blocks if not query or query in b.text.lower()]
        self.table.setRowCount(len(filtered))

        for row, block in enumerate(filtered):
            # 0: ID
            item_id = QTableWidgetItem(f"#{block.id}")
            item_id.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, item_id)

            # 1: Status
            status_item = QTableWidgetItem(block.status.upper())
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if block.status == "completed":
                status_item.setForeground(Qt.GlobalColor.green)
            elif block.status == "failed":
                status_item.setForeground(Qt.GlobalColor.red)
            else:
                status_item.setForeground(Qt.GlobalColor.yellow)
            self.table.setItem(row, 1, status_item)

            # 2: Text
            self.table.setItem(row, 2, QTableWidgetItem(block.text))

            # 3: Voice
            self.table.setItem(row, 3, QTableWidgetItem(block.voice_key or "Default"))

            # 4: Duration
            dur_str = f"{block.duration:.2f}s" if block.duration > 0 else "-"
            item_dur = QTableWidgetItem(dur_str)
            item_dur.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, item_dur)

            # 5: Actions
            action_w = QWidget()
            a_layout = QHBoxLayout(action_w)
            a_layout.setContentsMargins(4, 2, 4, 2)
            a_layout.setSpacing(6)

            has_audio = block.audio_file and (self.project.project_dir / block.audio_file).is_file()
            btn_play = TransparentToolButton(FluentIcon.PLAY, action_w)
            btn_play.setEnabled(bool(has_audio))
            if has_audio:
                audio_full = str(self.project.project_dir / block.audio_file)
                btn_play.clicked.connect(
                    lambda _, a=audio_full, b_id=block.id: self.play_audio_requested.emit(a, f"Block #{b_id}")
                )
            a_layout.addWidget(btn_play)

            btn_edit = TransparentToolButton(FluentIcon.EDIT, action_w)
            btn_edit.clicked.connect(lambda _, b=block: self._edit_block(b))
            a_layout.addWidget(btn_edit)

            btn_render = TransparentToolButton(FluentIcon.SYNC, action_w)
            btn_render.clicked.connect(lambda _, b_id=block.id: self._render_block(b_id))
            a_layout.addWidget(btn_render)

            self.table.setCellWidget(row, 5, action_w)

    def _on_double_click(self, index):
        row = index.row()
        block_id = int(self.table.item(row, 0).text().replace("#", ""))
        for b in self.project.blocks:
            if b.id == block_id:
                self._edit_block(b)
                break

    def _edit_block(self, block: TextBlock):
        voices = list_local_voices()
        dlg = BlockEditDialog(block, voices, self)
        if dlg.exec():
            data = dlg.get_updated_data()
            block.text = data["text"]
            block.voice_key = data["voice_key"]
            block.status = "pending"
            self.project.save()
            self.refresh()
            self._render_block(block.id)

    def _render_block(self, block_id: int):
        if not self.project:
            return
        try:
            res_block = self.project.synthesize_block(block_id)
            self.refresh()
            if res_block.status == "completed":
                audio_path = str(self.project.project_dir / res_block.audio_file)
                self.play_audio_requested.emit(audio_path, f"Block #{block_id} (Updated)")
                InfoBar.success(title="Block Rendered", content=f"Block #{block_id} is up to date", parent=self)
            else:
                InfoBar.error(title="Render Failed", content=res_block.error_message or "Unknown error", parent=self)
        except Exception as e:
            InfoBar.error(title="Error", content=str(e), parent=self)

    def _repack_master(self):
        if not self.project:
            return
        try:
            master_file = self.project.build_master_audio(output_format="wav", pause_ms=350, normalize=True)
            self.play_audio_requested.emit(str(master_file), f"{self.project.name} Master Audio")
            InfoBar.success(
                title="Master Re-packed! ⚡",
                content=f"Stitched master audio: {master_file.name}",
                parent=self,
                position=InfoBarPosition.TOP,
            )
        except Exception as e:
            InfoBar.error(title="Re-pack Failed", content=str(e), parent=self)
