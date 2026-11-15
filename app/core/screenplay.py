import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Predefined curated Fluent accent colors for character badges
CHARACTER_COLORS = [
    "#0078D4",  # Fluent Blue (e.g. Narrator / Protagonist)
    "#E3008C",  # Fluent Magenta / Rose (e.g. Female Lead)
    "#107C41",  # Fluent Green (e.g. Male Co-Star)
    "#8764B8",  # Fluent Purple (e.g. Royalty / Mystery)
    "#D83B01",  # Fluent Orange / Amber (e.g. Comic / Energetic)
    "#008272",  # Fluent Teal (e.g. Mentor / Calm)
    "#4F46E5",  # Fluent Indigo (e.g. Supporting character)
    "#C239B3",  # Fluent Orchid
]

# Common female keywords to intelligently suggest female voice models
FEMALE_KEYWORDS = {
    "rani", "priya", "priyamvada", "anita", "pooja", "neha", "sunita", "radha",
    "sita", "gita", "mary", "sarah", "emma", "alice", "woman", "girl", "queen",
    "mother", "mom", "sister", "daughter", "lady", "female", "she", "her",
}

# Common male keywords to intelligently suggest male voice models
MALE_KEYWORDS = {
    "vikram", "pratham", "rahul", "amit", "rohit", "raj", "arjun", "karan",
    "ram", "krishna", "john", "michael", "david", "man", "boy", "king",
    "father", "dad", "brother", "son", "sir", "male", "he", "his",
}


class ScreenplayParser:
    """Robust parser for screenplay, multi-character dialogue, and script speaker attribution."""

    # Matches:
    # 1. [Speaker Name]: dialogue
    # 2. (Speaker Name): dialogue
    # 3. <Speaker Name>: dialogue
    # 4. Speaker Name: dialogue
    SPEAKER_PATTERN = re.compile(
        r"^(?:\[(?P<bracket_spk>[^\]\:\n]+)\]|\((?P<paren_spk>[^\)\:\n]+)\)|<(?P<angle_spk>[^>\:\n]+)>|(?P<plain_spk>[A-Za-z\u0900-\u097f][A-Za-z0-9_\u0900-\u097f\s]{1,30}))\s*:\s*(?P<dialogue>.*)$",
        re.MULTILINE,
    )

    @classmethod
    def has_screenplay_tags(cls, text: str) -> bool:
        """Check if text contains explicit speaker / screenplay dialogue tags."""
        if not text:
            return False
        # Look for at least one bracket speaker tag [Name]: or plain Name: at start of line
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if cls.extract_speaker_from_line(line) is not None:
                return True
        return False

    @classmethod
    def extract_speaker_from_line(cls, line: str) -> Optional[Tuple[str, str]]:
        """Extract (speaker_name, dialogue_text) from a single line if present."""
        line = line.strip()
        if not line:
            return None

        # 1. Bracket format: [Vikram]: Hello or [Vikram] Hello
        m_bracket = re.match(r"^\[([^\]]+)\]\s*:?\s*(.*)$", line)
        if m_bracket:
            spk = m_bracket.group(1).strip()
            dial = m_bracket.group(2).strip()
            if spk and len(spk) <= 35:
                return spk, dial

        # 2. Angle format: <Vikram>: Hello
        m_angle = re.match(r"^<([^>]+)>\s*:?\s*(.*)$", line)
        if m_angle:
            spk = m_angle.group(1).strip()
            dial = m_angle.group(2).strip()
            if spk and len(spk) <= 35:
                return spk, dial

        # 3. Plain format: Speaker: Dialogue (avoid matching URLs like http:// or numbers like 10:30)
        m_plain = re.match(r"^([A-Za-z\u0900-\u097f][A-Za-z0-9_\u0900-\u097f\s]{1,25}):\s+(.*)$", line)
        if m_plain:
            spk = m_plain.group(1).strip()
            dial = m_plain.group(2).strip()
            # Guard against common false positives (e.g. Note:, Example:, https:)
            if spk.lower() not in {"http", "https", "note", "example", "url", "ps", "tips"}:
                return spk, dial

        return None

    @classmethod
    def parse_screenplay(cls, text: str) -> List[Dict[str, str]]:
        """Parse raw screenplay script into structured dialogue turns.
        
        Returns a list of dicts: [{'speaker': 'Vikram', 'text': '...'}, ...]
        Lines without a speaker tag continue under the currently active speaker
        (or 'Narrator' if at the beginning).
        """
        if not text:
            return []

        # Automatically insert newline before inline speaker tags e.g. "Hi. [Guest]: Hello."
        normalized = re.sub(r"(?<!^)(?<!\n)\s*(\[[^\]\n]+\]\s*:?)", r"\n\1", text)

        turns: List[Dict[str, str]] = []
        current_speaker = "Narrator"
        current_lines: List[str] = []

        for raw_line in normalized.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            extracted = cls.extract_speaker_from_line(line)
            if extracted:
                spk, dial = extracted
                # If we have accumulated text for previous speaker, flush it
                if current_lines:
                    turns.append({
                        "speaker": current_speaker,
                        "text": " ".join(current_lines).strip(),
                    })
                    current_lines = []

                current_speaker = spk
                if dial:
                    current_lines.append(dial)
            else:
                current_lines.append(line)

        if current_lines:
            turns.append({
                "speaker": current_speaker,
                "text": " ".join(current_lines).strip(),
            })

        return [t for t in turns if t["text"]]

    @classmethod
    def extract_characters(cls, text: str) -> List[str]:
        """Extract all unique character names in order of appearance."""
        turns = cls.parse_screenplay(text)
        seen = set()
        characters: List[str] = []
        for t in turns:
            spk = t["speaker"]
            if spk not in seen:
                seen.add(spk)
                characters.append(spk)
        return characters

    @classmethod
    def generate_character_palette(
        cls,
        characters: List[str],
        available_voices: List[Dict[str, Any]],
        default_voice_key: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Generate a color-coded voice assignment palette for each detected character.
        
        Attempts intelligent gender & language pairing:
        - Female names get female voice models
        - Male names get male voice models
        - Each character gets a distinct Fluent UI accent color
        """
        palette: Dict[str, Dict[str, Any]] = {}
        if not characters:
            return palette

        # Categorize available voices
        male_voices: List[Dict[str, Any]] = []
        female_voices: List[Dict[str, Any]] = []
        neutral_voices: List[Dict[str, Any]] = []

        for v in available_voices:
            v_name = v.get("name", "").lower()
            v_key = v.get("key", "").lower()
            if any(k in v_name or k in v_key for k in ("priyamvada", "female", "lessac", "woman", "girl")):
                female_voices.append(v)
            elif any(k in v_name or k in v_key for k in ("pratham", "male", "man", "boy", "ryan")):
                male_voices.append(v)
            else:
                neutral_voices.append(v)

        all_voices = available_voices or []
        fallback_key = default_voice_key or (all_voices[0]["key"] if all_voices else "")

        used_voice_keys: set = set()

        for idx, char_name in enumerate(characters):
            clean_name = char_name.lower().strip()
            assigned_color = CHARACTER_COLORS[idx % len(CHARACTER_COLORS)]

            # Check gender hint
            is_female = any(f in clean_name for f in FEMALE_KEYWORDS)
            is_male = any(m in clean_name for f in MALE_KEYWORDS for m in (f,))

            target_voice_key = ""
            gender_label = "neutral"

            if is_female and female_voices:
                # Prioritize voice with same language script if Indian/Hindi name
                is_indian_name = any(k in clean_name for k in ("rani", "priya", "priyamvada", "anita", "pooja", "radha", "sita", "gita"))
                sorted_fem = sorted(female_voices, key=lambda v: (0 if is_indian_name and v.get("key", "").startswith("hi") else 1))
                cand = next((v["key"] for v in sorted_fem if v["key"] not in used_voice_keys), sorted_fem[0]["key"])
                target_voice_key = cand
                gender_label = "female"
            elif is_male and male_voices:
                cand = next((v["key"] for v in male_voices if v["key"] not in used_voice_keys), male_voices[0]["key"])
                target_voice_key = cand
                gender_label = "male"
            else:
                # Cycle through voices to give different characters distinct voices
                if all_voices:
                    voice_idx = idx % len(all_voices)
                    target_voice_key = all_voices[voice_idx]["key"]
                else:
                    target_voice_key = fallback_key

            used_voice_keys.add(target_voice_key)

            palette[char_name] = {
                "voice_key": target_voice_key,
                "color": assigned_color,
                "gender": gender_label,
            }

        return palette
