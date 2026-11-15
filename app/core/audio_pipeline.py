import os
from pathlib import Path
import subprocess
from typing import Any, Callable, Dict, List, Optional
import wave

from app.utils.atomic_audio import validate_wav_file, write_silence_wav
from app.utils.paths import get_ffmpeg_executable


class AudioPipeline:
    """Core audio processing, concatenation, DSP mixing, and multi-format export."""

    def __init__(self, ffmpeg_bin: Optional[Path] = None):
        self.ffmpeg_bin = Path(ffmpeg_bin) if ffmpeg_bin else get_ffmpeg_executable()

    def concatenate_wavs_fast(
        self,
        wav_files: List[Path],
        output_path: Path,
        pause_ms: int = 350,
    ) -> Path:
        """Losslessly concatenate multiple WAV files that share sample rate & channel config.
        
        Inserts silence of pause_ms duration between chunks.
        Operates directly using Python wave stdlib for instant execution.
        """
        if not wav_files:
            raise ValueError("No WAV files provided for concatenation.")

        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_output = output_path.with_suffix(".tmp.wav")

        # Read first file to get parameters
        first_file = wav_files[0]
        with wave.open(str(first_file), "rb") as wf:
            params = wf.getparams()
            n_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            framerate = wf.getframerate()

        # Compute silence frames for pause between blocks
        pause_frames_count = int(framerate * (pause_ms / 1000.0))
        silence_bytes = b"\x00" * (pause_frames_count * n_channels * sample_width)

        with wave.open(str(tmp_output), "wb") as out_wf:
            out_wf.setparams(params)

            for i, wav_path in enumerate(wav_files):
                with wave.open(str(wav_path), "rb") as in_wf:
                    # Verify matching audio format
                    if (
                        in_wf.getnchannels() != n_channels
                        or in_wf.getsampwidth() != sample_width
                        or in_wf.getframerate() != framerate
                    ):
                        # Fallback to FFmpeg if audio streams differ in format
                        out_wf.close()
                        if tmp_output.exists():
                            tmp_output.unlink()
                        return self.concatenate_with_ffmpeg(wav_files, output_path, pause_ms)

                    out_wf.writeframes(in_wf.readframes(in_wf.getnframes()))

                # Insert pause between chunks (but not after the last chunk)
                if pause_ms > 0 and i < len(wav_files) - 1:
                    out_wf.writeframes(silence_bytes)

        validate_wav_file(tmp_output)
        tmp_output.replace(output_path)
        return output_path

    def concatenate_with_ffmpeg(
        self,
        wav_files: List[Path],
        output_path: Path,
        pause_ms: int = 350,
    ) -> Path:
        """Robust concatenation using FFmpeg, auto-resampling different audio streams."""
        if not wav_files:
            raise ValueError("No WAV files provided for concatenation.")

        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_output = output_path.with_suffix(".tmp.wav")

        # Create temporary concat demuxer manifest
        concat_txt = output_path.with_suffix(".concat.txt")
        pause_wav = None

        try:
            # If pause is requested, synthesize a short silence WAV to insert between items
            lines = []
            if pause_ms > 0 and len(wav_files) > 1:
                pause_wav = output_path.parent / f"_pause_{pause_ms}ms.wav"
                write_silence_wav(pause_wav, duration_seconds=pause_ms / 1000.0, sample_rate=22050)

            for i, f in enumerate(wav_files):
                lines.append(f"file '{f.resolve()}'")
                if pause_wav and i < len(wav_files) - 1:
                    lines.append(f"file '{pause_wav.resolve()}'")

            concat_txt.write_text("\n".join(lines), encoding="utf-8")

            cmd = [
                str(self.ffmpeg_bin),
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_txt),
                "-c:a", "pcm_s16le",
                str(tmp_output),
            ]

            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode != 0:
                raise RuntimeError(f"FFmpeg concat failed: {res.stderr}")

            validate_wav_file(tmp_output)
            tmp_output.replace(output_path)
            return output_path

        finally:
            if concat_txt.exists():
                concat_txt.unlink()
            if pause_wav and pause_wav.exists():
                pause_wav.unlink()

    def normalize_loudness(
        self,
        input_wav: Path,
        output_wav: Path,
        target_i: float = -16.0,
        true_peak: float = -1.5,
    ) -> Path:
        """Apply EBU R128 loudness normalization using FFmpeg loudnorm filter."""
        input_wav = Path(input_wav).resolve()
        output_wav = Path(output_wav).resolve()
        output_wav.parent.mkdir(parents=True, exist_ok=True)
        tmp_wav = output_wav.with_suffix(".tmp.wav")

        cmd = [
            str(self.ffmpeg_bin),
            "-y",
            "-i", str(input_wav),
            "-af", f"loudnorm=I={target_i}:TP={true_peak}:LRA=11",
            "-c:a", "pcm_s16le",
            str(tmp_wav),
        ]

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg loudnorm failed: {res.stderr}")

        validate_wav_file(tmp_wav)
        tmp_wav.replace(output_wav)
        return output_wav

    def export_to_mp3(
        self,
        input_wav: Path,
        output_mp3: Path,
        bitrate: str = "192k",
        metadata: Optional[Dict[str, str]] = None,
    ) -> Path:
        """Export audio to MP3 with optional ID3 metadata tags."""
        input_wav = Path(input_wav).resolve()
        output_mp3 = Path(output_mp3).resolve()
        output_mp3.parent.mkdir(parents=True, exist_ok=True)
        tmp_mp3 = output_mp3.with_suffix(".tmp.mp3")

        cmd = [
            str(self.ffmpeg_bin),
            "-y",
            "-i", str(input_wav),
            "-c:a", "libmp3lame",
            "-b:a", bitrate,
        ]

        if metadata:
            for k, v in metadata.items():
                cmd.extend(["-metadata", f"{k}={v}"])

        cmd.append(str(tmp_mp3))

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg MP3 export failed: {res.stderr}")

        tmp_mp3.replace(output_mp3)
        return output_mp3
