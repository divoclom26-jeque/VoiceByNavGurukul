#!/usr/bin/env bash
# Standalone binary builder using PyInstaller
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

echo "=========================================================="
echo " Building Standalone VoiceStudio Executable (PyInstaller) "
echo "=========================================================="

if [ ! -d ".venv" ]; then
    echo "[!] Virtual environment not found. Run ./run_dev.sh first."
    exit 1
fi

source .venv/bin/activate

echo "[*] Cleaning previous build artifacts..."
rm -rf build dist

echo "[*] Running PyInstaller with voice_studio.spec..."
pyinstaller --clean voice_studio.spec

echo ""
echo "[+] Build complete!"
echo "    Standalone binary output: ${PROJECT_DIR}/dist/VoiceStudio/VoiceStudio"
echo ""
echo "To test the standalone binary:"
echo "    ./dist/VoiceStudio/VoiceStudio voices"
echo "    ./dist/VoiceStudio/VoiceStudio gui"
