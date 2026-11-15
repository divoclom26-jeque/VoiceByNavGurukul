import math
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.text_processor import TextProcessor


class EditorWidget(QFrame):
    """Text editor with chapter inputs, file import, and live text metrics."""

    text_changed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setProperty("class", "card-panel")
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Header: Project Name & Import File
        header_row = QHBoxLayout()
        lbl_proj = QLabel("Project Title:")
        lbl_proj.setStyleSheet("font-weight: 600; color: #a6adc8;")
        self.txt_project_name = QLineEdit("My Audio Story")
        self.txt_project_name.setPlaceholderText("Enter project / chapter title...")

        self.btn_import = QPushButton("📂 Open File")
        self.btn_import.setProperty("class", "btn-secondary")

        self.btn_clear = QPushButton("🗑 Clear")
        self.btn_clear.setProperty("class", "btn-secondary")

        header_row.addWidget(lbl_proj)
        header_row.addWidget(self.txt_project_name, stretch=1)
        header_row.addWidget(self.btn_import)
        header_row.addWidget(self.btn_clear)
        layout.addLayout(header_row)

        # Text Editor
        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText(
            "Paste or write your text, chapter, or podcast script here...\n\n"
            "Markdown headings, quotes, and punctuation are automatically handled and normalized."
        )
        layout.addWidget(self.text_edit, stretch=1)

        # Bottom stats bar
        stats_row = QHBoxLayout()
        self.lbl_stats = QLabel("Words: 0 | Characters: 0 | Estimated Duration: 0s | Blocks: 0")
        self.lbl_stats.setStyleSheet("color: #a6adc8; font-size: 12px;")
        stats_row.addWidget(self.lbl_stats)
        stats_row.addStretch()

        self.btn_preview_chunks = QPushButton("🔍 Preview Chunks")
        self.btn_preview_chunks.setProperty("class", "btn-secondary")
        stats_row.addWidget(self.btn_preview_chunks)

        layout.addLayout(stats_row)

    def _connect_signals(self):
        self.text_edit.textChanged.connect(self._on_text_changed)
        self.btn_import.clicked.connect(self._import_file)
        self.btn_clear.clicked.connect(self.clear)

    def _on_text_changed(self):
        text = self.text_edit.toPlainText().strip()
        chars = len(text)
        words = len(text.split()) if text else 0

        # Typical reading speed: ~150 words per minute (2.5 words/sec)
        est_seconds = int((words / 150.0) * 60)
        mins, secs = divmod(est_seconds, 60)
        time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"

        # Estimated block count
        blocks = TextProcessor.split_into_blocks(text, max_chars=280) if text else []
        block_count = len(blocks)

        self.lbl_stats.setText(
            f"Words: {words:,} | Characters: {chars:,} | "
            f"Est. Duration: ~{time_str} | Blocks: {block_count}"
        )
        self.text_changed.emit(text)

    def _import_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Text File",
            "",
            "Text & Markdown Files (*.txt *.md);;All Files (*)",
        )
        if file_path:
            p = Path(file_path)
            content = p.read_text(encoding="utf-8", errors="replace")
            self.text_edit.setPlainText(content)
            self.txt_project_name.setText(p.stem.replace("_", " ").title())

    def get_text(self) -> str:
        return self.text_edit.toPlainText().strip()

    def set_text(self, text: str):
        self.text_edit.setPlainText(text)

    def get_project_name(self) -> str:
        name = self.txt_project_name.text().strip()
        return name if name else "Untitled Project"

    def set_project_name(self, name: str):
        self.txt_project_name.setText(name)

    def clear(self):
        self.text_edit.clear()
