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
        fade_ms: int = 15,
    ) -> Path:
        """Losslessly concatenate multiple WAV files that share sample rate & channel config.
        
        Inserts silence of pause_ms duration between chunks.
        Applies smooth micro fade-in and fade-out (fade_ms) to eliminate seam clicks.
        Operates directly using Python wave stdlib and numpy for instant execution.
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

                    raw_frames = in_wf.readframes(in_wf.getnframes())
                    if fade_ms > 0 and sample_width == 2:
                        raw_frames = self.apply_micro_fades(
                            raw_frames, n_channels, sample_width, framerate, fade_ms
                        )

                    out_wf.writeframes(raw_frames)

                # Insert pause between chunks (but not after the last chunk)
                if pause_ms > 0 and i < len(wav_files) - 1:
                    out_wf.writeframes(silence_bytes)

        validate_wav_file(tmp_output)
        tmp_output.replace(output_path)
        return output_path

    @staticmethod
    def apply_micro_fades(
        raw_bytes: bytes,
        n_channels: int,
        sample_width: int,
        framerate: int,
        fade_ms: int = 15,
    ) -> bytes:
        """Apply linear micro fade-in and fade-out to prevent clicks and DC offset pops."""
        if sample_width != 2 or fade_ms <= 0:
            return raw_bytes

        fade_len = int(framerate * (fade_ms / 1000.0))
        if fade_len <= 0:
            return raw_bytes

        import numpy as np

        samples = np.frombuffer(raw_bytes, dtype=np.int16).copy()
        total_samples = len(samples) // n_channels
        if total_samples < fade_len * 2:
            return raw_bytes

        fade_in = np.linspace(0.0, 1.0, fade_len, dtype=np.float32)
        fade_out = np.linspace(1.0, 0.0, fade_len, dtype=np.float32)

        if n_channels == 1:
            samples[:fade_len] = (samples[:fade_len] * fade_in).astype(np.int16)
            samples[-fade_len:] = (samples[-fade_len:] * fade_out).astype(np.int16)
        else:
            for ch in range(n_channels):
                samples[ch::n_channels][:fade_len] = (
                    samples[ch::n_channels][:fade_len] * fade_in
                ).astype(np.int16)
                samples[ch::n_channels][-fade_len:] = (
                    samples[ch::n_channels][-fade_len:] * fade_out
                ).astype(np.int16)

        return samples.tobytes()

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

        concat_txt = output_path.with_suffix(".concat.txt")
        pause_wav = None

        try:
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

    def mix_background_music(
        self,
        speech_wav: Path,
        music_file: Path,
        output_wav: Path,
        music_volume: float = 0.22,
        ducking_ratio: float = 6.0,
        ducking_threshold: float = 0.03,
        attack_ms: int = 100,
        release_ms: int = 800,
        fade_out_sec: float = 2.0,
    ) -> Path:
        """Mix speech narration with background music using real-time auto-ducking and end fadeout.
        
        Whenever speech is active, the background music volume automatically attenuates.
        """
        speech_wav = Path(speech_wav).resolve()
        music_file = Path(music_file).resolve()
        output_wav = Path(output_wav).resolve()
        output_wav.parent.mkdir(parents=True, exist_ok=True)

        if not speech_wav.is_file():
            raise FileNotFoundError(f"Speech WAV not found: {speech_wav}")
        if not music_file.is_file():
            raise FileNotFoundError(f"Music file not found: {music_file}")

        speech_info = validate_wav_file(speech_wav)
        speech_dur = speech_info["duration"]

        fade_start = max(0.0, speech_dur - fade_out_sec)
        tmp_wav = output_wav.with_suffix(".tmp.wav")

        # Sidechain compression filtergraph:
        # [1:a] loops music, sets base volume, fades out at speech end
        # sidechaincompress ducks music when [0:a] (voice) speaks
        # amix sums the speech and ducked music together
        filtergraph = (
            f"[1:a]volume={music_volume:.3f},"
            f"afade=t=out:st={fade_start:.2f}:d={fade_out_sec:.2f}[bg_faded];"
            f"[bg_faded][0:a]sidechaincompress="
            f"threshold={ducking_threshold}:ratio={ducking_ratio}:attack={attack_ms}:release={release_ms}[ducked];"
            f"[0:a][ducked]amix=inputs=2:duration=first:dropout_transition=0:weights=1 1[out]"
        )

        cmd = [
            str(self.ffmpeg_bin),
            "-y",
            "-i", str(speech_wav),
            "-stream_loop", "-1",
            "-i", str(music_file),
            "-filter_complex", filtergraph,
            "-map", "[out]",
            "-c:a", "pcm_s16le",
            str(tmp_wav),
        ]

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg music mix failed: {res.stderr}")

        validate_wav_file(tmp_wav)
        tmp_wav.replace(output_wav)
        return output_wav

    def export_to_mp3(
        self,
        input_wav: Path,
        output_mp3: Path,
        bitrate: str = "192k",
        metadata: Optional[Dict[str, str]] = None,
        cover_image: Optional[Path] = None,
    ) -> Path:
        """Export audio to MP3 with ID3 tags and optional embedded cover art."""
        input_wav = Path(input_wav).resolve()
        output_mp3 = Path(output_mp3).resolve()
        output_mp3.parent.mkdir(parents=True, exist_ok=True)
        tmp_mp3 = output_mp3.with_suffix(".tmp.mp3")

        cmd = [str(self.ffmpeg_bin), "-y", "-i", str(input_wav)]

        has_cover = cover_image and Path(cover_image).is_file()
        if has_cover:
            cmd.extend(["-i", str(cover_image)])
            cmd.extend(["-map", "0:a", "-map", "1:v", "-c:v", "copy", "-id3v2_version", "3"])
            cmd.extend(["-metadata:s:v", 'title="Album cover"', "-metadata:s:v", 'comment="Cover (front)"'])
        else:
            cmd.extend(["-map", "0:a"])

        cmd.extend(["-c:a", "libmp3lame", "-b:a", bitrate])

        if metadata:
            for k, v in metadata.items():
                cmd.extend(["-metadata", f"{k}={v}"])

        cmd.append(str(tmp_mp3))

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg MP3 export failed: {res.stderr}")

        tmp_mp3.replace(output_mp3)
        return output_mp3

    def export_to_m4b(
        self,
        input_wav: Path,
        output_m4b: Path,
        bitrate: str = "128k",
        metadata: Optional[Dict[str, str]] = None,
        chapters: Optional[List[Dict[str, Any]]] = None,
        cover_image: Optional[Path] = None,
    ) -> Path:
        """Export to M4B audiobook format with AAC audio, chapter marks, and cover art."""
        input_wav = Path(input_wav).resolve()
        output_m4b = Path(output_m4b).resolve()
        output_m4b.parent.mkdir(parents=True, exist_ok=True)
        tmp_m4b = output_m4b.with_suffix(".tmp.m4b")

        meta_txt = output_m4b.with_suffix(".ffmetadata.txt")
        try:
            # Generate FFmpeg metadata text for chapters
            meta_lines = [";FFMETADATA1"]
            if metadata:
                for k, v in metadata.items():
                    meta_lines.append(f"{k}={v}")

            if chapters:
                for ch in chapters:
                    meta_lines.append("[CHAPTER]")
                    meta_lines.append("TIMEBASE=1/1000")
                    meta_lines.append(f"START={int(ch.get('start_ms', 0))}")
                    meta_lines.append(f"END={int(ch.get('end_ms', 0))}")
                    meta_lines.append(f"title={ch.get('title', 'Chapter')}")

            meta_txt.write_text("\n".join(meta_lines), encoding="utf-8")

            cmd = [
                str(self.ffmpeg_bin),
                "-y",
                "-i", str(input_wav),
                "-i", str(meta_txt),
            ]

            has_cover = cover_image and Path(cover_image).is_file()
            if has_cover:
                cmd.extend(["-i", str(cover_image)])
                cmd.extend(["-map", "0:a", "-map", "2:v", "-c:v", "copy", "-disposition:v", "attached_pic"])
            else:
                cmd.extend(["-map", "0:a"])

            cmd.extend([
                "-map_metadata", "1",
                "-c:a", "aac",
                "-b:a", bitrate,
                "-f", "mp4",
                str(tmp_m4b),
            ])

            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode != 0:
                raise RuntimeError(f"FFmpeg M4B export failed: {res.stderr}")

            tmp_m4b.replace(output_m4b)
            return output_m4b

        finally:
            if meta_txt.exists():
                meta_txt.unlink()

    def export_to_flac(
        self,
        input_wav: Path,
        output_flac: Path,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Path:
        """Export audio to lossless FLAC container."""
        input_wav = Path(input_wav).resolve()
        output_flac = Path(output_flac).resolve()
        output_flac.parent.mkdir(parents=True, exist_ok=True)
        tmp_flac = output_flac.with_suffix(".tmp.flac")

        cmd = [
            str(self.ffmpeg_bin),
            "-y",
            "-i", str(input_wav),
            "-c:a", "flac",
        ]

        if metadata:
            for k, v in metadata.items():
                cmd.extend(["-metadata", f"{k}={v}"])

        cmd.append(str(tmp_flac))

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg FLAC export failed: {res.stderr}")

        tmp_flac.replace(output_flac)
        return output_flac
