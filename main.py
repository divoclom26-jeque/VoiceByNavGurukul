#!/usr/bin/env python3
"""Main Entry Point for Local Voice Engine Studio (CLI & Engine)."""
import argparse
import sys
from pathlib import Path

from app.core import AudioPipeline, Project, ProjectManager, TextProcessor
from app.tts import (
    PiperTTSEngine,
    download_piper_voice,
    get_remote_voices_catalog,
    list_local_voices,
)
from app.utils.atomic_audio import validate_wav_file
from app.utils.paths import PROJECTS_DIR, ensure_directories


def cmd_voices(args):
    """List installed local voice models."""
    voices = list_local_voices()
    if not voices:
        print("\n[!] No local voice models found in models/voices/.")
        print("    Download one with: python main.py download --voice en_US-lessac-low")
        print("    Or Hindi voice with: python main.py download --voice hi_IN-pratham-medium\n")
        return

    print(f"\n[+] Installed Voice Models ({len(voices)}):")
    print("-" * 75)
    print(f"{'KEY':<26} {'LANG':<10} {'RATE':<8} {'SPEAKERS':<10} {'SIZE':<8}")
    print("-" * 75)
    for v in voices:
        print(f"{v['key']:<26} {v['language']:<10} {v['sample_rate']:<8} {v['num_speakers']:<10} {v['size_mb']} MB")
    print("-" * 75)
    print()


def cmd_catalog(args):
    """Search or list available remote voices."""
    print("[*] Fetching catalog from Hugging Face...")
    try:
        catalog = get_remote_voices_catalog()
    except Exception as e:
        print(f"[!] Failed to fetch catalog: {e}")
        return

    query = (args.search or "").lower().strip()
    matches = []
    for key, data in catalog.items():
        lang_code = data.get("language", {}).get("code", "")
        lang_name = data.get("language", {}).get("name_english", "")
        quality = data.get("quality", "")
        if not query or query in key.lower() or query in lang_code.lower() or query in lang_name.lower():
            matches.append((key, lang_code, quality, lang_name))

    print(f"\n[+] Available Remote Voices ({len(matches)} matches):")
    print("-" * 80)
    print(f"{'VOICE KEY':<30} {'LANG':<10} {'QUALITY':<12} {'NAME':<20}")
    print("-" * 80)
    for k, lang, q, name in matches[:args.limit]:
        print(f"{k:<30} {lang:<10} {q:<12} {name:<20}")
    if len(matches) > args.limit:
        print(f"... and {len(matches) - args.limit} more. Filter with: python main.py catalog --search <query>")
    print("-" * 80)
    print()


def cmd_download(args):
    """Download a voice from Hugging Face."""
    voice_key = args.voice
    print(f"[*] Downloading voice model: {voice_key}")
    try:
        res = download_piper_voice(voice_key)
        print(f"[+] Download complete!")
        print(f"    Model:  {res['model_path']}")
        print(f"    Config: {res['config_path']}\n")
    except Exception as e:
        print(f"[!] Download failed: {e}")
        sys.exit(1)


def cmd_synthesize(args):
    """Synthesize text to WAV file."""
    if args.file:
        file_path = Path(args.file)
        if not file_path.is_file():
            print(f"[!] File not found: {file_path}")
            sys.exit(1)
        text = file_path.read_text(encoding="utf-8")
    elif args.text:
        text = args.text
    else:
        print("[!] Error: Either --text or --file must be specified.")
        sys.exit(1)

    voices = list_local_voices()
    if not voices:
        print("[!] No voice models found locally. Auto-downloading 'en_US-lessac-low'...")
        download_piper_voice("en_US-lessac-low")
        voices = list_local_voices()

    voice_map = {v["key"]: v for v in voices}
    selected_voice = None
    if args.voice:
        if args.voice in voice_map:
            selected_voice = voice_map[args.voice]
        else:
            candidates = [v for k, v in voice_map.items() if args.voice.lower() in k.lower()]
            if candidates:
                selected_voice = candidates[0]
            else:
                print(f"[!] Voice '{args.voice}' not found locally. Available: {list(voice_map.keys())}")
                sys.exit(1)
    else:
        selected_voice = voices[0]

    voice_config = dict(selected_voice)
    voice_config["speed"] = args.speed
    if args.speaker is not None:
        voice_config["speaker"] = args.speaker

    output_path = Path(args.output).resolve()
    print(f"[*] Synthesizing using voice: {selected_voice['key']} (speed: {args.speed}x)")
    print(f"    Output: {output_path}")

    # Process text through clean_text_for_speech
    cleaned_text = TextProcessor.clean_text_for_speech(text)

    engine = PiperTTSEngine()
    try:
        engine.synthesize_to_wav(cleaned_text, output_path, voice_config)
        info = validate_wav_file(output_path)
        print(f"[+] Success! Audio saved to: {output_path}")
        print(f"    Duration:    {info['duration']:.2f} seconds")
        print(f"    Sample Rate: {info['framerate']} Hz")
        print(f"    Channels:    {info['channels']}")
        print(f"    File Size:   {info['size_bytes'] / 1024:.1f} KB\n")
    except Exception as e:
        print(f"[!] Synthesis failed: {e}")
        sys.exit(1)


def cmd_chunk(args):
    """Preview text cleaning and chunking."""
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    else:
        text = args.text or ""

    blocks = TextProcessor.split_into_blocks(text, max_chars=args.max_chars)
    print(f"\n[+] Text broken into {len(blocks)} blocks (max_chars={args.max_chars}):")
    print("=" * 70)
    for i, b in enumerate(blocks, 1):
        print(f"[{i:02d}] ({len(b)} chars): {b}")
    print("=" * 70)
    print()


def cmd_create_project(args):
    """Create a long-form audio production project."""
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    else:
        text = args.text or ""

    voices = list_local_voices()
    voice_keys = [v["key"] for v in voices]
    voice_key = args.voice
    if not voice_key or voice_key not in voice_keys:
        if voices:
            voice_key = voices[0]["key"]
            print(f"[*] Using default voice: {voice_key}")
        else:
            print("[!] Please download a voice first: python main.py download -v en_US-lessac-low")
            sys.exit(1)

    project = ProjectManager.create_project(
        name=args.name,
        text=text,
        voice_key=voice_key,
        speed=args.speed,
        max_chars=args.max_chars,
    )
    print(f"\n[+] Created project: '{project.name}'")
    print(f"    Location: {project.project_dir}")
    print(f"    Total Blocks: {len(project.blocks)}")
    print(f"    To render all blocks, run: python main.py render-project --name {project.project_dir.name}\n")


def cmd_render_project(args):
    """Render all blocks of a project and build master audio."""
    project_dir = PROJECTS_DIR / args.name
    if not project_dir.is_dir():
        print(f"[!] Project directory not found: {project_dir}")
        sys.exit(1)

    project = Project.load(project_dir)
    print(f"\n[*] Rendering Project: {project.name} ({len(project.blocks)} blocks, Voice: {project.voice_key})")

    def progress(cur, tot, msg):
        print(f"    [{cur}/{tot}] {msg}")

    project.synthesize_all(progress_callback=progress, force_rebuild=args.force)

    print("\n[*] Building master audio (pause: 350ms, loudnorm: True)...")
    fmt = "mp3" if args.mp3 else "wav"
    master_file = project.build_master_audio(output_format=fmt, pause_ms=args.pause)
    info = validate_wav_file(master_file) if fmt == "wav" else {"size_bytes": master_file.stat().st_size}

    print(f"[+] Master Audio Ready: {master_file}")
    if "duration" in info:
        print(f"    Total Duration: {info['duration']:.2f} seconds")
    print(f"    File Size: {info['size_bytes'] / 1024:.1f} KB\n")


def cmd_render_block(args):
    """Re-synthesize a single block in a project."""
    project_dir = PROJECTS_DIR / args.name
    project = Project.load(project_dir)

    print(f"[*] Re-synthesizing Block {args.block_id} in {project.name}...")
    block = project.synthesize_block(args.block_id)
    if block.status == "completed":
        print(f"[+] Block {block.id} synthesized successfully!")
        print(f"    Duration: {block.duration:.2f}s")
        print(f"    Audio: {project.project_dir / block.audio_file}\n")
    else:
        print(f"[!] Block {block.id} failed: {block.error_message}\n")


def cmd_list_projects(args):
    """List all user projects."""
    projects = ProjectManager.list_projects()
    if not projects:
        print("\n[!] No projects found in projects/.\n")
        return

    print(f"\n[+] Projects ({len(projects)}):")
    print("-" * 75)
    print(f"{'SLUG':<25} {'NAME':<20} {'VOICE':<20} {'BLOCKS':<8}")
    print("-" * 75)
    for p in projects:
        print(f"{p['id']:<25} {p['name']:<20} {p['voice_key']:<20} {p['blocks']:<8}")
    print("-" * 75)
    print()


def cmd_gui(args):
    """Launch the PySide6 Desktop GUI."""
    try:
        from PySide6.QtWidgets import QApplication
        from app.ui.main_window import MainWindow
    except ImportError as e:
        print(f"[!] PySide6 is required to run the desktop GUI: {e}")
        print("    Install it via: uv pip install --python .venv PySide6")
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setApplicationName("Voice Studio AI")
    app.setOrganizationName("NavGurukul")

    icon_path = Path(__file__).parent / "assets" / "icon.png"
    if icon_path.is_file():
        from PySide6.QtGui import QIcon
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


def main():
    ensure_directories()

    # If no CLI arguments provided, launch GUI directly
    if len(sys.argv) == 1:
        cmd_gui(None)
        return

    parser = argparse.ArgumentParser(
        description="Local Voice Engine Studio - High-Performance Offline Text-to-Voice",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Command: gui
    sub_gui = subparsers.add_parser("gui", help="Launch the PySide6 Desktop GUI")
    sub_gui.set_defaults(func=cmd_gui)

    # Command: voices
    sub_voices = subparsers.add_parser("voices", help="List locally installed voice models")
    sub_voices.set_defaults(func=cmd_voices)

    # Command: catalog
    sub_cat = subparsers.add_parser("catalog", help="Search available remote voices on Hugging Face")
    sub_cat.add_argument("--search", "-s", type=str, default="", help="Search query (e.g. 'en', 'hi', 'medium')")
    sub_cat.add_argument("--limit", "-n", type=int, default=25, help="Max results to display")
    sub_cat.set_defaults(func=cmd_catalog)

    # Command: download
    sub_dl = subparsers.add_parser("download", help="Download a voice model by key")
    sub_dl.add_argument("--voice", "-v", type=str, required=True, help="Voice key (e.g. 'hi_IN-pratham-medium')")
    sub_dl.set_defaults(func=cmd_download)

    # Command: synthesize / speak
    sub_syn = subparsers.add_parser("synthesize", aliases=["speak"], help="Synthesize text to WAV file")
    sub_syn.add_argument("--text", "-t", type=str, help="Text to speak")
    sub_syn.add_argument("--file", "-f", type=str, help="Text file to read")
    sub_syn.add_argument("--voice", "-v", type=str, help="Voice model key or partial name")
    sub_syn.add_argument("--output", "-o", type=str, default="projects/output.wav", help="Output .wav path")
    sub_syn.add_argument("--speed", type=float, default=1.0, help="Speech speed multiplier (0.5 to 2.0)")
    sub_syn.add_argument("--speaker", type=int, default=None, help="Speaker ID for multi-speaker voices")
    sub_syn.set_defaults(func=cmd_synthesize)

    # Command: chunk-text
    sub_chk = subparsers.add_parser("chunk-text", help="Preview text cleaning and chunking")
    sub_chk.add_argument("--text", "-t", type=str, help="Text string")
    sub_chk.add_argument("--file", "-f", type=str, help="Text file to read")
    sub_chk.add_argument("--max-chars", "-m", type=int, default=280, help="Max characters per block")
    sub_chk.set_defaults(func=cmd_chunk)

    # Command: create-project
    sub_cp = subparsers.add_parser("create-project", help="Create a new long-form audio project")
    sub_cp.add_argument("--name", "-n", type=str, required=True, help="Project name")
    sub_cp.add_argument("--file", "-f", type=str, help="Source text/markdown file")
    sub_cp.add_argument("--text", "-t", type=str, help="Source text")
    sub_cp.add_argument("--voice", "-v", type=str, help="Voice key")
    sub_cp.add_argument("--speed", type=float, default=1.0, help="Speech speed")
    sub_cp.add_argument("--max-chars", type=int, default=280, help="Max characters per chunk")
    sub_cp.set_defaults(func=cmd_create_project)

    # Command: render-project
    sub_rp = subparsers.add_parser("render-project", help="Render all blocks of a project and build master audio")
    sub_rp.add_argument("--name", "-n", type=str, required=True, help="Project slug or directory name")
    sub_rp.add_argument("--pause", type=int, default=350, help="Pause duration between chunks in ms")
    sub_rp.add_argument("--mp3", action="store_true", help="Export to MP3 instead of WAV")
    sub_rp.add_argument("--force", action="store_true", help="Force re-rendering completed blocks")
    sub_rp.set_defaults(func=cmd_render_project)

    # Command: render-block
    sub_rb = subparsers.add_parser("render-block", help="Re-synthesize a single block in a project")
    sub_rb.add_argument("--name", "-n", type=str, required=True, help="Project slug or directory name")
    sub_rb.add_argument("--block-id", "-b", type=int, required=True, help="Block ID to synthesize")
    sub_rb.set_defaults(func=cmd_render_block)

    # Command: list-projects
    sub_lp = subparsers.add_parser("list-projects", help="List all projects")
    sub_lp.set_defaults(func=cmd_list_projects)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
