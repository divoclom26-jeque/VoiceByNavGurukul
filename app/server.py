import asyncio
import json
import logging
import os
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.core.audio_pipeline import AudioPipeline
from app.core.project_manager import Project, ProjectManager, TextBlock
from app.core.text_processor import TextProcessor
from app.tts import (
    KokoroTTSEngine,
    PiperTTSEngine,
    download_piper_voice,
    get_remote_voices_catalog,
    list_local_voices,
)
from app.utils.atomic_audio import validate_wav_file
from app.utils.paths import PROJECT_ROOT, PROJECTS_DIR

logger = logging.getLogger(__name__)

app = FastAPI(title="Voice Studio AI API")

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pipeline = AudioPipeline()


# Models for requests
class CreateProjectRequest(BaseModel):
    name: str
    text: str
    voice_key: str
    speed: float = 1.0
    max_chars: int = 280


class UpdateBlockRequest(BaseModel):
    text: Optional[str] = None
    voice_key: Optional[str] = None
    speed: Optional[float] = None


class MasterAudioRequest(BaseModel):
    format: str = "wav"  # "wav", "mp3", "m4b", "flac"
    pause_ms: int = 350
    normalize: bool = True
    music_file: Optional[str] = None
    music_volume: float = 0.22
    ducking_ratio: float = 6.0
    title: Optional[str] = None
    author: Optional[str] = None
    narrator: Optional[str] = None
    cover_image: Optional[str] = None


class TestVoiceRequest(BaseModel):
    voice_key: str
    speed: float = 1.0


# In-memory progress tracker for active synthesis tasks
_ACTIVE_TASKS: Dict[str, Dict[str, Any]] = {}


@app.get("/api/voices")
def get_voices():
    """Get installed voices and remote catalog."""
    installed = list_local_voices()
    catalog = {}
    try:
        catalog = get_remote_voices_catalog()
    except Exception as e:
        logger.warning(f"Could not fetch remote voices catalog: {e}")

    return {
        "installed": installed,
        "remote_catalog": catalog,
        "total_installed": len(installed),
    }


@app.post("/api/voices/download")
def download_voice(payload: Dict[str, str], background_tasks: BackgroundTasks):
    voice_key = payload.get("voice_key")
    if not voice_key:
        raise HTTPException(status_code=400, detail="voice_key is required")

    task_id = f"dl_{voice_key}"
    _ACTIVE_TASKS[task_id] = {"status": "downloading", "progress": 0, "voice_key": voice_key}

    def _dl():
        try:
            download_piper_voice(voice_key)
            _ACTIVE_TASKS[task_id] = {"status": "completed", "progress": 100, "voice_key": voice_key}
        except Exception as e:
            _ACTIVE_TASKS[task_id] = {"status": "failed", "error": str(e), "voice_key": voice_key}

    background_tasks.add_task(_dl)
    return {"task_id": task_id, "status": "started"}


@app.get("/api/tasks/{task_id}")
def get_task_status(task_id: str):
    task = _ACTIVE_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.post("/api/voices/test")
def test_voice_sample(payload: TestVoiceRequest):
    """Generate a quick 2-second audio sample for preview."""
    voices = {v["key"]: v for v in list_local_voices()}
    if payload.voice_key not in voices:
        raise HTTPException(status_code=404, detail="Voice not found")

    voice_cfg = dict(voices[payload.voice_key])
    voice_cfg["speed"] = payload.speed

    preview_dir = PROJECTS_DIR / "_preview"
    preview_dir.mkdir(parents=True, exist_ok=True)
    out_wav = preview_dir / f"test_{payload.voice_key}.wav"

    sample_text = (
        "नमस्ते! यह आपकी आवाज़ का नमूना है।"
        if payload.voice_key.startswith("hi")
        else "Hello! This is a real-time sample of the selected voice."
    )

    engine = PiperTTSEngine()
    engine.synthesize_to_wav(sample_text, out_wav, voice_cfg)
    return {"audio_url": f"/api/audio?path={out_wav.resolve()}"}


@app.get("/api/projects")
def list_projects():
    return ProjectManager.list_projects()


@app.post("/api/projects/create")
def create_project(payload: CreateProjectRequest):
    proj = ProjectManager.create_project(
        name=payload.name,
        text=payload.text,
        voice_key=payload.voice_key,
        speed=payload.speed,
        max_chars=payload.max_chars,
    )
    return {
        "slug": proj.project_dir.name,
        "name": proj.name,
        "blocks": [b.__dict__ for b in proj.blocks],
        "voice_key": proj.voice_key,
    }


@app.get("/api/projects/{slug}")
def get_project(slug: str):
    p_dir = PROJECTS_DIR / slug
    if not p_dir.is_dir():
        raise HTTPException(status_code=404, detail="Project not found")

    proj = Project.load(p_dir)
    return {
        "slug": slug,
        "name": proj.name,
        "voice_key": proj.voice_key,
        "speed": proj.speed,
        "blocks": [b.__dict__ for b in proj.blocks],
        "metadata": proj.metadata,
        "exports": [f.name for f in (proj.exports_dir).glob("*") if f.is_file()],
    }


@app.post("/api/projects/{slug}/synthesize")
def synthesize_project(slug: str, background_tasks: BackgroundTasks):
    p_dir = PROJECTS_DIR / slug
    if not p_dir.is_dir():
        raise HTTPException(status_code=404, detail="Project not found")

    proj = Project.load(p_dir)
    task_id = f"syn_{slug}"
    _ACTIVE_TASKS[task_id] = {
        "status": "running",
        "current": 0,
        "total": len(proj.blocks),
        "message": "Starting synthesis...",
    }

    def _run():
        def progress(cur, tot, msg):
            _ACTIVE_TASKS[task_id] = {
                "status": "running",
                "current": cur,
                "total": tot,
                "message": msg,
            }

        try:
            proj.synthesize_all(progress_callback=progress)
            # Build initial master WAV
            master_file = proj.build_master_audio(output_format="wav", pause_ms=350, normalize=True)
            _ACTIVE_TASKS[task_id] = {
                "status": "completed",
                "current": len(proj.blocks),
                "total": len(proj.blocks),
                "message": "Complete!",
                "master_url": f"/api/audio?path={master_file.resolve()}",
            }
        except Exception as e:
            _ACTIVE_TASKS[task_id] = {"status": "failed", "error": str(e)}

    background_tasks.add_task(_run)
    return {"task_id": task_id, "status": "started"}


@app.post("/api/projects/{slug}/block/{block_id}")
def update_and_render_block(slug: str, block_id: int, payload: UpdateBlockRequest):
    p_dir = PROJECTS_DIR / slug
    if not p_dir.is_dir():
        raise HTTPException(status_code=404, detail="Project not found")

    proj = Project.load(p_dir)
    if payload.text is not None:
        proj.update_block_text(block_id, payload.text)
    if payload.voice_key is not None or payload.speed is not None:
        proj.assign_block_voice(block_id, voice_key=payload.voice_key, speed=payload.speed)

    updated_block = proj.synthesize_block(block_id)
    audio_full = proj.project_dir / updated_block.audio_file if updated_block.audio_file else None

    return {
        "block": updated_block.__dict__,
        "audio_url": f"/api/audio?path={audio_full.resolve()}" if audio_full and audio_full.is_file() else None,
    }


@app.post("/api/projects/{slug}/repack")
def fast_repack_master(slug: str):
    p_dir = PROJECTS_DIR / slug
    if not p_dir.is_dir():
        raise HTTPException(status_code=404, detail="Project not found")

    proj = Project.load(p_dir)
    master_wav = proj.build_master_audio(output_format="wav", pause_ms=350, normalize=True)
    return {
        "master_url": f"/api/audio?path={master_wav.resolve()}",
        "name": master_wav.name,
    }


@app.post("/api/projects/{slug}/produce_master")
def produce_master_audio(slug: str, payload: MasterAudioRequest):
    p_dir = PROJECTS_DIR / slug
    if not p_dir.is_dir():
        raise HTTPException(status_code=404, detail="Project not found")

    proj = Project.load(p_dir)
    speech_master = proj.build_master_audio(output_format="wav", pause_ms=payload.pause_ms, normalize=payload.normalize)
    active_track = speech_master

    # Background music mixing if provided
    if payload.music_file and Path(payload.music_file).is_file():
        mixed_wav = proj.exports_dir / f"{proj.name}_mixed.wav"
        pipeline.mix_background_music(
            speech_wav=speech_master,
            music_file=Path(payload.music_file),
            output_wav=mixed_wav,
            music_volume=payload.music_volume,
            ducking_ratio=payload.ducking_ratio,
        )
        active_track = mixed_wav

    metadata = {
        "title": payload.title or proj.name,
        "artist": payload.author or "Voice Studio AI",
        "album": payload.title or proj.name,
        "composer": payload.narrator or proj.voice_key,
    }

    cover_img = Path(payload.cover_image) if payload.cover_image and Path(payload.cover_image).is_file() else None

    # Chapters
    chapters = []
    cur_ms = 0
    for i, b in enumerate(proj.blocks):
        dur_ms = int(b.duration * 1000)
        chapters.append({
            "start_ms": cur_ms,
            "end_ms": cur_ms + dur_ms,
            "title": f"Chapter {i+1}: {b.text[:30]}",
        })
        cur_ms += dur_ms + payload.pause_ms

    fmt = payload.format.lower()
    final_file = None
    if fmt == "m4b":
        final_file = proj.exports_dir / f"{proj.name}_audiobook.m4b"
        pipeline.export_to_m4b(active_track, final_file, metadata=metadata, chapters=chapters, cover_image=cover_img)
    elif fmt == "mp3":
        final_file = proj.exports_dir / f"{proj.name}_podcast.mp3"
        pipeline.export_to_mp3(active_track, final_file, metadata=metadata, cover_image=cover_img)
    elif fmt == "flac":
        final_file = proj.exports_dir / f"{proj.name}_master.flac"
        pipeline.export_to_flac(active_track, final_file, metadata=metadata)
    else:
        final_file = proj.exports_dir / f"{proj.name}_master.wav"
        if active_track != final_file:
            shutil.copy2(active_track, final_file)

    return {
        "file_url": f"/api/audio?path={final_file.resolve()}",
        "filename": final_file.name,
        "format": fmt.upper(),
    }


@app.get("/api/audio")
def stream_audio(request: Request, path: str):
    """Stream audio with HTTP 206 Partial Content support for seeking in WaveSurfer.js."""
    file_path = Path(path).resolve()
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Audio file not found")

    file_size = file_path.stat().st_size
    range_header = request.headers.get("range")

    content_type = "audio/wav"
    if file_path.suffix.lower() == ".mp3":
        content_type = "audio/mpeg"
    elif file_path.suffix.lower() == ".m4b":
        content_type = "audio/mp4"
    elif file_path.suffix.lower() == ".flac":
        content_type = "audio/flac"

    if not range_header:
        return FileResponse(file_path, media_type=content_type)

    # Parse range header
    byte_range = range_header.replace("bytes=", "").split("-")
    start = int(byte_range[0])
    end = int(byte_range[1]) if byte_range[1] else file_size - 1
    content_length = (end - start) + 1

    def iterfile():
        with open(file_path, "rb") as f:
            f.seek(start)
            bytes_left = content_length
            while bytes_left > 0:
                chunk_size = min(65536, bytes_left)
                data = f.read(chunk_size)
                if not data:
                    break
                bytes_left -= len(data)
                yield data

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(content_length),
        "Content-Type": content_type,
    }

    return StreamingResponse(iterfile(), status_code=206, headers=headers)


# Mount static files if frontend/dist exists
frontend_dist = PROJECT_ROOT / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="static")
