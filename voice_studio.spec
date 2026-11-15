# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys

block_cipher = None

project_dir = Path.cwd()

datas = [
    (str(project_dir / "app" / "ui" / "styles.qss"), "app/ui"),
    (str(project_dir / "assets" / "icon.png"), "assets"),
    (str(project_dir / "assets" / "icon.svg"), "assets"),
]

hiddenimports = [
    "PySide6.QtMultimedia",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "soundfile",
    "mutagen",
    "num2words",
    "kokoro_onnx",
    "onnxruntime",
    "numpy",
    "requests",
    "tqdm",
]

a = Analysis(
    ["main.py"],
    pathex=[str(project_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VoiceStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # Set to True so CLI flags (voices, speak, etc.) can be used as well
    icon=str(project_dir / "assets" / "icon.png"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="VoiceStudio",
)
