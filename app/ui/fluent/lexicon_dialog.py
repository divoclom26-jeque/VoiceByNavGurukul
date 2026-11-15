import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
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
    CheckBox,
    ComboBox,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    SearchLineEdit,
    SubtitleLabel,
    TableWidget,
    TransparentToolButton,
)

from app.core.lexicon import LexiconManager
from app.tts import PiperTTSEngine, list_local_voices
from app.utils.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)


class LexiconDialog(QDialog):
    """Modern Fluent Dialog for managing phonetic word pronunciation dictionaries."""

    rules_updated = Signal()

    def __init__(self, parent: Optional[QWidget] = None, project_dir: Optional[Path] = None):
        super().__init__(parent)
        self.setWindowTitle("Pronunciation & Phonetic Dictionary")
        self.resize(780, 560)
        self.setMinimumSize(640, 460)

        self.project_dir = Path(project_dir) if project_dir else None
        self._setup_ui()
        self._load_table()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(14)

        # 1. Header
        header_layout = QVBoxLayout()
        header_layout.setSpacing(2)
        lbl_head = SubtitleLabel("📖 Pronunciation & Phonetic Dictionary", self)
        lbl_sub = CaptionLabel(
            "Define how specific names, technical acronyms, or non-standard words are spoken by the AI voice.",
            self,
        )
        header_layout.addWidget(lbl_head)
        header_layout.addWidget(lbl_sub)
        main_layout.addLayout(header_layout)

        # 2. Add Rule Card
        add_card = CardWidget(self)
        add_layout = QVBoxLayout(add_card)
        add_layout.setContentsMargins(16, 14, 16, 14)
        add_layout.setSpacing(10)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        self.txt_word = LineEdit(self)
        self.txt_word.setPlaceholderText("Word or Term (e.g. NavGurukul, SQL)")
        self.txt_replacement = LineEdit(self)
        self.txt_replacement.setPlaceholderText("Pronunciation / Spoken As (e.g. नवगुरुकुल, सीक्वेल)")
        row1.addWidget(self.txt_word, stretch=1)
        row1.addWidget(self.txt_replacement, stretch=1)
        add_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(12)
        self.chk_whole_word = CheckBox("Whole word only", self)
        self.chk_whole_word.setChecked(True)
        self.chk_case = CheckBox("Case sensitive", self)
        self.chk_case.setChecked(False)

        self.combo_scope = ComboBox(self)
        self.combo_scope.addItem("Global (All Projects)", userData="global")
        if self.project_dir:
            self.combo_scope.addItem(f"Project Only ({self.project_dir.name})", userData="project")

        self.btn_add = PrimaryPushButton(FluentIcon.ADD, "Add Rule", self)
        self.btn_add.setFixedHeight(34)
        self.btn_add.clicked.connect(self._add_rule)

        row2.addWidget(self.chk_whole_word)
        row2.addWidget(self.chk_case)
        row2.addWidget(self.combo_scope)
        row2.addStretch()
        row2.addWidget(self.btn_add)
        add_layout.addLayout(row2)

        main_layout.addWidget(add_card)

        # 3. Table Card
        table_card = CardWidget(self)
        t_layout = QVBoxLayout(table_card)
        t_layout.setContentsMargins(16, 14, 16, 14)
        t_layout.setSpacing(10)

        t_header = QHBoxLayout()
        t_header.addWidget(BodyLabel("Active Pronunciation Rules:", self))
        t_header.addStretch()
        self.search_bar = SearchLineEdit(self)
        self.search_bar.setPlaceholderText("Search dictionary...")
        self.search_bar.setFixedWidth(220)
        self.search_bar.textChanged.connect(self._load_table)
        t_header.addWidget(self.search_bar)
        t_layout.addLayout(t_header)

        self.table = TableWidget(self)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Word / Term",
            "Spoken As",
            "Scope",
            "Match",
            "Case",
            "Action",
        ])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(TableWidget.EditTrigger.NoEditTriggers)

        t_layout.addWidget(self.table, stretch=1)
        main_layout.addWidget(table_card, stretch=1)

        # 4. Footer
        footer = QHBoxLayout()
        footer.addStretch()
        self.btn_close = PushButton("Close", self)
        self.btn_close.clicked.connect(self.accept)
        footer.addWidget(self.btn_close)
        main_layout.addLayout(footer)

    def _load_table(self):
        query = self.search_bar.text().strip().lower()
        global_entries = LexiconManager.load_global_lexicon()
        proj_entries = LexiconManager.load_project_lexicon(self.project_dir) if self.project_dir else {}

        all_rules = []
        for w, d in global_entries.items():
            if not query or query in w.lower() or query in d.get("replacement", "").lower():
                all_rules.append((w, d, "Global", True))

        for w, d in proj_entries.items():
            if not query or query in w.lower() or query in d.get("replacement", "").lower():
                all_rules.append((w, d, "Project", False))

        self.table.setRowCount(len(all_rules))

        for row, (word, data, scope_label, is_glob) in enumerate(all_rules):
            # 0: Word
            self.table.setItem(row, 0, QTableWidgetItem(word))
            # 1: Replacement
            self.table.setItem(row, 1, QTableWidgetItem(data.get("replacement", "")))
            # 2: Scope
            item_scope = QTableWidgetItem(scope_label)
            item_scope.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, item_scope)
            # 3: Whole word
            ww_str = "Whole Word" if data.get("whole_word", True) else "Substring"
            item_ww = QTableWidgetItem(ww_str)
            item_ww.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, item_ww)
            # 4: Case
            case_str = "Match Case" if data.get("case_sensitive", False) else "Any Case"
            item_case = QTableWidgetItem(case_str)
            item_case.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, item_case)

            # 5: Action buttons
            action_w = QWidget()
            a_layout = QHBoxLayout(action_w)
            a_layout.setContentsMargins(4, 2, 4, 2)
            a_layout.setSpacing(6)

            # Preview pronunciation speech button
            btn_play = TransparentToolButton(FluentIcon.PLAY, action_w)
            btn_play.setToolTip(f"Preview pronunciation of '{word}'")
            btn_play.clicked.connect(lambda _, r=data.get("replacement", ""): self._preview_speech(r))
            a_layout.addWidget(btn_play)

            # Delete button
            btn_del = TransparentToolButton(FluentIcon.DELETE, action_w)
            btn_del.setToolTip(f"Delete rule '{word}'")
            btn_del.clicked.connect(lambda _, w=word, g=is_glob: self._delete_rule(w, g))
            a_layout.addWidget(btn_del)

            self.table.setCellWidget(row, 5, action_w)

    def _add_rule(self):
        word = self.txt_word.text().strip()
        replacement = self.txt_replacement.text().strip()
        if not word or not replacement:
            InfoBar.warning(
                title="Incomplete Input",
                content="Please provide both Word and Replacement pronunciation.",
                parent=self,
            )
            return

        is_global = (self.combo_scope.currentData() == "global")
        whole_word = self.chk_whole_word.isChecked()
        case_sensitive = self.chk_case.isChecked()

        try:
            LexiconManager.add_entry(
                word=word,
                replacement=replacement,
                whole_word=whole_word,
                case_sensitive=case_sensitive,
                is_global=is_global,
                project_dir=self.project_dir,
            )
            self.txt_word.clear()
            self.txt_replacement.clear()
            self._load_table()
            self.rules_updated.emit()
            InfoBar.success(
                title="Rule Saved",
                content=f"'{word}' will now be spoken as '{replacement}'",
                parent=self,
                position=InfoBarPosition.TOP,
            )
        except Exception as e:
            InfoBar.error(title="Save Error", content=str(e), parent=self)

    def _delete_rule(self, word: str, is_global: bool):
        LexiconManager.remove_entry(word, is_global=is_global, project_dir=self.project_dir)
        self._load_table()
        self.rules_updated.emit()
        InfoBar.info(
            title="Rule Deleted",
            content=f"Removed pronunciation rule for '{word}'",
            parent=self,
            position=InfoBarPosition.TOP,
        )

    def _preview_speech(self, text: str):
        voices = list_local_voices()
        if not voices:
            InfoBar.warning(title="No Voice", content="No local voice model available to preview.", parent=self)
            return

        # Pick Hindi voice if text has Devanagari, else first voice
        voice_cfg = voices[0]
        has_devanagari = any("\u0900" <= ch <= "\u097f" for ch in text)
        for v in voices:
            if has_devanagari and v.get("language", "").startswith("hi"):
                voice_cfg = v
                break

        test_dir = PROJECT_ROOT / "projects" / "_preview"
        test_dir.mkdir(parents=True, exist_ok=True)
        preview_wav = test_dir / "lexicon_preview.wav"

        try:
            engine = PiperTTSEngine()
            engine.synthesize_to_wav(text, preview_wav, voice_cfg)

            # Play using Qt Multimedia
            from PySide6.QtCore import QUrl
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

            if not hasattr(self, "_preview_player"):
                self._preview_player = QMediaPlayer(self)
                self._preview_output = QAudioOutput(self)
                self._preview_player.setAudioOutput(self._preview_output)

            self._preview_player.setSource(QUrl.fromLocalFile(str(preview_wav)))
            self._preview_player.play()
        except Exception as e:
            logger.error("Preview speech error: %s", e)
            InfoBar.error(title="Preview Error", content=str(e), parent=self)
