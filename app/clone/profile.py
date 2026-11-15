from dataclasses import asdict, dataclass
import datetime
import json
import logging
from pathlib import Path
import re
import shutil
from typing import Any, Dict, List, Optional
import numpy as np

from app.clone.dsp import AudioDSP
from app.clone.speaker_encoder import SpeakerEncoder
from app.utils.paths import MODELS_DIR

logger = logging.getLogger(__name__)

CLONES_DIR = MODELS_DIR / "clones"


@dataclass
class CloneProfile:
    id: str
    name: str
    language: str
    created_at: str
    base_voice_key: str
    reference_audio: str  # Relative to clone directory
    embedding_file: str   # Relative to clone directory
    preview_audio: Optional[str] = None
    pitch_shift: float = 0.0
    speed_factor: float = 1.0
    spectral_envelope_file: Optional[str] = "spectral_envelope.npy"
    clones_dir_path: Optional[str] = None

    @property
    def clone_dir(self) -> Path:
        if self.clones_dir_path:
            return Path(self.clones_dir_path) / self.id
        return CLONES_DIR / self.id

    @property
    def full_reference_path(self) -> Path:
        return self.clone_dir / self.reference_audio

    @property
    def full_embedding_path(self) -> Path:
        return self.clone_dir / self.embedding_file

    @property
    def full_spectral_envelope_path(self) -> Path:
        filename = self.spectral_envelope_file or "spectral_envelope.npy"
        return self.clone_dir / filename

    @property
    def full_preview_path(self) -> Optional[Path]:
        return self.clone_dir / self.preview_audio if self.preview_audio else None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], clones_dir_path: Optional[str] = None) -> "CloneProfile":
        if "clones_dir_path" not in data and clones_dir_path:
            data["clones_dir_path"] = clones_dir_path
        if "spectral_envelope_file" not in data:
            data["spectral_envelope_file"] = "spectral_envelope.npy"
        return cls(**data)


class CloneManager:
    """Manages creation, loading, listing, and deletion of custom local cloned voice profiles."""

    def __init__(self, clones_dir: Optional[Path] = None):
        self.clones_dir = clones_dir or CLONES_DIR
        self.clones_dir.mkdir(parents=True, exist_ok=True)
        self.encoder = SpeakerEncoder()

    def list_clones(self) -> List[CloneProfile]:
        """List all installed local cloned voice profiles."""
        if not self.clones_dir.is_dir():
            return []

        profiles = []
        for p_dir in sorted(self.clones_dir.iterdir()):
            if not p_dir.is_dir():
                continue
            profile_json = p_dir / "profile.json"
            if profile_json.is_file():
                try:
                    data = json.loads(profile_json.read_text(encoding="utf-8"))
                    profiles.append(CloneProfile.from_dict(data, clones_dir_path=str(self.clones_dir)))
                except Exception as e:
                    logger.warning("Could not read clone profile %s: %s", profile_json, e)
        return profiles

    def get_clone(self, clone_id: str) -> Optional[CloneProfile]:
        """Retrieve a clone profile by ID."""
        p_dir = self.clones_dir / clone_id
        profile_json = p_dir / "profile.json"
        if profile_json.is_file():
            try:
                data = json.loads(profile_json.read_text(encoding="utf-8"))
                return CloneProfile.from_dict(data, clones_dir_path=str(self.clones_dir))
            except Exception as e:
                logger.error("Failed loading clone %s: %s", clone_id, e)
        return None

    def create_clone(
        self,
        name: str,
        reference_audio_path: Path,
        language: str = "hi_IN",
        base_voice_key: str = "hi_IN-pratham-medium",
        pitch_shift: float = 0.0,
    ) -> CloneProfile:
        """Create a new local voice clone from user reference audio."""
        name_clean = name.strip() or "My Cloned Voice"
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", name_clean.lower()).strip("_")
        clone_id = f"clone_{slug}_{int(datetime.datetime.now().timestamp()) % 100000}"

        target_dir = self.clones_dir / clone_id
        target_dir.mkdir(parents=True, exist_ok=True)

        ref_wav_name = "reference_sample.wav"
        target_ref_wav = target_dir / ref_wav_name

        # 1. Clean, highpass, denoise, and normalize reference audio
        clean_meta = AudioDSP.clean_voice_sample(
            input_path=reference_audio_path,
            output_path=target_ref_wav,
            target_sr=22050,
            min_duration_sec=2.0,
        )

        import soundfile as sf
        clean_data, clean_sr = sf.read(str(target_ref_wav), dtype="float32")

        # 2. Extract 256-D speaker embedding
        emb = self.encoder.extract_embedding_from_file(target_ref_wav)
        emb_file_name = "speaker_embedding.npy"
        target_emb_file = target_dir / emb_file_name
        np.save(str(target_emb_file), emb)

        # 3. Extract and persist vocal tract spectral envelope
        spec_env = AudioDSP.extract_spectral_envelope(clean_data, sr=clean_sr)
        spec_file_name = "spectral_envelope.npy"
        target_spec_file = target_dir / spec_file_name
        np.save(str(target_spec_file), spec_env)

        # 4. Measure natural pitch and compute auto pitch-shift if pitch_shift was not explicitly provided
        if abs(pitch_shift) < 0.05:
            user_f0 = AudioDSP.estimate_median_f0(clean_data, sr=clean_sr)
            base_f0_map = {
                "hi_IN-pratham-medium": 107.0,
                "hi_IN-priyamvada-medium": 220.0,
                "en_US-lessac-medium": 140.0,
                "en_US-ryan-medium": 115.0,
                "en_US-amy-medium": 215.0,
            }
            nominal_base_f0 = base_f0_map.get(base_voice_key, 120.0)
            pitch_shift = float(np.clip(round(12.0 * np.log2(user_f0 / nominal_base_f0), 1), -12.0, 12.0))
            logger.info("Auto-calculated pitch shift: %s semitones (User F0: %.1fHz, Base: %.1fHz)", pitch_shift, user_f0, nominal_base_f0)

        # 5. Create profile
        profile = CloneProfile(
            id=clone_id,
            name=name_clean,
            language=language,
            created_at=datetime.datetime.now().isoformat(),
            base_voice_key=base_voice_key,
            reference_audio=ref_wav_name,
            embedding_file=emb_file_name,
            preview_audio=None,
            pitch_shift=pitch_shift,
            spectral_envelope_file=spec_file_name,
            clones_dir_path=str(self.clones_dir),
        )

        profile_json = target_dir / "profile.json"
        profile_json.write_text(json.dumps(profile.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

        return profile

    def delete_clone(self, clone_id: str) -> bool:
        """Permanently delete a cloned voice profile."""
        p_dir = self.clones_dir / clone_id
        if p_dir.is_dir():
            shutil.rmtree(p_dir, ignore_errors=True)
            return True
        return False

    def load_embedding(self, clone_id: str) -> Optional[np.ndarray]:
        """Load the 256-D speaker embedding for a clone."""
        clone = self.get_clone(clone_id)
        if clone and clone.full_embedding_path.is_file():
            try:
                return np.load(str(clone.full_embedding_path))
            except Exception as e:
                logger.error("Failed loading embedding for %s: %s", clone_id, e)
        return None

    def load_spectral_envelope(self, clone_id: str) -> Optional[np.ndarray]:
        """Load the vocal tract spectral envelope for a clone, generating dynamically if missing."""
        import soundfile as sf
        clone = self.get_clone(clone_id)
        if not clone:
            return None

        if clone.full_spectral_envelope_path.is_file():
            try:
                return np.load(str(clone.full_spectral_envelope_path))
            except Exception as e:
                logger.error("Failed loading spectral envelope for %s: %s", clone_id, e)

        # Dynamic fallback from reference audio
        if clone.full_reference_path.is_file():
            try:
                data, sr = sf.read(str(clone.full_reference_path), dtype="float32")
                env = AudioDSP.extract_spectral_envelope(data, sr=sr)
                np.save(str(clone.full_spectral_envelope_path), env)
                return env
            except Exception as e:
                logger.error("Failed generating spectral envelope from reference: %s", e)
        return None

    def get_effective_pitch_shift(self, clone_id: str) -> float:
        """Get the pitch shift for a clone, auto-computing and persisting if it was 0.0."""
        import soundfile as sf
        clone = self.get_clone(clone_id)
        if not clone:
            return 0.0

        if abs(clone.pitch_shift) > 0.1:
            return clone.pitch_shift

        # Check if reference audio exists to auto-compute
        if clone.full_reference_path.is_file():
            try:
                data, sr = sf.read(str(clone.full_reference_path), dtype="float32")
                user_f0 = AudioDSP.estimate_median_f0(data, sr=sr)
                base_f0_map = {
                    "hi_IN-pratham-medium": 107.0,
                    "hi_IN-priyamvada-medium": 220.0,
                    "en_US-lessac-medium": 140.0,
                    "en_US-ryan-medium": 115.0,
                    "en_US-amy-medium": 215.0,
                }
                nominal_base_f0 = base_f0_map.get(clone.base_voice_key, 120.0)
                shift = float(np.clip(round(12.0 * np.log2(user_f0 / nominal_base_f0), 1), -12.0, 12.0))
                clone.pitch_shift = shift
                # Update profile.json
                p_file = clone.clone_dir / "profile.json"
                p_file.write_text(json.dumps(clone.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
                return shift
            except Exception as e:
                logger.warning("Could not auto-calculate pitch shift: %s", e)
        return 0.0
