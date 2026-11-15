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
        pauses_ms: Optional[List[int]] = None,
    ) -> Path:
        """Losslessly concatenate multiple WAV files that share sample rate & channel config.
        
        Inserts silence of pause_ms (or individual pauses_ms[i]) duration between chunks.
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
                if i < len(wav_files) - 1:
                    cur_pause_ms = (
                        pauses_ms[i] if pauses_ms and i < len(pauses_ms) else pause_ms
                    )
                    if cur_pause_ms > 0:
                        pause_frames_count = int(framerate * (cur_pause_ms / 1000.0))
                        silence_bytes = b"\x00" * (
                            pause_frames_count * n_channels * sample_width
                        )
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

    STUDIO_PRESETS: Dict[str, Dict[str, Any]] = {
        "podcast_warmth": {
            "name": "🎙️ Podcast Warmth",
            "desc": "Rich low-end proximity (+3dB @ 120Hz) with optical compression",
            "filter": "highpass=f=75,equalizer=f=120:width_type=o:width=1.5:g=3.0,equalizer=f=3500:width_type=o:width=1.2:g=1.5,acompressor=threshold=-18dB:ratio=3:attack=20:release=250:makeup=2",
            "target_i": -16.0,
            "true_peak": -1.5,
        },
        "broadcast_clarity": {
            "name": "📻 Broadcast Clarity",
            "desc": "Crisp speech intelligibility, de-essing, and punchy broadcast compression",
            "filter": "highpass=f=85,equalizer=f=300:width_type=o:width=1.5:g=-1.5,equalizer=f=3200:width_type=o:width=1.0:g=3.5,equalizer=f=7500:width_type=o:width=1.5:g=-2.5,acompressor=threshold=-14dB:ratio=4:attack=10:release=150:makeup=2.5",
            "target_i": -14.0,
            "true_peak": -1.0,
        },
        "audiobook_acx": {
            "name": "📖 Audiobook Standard (ACX)",
            "desc": "Audible ACX compliant (-19.5 LUFS, peak <= -3.0dB, soft leveling)",
            "filter": "highpass=f=80,lowpass=f=15000,acompressor=threshold=-20dB:ratio=2.5:attack=30:release=300:makeup=1.5",
            "target_i": -19.5,
            "true_peak": -3.0,
        },
        "crisp_clean": {
            "name": "⚡ Crisp & Clean",
            "desc": "Transparent studio speech with high-pass rumble filter",
            "filter": "highpass=f=80,equalizer=f=2500:width_type=o:width=1.0:g=1.5",
            "target_i": -16.0,
            "true_peak": -1.5,
        },
        "bypass": {
            "name": "🚫 Bypass FX (Raw Voice)",
            "desc": "Unprocessed direct neural TTS voice",
            "filter": None,
            "target_i": -16.0,
            "true_peak": -1.5,
        },
    }

    def apply_studio_fx_preset(
        self,
        input_wav: Path,
        output_wav: Path,
        preset_key: str = "crisp_clean",
        add_room_tone: bool = False,
        custom_target_i: Optional[float] = None,
    ) -> Path:
        """Apply broadcast-grade studio mastering EQ, compression, de-essing, room tone, and loudnorm."""
        input_wav = Path(input_wav).resolve()
        output_wav = Path(output_wav).resolve()
        output_wav.parent.mkdir(parents=True, exist_ok=True)
        tmp_wav = output_wav.with_suffix(".tmp.wav")

        preset = self.STUDIO_PRESETS.get(preset_key, self.STUDIO_PRESETS["crisp_clean"])
        dsp_filter = preset.get("filter")
        target_i = custom_target_i if custom_target_i is not None else preset.get("target_i", -16.0)
        true_peak = preset.get("true_peak", -1.5)

        loudnorm_filter = f"loudnorm=I={target_i}:TP={true_peak}:LRA=11"

        if add_room_tone:
            # Generate faint ambient room tone bed (-54dB) and mix with speech before EQ/compression
            base_chain = f"{dsp_filter}," if dsp_filter else ""
            filtergraph = (
                f"[1:a]volume=0.0006[room];"
                f"[0:a][room]amix=inputs=2:duration=first:dropout_transition=0[mix];"
                f"[mix]{base_chain}{loudnorm_filter}[out]"
            )
            cmd = [
                str(self.ffmpeg_bin),
                "-y",
                "-i", str(input_wav),
                "-f", "lavfi",
                "-i", "anoisesrc=c=pink:r=22050:a=0.0006",
                "-filter_complex", filtergraph,
                "-map", "[out]",
                "-c:a", "pcm_s16le",
                str(tmp_wav),
            ]
        else:
            filter_parts = []
            if dsp_filter:
                filter_parts.append(dsp_filter)
            filter_parts.append(loudnorm_filter)
            full_af = ",".join(filter_parts)

            cmd = [
                str(self.ffmpeg_bin),
                "-y",
                "-i", str(input_wav),
                "-af", full_af,
                "-c:a", "pcm_s16le",
                str(tmp_wav),
            ]

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg studio mastering preset failed: {res.stderr}")

        validate_wav_file(tmp_wav)
        tmp_wav.replace(output_wav)
        return output_wav

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

    def export_audiogram_video(
        self,
        speech_wav: Path,
        output_mp4: Path,
        title: str = "Voice Engine AI",
        author: str = "Voice Engine",
        subtitle_srt: Optional[Path] = None,
        aspect_ratio: str = "square",
        waveform_color: str = "0x38BDF8",
        bg_color: str = "0x0F172A",
    ) -> Path:
        """Export speech audio to high-definition Audiogram video (.MP4) with animated waveform and burned subtitles.
        
        Supports aspect ratios:
        - "square" (1:1, 1080x1080) for Instagram posts / LinkedIn
        - "vertical" (9:16, 1080x1920) for Instagram Reels / YouTube Shorts / TikTok
        - "landscape" (16:9, 1920x1080) for YouTube / Web / Presentations
        """
        import tempfile

        speech_wav = Path(speech_wav).resolve()
        validate_wav_file(speech_wav)

        output_mp4 = Path(output_mp4).resolve()
        output_mp4.parent.mkdir(parents=True, exist_ok=True)
        tmp_mp4 = output_mp4.with_suffix(".tmp.mp4")

        # Configure dimensions based on aspect ratio
        ar = aspect_ratio.lower().strip()
        if ar in ("vertical", "9:16", "reel", "story"):
            w, h = 1080, 1920
            wave_w, wave_h = 920, 320
            title_y, author_y = 480, 560
            margin_v = 360
            title_size, author_size, sub_size = 46, 26, 28
        elif ar in ("landscape", "16:9", "youtube"):
            w, h = 1920, 1080
            wave_w, wave_h = 1400, 260
            title_y, author_y = 180, 250
            margin_v = 140
            title_size, author_size, sub_size = 48, 26, 30
        else:  # square (1:1, 1080x1080)
            w, h = 1080, 1080
            wave_w, wave_h = 880, 260
            title_y, author_y = 180, 250
            margin_v = 120
            title_size, author_size, sub_size = 44, 24, 28

        temp_files: List[Path] = []
        try:
            # Prepare title text file if provided
            last_bg = "bg0"
            filter_steps = [f"color=c={bg_color}:s={w}x{h}:r=25[{last_bg}]"]

            if title and title.strip():
                t_file = output_mp4.with_name(f".tmp_title_{os.getpid()}.txt")
                t_file.write_text(title.strip(), encoding="utf-8")
                temp_files.append(t_file)
                t_esc = str(t_file).replace("\\", "/").replace(":", "\\:")
                filter_steps.append(
                    f"[{last_bg}]drawtext=textfile='{t_esc}':font='Noto Sans Devanagari':fontsize={title_size}:fontcolor=white:x=(w-text_w)/2:y={title_y}[bg_title]"
                )
                last_bg = "bg_title"

            if author and author.strip():
                a_file = output_mp4.with_name(f".tmp_author_{os.getpid()}.txt")
                a_file.write_text(author.strip(), encoding="utf-8")
                temp_files.append(a_file)
                a_esc = str(a_file).replace("\\", "/").replace(":", "\\:")
                filter_steps.append(
                    f"[{last_bg}]drawtext=textfile='{a_esc}':font='Noto Sans Devanagari':fontsize={author_size}:fontcolor=0x94A3B8:x=(w-text_w)/2:y={author_y}[bg_author]"
                )
                last_bg = "bg_author"

            # Animated waveform overlay
            filter_steps.append(
                f"[0:a]showwaves=s={wave_w}x{wave_h}:mode=cline:colors={waveform_color}:scale=sqrt:draw=scale[wave_raw]"
            )
            filter_steps.append("[wave_raw]colorkey=0x000000:0.1:0.1[wave]")
            filter_steps.append(f"[{last_bg}][wave]overlay=(W-w)/2:(H-h)/2[v_wave]")

            # Optional burned subtitles
            if subtitle_srt and Path(subtitle_srt).is_file():
                s_esc = str(Path(subtitle_srt).resolve()).replace("\\", "/").replace(":", "\\:")
                filter_steps.append(
                    f"[v_wave]subtitles='{s_esc}':force_style='FontName=Noto Sans Devanagari,FontSize={sub_size},PrimaryColour=&H00FFFFFF&,OutlineColour=&H00000000&,Outline=2,Alignment=2,MarginV={margin_v}'[v_out]"
                )
            else:
                filter_steps.append("[v_wave]null[v_out]")

            filtergraph = ";".join(filter_steps)

            cmd = [
                str(self.ffmpeg_bin),
                "-y",
                "-i", str(speech_wav),
                "-filter_complex", filtergraph,
                "-map", "[v_out]",
                "-map", "0:a",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                str(tmp_mp4),
            ]

            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode != 0:
                raise RuntimeError(f"FFmpeg Audiogram video export failed: {res.stderr}")

            tmp_mp4.replace(output_mp4)
            return output_mp4

        finally:
            for tf in temp_files:
                if tf.exists():
                    try:
                        tf.unlink()
                    except Exception:
                        pass

