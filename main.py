#!/usr/bin/env python3
"""Main Entry Point for Local Voice Engine Studio (CLI & Engine)."""
import argparse
import sys
from pathlib import Path

from app.tts import (
    PiperTTSEngine,
    download_piper_voice,
    get_remote_voices_catalog,
    list_local_voices,
)
from app.utils.atomic_audio import validate_wav_file
from app.utils.paths import ensure_directories, get_piper_executable


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
    # Determine text
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

    # Check voices
    voices = list_local_voices()
    if not voices:
        print("[!] No voice models found locally. Auto-downloading 'en_US-lessac-low'...")
        download_piper_voice("en_US-lessac-low")
        voices = list_local_voices()

    # Find chosen voice
    voice_map = {v["key"]: v for v in voices}
    selected_voice = None
    if args.voice:
        if args.voice in voice_map:
            selected_voice = voice_map[args.voice]
        else:
            # Check partial match
            candidates = [v for k, v in voice_map.items() if args.voice.lower() in k.lower()]
            if candidates:
                selected_voice = candidates[0]
            else:
                print(f"[!] Voice '{args.voice}' not found locally. Available: {list(voice_map.keys())}")
                sys.exit(1)
    else:
        selected_voice = voices[0]

    # Configure voice config
    voice_config = dict(selected_voice)
    voice_config["speed"] = args.speed
    if args.speaker is not None:
        voice_config["speaker"] = args.speaker

    output_path = Path(args.output).resolve()
    print(f"[*] Synthesizing using voice: {selected_voice['key']} (speed: {args.speed}x)")
    print(f"    Output: {output_path}")

    engine = PiperTTSEngine()
    try:
        engine.synthesize_to_wav(text, output_path, voice_config)
        info = validate_wav_file(output_path)
        print(f"[+] Success! Audio saved to: {output_path}")
        print(f"    Duration:    {info['duration']:.2f} seconds")
        print(f"    Sample Rate: {info['framerate']} Hz")
        print(f"    Channels:    {info['channels']}")
        print(f"    File Size:   {info['size_bytes'] / 1024:.1f} KB\n")
    except Exception as e:
        print(f"[!] Synthesis failed: {e}")
        sys.exit(1)


def main():
    ensure_directories()
    parser = argparse.ArgumentParser(
        description="Local Voice Engine Studio - High-Performance Offline Text-to-Voice",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

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

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
