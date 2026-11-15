#!/usr/bin/env bash
# Convenience launcher script for Local Voice Engine Studio
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d ".venv" ]; then
    echo "[*] Creating virtual environment..."
    uv venv --python 3.11 .venv
    echo "[*] Installing dependencies..."
    uv pip install --python .venv -r requirements.txt
fi

if [ ! -d "frontend/dist" ]; then
    echo "[*] Building modern React frontend..."
    cd frontend && npm install && npm run build && cd ..
fi

source .venv/bin/activate
python main.py "$@"
