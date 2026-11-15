import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from app.tts.base import BaseTTSEngine
from app.utils.atomic_audio import validate_wav_file, write_silence_wav
from app.utils.paths import get_piper_executable


class PiperTTSEngine(BaseTTSEngine):
    """Adapter for running speech synthesis via the Piper binary/ONNX engine."""

    def __init__(self, executable: Optional[Path] = None):
        self.executable = Path(executable) if executable else get_piper_executable()

    @property
    def engine_name(self) -> str:
        return "piper"

    def validate(self, voice_config: Dict[str, Any]) -> None:
        """Verify Piper executable and model files exist."""
        if not self.executable or not self.executable.is_file():
            raise FileNotFoundError(
                f"Piper executable not found at '{self.executable}'. "
                "Ensure piper-tts is installed in the virtualenv or system PATH."
            )

        if not os.access(self.executable, os.X_OK):
            raise PermissionError(f"Piper binary at '{self.executable}' is not executable.")

        model_path = Path(voice_config.get("model_path", ""))
        if not model_path.is_file():
            raise FileNotFoundError(f"Piper ONNX model file missing: '{model_path}'")

        config_path = Path(voice_config.get("config_path", ""))
        if not config_path.is_file():
            raise FileNotFoundError(f"Piper voice config JSON missing: '{config_path}'")

    def synthesize_to_wav(
        self,
        text: str,
        output_wav: Path,
        voice_config: Dict[str, Any],
    ) -> Path:
        """Synthesize text to WAV file via Piper subprocess.
        
        Args:
            text: Text to speak.
            output_wav: Final destination path for the WAV.
            voice_config: Dictionary containing 'model_path', 'config_path',
                          optional 'speed' (default 1.0), 'speaker' (default 0),
                          'sample_rate' (default 22050).
        """
        self.validate(voice_config)
        output_wav = Path(output_wav).resolve()
        output_wav.parent.mkdir(parents=True, exist_ok=True)

        stripped = text.strip()
        sample_rate = int(voice_config.get("sample_rate", 22050))

        # Safeguard: If text contains no letters or numbers (only symbols or spaces),
        # return a short clean silent WAV to prevent Piper from producing silence bursts or crashing.
        if not any(char.isalnum() for char in stripped):
            return write_silence_wav(output_wav, duration_seconds=0.25, sample_rate=sample_rate)

        # Temporary output path for atomic write
        tmp_wav = output_wav.with_suffix(".tmp.wav")
        if tmp_wav.exists():
            tmp_wav.unlink()

        # Calculate length-scale from speed (speed 1.25 -> length_scale 0.8)
        speed = float(voice_config.get("speed", 1.0))
        speed_clamped = max(0.25, min(3.0, speed))
        length_scale = 1.0 / speed_clamped

        cmd = [
            str(self.executable),
            "--model", str(voice_config["model_path"]),
            "--config", str(voice_config["config_path"]),
            "--output_file", str(tmp_wav),
            "--length-scale", f"{length_scale:.4f}",
        ]

        # Add speaker ID if specified
        speaker = voice_config.get("speaker")
        if speaker is not None:
            cmd.extend(["--speaker", str(speaker)])

        # Optional sentence silence
        sentence_silence = voice_config.get("sentence_silence")
        if sentence_silence is not None:
            cmd.extend(["--sentence-silence", str(sentence_silence)])

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            _, stderr = proc.communicate(input=stripped.encode("utf-8"))

            if proc.returncode != 0:
                err_msg = stderr.decode("utf-8", errors="replace").strip()
                raise RuntimeError(f"Piper execution failed (code {proc.returncode}): {err_msg}")

            # Validate that tmp_wav was created and is a non-empty, valid WAV file
            validate_wav_file(tmp_wav)

            # Atomic replace to target file
            tmp_wav.replace(output_wav)
            return output_wav

        except Exception as e:
            if tmp_wav.exists():
                try:
                    tmp_wav.unlink()
                except OSError:
                    pass
            raise e
