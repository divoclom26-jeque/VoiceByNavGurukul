"""TTS engine abstraction and adapters."""
from .base import BaseTTSEngine
from .kokoro_engine import KokoroTTSEngine, download_kokoro_model
from .piper_engine import PiperTTSEngine
from .voice_manager import (
    download_piper_voice,
    get_remote_voices_catalog,
    list_local_voices,
)

__all__ = [
    "BaseTTSEngine",
    "PiperTTSEngine",
    "KokoroTTSEngine",
    "download_kokoro_model",
    "list_local_voices",
    "download_piper_voice",
    "get_remote_voices_catalog",
]
