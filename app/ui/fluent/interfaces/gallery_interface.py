import logging
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CaptionLabel,
    CardWidget,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    ProgressBar,
    PushButton,
    SearchLineEdit,
    SubtitleLabel,
    TableWidget,
)

from app.tts.voice_manager import get_remote_voices_catalog, list_local_voices
from app.ui.workers import DownloadVoiceWorker

logger = logging.getLogger(__name__)


class GalleryInterface(QWidget):
    """Voice Gallery Interface for browsing and installing Hugging Face voices."""

    voice_installed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("gallery_interface")

        self.catalog: Dict[str, Any] = {}
        self.download_worker: Optional[DownloadVoiceWorker] = None
        self._setup_ui()
        self._load_catalog()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        card = CardWidget(self)
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(16, 16, 16, 16)
        c_layout.setSpacing(12)

        # Header Row
        top_row = QHBoxLayout()
        lbl_head = SubtitleLabel("Hugging Face Voice Models", self)
        top_row.addWidget(lbl_head)
        top_row.addStretch()

        self.search_bar = SearchLineEdit(self)
        self.search_bar.setPlaceholderText("Search Hindi, English, Spanish...")
        self.search_bar.setFixedWidth(240)
        self.search_bar.textChanged.connect(self._populate_table)
        top_row.addWidget(self.search_bar)

        self.btn_refresh = PushButton(FluentIcon.SYNC, "Refresh", self)
        self.btn_refresh.clicked.connect(self._load_catalog)
        top_row.addWidget(self.btn_refresh)
        c_layout.addLayout(top_row)

        # Download progress
        self.progress_bar = ProgressBar(self)
        self.progress_bar.setVisible(False)
        self.lbl_status = CaptionLabel("", self)
        self.lbl_status.setVisible(False)
        c_layout.addWidget(self.lbl_status)
        c_layout.addWidget(self.progress_bar)

        # Table
        self.table = TableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Voice Key", "Language", "Quality", "Speakers", "Action"])
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

    def _load_catalog(self):
        try:
            self.catalog = get_remote_voices_catalog()
            self._populate_table()
        except Exception as e:
            logger.error(f"Catalog load error: {e}")

    def _populate_table(self):
        installed_keys = {v["key"] for v in list_local_voices()}
        query = self.search_bar.text().lower().strip()

        matching = []
        for key, data in self.catalog.items():
            lang_code = data.get("language", {}).get("code", "")
            lang_name = data.get("language", {}).get("name_english", "")
            if not query or query in key.lower() or query in lang_code.lower() or query in lang_name.lower():
                matching.append(key)

        def sort_fn(k):
            is_inst = k in installed_keys
            is_hi = k.startswith("hi")
            is_en = k.startswith("en")
            return (not is_inst, not is_hi, not is_en, k)

        matching.sort(key=sort_fn)
        display_list = matching[:50]

        self.table.clearContents()
        self.table.setRowCount(len(display_list))

        for row, key in enumerate(display_list):
            data = self.catalog[key]
            lang_name = data.get("language", {}).get("name_english", "Unknown")
            lang_code = data.get("language", {}).get("code", "")
            quality = data.get("quality", "medium")
            speakers = str(data.get("num_speakers", 1))

            self.table.setItem(row, 0, QTableWidgetItem(key))
            self.table.setItem(row, 1, QTableWidgetItem(f"{lang_name} ({lang_code})"))
            self.table.setItem(row, 2, QTableWidgetItem(quality))
            self.table.setItem(row, 3, QTableWidgetItem(speakers))

            if key in installed_keys:
                lbl_done = CaptionLabel("✓ Installed")
                lbl_done.setStyleSheet("color: #a6e3a1; font-weight: bold;")
                lbl_done.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setCellWidget(row, 4, lbl_done)
            else:
                btn_dl = PushButton(FluentIcon.DOWN, "Install")
                btn_dl.clicked.connect(lambda _, k=key: self._start_download(k))
                self.table.setCellWidget(row, 4, btn_dl)

    def _start_download(self, voice_key: str):
        if self.download_worker and self.download_worker.isRunning():
            InfoBar.warning(title="Busy", content="A download is already in progress.", parent=self)
            return

        self.progress_bar.setVisible(True)
        self.lbl_status.setVisible(True)
        self.progress_bar.setValue(0)
        self.lbl_status.setText(f"Downloading {voice_key}...")

        self.download_worker = DownloadVoiceWorker(voice_key, self)
        self.download_worker.progress.connect(self._on_download_progress)
        self.download_worker.finished.connect(self._on_download_finished)
        self.download_worker.error.connect(self._on_download_error)
        self.download_worker.start()

    def _on_download_progress(self, phase: str, cur: int, tot: int):
        if tot > 0:
            pct = int((cur / tot) * 100)
            self.progress_bar.setValue(pct)
            mb_c = cur / (1024 * 1024)
            mb_t = tot / (1024 * 1024)
            self.lbl_status.setText(f"Downloading {phase}: {mb_c:.1f} MB / {mb_t:.1f} MB ({pct}%)")

    def _on_download_finished(self, voice_key: str):
        self.progress_bar.setVisible(False)
        self.lbl_status.setVisible(False)
        self._populate_table()
        self.voice_installed.emit(voice_key)
        InfoBar.success(title="Voice Installed", content=f"Voice '{voice_key}' ready to use!", parent=self)

    def _on_download_error(self, err: str):
        self.progress_bar.setVisible(False)
        self.lbl_status.setVisible(False)
        InfoBar.error(title="Download Error", content=err, parent=self)
