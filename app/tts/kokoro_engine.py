import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.tts.base import BaseTTSEngine
from app.utils.atomic_audio import validate_wav_file, write_silence_wav
from app.utils.paths import MODELS_DIR

logger = logging.getLogger(__name__)

KOKORO_DIR = MODELS_DIR / "kokoro"
KOKORO_MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
KOKORO_VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"

DEFAULT_KOKORO_VOICES = [
    # American Female
    "af_sarah", "af_bella", "af_nicole", "af_sky", "af_heart", "af_alloy", "af_aoede", "af_jessica",
    # American Male
    "am_adam", "am_michael", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_onyx", "am_puck",
    # British Female
    "bf_emma", "bf_isabella", "bf_alice", "bf_lily",
    # British Male
    "bm_george", "bm_lewis", "bm_daniel", "bm_fable",
]


class KokoroTTSEngine(BaseTTSEngine):
    """Adapter for Kokoro 82M Neural TTS running locally via ONNX."""

    def __init__(
        self,
        model_path: Optional[Path] = None,
        voices_path: Optional[Path] = None,
    ):
        self.model_path = Path(model_path) if model_path else KOKORO_DIR / "kokoro-v1.0.onnx"
        self.voices_path = Path(voices_path) if voices_path else KOKORO_DIR / "voices-v1.0.bin"
        self._kokoro_instance = None

    @property
    def engine_name(self) -> str:
        return "kokoro"

    def is_available(self) -> bool:
        """Check if Kokoro ONNX model files are downloaded locally."""
        return self.model_path.is_file() and self.voices_path.is_file()

    def validate(self, voice_config: Dict[str, Any]) -> None:
        """Verify model files exist."""
        m_path = Path(voice_config.get("model_path", self.model_path))
        v_path = Path(voice_config.get("voices_path", self.voices_path))

        if not m_path.is_file():
            raise FileNotFoundError(
                f"Kokoro ONNX model missing at '{m_path}'. "
                "Download it using the Voice Gallery or download_kokoro_model()."
            )
        if not v_path.is_file():
            raise FileNotFoundError(f"Kokoro voices file missing at '{v_path}'.")

    def _get_kokoro(self, model_path: Path, voices_path: Path):
        """Lazy-load and cache Kokoro ONNX runtime."""
        if self._kokoro_instance is None:
            try:
                from kokoro_onnx import Kokoro
            except ImportError as e:
                raise ImportError(
                    "kokoro-onnx is not installed. Install via: uv pip install kokoro-onnx soundfile"
                ) from e

            self._kokoro_instance = Kokoro(str(model_path), str(voices_path))
        return self._kokoro_instance

    def synthesize_to_wav(
        self,
        text: str,
        output_wav: Path,
        voice_config: Dict[str, Any],
    ) -> Path:
        """Synthesize text using Kokoro Neural TTS."""
        m_path = Path(voice_config.get("model_path", self.model_path))
        v_path = Path(voice_config.get("voices_path", self.voices_path))
        self.validate({"model_path": m_path, "voices_path": v_path})

        output_wav = Path(output_wav).resolve()
        output_wav.parent.mkdir(parents=True, exist_ok=True)
        stripped = text.strip()

        # Safeguard: If text is empty or has no letters/digits
        if not any(char.isalnum() for char in stripped):
            return write_silence_wav(output_wav, duration_seconds=0.25, sample_rate=24000)

        tmp_wav = output_wav.with_suffix(".tmp.wav")
        if tmp_wav.exists():
            tmp_wav.unlink()

        try:
            import soundfile as sf
            kokoro = self._get_kokoro(m_path, v_path)

            voice = voice_config.get("voice", voice_config.get("speaker", "af_sarah"))
            speed = float(voice_config.get("speed", 1.0))
            lang = voice_config.get("lang", "en-us")

            # Determine lang from voice prefix
            if str(voice).startswith("b"):
                lang = "en-gb"
            elif str(voice).startswith("a"):
                lang = "en-us"

            samples, sample_rate = kokoro.create(
                stripped,
                voice=voice,
                speed=speed,
                lang=lang,
            )

            # Write WAV via soundfile
            sf.write(str(tmp_wav), samples, sample_rate)
            validate_wav_file(tmp_wav)
            tmp_wav.replace(output_wav)
            return output_wav

        except Exception as e:
            if tmp_wav.exists():
                try:
                    tmp_wav.unlink()
                except OSError:
                    pass
            raise e


def download_kokoro_model(
    target_dir: Optional[Path] = None,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
) -> Dict[str, Path]:
    """Download Kokoro v1.0 ONNX model and voices file."""
    from app.tts.voice_manager import download_file_with_progress

    dest_dir = target_dir or KOKORO_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    model_dest = dest_dir / "kokoro-v1.0.onnx"
    voices_dest = dest_dir / "voices-v1.0.bin"

    # 1. Download voices file (~25MB)
    if not voices_dest.is_file():
        download_file_with_progress(
            KOKORO_VOICES_URL,
            voices_dest,
            description="Downloading Kokoro voices",
            progress_callback=(lambda cur, tot: progress_callback("voices", cur, tot)) if progress_callback else None,
        )

    # 2. Download ONNX weights (~320MB)
    if not model_dest.is_file():
        download_file_with_progress(
            KOKORO_MODEL_URL,
            model_dest,
            description="Downloading Kokoro model",
            progress_callback=(lambda cur, tot: progress_callback("model", cur, tot)) if progress_callback else None,
        )

    return {"model_path": model_dest, "voices_path": voices_dest}
