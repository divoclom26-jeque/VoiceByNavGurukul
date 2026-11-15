from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.server import app
from app.utils.atomic_audio import write_silence_wav

client = TestClient(app)


def test_server_voices_endpoint():
    response = client.get("/api/voices")
    assert response.status_code == 200
    data = response.json()
    assert "installed" in data
    assert "total_installed" in data
    assert data["total_installed"] >= 1


def test_server_project_lifecycle(tmp_path: Path):
    # 1. Create project
    payload = {
        "name": "API Test Project",
        "text": "Hello from FastAPI testing. Second sentence is here.",
        "voice_key": "en_US-lessac-low",
        "speed": 1.0,
        "max_chars": 50,
    }
    create_res = client.post("/api/projects/create", json=payload)
    assert create_res.status_code == 200
    data = create_res.json()
    slug = data["slug"]
    assert len(data["blocks"]) >= 2

    # 2. Get project details
    get_res = client.get(f"/api/projects/{slug}")
    assert get_res.status_code == 200
    p_data = get_res.json()
    assert p_data["name"] == "API Test Project"

    # 3. Clean up
    from app.utils.paths import PROJECTS_DIR
    import shutil
    p_dir = PROJECTS_DIR / slug
    if p_dir.is_dir():
        shutil.rmtree(p_dir)


def test_server_audio_streaming(tmp_path: Path):
    audio_file = tmp_path / "test_stream.wav"
    write_silence_wav(audio_file, duration_seconds=0.5, sample_rate=16000)

    # Test full fetch
    res = client.get(f"/api/audio?path={audio_file.resolve()}")
    assert res.status_code == 200
    assert len(res.content) > 1000

    # Test range request (HTTP 206) for WaveSurfer.js seeking
    headers = {"Range": "bytes=0-499"}
    res_range = client.get(f"/api/audio?path={audio_file.resolve()}", headers=headers)
    assert res_range.status_code == 206
    assert len(res_range.content) == 500
    assert "bytes 0-499/" in res_range.headers.get("Content-Range", "")
