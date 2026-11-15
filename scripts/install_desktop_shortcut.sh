#!/usr/bin/env bash
# Install Linux Desktop shortcut in ~/.local/share/applications/
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="${HOME}/.local/share/applications"
TARGET_FILE="${TARGET_DIR}/VoiceStudio.desktop"

mkdir -p "$TARGET_DIR"

cat > "$TARGET_FILE" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Voice Studio AI
GenericName=Local Text-to-Voice Audio Studio
Comment=High-performance, private, offline-capable voice synthesis & audiobook production
Exec=${PROJECT_DIR}/run_dev.sh
Icon=${PROJECT_DIR}/assets/icon.png
Path=${PROJECT_DIR}
Terminal=false
Categories=AudioVideo;Audio;AudioVideoEditing;
Keywords=tts;voice;speech;audiobook;podcast;piper;ai;
StartupNotify=true
StartupWMClass=Voice Studio AI
EOF

chmod +x "$TARGET_FILE"
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$TARGET_DIR" || true
fi

echo "[+] Desktop shortcut installed successfully at: $TARGET_FILE"
echo "    You can now launch 'Voice Studio AI' from your desktop application menu!"
