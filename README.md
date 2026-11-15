# 🎙️ Voice Studio AI — Local Text-to-Voice & Audiobook Studio

> **High-Performance, 100% Private, Offline-Capable Desktop Application for Long-Form Audio & Podcast Production.**

Built from scratch using **Python 3.11**, **PySide6 (Qt6)**, **Piper TTS (Rhasspy)**, **Kokoro ONNX (82M)**, and **FFmpeg**.

---

## ✨ Key Features

* **🔒 100% Offline & Private:** Zero cloud dependencies, zero subscriptions, zero API keys. Runs entirely on your local CPU or GPU.
* **🗣️ Dual Local TTS Engines:**
  * **Piper TTS:** Extremely lightweight, real-time CPU synthesis with multilingual support (Hindi, English, etc.).
  * **Kokoro ONNX (82M):** Ultra-realistic neural voice model for studio-grade human speech.
* **✂️ Smart Text Normalizer & Chunker:**
  * Eliminates markdown, code, and non-pronounceable symbols.
  * Expands abbreviations (`Dr.` ➔ `Doctor`, `Prof.` ➔ `Professor`) and currencies (`$50` ➔ `50 dollars`, `₹500` ➔ `500 rupees`).
  * Splits texts safely into 200–280 character blocks respecting multi-language sentence boundaries (English `. ! ?`, Hindi `।`).
* **🔍 Per-Block Review & Dialogue Studio (Phase 4):**
  * View every sentence in an interactive table with status badges and durations.
  * Preview individual blocks with one click.
  * Double-click to edit any typo in block #14 and re-synthesize **only that block**.
  * **⚡ Fast Re-Pack:** Re-stitch the master audio in under 1 second without re-rendering the whole book!
  * **Multi-Voice / Dialogue Assignment:** Assign different voices to different blocks (e.g. Narrator vs. Character A).
* **🎚️ Background Music & Auto-Ducking (Phase 5):**
  * Ambient background music mixing via FFmpeg `sidechaincompress`.
  * **Automatic Ducking:** Music volume drops whenever voice narration speaks and fades out smoothly at the end.
* **📖 Audiobook & Podcast Mastering:**
  * **`.m4b` Audiobooks:** AAC audio with embedded chapter marks, metadata, and book cover art.
  * **`.mp3` Podcasts:** 192kbps MP3 with ID3v2 tags and cover image.
  * **`.wav` / `.flac`:** Lossless studio master archives.
  * **EBU R128 Loudness Normalization (`loudnorm`)**: Broadcast-standard sound levels across speech and music.
* **🖥️ Modern PySide6 Desktop GUI:**
  * Dark theme styling, non-blocking `QThread` workers (UI never hangs), scrubbable audio player, in-app Hugging Face voice gallery.

---

## 🏗️ System Architecture

```
my-voice-studio/
├── app/
│   ├── core/                      # Core audio & text pipeline
│   │   ├── text_processor.py      # Normalization, regex chunking, cleanups
│   │   ├── audio_pipeline.py      # FFmpeg runner, concat, auto-ducking, M4B/MP3
│   │   └── project_manager.py     # Project manifest, per-block editing & re-pack
│   ├── tts/                       # TTS engine abstraction & adapters
│   │   ├── base.py                # BaseTTSEngine abstract interface
│   │   ├── piper_engine.py        # Piper TTS adapter (Fast CPU / ONNX)
│   │   ├── kokoro_engine.py       # Kokoro Neural 82M adapter
│   │   └── voice_manager.py       # Hugging Face catalog & voice downloader
│   ├── ui/                        # Presentation (PySide6 / Qt6)
│   │   ├── main_window.py         # Main window with sidebar navigation
│   │   ├── workers.py             # Background QThread workers
│   │   ├── styles.qss             # Modern dark stylesheet
│   │   └── components/            # Modular widgets:
│   │       ├── editor_widget.py   # Script editor with live metrics
│   │       ├── player_widget.py   # Waveform & playback bar
│   │       ├── block_table.py     # Per-block review & dialogue editor
│   │       ├── mixer_widget.py    # Podcast music mixer & M4B mastering
│   │       ├── voice_gallery.py   # Hugging Face voice model downloader
│   │       └── project_history.py # Projects history & folder explorer
│   └── utils/
│       ├── atomic_audio.py        # Safe audio writing & WAV validation
│       └── paths.py               # Resource & directory resolution
├── assets/                        # App icons (PNG/SVG)
├── models/voices/                 # Local voice weights (.onnx) & configs (.json)
├── projects/                      # User project data, segments, exports
├── scripts/                       # Build & installation scripts
├── tests/                         # Pytest test suite (25 tests)
├── requirements.txt
├── run_dev.sh                     # Linux dev & app launcher
├── main.py                        # Entry point (CLI & GUI)
└── voice_studio.spec              # PyInstaller standalone build spec
```

---

## 🚀 Quick Start

### 1. Launch the Desktop GUI
Simply run the development launcher (it automatically creates the `.venv` and installs dependencies on first launch):
```bash
./run_dev.sh
```

### 2. Desktop Shortcut (Linux)
To install Voice Studio AI into your Linux Application Menu:
```bash
./scripts/install_desktop_shortcut.sh
```

---

## 💻 CLI Commands

Voice Studio AI can also be run entirely from the terminal:

```bash
# List installed local voices
./run_dev.sh voices

# Browse available voices from Hugging Face
./run_dev.sh catalog --search hindi

# Download a voice model
./run_dev.sh download --voice hi_IN-pratham-medium
./run_dev.sh download --voice en_US-lessac-low

# Quick text-to-speech
./run_dev.sh speak --text "Hello world! This is offline AI." --output projects/hello.wav

# Preview text cleaning & chunking
./run_dev.sh chunk-text --text "Doctor Smith invested $500 at 15% interest. He was delighted!"

# Create and render a full audio project
./run_dev.sh create-project --name "Chapter 1" --voice "en_US-lessac-low" --file story.txt
./run_dev.sh render-project --name chapter_1 --mp3

# Re-render a single block
./run_dev.sh render-block --name chapter_1 --block-id 3
```

---

## 🧪 Running Automated Tests

Run the full test suite with Pytest:
```bash
.venv/bin/pytest -v
```
*(All 25 unit and UI tests verify audio generation, text normalizer, auto-ducking, M4B chapters, and Qt widgets)*

---

## 📦 Building Standalone Executable (PyInstaller)

To compile a self-contained, standalone executable:
```bash
./scripts/build_binary.sh
```
The output will be created at:
```
dist/VoiceStudio/VoiceStudio
```

---

## 📄 License
MIT License. Created for offline, private, and high-quality voice production.
