import logging
from pathlib import Path
from typing import List, Optional

from app.core.project_manager import Project, TextBlock

logger = logging.getLogger(__name__)


class SubtitleGenerator:
    """Utility for generating synchronized SRT and WebVTT subtitle files from text blocks."""

    @staticmethod
    def format_timestamp_srt(seconds: float) -> str:
        """Format seconds into standard SRT timestamp: HH:MM:SS,mmm"""
        seconds = max(0.0, seconds)
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int(round((seconds - int(seconds)) * 1000))
        if millis >= 1000:
            millis = 999
        return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"

    @staticmethod
    def format_timestamp_vtt(seconds: float) -> str:
        """Format seconds into standard WebVTT timestamp: HH:MM:SS.mmm"""
        seconds = max(0.0, seconds)
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int(round((seconds - int(seconds)) * 1000))
        if millis >= 1000:
            millis = 999
        return f"{hrs:02d}:{mins:02d}:{secs:02d}.{millis:03d}"

    @classmethod
    def generate_srt(
        cls,
        blocks: List[TextBlock],
        output_path: Path,
        include_speaker: bool = True,
    ) -> Path:
        """Generate a standard .SRT subtitle file from timed project blocks."""
        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        lines: List[str] = []
        cue_idx = 1

        for b in blocks:
            if b.status != "completed" or b.duration <= 0:
                continue

            start_str = cls.format_timestamp_srt(b.start_time)
            end_str = cls.format_timestamp_srt(b.end_time)

            text = b.text.strip()
            if include_speaker and b.speaker_label:
                text = f"[{b.speaker_label}]: {text}"

            lines.append(str(cue_idx))
            lines.append(f"{start_str} --> {end_str}")
            lines.append(text)
            lines.append("")  # Blank separator
            cue_idx += 1

        output_path.write_text("\n".join(lines), encoding="utf-8")
        return output_path

    @classmethod
    def generate_vtt(
        cls,
        blocks: List[TextBlock],
        output_path: Path,
        include_speaker: bool = True,
    ) -> Path:
        """Generate a standard WebVTT .VTT subtitle file from timed project blocks."""
        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        lines: List[str] = ["WEBVTT", ""]
        cue_idx = 1

        for b in blocks:
            if b.status != "completed" or b.duration <= 0:
                continue

            start_str = cls.format_timestamp_vtt(b.start_time)
            end_str = cls.format_timestamp_vtt(b.end_time)

            text = b.text.strip()
            if include_speaker and b.speaker_label:
                text = f"<v {b.speaker_label}>{text}"

            lines.append(str(cue_idx))
            lines.append(f"{start_str} --> {end_str}")
            lines.append(text)
            lines.append("")  # Blank separator
            cue_idx += 1

        output_path.write_text("\n".join(lines), encoding="utf-8")
        return output_path

    @classmethod
    def export_from_project(
        cls,
        project: Project,
        format: str = "srt",
        output_path: Optional[Path] = None,
        include_speaker: bool = True,
    ) -> Path:
        """Export project blocks as SRT or WebVTT subtitles."""
        fmt = format.lower().replace(".", "")
        if output_path is None:
            filename = f"{project.name}_subtitles.{fmt}"
            output_path = project.exports_dir / filename

        # Ensure project timings are up-to-date
        project.update_timings()

        if fmt == "vtt":
            return cls.generate_vtt(project.blocks, output_path, include_speaker=include_speaker)
        return cls.generate_srt(project.blocks, output_path, include_speaker=include_speaker)
