import os
import shutil
import sys
from pathlib import Path

# Project root is the root directory containing `app/`
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

MODELS_DIR = PROJECT_ROOT / "models"
VOICES_DIR = MODELS_DIR / "voices"
PROJECTS_DIR = PROJECT_ROOT / "projects"
ASSETS_DIR = PROJECT_ROOT / "assets"

def get_piper_executable() -> Path:
    """Find the Piper executable in the virtual environment, system PATH, or environment variable."""
    env_override = os.environ.get("PIPER_EXECUTABLE")
    if env_override and Path(env_override).is_file():
        return Path(env_override)

    # Check active venv bin directory (where python is executing from)
    venv_bin = Path(sys.prefix) / "bin" / "piper"
    if venv_bin.is_file():
        return venv_bin

    # Check local .venv in project root
    project_venv_bin = PROJECT_ROOT / ".venv" / "bin" / "piper"
    if project_venv_bin.is_file():
        return project_venv_bin

    # Check system PATH
    sys_piper = shutil.which("piper")
    if sys_piper:
        return Path(sys_piper)

    # Fallback to project_venv_bin even if not found yet
    return project_venv_bin

def get_ffmpeg_executable() -> Path:
    """Find the FFmpeg executable."""
    env_override = os.environ.get("FFMPEG_EXECUTABLE")
    if env_override and Path(env_override).is_file():
        return Path(env_override)

    sys_ffmpeg = shutil.which("ffmpeg")
    if sys_ffmpeg:
        return Path(sys_ffmpeg)

    return Path("/usr/bin/ffmpeg")

def ensure_directories() -> None:
    """Ensure core project directories exist."""
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
