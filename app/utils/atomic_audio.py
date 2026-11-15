import os
import wave
from pathlib import Path
from typing import Any, Dict


class InvalidWavError(Exception):
    """Raised when a WAV file is invalid or corrupt."""
    pass


def validate_wav_file(path: Path) -> Dict[str, Any]:
    """Validate that the given file is a non-empty, well-formed WAV file.
    
    Returns a dictionary of audio characteristics.
    """
    if not path.is_file():
        raise InvalidWavError(f"WAV file does not exist: {path}")

    size_bytes = path.stat().st_size
    if size_bytes < 44:  # Minimum standard WAV header size
        raise InvalidWavError(f"WAV file is too small ({size_bytes} bytes), header incomplete: {path}")

    try:
        with wave.open(str(path), "rb") as wf:
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            framerate = wf.getframerate()
            n_frames = wf.getnframes()
            duration = n_frames / float(framerate) if framerate > 0 else 0.0

            if n_frames == 0 or duration <= 0:
                raise InvalidWavError(f"WAV file contains 0 audio frames: {path}")

            return {
                "channels": channels,
                "sample_width": sample_width,
                "framerate": framerate,
                "n_frames": n_frames,
                "duration": duration,
                "size_bytes": size_bytes,
            }
    except Exception as e:
        if isinstance(e, InvalidWavError):
            raise
        raise InvalidWavError(f"Failed to read WAV header from {path}: {e}") from e


def write_silence_wav(
    output_wav: Path,
    duration_seconds: float = 0.2,
    sample_rate: int = 22050,
    channels: int = 1,
) -> Path:
    """Generate a valid silent WAV file atomically."""
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_wav.with_suffix(".tmp.wav")

    n_frames = int(sample_rate * duration_seconds)
    silence_bytes = b"\x00\x00" * n_frames * channels  # 16-bit PCM silence

    with wave.open(str(tmp_path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(silence_bytes)

    # Atomic rename
    tmp_path.replace(output_wav)
    return output_wav
