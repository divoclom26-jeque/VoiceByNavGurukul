import logging
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QMessageBox,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
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
from app.ui.fluent.block_edit_dialog import FluentBlockEditDialog

logger = logging.getLogger(__name__)


def _format_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


class BlockInterface(QWidget):
    """Fluent Descript-Style Block Review & Dialogue Studio Interface.
    
    Provides text-to-audio seeking, instant selective re-takes, block-level tuning,
    and automatic master audio re-stitching with micro-crossfades.
    """

    play_audio_requested = Signal(str, str)  # audio_path, title
    seek_master_requested = Signal(float)  # seek seconds in master timeline
    master_repacked = Signal(str, float)  # master_audio_path, duration

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
        self.lbl_head = SubtitleLabel("🎙️ Descript-Style Dialogue & Block Studio", self)
        top_row.addWidget(self.lbl_head)
        top_row.addStretch()

        self.search_bar = SearchLineEdit(self)
        self.search_bar.setPlaceholderText("Filter script by text...")
        self.search_bar.setFixedWidth(220)
        self.search_bar.textChanged.connect(self.refresh)
        top_row.addWidget(self.search_bar)

        self.btn_characters = PushButton(FluentIcon.PEOPLE, "Characters", self)
        self.btn_characters.setToolTip("Configure character voices and multi-speaker palette")
        self.btn_characters.clicked.connect(self._open_characters_dialog)
        top_row.addWidget(self.btn_characters)

        self.btn_add_block = PushButton(FluentIcon.ADD, "Add Block", self)
        self.btn_add_block.clicked.connect(self._add_new_block)
        top_row.addWidget(self.btn_add_block)

        self.btn_repack = PrimaryPushButton(FluentIcon.SYNC, "Fast Re-Pack Master", self)
        self.btn_repack.clicked.connect(self._repack_master)
        top_row.addWidget(self.btn_repack)

        card_layout.addLayout(top_row)

        # Info bar metrics
        self.lbl_metrics = CaptionLabel("No project loaded.", self)
        self.lbl_metrics.setStyleSheet("font-weight: 500;")
        card_layout.addWidget(self.lbl_metrics)

        # Fluent Table
        self.table = TableWidget(self)
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "#",
            "Status",
            "Timeline",
            "Text Segment",
            "Voice / Speaker",
            "Duration",
            "Actions",
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(TableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._on_double_click)

        card_layout.addWidget(self.table, stretch=1)
        main_layout.addWidget(card, stretch=1)

    def load_project(self, project: Project):
        self.project = project
        self.lbl_head.setText(f"🎙️ Dialogue & Block Studio: {project.name}")
        self.refresh()

    def refresh(self):
        if not self.project:
            self.table.setRowCount(0)
            self.lbl_metrics.setText("No project loaded.")
            return

        total_blocks = len(self.project.blocks)
        completed_blocks = sum(1 for b in self.project.blocks if b.status == "completed")
        total_dur = sum(b.duration for b in self.project.blocks if b.duration > 0)
        mins, secs = divmod(int(total_dur), 60)
        time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"

        self.lbl_metrics.setText(
            f"Project Blocks: {total_blocks} | Completed: {completed_blocks}/{total_blocks} | "
            f"Speech Audio: ~{time_str} | Double-click row to Edit & Re-take"
        )

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
                status_item.setForeground(QColor("#2e7d32"))
            elif block.status == "failed":
                status_item.setForeground(QColor("#c62828"))
            else:
                status_item.setForeground(QColor("#ef6c00"))
            self.table.setItem(row, 1, status_item)

            # 2: Timeline
            time_badge = f"{_format_time(block.start_time)} - {_format_time(block.end_time)}"
            item_time = QTableWidgetItem(time_badge)
            item_time.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, item_time)

            # 3: Text Segment
            self.table.setItem(row, 3, QTableWidgetItem(block.text))

            # 4: Voice / Character
            if block.speaker_label:
                char_data = self.project.get_character_palette().get(block.speaker_label, {})
                spk_color = char_data.get("color", "#0078D4")
                v_name = block.voice_key or "Default"
                voice_display = f"🎭 {block.speaker_label} ({v_name})"
                item_voice = QTableWidgetItem(voice_display)
                item_voice.setForeground(QColor(spk_color))
            else:
                voice_display = block.voice_key or "Default"
                item_voice = QTableWidgetItem(voice_display)
            self.table.setItem(row, 4, item_voice)

            # 5: Duration
            dur_str = f"{block.duration:.2f}s" if block.duration > 0 else "-"
            item_dur = QTableWidgetItem(dur_str)
            item_dur.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 5, item_dur)

            # 6: Action buttons
            action_w = QWidget()
            a_layout = QHBoxLayout(action_w)
            a_layout.setContentsMargins(4, 2, 4, 2)
            a_layout.setSpacing(6)

            has_audio = block.audio_file and (self.project.project_dir / block.audio_file).is_file()

            # Seek to block in Master timeline
            btn_seek = TransparentToolButton(FluentIcon.PLAY, action_w)
            btn_seek.setEnabled(bool(has_audio))
            btn_seek.setToolTip(f"Play Block #{block.id} in Master Timeline ({_format_time(block.start_time)})")
            if has_audio:
                btn_seek.clicked.connect(lambda _, st=block.start_time: self.seek_master_requested.emit(st))
            a_layout.addWidget(btn_seek)

            # Instant 1-Click Re-take
            btn_retake = TransparentToolButton(FluentIcon.SYNC, action_w)
            btn_retake.setToolTip(f"Instant Re-Take Block #{block.id} (Re-renders audio with micro-crossfade)")
            btn_retake.clicked.connect(lambda _, b_id=block.id: self._quick_retake(b_id))
            a_layout.addWidget(btn_retake)

            # Edit Dialog
            btn_edit = TransparentToolButton(FluentIcon.EDIT, action_w)
            btn_edit.setToolTip("Edit text, voice, speed & pause")
            btn_edit.clicked.connect(lambda _, b=block: self._edit_block(b))
            a_layout.addWidget(btn_edit)

            # Delete / Cut Block
            btn_cut = TransparentToolButton(FluentIcon.DELETE, action_w)
            btn_cut.setToolTip(f"Cut Block #{block.id} from audio and script")
            btn_cut.clicked.connect(lambda _, b_id=block.id: self._cut_block(b_id))
            a_layout.addWidget(btn_cut)

            self.table.setCellWidget(row, 6, action_w)

    def _on_double_click(self, index):
        row = index.row()
        block_id = int(self.table.item(row, 0).text().replace("#", ""))
        for b in self.project.blocks:
            if b.id == block_id:
                self._edit_block(b)
                break

    def _edit_block(self, block: TextBlock):
        if not self.project:
            return
        dlg = FluentBlockEditDialog(self.project, block, self)
        dlg.block_updated.connect(lambda _: self._on_block_modified())
        dlg.block_deleted.connect(lambda _: self._on_block_modified())
        dlg.exec()

    def _quick_retake(self, block_id: int):
        """1-Click Instant Re-take of a single block."""
        if not self.project:
            return
        try:
            self.project.retake_block(block_id=block_id, rebuild_master=True)
            self._on_block_modified()
            InfoBar.success(
                title="Instant Re-Take Complete ⚡",
                content=f"Block #{block_id} re-rendered and micro-crossfaded into master.",
                parent=self,
                position=InfoBarPosition.TOP,
            )
        except Exception as e:
            logger.error("Quick retake failed: %s", e)
            InfoBar.error(title="Re-Take Failed", content=str(e), parent=self)

    def _cut_block(self, block_id: int):
        """Cut a block from the project."""
        if not self.project:
            return

        res = QMessageBox.question(
            self,
            "Cut Audio Block",
            f"Are you sure you want to cut Block #{block_id}? "
            "Its text and audio will be removed from the master audio timeline.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if res == QMessageBox.StandardButton.Yes:
            if self.project.delete_block(block_id, rebuild_master=True):
                self._on_block_modified()
                InfoBar.info(
                    title="Block Cut ✂️",
                    content=f"Block #{block_id} cut out. Master audio seamlessly restitched.",
                    parent=self,
                    position=InfoBarPosition.TOP,
                )
            else:
                InfoBar.error(title="Cut Failed", content="Could not delete block.", parent=self)

    def _add_new_block(self):
        """Prompt to add a new sentence block to the project."""
        if not self.project:
            InfoBar.warning(title="No Project", content="Load or synthesize a project first.", parent=self)
            return

        text, ok = QInputDialog.getMultiLineText(
            self,
            "Add New Audio Block",
            "Enter sentence or text to insert into the project:",
        )
        if ok and text.strip():
            try:
                new_b = self.project.add_block(text.strip(), synthesize_now=True)
                self._on_block_modified()
                InfoBar.success(
                    title="Block Added 🎉",
                    content=f"Block #{new_b.id} synthesized and appended to master.",
                    parent=self,
                    position=InfoBarPosition.TOP,
                )
            except Exception as e:
                logger.error("Failed adding block: %s", e)
                InfoBar.error(title="Add Failed", content=str(e), parent=self)

    def _on_block_modified(self):
        self.refresh()
        if self.project:
            master_file = self.project.exports_dir / f"{self.project.name}_master.wav"
            if master_file.is_file():
                dur = sum(b.duration for b in self.project.blocks if b.duration > 0)
                self.master_repacked.emit(str(master_file), dur)

    def _repack_master(self):
        if not self.project:
            return
        try:
            master_file = self.project.build_master_audio(output_format="wav", pause_ms=350, normalize=True)
            dur = sum(b.duration for b in self.project.blocks if b.duration > 0)
            self.master_repacked.emit(str(master_file), dur)
            self.refresh()
            InfoBar.success(
                title="Master Re-packed! ⚡",
                content=f"Stitched master audio with micro-crossfades: {master_file.name}",
                parent=self,
                position=InfoBarPosition.TOP,
            )
        except Exception as e:
            InfoBar.error(title="Re-pack Failed", content=str(e), parent=self)

    def _open_characters_dialog(self):
        if not self.project:
            InfoBar.warning(title="No Project", content="Load or synthesize a project first.", parent=self)
            return

        from app.ui.fluent.speaker_dialog import CharacterPaletteDialog

        dlg = CharacterPaletteDialog(self.project, parent=self.window())
        dlg.palette_applied.connect(self.refresh)
        dlg.exec()
