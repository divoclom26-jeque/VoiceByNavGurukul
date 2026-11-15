from dataclasses import asdict, dataclass
import datetime
import json
import logging
from pathlib import Path
import re
from typing import Any, Callable, Dict, List, Optional

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

    def build_master_audio(
        self,
        output_format: str = "wav",
        pause_ms: int = 350,
        normalize: bool = True,
        pipeline: Optional[AudioPipeline] = None,
    ) -> Path:
        """Concatenate all completed segments into a unified master audio file."""
        pipeline = pipeline or AudioPipeline()

        completed_files = []
        for b in self.blocks:
            if b.status == "completed" and b.audio_file:
                seg_path = self.project_dir / b.audio_file
                if seg_path.is_file():
                    completed_files.append(seg_path)

        if not completed_files:
            raise RuntimeError("No completed audio segments available to build master audio.")

        raw_master = self.exports_dir / f"{self.name}_raw.wav"
        final_master_wav = self.exports_dir / f"{self.name}_master.wav"

        # 1. Concatenate all blocks with inter-sentence pauses
        pipeline.concatenate_wavs_fast(completed_files, raw_master, pause_ms=pause_ms)

        # 2. Normalize loudness (EBU R128) if requested
        if normalize:
            pipeline.normalize_loudness(raw_master, final_master_wav)
            if raw_master.exists():
                raw_master.unlink()
        else:
            raw_master.replace(final_master_wav)

        # 3. Export to requested format
        if output_format.lower() == "mp3":
            final_mp3 = self.exports_dir / f"{self.name}_master.mp3"
            pipeline.export_to_mp3(
                final_master_wav,
                final_mp3,
                bitrate="192k",
                metadata={"title": self.name, "comment": "Created with Local Voice Engine Studio"},
            )
            return final_mp3

        return final_master_wav


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

        raw_blocks = TextProcessor.split_into_blocks(text, max_chars=max_chars, project_dir=project_dir)
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
            metadata={"source_char_count": len(text), "block_count": len(text_blocks)},
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
