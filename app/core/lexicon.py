import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from app.utils.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)

GLOBAL_LEXICON_PATH = PROJECT_ROOT / "models" / "lexicon.json"

DEFAULT_GLOBAL_ENTRIES: Dict[str, Dict[str, Any]] = {
    "NavGurukul": {
        "replacement": "नवगुरुकुल",
        "whole_word": True,
        "case_sensitive": False,
        "notes": "Non-profit organization name",
    },
    "SQL": {
        "replacement": "सीक्वेल",
        "whole_word": True,
        "case_sensitive": True,
        "notes": "Structured Query Language",
    },
    "PyTorch": {
        "replacement": "पाई-टॉर्च",
        "whole_word": True,
        "case_sensitive": False,
        "notes": "Machine learning framework",
    },
    "FastAPI": {
        "replacement": "फास्ट एपीआई",
        "whole_word": True,
        "case_sensitive": False,
        "notes": "Python web framework",
    },
    "AI": {
        "replacement": "ए-आई",
        "whole_word": True,
        "case_sensitive": True,
        "notes": "Artificial Intelligence",
    },
}


class LexiconManager:
    """Manages phonetic word substitution dictionaries (Global and Project-level)."""

    @classmethod
    def _ensure_global_file(cls) -> Path:
        GLOBAL_LEXICON_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not GLOBAL_LEXICON_PATH.is_file():
            with open(GLOBAL_LEXICON_PATH, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_GLOBAL_ENTRIES, f, ensure_ascii=False, indent=2)
        return GLOBAL_LEXICON_PATH

    @classmethod
    def load_global_lexicon(cls) -> Dict[str, Dict[str, Any]]:
        cls._ensure_global_file()
        try:
            with open(GLOBAL_LEXICON_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Failed to load global lexicon: %s", e)
            return dict(DEFAULT_GLOBAL_ENTRIES)

    @classmethod
    def save_global_lexicon(cls, entries: Dict[str, Dict[str, Any]]):
        cls._ensure_global_file()
        with open(GLOBAL_LEXICON_PATH, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)

    @classmethod
    def load_project_lexicon(cls, project_dir: Path) -> Dict[str, Dict[str, Any]]:
        p_file = Path(project_dir) / "lexicon.json"
        if not p_file.is_file():
            return {}
        try:
            with open(p_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Failed to load project lexicon from %s: %s", p_file, e)
            return {}

    @classmethod
    def save_project_lexicon(cls, project_dir: Path, entries: Dict[str, Dict[str, Any]]):
        p_dir = Path(project_dir)
        p_dir.mkdir(parents=True, exist_ok=True)
        p_file = p_dir / "lexicon.json"
        with open(p_file, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)

    @classmethod
    def get_combined_lexicon(cls, project_dir: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
        """Combine global lexicon with project-level overrides."""
        combined = cls.load_global_lexicon()
        if project_dir and Path(project_dir).is_dir():
            proj_entries = cls.load_project_lexicon(project_dir)
            combined.update(proj_entries)
        return combined

    @classmethod
    def add_entry(
        cls,
        word: str,
        replacement: str,
        whole_word: bool = True,
        case_sensitive: bool = False,
        notes: str = "",
        is_global: bool = True,
        project_dir: Optional[Path] = None,
    ):
        word = word.strip()
        replacement = replacement.strip()
        if not word or not replacement:
            raise ValueError("Word and replacement cannot be empty.")

        entry = {
            "replacement": replacement,
            "whole_word": bool(whole_word),
            "case_sensitive": bool(case_sensitive),
            "notes": notes.strip(),
        }

        if is_global or not project_dir:
            entries = cls.load_global_lexicon()
            entries[word] = entry
            cls.save_global_lexicon(entries)
        else:
            entries = cls.load_project_lexicon(project_dir)
            entries[word] = entry
            cls.save_project_lexicon(project_dir, entries)

    @classmethod
    def remove_entry(
        cls,
        word: str,
        is_global: bool = True,
        project_dir: Optional[Path] = None,
    ) -> bool:
        word = word.strip()
        if is_global or not project_dir:
            entries = cls.load_global_lexicon()
            if word in entries:
                del entries[word]
                cls.save_global_lexicon(entries)
                return True
        else:
            entries = cls.load_project_lexicon(project_dir)
            if word in entries:
                del entries[word]
                cls.save_project_lexicon(project_dir, entries)
                return True
        return False

    @classmethod
    def apply_lexicon(cls, text: str, project_dir: Optional[Path] = None) -> str:
        """Apply all phonetic and pronunciation substitutions to the given text."""
        if not text:
            return ""

        lexicon = cls.get_combined_lexicon(project_dir)
        if not lexicon:
            return text

        # Sort entries by length descending so longer phrases match first
        sorted_keys = sorted(lexicon.keys(), key=len, reverse=True)

        for word in sorted_keys:
            data = lexicon[word]
            replacement = data.get("replacement", "")
            if not replacement:
                continue

            whole_word = data.get("whole_word", True)
            case_sensitive = data.get("case_sensitive", False)
            flags = 0 if case_sensitive else re.IGNORECASE

            if whole_word:
                pattern = r"(?<!\w)" + re.escape(word) + r"(?!\w)"
            else:
                pattern = re.escape(word)

            text = re.sub(pattern, replacement, text, flags=flags)

        # Also normalize custom SSML pause tags: <break time="500ms"/> or [pause: 500ms]
        text = re.sub(r'\s*<\s*break\s+time\s*=\s*["\']?(\d+)(?:ms|s)?["\']?\s*/?>\s*', r" ... ", text, flags=re.IGNORECASE)
        text = re.sub(r'\s*\[\s*(?:pause|break)\s*:\s*(\d+)(?:ms|s)?\s*\]\s*', r" ... ", text, flags=re.IGNORECASE)
        text = re.sub(r"[ \t]+", " ", text).strip()

        return text
