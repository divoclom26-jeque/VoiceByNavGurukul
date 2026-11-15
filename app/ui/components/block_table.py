from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.project_manager import Project, TextBlock
from app.tts.voice_manager import list_local_voices


class BlockEditDialog(QDialog):
    """Dialog to edit the text and voice of an individual block."""

    def __init__(self, block: TextBlock, available_voices: List[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Edit Block #{block.id}")
        self.resize(500, 320)
        self.block = block

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Header info
        layout.addWidget(QLabel(f"<b>Block #{block.id} Content:</b>"))

        # Text edit
        self.text_edit = QPlainTextEdit(block.text)
        layout.addWidget(self.text_edit, stretch=1)

        # Voice override selector
        voice_row = QHBoxLayout()
        voice_row.addWidget(QLabel("Speaker / Voice Override:"))
        self.combo_voice = QComboBox()
        self.combo_voice.addItem("Default (Project Voice)", None)

        for v in available_voices:
            self.combo_voice.addItem(f"{v['name']} ({v['language']})", v["key"])

        # Select current if assigned
        if block.voice_key:
            idx = self.combo_voice.findData(block.voice_key)
            if idx >= 0:
                self.combo_voice.setCurrentIndex(idx)

        voice_row.addWidget(self.combo_voice, stretch=1)
        layout.addLayout(voice_row)

        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_updated_data(self):
        return {
            "text": self.text_edit.toPlainText().strip(),
            "voice_key": self.combo_voice.currentData(),
        }


class BlockTableWidget(QFrame):
    """Interactive table showing per-block status, audio preview, and individual re-synthesis."""

    play_block_requested = Signal(str, str)  # audio_path, title
    repack_master_requested = Signal()  # triggers fast master stitch
    block_updated = Signal(int)  # block_id

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setProperty("class", "card-panel")

        self.project: Optional[Project] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Top Bar
        top_bar = QHBoxLayout()
        self.lbl_heading = QLabel("Block Review & Dialogue Studio")
        self.lbl_heading.setProperty("class", "heading")
        top_bar.addWidget(self.lbl_heading)
        top_bar.addStretch()

        self.btn_repack = QPushButton("⚡ Fast Re-Pack Master")
        self.btn_repack.setProperty("class", "btn-primary")
        self.btn_repack.clicked.connect(self._repack_master)
        top_bar.addWidget(self.btn_repack)

        self.btn_refresh = QPushButton("🔄 Refresh")
        self.btn_refresh.setProperty("class", "btn-secondary")
        self.btn_refresh.clicked.connect(self.refresh)
        top_bar.addWidget(self.btn_refresh)

        layout.addLayout(top_bar)

        # Filter row
        filter_row = QHBoxLayout()
        self.txt_filter = QLineEdit()
        self.txt_filter.setPlaceholderText("Filter blocks by text or status...")
        self.txt_filter.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self.txt_filter)
        layout.addLayout(filter_row)

        # Table
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["#", "Status", "Text Segment", "Voice", "Duration", "Actions"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._on_row_double_clicked)

        layout.addWidget(self.table, stretch=1)

    def load_project(self, project: Project):
        self.project = project
        self.lbl_heading.setText(f"Block Review: {project.name} ({len(project.blocks)} blocks)")
        self.refresh()

    def refresh(self):
        if not self.project:
            self.table.setRowCount(0)
            return

        query = self.txt_filter.text().lower().strip()
        filtered_blocks = [
            b for b in self.project.blocks
            if not query or query in b.text.lower() or query in b.status.lower()
        ]

        self.table.setRowCount(len(filtered_blocks))
        available_voices = list_local_voices()

        for row, block in enumerate(filtered_blocks):
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
            voice_label = block.voice_key or "Default"
            self.table.setItem(row, 3, QTableWidgetItem(voice_label))

            # 4: Duration
            dur_str = f"{block.duration:.2f}s" if block.duration > 0 else "-"
            item_dur = QTableWidgetItem(dur_str)
            item_dur.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, item_dur)

            # 5: Actions container
            action_widget = QWidget()
            a_layout = QHBoxLayout(action_widget)
            a_layout.setContentsMargins(2, 2, 2, 2)
            a_layout.setSpacing(6)

            # Play Button
            has_audio = block.audio_file and (self.project.project_dir / block.audio_file).is_file()
            btn_play = QPushButton("▶ Play")
            btn_play.setProperty("class", "btn-secondary")
            btn_play.setEnabled(bool(has_audio))
            if has_audio:
                audio_full = str(self.project.project_dir / block.audio_file)
                btn_play.clicked.connect(
                    lambda _, a=audio_full, b_id=block.id: self.play_block_requested.emit(a, f"Block #{b_id}")
                )
            a_layout.addWidget(btn_play)

            # Edit Button
            btn_edit = QPushButton("✏ Edit")
            btn_edit.setProperty("class", "btn-secondary")
            btn_edit.clicked.connect(lambda _, b=block: self._open_edit_dialog(b))
            a_layout.addWidget(btn_edit)

            # Regenerate Button
            btn_regen = QPushButton("⚡ Render")
            btn_regen.setProperty("class", "btn-secondary")
            btn_regen.clicked.connect(lambda _, b_id=block.id: self._render_single_block(b_id))
            a_layout.addWidget(btn_regen)

            self.table.setCellWidget(row, 5, action_widget)

    def _apply_filter(self):
        self.refresh()

    def _on_row_double_clicked(self, index):
        row = index.row()
        block_id_str = self.table.item(row, 0).text().replace("#", "")
        block_id = int(block_id_str)
        for b in self.project.blocks:
            if b.id == block_id:
                self._open_edit_dialog(b)
                break

    def _open_edit_dialog(self, block: TextBlock):
        available_voices = list_local_voices()
        dlg = BlockEditDialog(block, available_voices, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_updated_data()
            new_text = data["text"]
            voice_key = data["voice_key"]

            if new_text != block.text or voice_key != block.voice_key:
                block.text = new_text
                block.voice_key = voice_key
                block.status = "pending"
                self.project.save()
                self.refresh()

                # Prompt to re-synthesize this block immediately
                reply = QMessageBox.question(
                    self,
                    "Re-synthesize Block?",
                    f"Block #{block.id} was updated. Would you like to synthesize it now?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self._render_single_block(block.id)

    def _render_single_block(self, block_id: int):
        if not self.project:
            return

        try:
            res_block = self.project.synthesize_block(block_id)
            self.refresh()
            if res_block.status == "completed":
                # Play audio
                audio_path = str(self.project.project_dir / res_block.audio_file)
                self.play_block_requested.emit(audio_path, f"Block #{block_id} (Updated)")
            else:
                QMessageBox.critical(self, "Synthesis Error", f"Block #{block_id} failed: {res_block.error_message}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed rendering block: {e}")

    def _repack_master(self):
        if not self.project:
            return

        try:
            master_file = self.project.build_master_audio(output_format="wav", pause_ms=350, normalize=True)
            self.play_block_requested.emit(str(master_file), f"{self.project.name} Master Audio")
            QMessageBox.information(
                self,
                "Master Re-packed! ⚡",
                f"Master audio successfully re-stitched with your block changes!\n\nFile: {master_file.name}",
            )
        except Exception as e:
            QMessageBox.critical(self, "Re-pack Failed", str(e))
