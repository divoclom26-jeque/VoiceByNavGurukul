import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import urllib.request
import requests
from tqdm import tqdm

from app.utils.paths import VOICES_DIR

logger = logging.getLogger(__name__)

HF_PIPER_VOICES_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
HF_PIPER_VOICES_JSON = "https://huggingface.co/rhasspy/piper-voices/raw/main/voices.json"

# In-memory cache for voices catalog
_VOICES_CATALOG_CACHE: Optional[Dict[str, Any]] = None


def get_remote_voices_catalog(force_refresh: bool = False) -> Dict[str, Any]:
    """Fetch the online voices.json catalog from Hugging Face."""
    global _VOICES_CATALOG_CACHE
    if _VOICES_CATALOG_CACHE is not None and not force_refresh:
        return _VOICES_CATALOG_CACHE

    catalog_cache_file = VOICES_DIR / ".catalog_cache.json"
    if not force_refresh and catalog_cache_file.is_file():
        try:
            with open(catalog_cache_file, "r", encoding="utf-8") as f:
                _VOICES_CATALOG_CACHE = json.load(f)
                return _VOICES_CATALOG_CACHE
        except Exception:
            pass

    response = requests.get(HF_PIPER_VOICES_JSON, timeout=15)
    response.raise_for_status()
    catalog = response.json()
    _VOICES_CATALOG_CACHE = catalog

    try:
        VOICES_DIR.mkdir(parents=True, exist_ok=True)
        with open(catalog_cache_file, "w", encoding="utf-8") as f:
            json.dump(catalog, f)
    except Exception as e:
        logger.warning(f"Could not save voices catalog cache: {e}")

    return catalog


def list_local_voices(voices_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Scan the local voices directory and return all installed models."""
    target_dir = voices_dir or VOICES_DIR
    if not target_dir.is_dir():
        return []

    installed_voices = []
    # Search for all .onnx files
    for onnx_file in sorted(target_dir.glob("*.onnx")):
        # Look for corresponding .onnx.json or .json
        json_file = onnx_file.with_suffix(".onnx.json")
        if not json_file.is_file():
            json_file = onnx_file.with_suffix(".json")

        if not json_file.is_file():
            continue

        try:
            with open(json_file, "r", encoding="utf-8") as f:
                config_data = json.load(f)
        except Exception as e:
            logger.warning(f"Could not load config for {onnx_file}: {e}")
            config_data = {}

        audio_cfg = config_data.get("audio", {})
        sample_rate = audio_cfg.get("sample_rate", 22050)
        speaker_id_map = config_data.get("speaker_id_map", {})
        num_speakers = config_data.get("num_speakers", len(speaker_id_map) or 1)

        voice_key = onnx_file.stem
        # Extract language code if naming follows xx_YY-...
        lang = voice_key.split("-")[0] if "-" in voice_key else "unknown"

        installed_voices.append({
            "key": voice_key,
            "name": onnx_file.stem,
            "language": lang,
            "model_path": str(onnx_file.resolve()),
            "config_path": str(json_file.resolve()),
            "sample_rate": sample_rate,
            "num_speakers": num_speakers,
            "speakers": list(speaker_id_map.keys()) if speaker_id_map else ["default"],
            "size_mb": round(onnx_file.stat().st_size / (1024 * 1024), 2),
        })

    return installed_voices


def download_file_with_progress(
    url: str,
    dest_path: Path,
    description: str = "Downloading",
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> None:
    """Download a file with streaming progress to a temporary file before renaming."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest_path.with_suffix(dest_path.suffix + ".download")

    resp = requests.get(url, stream=True, timeout=30)
    resp.raise_for_status()
    total_size = int(resp.headers.get("content-length", 0))

    bytes_downloaded = 0
    with open(temp_path, "wb") as f, tqdm(
        total=total_size,
        unit="B",
        unit_scale=True,
        desc=description,
        disable=progress_callback is not None,
    ) as pbar:
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)
                bytes_downloaded += len(chunk)
                pbar.update(len(chunk))
                if progress_callback:
                    progress_callback(bytes_downloaded, total_size)

    temp_path.replace(dest_path)


def download_piper_voice(
    voice_key: str,
    target_dir: Optional[Path] = None,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
) -> Dict[str, Path]:
    """Download a Piper voice (.onnx and .onnx.json) by key from HuggingFace.
    
    Example keys: 'en_US-lessac-low', 'en_US-lessac-medium', 'hi_IN-pratham-medium'
    """
    dest_dir = target_dir or VOICES_DIR
    catalog = get_remote_voices_catalog()

    if voice_key not in catalog:
        raise ValueError(
            f"Voice key '{voice_key}' not found in Piper catalog. "
            f"Available sample keys: 'en_US-lessac-low', 'en_US-lessac-medium', 'hi_IN-pratham-medium'"
        )

    voice_entry = catalog[voice_key]
    files_dict = voice_entry.get("files", {})

    onnx_rel = None
    json_rel = None
    for file_rel in files_dict.keys():
        if file_rel.endswith(".onnx"):
            onnx_rel = file_rel
        elif file_rel.endswith(".onnx.json"):
            json_rel = file_rel

    if not onnx_rel or not json_rel:
        raise RuntimeError(f"Could not find .onnx and .onnx.json files for voice {voice_key}")

    target_onnx = dest_dir / f"{voice_key}.onnx"
    target_json = dest_dir / f"{voice_key}.onnx.json"

    # 1. Download ONNX config (small, few KB)
    json_url = f"{HF_PIPER_VOICES_BASE}/{json_rel}"
    download_file_with_progress(
        json_url,
        target_json,
        description=f"Downloading {voice_key} config",
        progress_callback=(lambda cur, tot: progress_callback("config", cur, tot)) if progress_callback else None,
    )

    # 2. Download ONNX model (approx 25MB - 65MB)
    onnx_url = f"{HF_PIPER_VOICES_BASE}/{onnx_rel}"
    download_file_with_progress(
        onnx_url,
        target_onnx,
        description=f"Downloading {voice_key} model",
        progress_callback=(lambda cur, tot: progress_callback("model", cur, tot)) if progress_callback else None,
    )

    return {"model_path": target_onnx, "config_path": target_json}
