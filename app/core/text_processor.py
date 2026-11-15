from pathlib import Path
import re
from typing import Dict, List, Optional
try:
    from num2words import num2words
except ImportError:
    num2words = None


class TextProcessor:
    """Pre-processing, cleaning, normalization, and chunking pipeline for TTS."""

    ABBREVIATIONS: Dict[str, str] = {
        r"\bDr\.\s*": "Doctor ",
        r"\bMr\.\s*": "Mister ",
        r"\bMrs\.\s*": "Missus ",
        r"\bMs\.\s*": "Miss ",
        r"\bProf\.\s*": "Professor ",
        r"\bSr\.\s*": "Senior ",
        r"\bJr\.\s*": "Junior ",
        r"\bvs\.\s*|\bvs\b": "versus ",
        r"\betc\.\s*": "et cetera ",
        r"\be\.g\.,?\s*": "for example, ",
        r"\bi\.e\.,?\s*": "that is, ",
        r"\bapprox\.\s*": "approximately ",
        r"\bmin\.\s*": "minutes ",
        r"\bsec\.\s*": "seconds ",
        r"\bhrs?\.\s*": "hours ",
        r"\bdept\.\s*": "department ",
        r"\buniv\.\s*": "university ",
        r"\bGov\.\s*": "Governor ",
        r"\bGen\.\s*": "General ",
        r"\bCol\.\s*": "Colonel ",
    }

    CURRENCY_MAP = [
        (re.compile(r"\$(\d+(?:\.\d{1,2})?)"), r"\1 dollars"),
        (re.compile(r"₹(\d+(?:\.\d{1,2})?)"), r"\1 rupees"),
        (re.compile(r"Rs\.?\s*(\d+(?:\.\d{1,2})?)", re.IGNORECASE), r"\1 rupees"),
        (re.compile(r"€(\d+(?:\.\d{1,2})?)"), r"\1 euros"),
        (re.compile(r"£(\d+(?:\.\d{1,2})?)"), r"\1 pounds"),
    ]

    @classmethod
    def clean_markdown(cls, text: str) -> str:
        """Strip markdown markers, code blocks, images, and formatting."""
        # Remove code blocks
        text = re.sub(r"```[\s\S]*?```", "", text)
        text = re.sub(r"`([^`]+)`", r"\1", text)

        # Remove image markdown: ![alt](url)
        text = re.sub(r"!\[.*?\]\(.*?\)", "", text)

        # Convert links [text](url) -> text
        text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)

        # Remove raw URLs
        text = re.sub(r"https?://\S+|www\.\S+", "", text)

        lines = []
        for line in text.splitlines():
            stripped = line.strip()

            # Remove markdown divider lines
            if stripped in ("---", "***", "___", "- - -", "* * *"):
                continue

            # Strip heading markdown (#, ##, ###...)
            line = re.sub(r"^#{1,6}\s*", "", line)

            # Strip blockquotes (> quote)
            line = re.sub(r"^>\s*", "", line)

            # Strip unordered lists (* item, - item, + item)
            line = re.sub(r"^[\*\-\+]\s+", "", line)

            # Strip ordered lists (1. item, 2. item)
            line = re.sub(r"^\d+\.\s+", "", line)

            # Strip bold and italics (*bold*, **bold**, _italic_, __italic__, ~~strike~~)
            line = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", line)
            line = re.sub(r"_{1,3}(.*?)_{1,3}", r"\1", line)
            line = re.sub(r"~{2}(.*?)~{2}", r"\1", line)

            lines.append(line)

        cleaned = "\n".join(lines)
        return cleaned

    @classmethod
    def normalize_abbreviations(cls, text: str) -> str:
        """Expand common abbreviations into full pronounceable words."""
        for pattern, replacement in cls.ABBREVIATIONS.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    @classmethod
    def normalize_symbols(cls, text: str) -> str:
        """Convert symbols, currencies, and percentages into spoken words."""
        # Currencies
        for pattern, replacement in cls.CURRENCY_MAP:
            text = pattern.sub(replacement, text)

        # Percentages: 25% -> 25 percent
        text = re.sub(r"(\d+)\s*%", r"\1 percent", text)

        # Symbols: & -> and, @ -> at, #1 -> number 1
        text = re.sub(r"\s+&\s+", " and ", text)
        text = re.sub(r"\s*@\s*", " at ", text)
        text = re.sub(r"#(\d+)", r"number \1", text)

        # Remove non-pronounceable stray symbols
        text = re.sub(r"[~^|{}\[\]\\<>]", " ", text)

        # Normalize multiple spaces, tabs, and newlines
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    @classmethod
    def convert_numbers(cls, text: str, lang: str = "en") -> str:
        """Optional: Convert standalone numbers to words using num2words."""
        if not num2words:
            return text

        def replace_num(match):
            val = match.group(0)
            try:
                # If integer
                if "." in val:
                    return num2words(float(val), lang=lang)
                return num2words(int(val), lang=lang)
            except Exception:
                return val

        # Match numbers separated by word boundaries
        return re.sub(r"\b\d+(?:\.\d+)?\b", replace_num, text)

    @classmethod
    def clean_text_for_speech(
        cls,
        text: str,
        expand_abbreviations: bool = True,
        convert_numbers_to_words: bool = False,
        lang: str = "en",
        project_dir: Optional[Path] = None,
        apply_lexicon: bool = True,
    ) -> str:
        """Full text pre-processing pipeline for speech synthesis."""
        if apply_lexicon:
            from app.core.lexicon import LexiconManager
            text = LexiconManager.apply_lexicon(text, project_dir=project_dir)

        cleaned = cls.clean_markdown(text)
        if expand_abbreviations:
            cleaned = cls.normalize_abbreviations(cleaned)
        cleaned = cls.normalize_symbols(cleaned)

        if convert_numbers_to_words:
            cleaned = cls.convert_numbers(cleaned, lang=lang)

        return cleaned

    @classmethod
    def apply_clause_phrasing(cls, text: str, lang: str = "en") -> str:
        """Insert natural clause breath markers before Hindi/English conjunctions in long sentences."""
        stripped = text.strip()
        if len(stripped) < 45:
            return text

        # Hindi conjunctions: कि, तथा, लेकिन, परंतु, क्योंकि, इसलिए, जिससे, ताकि, यद्यपि
        hindi_conjunctions = r"कि|तथा|लेकिन|परंतु|क्योंकि|इसलिए|जिससे|ताकि|यद्यपि"
        pattern_hi = re.compile(rf"(?<![,;—।\.\!\?])\s+({hindi_conjunctions})\s+", re.UNICODE)
        text = pattern_hi.sub(r", \1 ", text)

        # In Hindi: also split long clauses on 'और' if sentence has 12+ words
        words = text.split()
        if len(words) >= 12 and "और" in words:
            pattern_aur = re.compile(r"(?<![,;—।\.\!\?])\s+(और)\s+", re.UNICODE)
            text = pattern_aur.sub(r", और ", text)

        return text

    @classmethod
    def split_into_blocks(
        cls,
        text: str,
        max_chars: int = 280,
        expand_abbreviations: bool = True,
        lang: str = "en",
        project_dir: Optional[Path] = None,
        apply_lexicon: bool = True,
    ) -> List[str]:
        """Split long text into safe, pronounceable sentence/clause blocks.
        
        Preserves natural sentence boundaries (English . ! ?, Hindi ।, etc.).
        If a sentence exceeds max_chars, it splits on commas/semicolons, then whitespace.
        """
        cleaned = cls.clean_text_for_speech(
            text,
            expand_abbreviations=expand_abbreviations,
            lang=lang,
            project_dir=project_dir,
            apply_lexicon=apply_lexicon,
        )

        paragraphs = [p.strip() for p in cleaned.split("\n\n") if p.strip()]
        blocks: List[str] = []

        # Matches sentences ending with . ! ? or Devanagari danda ।
        sentence_regex = re.compile(r".+?(?:[\.\!\?।]+(?=\s+|$)|$)", re.DOTALL)

        for p in paragraphs:
            # Break paragraph into constituent sentences
            raw_sentences = [s.strip() for s in sentence_regex.findall(p) if s.strip()]
            for s in raw_sentences:
                # Apply clause phrasing on long sentences
                s = cls.apply_clause_phrasing(s, lang=lang)

                # If sentence fits within max_chars, keep as individual sentence block
                if len(s) <= max_chars:
                    blocks.append(s)
                else:
                    # If a single sentence exceeds max_chars, split on clauses (; , —)
                    clause_regex = re.compile(r".+?(?:[;,—\-]+(?=\s+|$)|$)", re.DOTALL)
                    clauses = [c.strip() for c in clause_regex.findall(s) if c.strip()]
                    clause_acc = ""

                    for c in clauses:
                        if len(c) > max_chars:
                            # Still too long: split on word boundaries
                            if clause_acc:
                                blocks.append(clause_acc)
                                clause_acc = ""
                            words = c.split()
                            word_acc = ""
                            for w in words:
                                if len(word_acc) + len(w) + 1 <= max_chars:
                                    word_acc = f"{word_acc} {w}".strip()
                                else:
                                    if word_acc:
                                        blocks.append(word_acc)
                                    word_acc = w
                            if word_acc:
                                blocks.append(word_acc)
                        else:
                            if len(clause_acc) + len(c) + 1 <= max_chars:
                                clause_acc = f"{clause_acc} {c}".strip()
                            else:
                                if clause_acc:
                                    blocks.append(clause_acc)
                                clause_acc = c
                    if clause_acc:
                        blocks.append(clause_acc)

        # Filter out any empty blocks or pure whitespace
        return [b for b in blocks if any(char.isalnum() for char in b)]
