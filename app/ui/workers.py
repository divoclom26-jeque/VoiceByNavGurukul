import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal

from app.core.audio_pipeline import AudioPipeline
from app.core.project_manager import Project, ProjectManager
from app.tts.piper_engine import PiperTTSEngine
from app.tts.voice_manager import download_piper_voice
from app.utils.atomic_audio import validate_wav_file

logger = logging.getLogger(__name__)


class SynthesisWorker(QThread):
    """Background worker for chunking, per-block speech synthesis, and audio mastering."""

    # Signals
    progress = Signal(int, int, str)  # current, total, status_text
    block_completed = Signal(int, float, str)  # block_id, duration_secs, audio_file
    finished = Signal(str, float, str)  # master_audio_path, total_duration, project_name
    error = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        project_name: str,
        text: str,
        voice_key: str,
        speed: float = 1.0,
        pause_ms: int = 350,
        output_format: str = "wav",
        normalize: bool = True,
        fx_preset: Optional[str] = "crisp_clean",
        add_room_tone: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.project_name = project_name
        self.text = text
        self.voice_key = voice_key
        self.speed = speed
        self.pause_ms = pause_ms
        self.output_format = output_format
        self.normalize = normalize
        self.fx_preset = fx_preset
        self.add_room_tone = add_room_tone
        self._is_cancelled = False

    def cancel(self):
        """Request the worker to stop processing gracefully."""
        self._is_cancelled = True

    def run(self):
        try:
            self.progress.emit(0, 100, "Preparing project and chunking text...")
            if self._is_cancelled:
                self.cancelled.emit()
                return

            # 1. Create project with smart chunking
            project = ProjectManager.create_project(
                name=self.project_name,
                text=self.text,
                voice_key=self.voice_key,
                speed=self.speed,
                max_chars=280,
            )

            total_blocks = len(project.blocks)
            if total_blocks == 0:
                self.error.emit("No pronounceable text found to synthesize.")
                return

            engine = PiperTTSEngine()
            voice_cfg = project.get_voice_config()

            # 2. Synthesize each block
            for idx, block in enumerate(project.blocks):
                if self._is_cancelled:
                    self.cancelled.emit()
                    return

                msg = f"Synthesizing block {idx + 1} of {total_blocks}..."
                self.progress.emit(idx, total_blocks, msg)

                out_wav = project.segments_dir / f"block_{block.id:04d}.wav"
                try:
                    engine.synthesize_to_wav(block.text, out_wav, voice_cfg)
                    info = validate_wav_file(out_wav)
                    block.audio_file = str(out_wav.relative_to(project.project_dir))
                    block.duration = info["duration"]
                    block.status = "completed"
                    block.error_message = None

                    self.block_completed.emit(block.id, block.duration, str(out_wav))
                except Exception as e:
                    block.status = "failed"
                    block.error_message = str(e)
                    logger.error(f"Failed block {block.id}: {e}")

                project.save()

            if self._is_cancelled:
                self.cancelled.emit()
                return

            # 3. Build master audio
            self.progress.emit(total_blocks, total_blocks, "Mastering and normalizing audio...")
            master_file = project.build_master_audio(
                output_format=self.output_format,
                pause_ms=self.pause_ms,
                normalize=self.normalize,
                fx_preset=self.fx_preset,
                add_room_tone=self.add_room_tone,
            )

            # Get final duration
            duration = 0.0
            if master_file.suffix.lower() == ".wav":
                duration = validate_wav_file(master_file).get("duration", 0.0)
            else:
                duration = sum(b.duration for b in project.blocks if b.status == "completed")

            self.progress.emit(total_blocks, total_blocks, "Complete!")
            self.finished.emit(str(master_file), duration, project.name)

        except Exception as e:
            logger.exception("SynthesisWorker error:")
            self.error.emit(str(e))


class DownloadVoiceWorker(QThread):
    """Background worker for downloading voice models from Hugging Face."""

    progress = Signal(str, int, int)  # phase, current_bytes, total_bytes
    finished = Signal(str)  # voice_key
    error = Signal(str)

    def __init__(self, voice_key: str, parent=None):
        super().__init__(parent)
        self.voice_key = voice_key

    def run(self):
        try:
            def on_progress(phase: str, cur: int, tot: int):
                self.progress.emit(phase, cur, tot)

            download_piper_voice(self.voice_key, progress_callback=on_progress)
            self.finished.emit(self.voice_key)
        except Exception as e:
            logger.exception("Voice download error:")
            self.error.emit(str(e))
