from dataclasses import asdict, dataclass
import datetime
import json
import logging
from pathlib import Path
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.core.audio_pipeline import AudioPipeline
from app.core.text_processor import TextProcessor
from app.tts.base import BaseTTSEngine
from app.tts.kokoro_engine import KokoroTTSEngine
from app.tts.piper_engine import PiperTTSEngine
from app.tts.voice_manager import list_local_voices
from app.utils.atomic_audio import validate_wav_file
from app.utils.paths import PROJECTS_DIR

logger = logging.getLogger(__name__)


@dataclass
class TextBlock:
    id: int
    text: str
    audio_file: Optional[str] = None  # Relative path to segment WAV
    status: str = "pending"  # "pending", "completed", "failed"
    duration: float = 0.0
    error_message: Optional[str] = None
    voice_key: Optional[str] = None  # Override voice per-block (multi-speaker)
    speed: Optional[float] = None  # Override speed per-block
    speaker_label: Optional[str] = None  # e.g. "Narrator", "Speaker A"
    pause_after_ms: Optional[int] = None  # Custom pause after this block (ms)
    start_time: float = 0.0  # Cumulative start time in master audio (seconds)
    end_time: float = 0.0  # Cumulative end time in master audio (seconds)


class Project:
    """Represents a long-form audio production project."""

    def __init__(
        self,
        project_dir: Path,
        name: str,
        voice_key: str,
        speed: float = 1.0,
        blocks: Optional[List[TextBlock]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.project_dir = Path(project_dir).resolve()
        self.segments_dir = self.project_dir / "segments"
        self.exports_dir = self.project_dir / "exports"
        self.name = name
        self.voice_key = voice_key
        self.speed = speed
        self.blocks = blocks or []
        self.metadata = metadata or {}

        self.segments_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)

    @property
    def manifest_path(self) -> Path:
        return self.project_dir / "manifest.json"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "voice_key": self.voice_key,
            "speed": self.speed,
            "updated_at": datetime.datetime.now().isoformat(),
            "blocks": [asdict(b) for b in self.blocks],
            "metadata": self.metadata,
        }

    def save(self) -> None:
        """Save project manifest atomically."""
        tmp_manifest = self.manifest_path.with_suffix(".tmp.json")
        with open(tmp_manifest, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        tmp_manifest.replace(self.manifest_path)

    @classmethod
    def load(cls, project_dir: Path) -> "Project":
        """Load an existing project from its directory."""
        project_dir = Path(project_dir).resolve()
        manifest_file = project_dir / "manifest.json"
        if not manifest_file.is_file():
            raise FileNotFoundError(f"Project manifest not found in {project_dir}")

        with open(manifest_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        blocks = [
            TextBlock(
                id=b["id"],
                text=b["text"],
                audio_file=b.get("audio_file"),
                status=b.get("status", "pending"),
                duration=b.get("duration", 0.0),
                error_message=b.get("error_message"),
                voice_key=b.get("voice_key"),
                speed=b.get("speed"),
                speaker_label=b.get("speaker_label"),
                pause_after_ms=b.get("pause_after_ms"),
                start_time=b.get("start_time", 0.0),
                end_time=b.get("end_time", 0.0),
            )
            for b in data.get("blocks", [])
        ]

        proj = cls(
            project_dir=project_dir,
            name=data.get("name", project_dir.name),
            voice_key=data.get("voice_key", ""),
            speed=data.get("speed", 1.0),
            blocks=blocks,
            metadata=data.get("metadata", {}),
        )
        return proj

    def get_voice_config_for_block(self, block: TextBlock) -> Dict[str, Any]:
        """Resolve voice configuration for a specific block (supporting per-block multi-voice)."""
        target_voice_key = block.voice_key or self.voice_key
        target_speed = block.speed or self.speed

        # Check if Kokoro voice
        if str(target_voice_key).startswith("kokoro:") or str(target_voice_key).startswith("af_") or str(target_voice_key).startswith("am_"):
            clean_voice = target_voice_key.replace("kokoro:", "")
            return {
                "engine": "kokoro",
                "voice": clean_voice,
                "speed": target_speed,
            }

        # Otherwise resolve Piper voice
        voices = {v["key"]: v for v in list_local_voices()}
        if target_voice_key not in voices:
            # Fallback to project default voice
            if self.voice_key in voices:
                target_voice_key = self.voice_key
            elif voices:
                target_voice_key = list(voices.keys())[0]
            else:
                raise ValueError(f"No local voice available for key '{target_voice_key}'")

        cfg = dict(voices[target_voice_key])
        cfg["engine"] = "piper"
        cfg["speed"] = target_speed
        return cfg

    def get_voice_config(self) -> Dict[str, Any]:
        """Find default voice configuration for this project."""
        dummy_block = TextBlock(id=0, text="", voice_key=self.voice_key, speed=self.speed)
        return self.get_voice_config_for_block(dummy_block)

    def update_block_text(self, block_id: int, new_text: str) -> TextBlock:
        """Update text of a block and mark it pending."""
        for b in self.blocks:
            if b.id == block_id:
                b.text = new_text.strip()
                b.status = "pending"
                self.save()
                return b
        raise KeyError(f"Block ID {block_id} not found.")

    def assign_block_voice(
        self,
        block_id: int,
        voice_key: Optional[str] = None,
        speaker_label: Optional[str] = None,
        speed: Optional[float] = None,
    ) -> TextBlock:
        """Assign a specific voice or speaker to a single block."""
        for b in self.blocks:
            if b.id == block_id:
                if voice_key is not None:
                    b.voice_key = voice_key
                if speaker_label is not None:
                    b.speaker_label = speaker_label
                if speed is not None:
                    b.speed = speed
                b.status = "pending"
                self.save()
                return b
        raise KeyError(f"Block ID {block_id} not found.")

    def synthesize_block(
        self,
        block_id: int,
        engine: Optional[BaseTTSEngine] = None,
    ) -> TextBlock:
        """Synthesize a single block by ID (ideal for block-by-block edits)."""
        target_block = None
        for b in self.blocks:
            if b.id == block_id:
                target_block = b
                break

        if not target_block:
            raise KeyError(f"Block ID {block_id} not found in project.")

        voice_cfg = self.get_voice_config_for_block(target_block)
        active_engine = engine
        if not active_engine:
            if voice_cfg.get("engine") == "kokoro":
                active_engine = KokoroTTSEngine()
            else:
                active_engine = PiperTTSEngine()

        out_wav = self.segments_dir / f"block_{target_block.id:04d}.wav"
        try:
            if voice_cfg.get("key", "").startswith("clone_"):
                from app.clone.engine import VoiceCloningEngine
                clone_engine = VoiceCloningEngine()
                clone_engine.synthesize_cloned(
                    target_block.text,
                    clone_id=voice_cfg["key"],
                    output_path=out_wav,
                    speed=voice_cfg.get("speed", 1.0),
                )
            else:
                active_engine.synthesize_to_wav(target_block.text, out_wav, voice_cfg)
            info = validate_wav_file(out_wav)
            target_block.audio_file = str(out_wav.relative_to(self.project_dir))
            target_block.duration = info["duration"]
            target_block.status = "completed"
            target_block.error_message = None
        except Exception as e:
            target_block.status = "failed"
            target_block.error_message = str(e)
            logger.error(f"Failed to synthesize block {block_id}: {e}")

        self.save()
        return target_block

    def synthesize_all(
        self,
        engine: Optional[BaseTTSEngine] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        force_rebuild: bool = False,
    ) -> List[TextBlock]:
        """Synthesize all pending blocks in the project."""
        piper_engine = PiperTTSEngine()
        kokoro_engine = KokoroTTSEngine()
        total = len(self.blocks)

        for i, block in enumerate(self.blocks):
            out_wav = self.segments_dir / f"block_{block.id:04d}.wav"

            if not force_rebuild and block.status == "completed" and out_wav.is_file():
                if progress_callback:
                    progress_callback(i + 1, total, f"Block {block.id} up to date")
                continue

            if progress_callback:
                progress_callback(i + 1, total, f"Rendering Block {block.id} of {total}...")

            voice_cfg = self.get_voice_config_for_block(block)
            active_engine = engine or (kokoro_engine if voice_cfg.get("engine") == "kokoro" else piper_engine)

            try:
                if voice_cfg.get("key", "").startswith("clone_"):
                    from app.clone.engine import VoiceCloningEngine
                    clone_engine = VoiceCloningEngine()
                    clone_engine.synthesize_cloned(
                        block.text,
                        clone_id=voice_cfg["key"],
                        output_path=out_wav,
                        speed=voice_cfg.get("speed", 1.0),
                    )
                else:
                    active_engine.synthesize_to_wav(block.text, out_wav, voice_cfg)
                info = validate_wav_file(out_wav)
                block.audio_file = str(out_wav.relative_to(self.project_dir))
                block.duration = info["duration"]
                block.status = "completed"
                block.error_message = None
            except Exception as e:
                block.status = "failed"
                block.error_message = str(e)
                logger.error(f"Failed rendering block {block.id}: {e}")

            # Save progress incrementally
            self.save()

        return self.blocks

    def update_timings(self, default_pause_ms: int = 350) -> None:
        """Calculate and store exact cumulative start_time and end_time for each block."""
        cumulative_time = 0.0
        for b in self.blocks:
            if b.status == "completed" and b.audio_file:
                b.start_time = round(cumulative_time, 3)
                b.end_time = round(cumulative_time + b.duration, 3)
                p_ms = b.pause_after_ms if b.pause_after_ms is not None else default_pause_ms
                cumulative_time = b.end_time + (p_ms / 1000.0)
            else:
                b.start_time = round(cumulative_time, 3)
                b.end_time = round(cumulative_time, 3)
        self.save()

    def build_master_audio(
        self,
        output_format: str = "wav",
        pause_ms: int = 350,
        normalize: bool = True,
        fx_preset: Optional[str] = "crisp_clean",
        add_room_tone: bool = False,
        pipeline: Optional[AudioPipeline] = None,
    ) -> Path:
        """Concatenate all completed segments into a unified master audio file with Studio FX mastering."""
        pipeline = pipeline or AudioPipeline()

        completed_files = []
        pauses_ms = []
        for b in self.blocks:
            if b.status == "completed" and b.audio_file:
                seg_path = self.project_dir / b.audio_file
                if seg_path.is_file():
                    completed_files.append(seg_path)
                    p_val = b.pause_after_ms if b.pause_after_ms is not None else pause_ms
                    pauses_ms.append(p_val)

        if not completed_files:
            raise RuntimeError("No completed audio segments available to build master audio.")

        raw_master = self.exports_dir / f"{self.name}_raw.wav"
        final_master_wav = self.exports_dir / f"{self.name}_master.wav"

        # 1. Concatenate all blocks with inter-sentence pauses and micro-crossfades
        pipeline.concatenate_wavs_fast(
            completed_files, raw_master, pause_ms=pause_ms, pauses_ms=pauses_ms
        )

        # 2. Apply Studio Mastering FX Preset and EBU R128 Loudnorm if requested
        if normalize:
            if fx_preset and fx_preset in pipeline.STUDIO_PRESETS:
                pipeline.apply_studio_fx_preset(
                    raw_master,
                    final_master_wav,
                    preset_key=fx_preset,
                    add_room_tone=add_room_tone,
                )
            else:
                pipeline.normalize_loudness(raw_master, final_master_wav)

            if raw_master.exists():
                raw_master.unlink()
        else:
            raw_master.replace(final_master_wav)

        # 3. Update cumulative block start and end timestamps
        self.update_timings(default_pause_ms=pause_ms)

        # 4. Export to requested format
        fmt = output_format.lower().strip()
        if fmt == "mp3":
            final_mp3 = self.exports_dir / f"{self.name}_master.mp3"
            pipeline.export_to_mp3(
                final_master_wav,
                final_mp3,
                bitrate="192k",
                metadata={"title": self.name, "comment": "Created with Local Voice Engine Studio"},
            )
            return final_mp3
        elif fmt == "flac":
            final_flac = self.exports_dir / f"{self.name}_master.flac"
            pipeline.export_to_flac(
                final_master_wav,
                final_flac,
                metadata={"title": self.name, "comment": "Created with Local Voice Engine Studio"},
            )
            return final_flac
        elif fmt == "m4b":
            final_m4b = self.exports_dir / f"{self.name}_master.m4b"
            chapters = []
            cur_ms = 0
            for i, b in enumerate(self.blocks):
                dur_ms = int(b.duration * 1000)
                chapters.append({
                    "start_ms": cur_ms,
                    "end_ms": cur_ms + dur_ms,
                    "title": f"Chapter {i+1}: {b.text[:30]}",
                })
                cur_ms += dur_ms + pause_ms
            pipeline.export_to_m4b(
                final_master_wav,
                final_m4b,
                metadata={"title": self.name, "comment": "Created with Local Voice Engine Studio"},
                chapters=chapters,
            )
            return final_m4b
        elif "audiogram" in fmt or fmt == "mp4":
            return self.export_audiogram(aspect_ratio="square", pipeline=pipeline)
        elif fmt == "srt":
            return self.export_subtitles(format="srt")
        elif fmt == "vtt":
            return self.export_subtitles(format="vtt")

        return final_master_wav

    def export_subtitles(
        self,
        format: str = "srt",
        output_path: Optional[Path] = None,
        include_speaker: bool = True,
    ) -> Path:
        """Export synchronized project subtitles as SRT or WebVTT."""
        from app.core.subtitles import SubtitleGenerator
        return SubtitleGenerator.export_from_project(
            self,
            format=format,
            output_path=output_path,
            include_speaker=include_speaker,
        )

    def export_audiogram(
        self,
        aspect_ratio: str = "square",
        output_path: Optional[Path] = None,
        burn_subtitles: bool = True,
        waveform_color: str = "0x38BDF8",
        bg_color: str = "0x0F172A",
        pipeline: Optional[AudioPipeline] = None,
    ) -> Path:
        """Generate high-definition Audiogram social video (.MP4) with animated waveform and burned subtitles."""
        pipeline = pipeline or AudioPipeline()
        master_wav = self.exports_dir / f"{self.name}_master.wav"
        if not master_wav.is_file():
            master_wav = self.build_master_audio(output_format="wav", pipeline=pipeline)

        if output_path is None:
            output_path = self.exports_dir / f"{self.name}_audiogram_{aspect_ratio}.mp4"

        srt_path = None
        if burn_subtitles:
            srt_path = self.export_subtitles(format="srt")

        return pipeline.export_audiogram_video(
            speech_wav=master_wav,
            output_mp4=output_path,
            title=self.name,
            author="Voice Studio",
            subtitle_srt=srt_path,
            aspect_ratio=aspect_ratio,
            waveform_color=waveform_color,
            bg_color=bg_color,
        )

    def retake_block(
        self,
        block_id: int,
        new_text: Optional[str] = None,
        voice_key: Optional[str] = None,
        speed: Optional[float] = None,
        pause_after_ms: Optional[int] = None,
        rebuild_master: bool = True,
    ) -> TextBlock:
        """Instant Re-Take: update block text/voice/speed, re-synthesize, and re-pack master audio."""
        target_block = None
        for b in self.blocks:
            if b.id == block_id:
                target_block = b
                break

        if not target_block:
            raise KeyError(f"Block ID {block_id} not found in project.")

        if new_text is not None:
            target_block.text = new_text.strip()
        if voice_key is not None:
            target_block.voice_key = voice_key
        if speed is not None:
            target_block.speed = speed
        if pause_after_ms is not None:
            target_block.pause_after_ms = pause_after_ms

        target_block.status = "pending"
        self.save()

        # Re-synthesize this single block
        self.synthesize_block(block_id)

        # Re-pack master if requested and previous master audio exists
        if rebuild_master and target_block.status == "completed":
            try:
                self.build_master_audio(normalize=False)
            except Exception as e:
                logger.warning("Could not auto-rebuild master after retake: %s", e)

        return target_block

    def delete_block(self, block_id: int, rebuild_master: bool = True) -> bool:
        """Cut Text = Cut Audio: delete block from script, delete its WAV, and update master."""
        target_idx = None
        for i, b in enumerate(self.blocks):
            if b.id == block_id:
                target_idx = i
                break

        if target_idx is None:
            return False

        block = self.blocks.pop(target_idx)

        # Delete audio segment if present
        if block.audio_file:
            seg_path = self.project_dir / block.audio_file
            if seg_path.is_file():
                try:
                    seg_path.unlink()
                except Exception as e:
                    logger.warning("Failed to remove deleted segment file %s: %s", seg_path, e)

        # Re-index remaining blocks
        for i, b in enumerate(self.blocks):
            b.id = i + 1

        self.save()

        # Re-pack master if any completed blocks remain
        if rebuild_master and any(b.status == "completed" for b in self.blocks):
            try:
                self.build_master_audio(normalize=False)
            except Exception as e:
                logger.warning("Could not auto-rebuild master after delete: %s", e)

        return True

    def add_block(
        self,
        text: str,
        after_block_id: Optional[int] = None,
        voice_key: Optional[str] = None,
        speed: Optional[float] = None,
        pause_after_ms: Optional[int] = None,
        synthesize_now: bool = True,
    ) -> TextBlock:
        """Insert a new text block at the specified position and synthesize it."""
        text = text.strip()
        if not text:
            raise ValueError("Block text cannot be empty.")

        new_block = TextBlock(
            id=len(self.blocks) + 1,
            text=text,
            voice_key=voice_key,
            speed=speed,
            pause_after_ms=pause_after_ms,
            status="pending",
        )

        if after_block_id is not None:
            insert_idx = len(self.blocks)
            for i, b in enumerate(self.blocks):
                if b.id == after_block_id:
                    insert_idx = i + 1
                    break
            self.blocks.insert(insert_idx, new_block)
        else:
            self.blocks.append(new_block)

        # Re-index blocks
        for i, b in enumerate(self.blocks):
            b.id = i + 1

        self.save()

        if synthesize_now:
            self.synthesize_block(new_block.id)
            try:
                self.build_master_audio(normalize=False)
            except Exception as e:
                logger.warning("Could not rebuild master after adding block: %s", e)

        return new_block

    def get_character_palette(self) -> Dict[str, Dict[str, Any]]:
        """Return character palette from project metadata."""
        return self.metadata.get("characters", {})

    def set_character_voice(
        self,
        character: str,
        voice_key: str,
        update_blocks: bool = True,
    ) -> None:
        """Update voice for a character and optionally update all matching blocks."""
        if "characters" not in self.metadata:
            self.metadata["characters"] = {}
        if character not in self.metadata["characters"]:
            from app.core.screenplay import CHARACTER_COLORS

            idx = len(self.metadata["characters"])
            self.metadata["characters"][character] = {
                "color": CHARACTER_COLORS[idx % len(CHARACTER_COLORS)],
                "gender": "neutral",
            }

        self.metadata["characters"][character]["voice_key"] = voice_key

        if update_blocks:
            for b in self.blocks:
                if b.speaker_label == character:
                    b.voice_key = voice_key
                    b.status = "pending"

        self.save()

    def set_character_color(self, character: str, color_hex: str) -> None:
        """Update display badge color for a character."""
        if "characters" not in self.metadata:
            self.metadata["characters"] = {}
        if character not in self.metadata["characters"]:
            self.metadata["characters"][character] = {
                "voice_key": self.voice_key,
                "gender": "neutral",
            }
        self.metadata["characters"][character]["color"] = color_hex
        self.save()

    def split_block(
        self,
        block_id: int,
        split_char_index: int,
        synthesize_now: bool = True,
    ) -> Tuple[TextBlock, TextBlock]:
        """Split a block into two smaller blocks at split_char_index."""
        target_idx = None
        for i, b in enumerate(self.blocks):
            if b.id == block_id:
                target_idx = i
                break

        if target_idx is None:
            raise KeyError(f"Block ID {block_id} not found.")

        target = self.blocks[target_idx]
        full_text = target.text
        if split_char_index <= 0 or split_char_index >= len(full_text):
            raise ValueError(f"Invalid split index {split_char_index} for text length {len(full_text)}")

        text_a = full_text[:split_char_index].strip()
        text_b = full_text[split_char_index:].strip()

        if not text_a or not text_b:
            raise ValueError("Split would produce an empty block.")

        target.text = text_a
        target.status = "pending"

        new_block = TextBlock(
            id=block_id + 1,
            text=text_b,
            voice_key=target.voice_key,
            speed=target.speed,
            pause_after_ms=target.pause_after_ms,
            status="pending",
        )
        self.blocks.insert(target_idx + 1, new_block)

        # Re-index blocks
        for i, b in enumerate(self.blocks):
            b.id = i + 1

        self.save()

        if synthesize_now:
            self.synthesize_block(target.id)
            self.synthesize_block(new_block.id)
            try:
                self.build_master_audio(normalize=False)
            except Exception as e:
                logger.warning("Could not rebuild master after split: %s", e)

        return target, new_block


class ProjectManager:
    """Manages creation, indexing, and loading of audio projects."""

    @staticmethod
    def slugify(name: str) -> str:
        s = re.sub(r"[^\w\s-]", "", name).strip().lower()
        return re.sub(r"[-\s]+", "_", s) or "untitled_project"

    @classmethod
    def create_project(
        cls,
        name: str,
        text: str,
        voice_key: str,
        speed: float = 1.0,
        max_chars: int = 280,
    ) -> Project:
        """Create a new project by chunking source text into blocks."""
        slug = cls.slugify(name)
        project_dir = PROJECTS_DIR / slug
        if project_dir.exists():
            slug = f"{slug}_{int(datetime.datetime.now().timestamp())}"
            project_dir = PROJECTS_DIR / slug

        project_dir.mkdir(parents=True, exist_ok=True)

        # Check if text contains screenplay dialogue tags
        from app.core.screenplay import ScreenplayParser

        has_screenplay = ScreenplayParser.has_screenplay_tags(text)

        text_blocks: List[TextBlock] = []
        char_palette: Dict[str, Dict[str, Any]] = {}

        if has_screenplay:
            turns = ScreenplayParser.parse_screenplay(text)
            characters = ScreenplayParser.extract_characters(text)
            voices = list_local_voices()
            char_palette = ScreenplayParser.generate_character_palette(
                characters, voices, default_voice_key=voice_key
            )

            block_id = 1
            for turn in turns:
                spk = turn["speaker"]
                turn_text = turn["text"]
                spk_voice = char_palette.get(spk, {}).get("voice_key") or voice_key

                # Split turn text if it exceeds max_chars
                turn_chunks = TextProcessor.split_into_blocks(
                    turn_text, max_chars=max_chars, project_dir=project_dir
                )
                for chunk in turn_chunks:
                    text_blocks.append(
                        TextBlock(
                            id=block_id,
                            text=chunk,
                            voice_key=spk_voice,
                            speaker_label=spk,
                        )
                    )
                    block_id += 1
        else:
            raw_blocks = TextProcessor.split_into_blocks(
                text, max_chars=max_chars, project_dir=project_dir
            )
            text_blocks = [
                TextBlock(id=i + 1, text=block_text)
                for i, block_text in enumerate(raw_blocks)
            ]

        project = Project(
            project_dir=project_dir,
            name=name,
            voice_key=voice_key,
            speed=speed,
            blocks=text_blocks,
            metadata={
                "source_char_count": len(text),
                "block_count": len(text_blocks),
                "is_screenplay": has_screenplay,
                "characters": char_palette,
            },
        )
        project.save()
        return project

    @classmethod
    def list_projects(cls) -> List[Dict[str, Any]]:
        """List all projects in the projects/ folder."""
        if not PROJECTS_DIR.is_dir():
            return []

        projects = []
        for d in sorted(PROJECTS_DIR.iterdir()):
            manifest = d / "manifest.json"
            if d.is_dir() and manifest.is_file():
                try:
                    with open(manifest, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    projects.append({
                        "id": d.name,
                        "name": data.get("name", d.name),
                        "voice_key": data.get("voice_key"),
                        "blocks": len(data.get("blocks", [])),
                        "updated_at": data.get("updated_at"),
                        "path": str(d.resolve()),
                    })
                except Exception as e:
                    logger.warning(f"Could not read manifest at {manifest}: {e}")

        return projects
