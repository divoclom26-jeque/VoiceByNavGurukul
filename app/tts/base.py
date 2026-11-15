from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict


class BaseTTSEngine(ABC):
    """Abstract base class for all speech synthesis engines."""

    @property
    @abstractmethod
    def engine_name(self) -> str:
        """Return the unique name of this engine (e.g. 'piper', 'kokoro')."""
        pass

    @abstractmethod
    def validate(self, voice_config: Dict[str, Any]) -> None:
        """Verify model files, binaries, and configurations exist before running."""
        pass

    @abstractmethod
    def synthesize_to_wav(
        self,
        text: str,
        output_wav: Path,
        voice_config: Dict[str, Any],
    ) -> Path:
        """Synthesize plain text to a valid WAV file.
        
        Args:
            text: Cleaned text string to synthesize.
            output_wav: Destination file path for generated .wav.
            voice_config: Configuration dictionary containing model paths, speed, speaker id, etc.

        Returns:
            The Path to the generated and validated WAV file.
        """
        pass
