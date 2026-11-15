import logging
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.tts.voice_manager import (
    get_remote_voices_catalog,
    list_local_voices,
)
from app.ui.workers import DownloadVoiceWorker

logger = logging.getLogger(__name__)


class VoiceGalleryWidget(QFrame):
    """Voice browser & model downloader for Hugging Face Piper models."""

    voice_installed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setProperty("class", "card-panel")

        self.catalog: Dict[str, Any] = {}
        self.download_worker: Optional[DownloadVoiceWorker] = None

        self._setup_ui()
        self._load_catalog_async()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Header
        top_bar = QHBoxLayout()
        lbl_heading = QLabel("Voice Model Gallery")
        lbl_heading.setProperty("class", "heading")
        top_bar.addWidget(lbl_heading)
        top_bar.addStretch()

        self.btn_refresh = QPushButton("🔄 Refresh Catalog")
        self.btn_refresh.setProperty("class", "btn-secondary")
        self.btn_refresh.clicked.connect(self._refresh_catalog)
        top_bar.addWidget(self.btn_refresh)
        layout.addLayout(top_bar)

        # Search Bar
        search_row = QHBoxLayout()
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Search by voice name or language (e.g. hindi, en_US, female)...")
        self.txt_search.textChanged.connect(self._filter_table)
        search_row.addWidget(self.txt_search)
        layout.addLayout(search_row)

        # Download status bar (hidden by default)
        self.dl_status_frame = QFrame()
        dl_layout = QHBoxLayout(self.dl_status_frame)
        dl_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_dl_status = QLabel("Downloading...")
        self.lbl_dl_status.setStyleSheet("color: #89b4fa; font-weight: 500;")
        self.dl_progress = QProgressBar()
        self.dl_progress.setRange(0, 100)
        dl_layout.addWidget(self.lbl_dl_status)
        dl_layout.addWidget(self.dl_progress, stretch=1)
        self.dl_status_frame.setVisible(False)
        layout.addWidget(self.dl_status_frame)

        # Table of Voices
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "Voice Key", "Language", "Quality", "Speakers", "Size (MB)", "Action"
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        layout.addWidget(self.table, stretch=1)

    def _load_catalog_async(self):
        try:
            self.catalog = get_remote_voices_catalog()
            self._populate_table()
        except Exception as e:
            logger.error(f"Failed to load remote catalog: {e}")

    def _refresh_catalog(self):
        try:
            self.catalog = get_remote_voices_catalog(force_refresh=True)
            self._populate_table()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to refresh catalog: {e}")

    def _populate_table(self):
        installed_keys = {v["key"] for v in list_local_voices()}
        query = self.txt_search.text().lower().strip()

        matching_keys = []
        for key, data in self.catalog.items():
            lang_code = data.get("language", {}).get("code", "")
            lang_name = data.get("language", {}).get("name_english", "")
            if (
                not query
                or query in key.lower()
                or query in lang_code.lower()
                or query in lang_name.lower()
            ):
                matching_keys.append(key)

        # Prioritize installed voices first, then Hindi and English
        def sort_key(k):
            is_installed = k in installed_keys
            is_hindi = k.startswith("hi")
            is_en = k.startswith("en")
            return (not is_installed, not is_hindi, not is_en, k)

        matching_keys.sort(key=sort_key)

        self.table.setRowCount(len(matching_keys))
        for row, key in enumerate(matching_keys):
            data = self.catalog[key]
            lang_name = data.get("language", {}).get("name_english", "Unknown")
            lang_code = data.get("language", {}).get("code", "")
            quality = data.get("quality", "medium")
            speakers = str(data.get("num_speakers", 1))

            # Approximate size
            size_bytes = 0
            for f_info in data.get("files", {}).values():
                size_bytes += f_info.get("size_bytes", 0)
            size_mb = f"{size_bytes / (1024 * 1024):.1f}" if size_bytes else "~60.0"

            self.table.setItem(row, 0, QTableWidgetItem(key))
            self.table.setItem(row, 1, QTableWidgetItem(f"{lang_name} ({lang_code})"))
            self.table.setItem(row, 2, QTableWidgetItem(quality))
            self.table.setItem(row, 3, QTableWidgetItem(speakers))
            self.table.setItem(row, 4, QTableWidgetItem(size_mb))

            if key in installed_keys:
                lbl_installed = QLabel("✓ Installed")
                lbl_installed.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl_installed.setStyleSheet("color: #a6e3a1; font-weight: bold;")
                self.table.setCellWidget(row, 5, lbl_installed)
            else:
                btn_dl = QPushButton("⬇ Download")
                btn_dl.setProperty("class", "btn-secondary")
                btn_dl.clicked.connect(lambda _, k=key: self._start_download(k))
                self.table.setCellWidget(row, 5, btn_dl)

    def _filter_table(self):
        self._populate_table()

    def _start_download(self, voice_key: str):
        if self.download_worker and self.download_worker.isRunning():
            QMessageBox.information(self, "Download in Progress", "Please wait for current download to complete.")
            return

        self.dl_status_frame.setVisible(True)
        self.lbl_dl_status.setText(f"Downloading {voice_key}...")
        self.dl_progress.setValue(0)

        self.download_worker = DownloadVoiceWorker(voice_key, self)
        self.download_worker.progress.connect(self._on_download_progress)
        self.download_worker.finished.connect(self._on_download_finished)
        self.download_worker.error.connect(self._on_download_error)
        self.download_worker.start()

    def _on_download_progress(self, phase: str, cur: int, tot: int):
        if tot > 0:
            percent = int((cur / tot) * 100)
            self.dl_progress.setValue(percent)
            mb_cur = cur / (1024 * 1024)
            mb_tot = tot / (1024 * 1024)
            self.lbl_dl_status.setText(f"Downloading {phase}: {mb_cur:.1f} MB / {mb_tot:.1f} MB ({percent}%)")

    def _on_download_finished(self, voice_key: str):
        self.dl_status_frame.setVisible(False)
        self._populate_table()
        self.voice_installed.emit(voice_key)
        QMessageBox.information(self, "Download Complete", f"Voice '{voice_key}' installed successfully!")

    def _on_download_error(self, err_msg: str):
        self.dl_status_frame.setVisible(False)
        QMessageBox.critical(self, "Download Error", f"Failed to download voice: {err_msg}")
