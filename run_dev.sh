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

# If running with --web, ensure frontend is built
for arg in "$@"; do
    if [ "$arg" == "--web" ] || [ "$arg" == "--browser" ]; then
        if [ ! -d "frontend/dist" ] && [ -d "frontend" ]; then
            echo "[*] Building React web interface..."
            cd frontend && npm install && npm run build && cd ..
        fi
        break
    fi
done

source .venv/bin/activate
python main.py "$@"
