# -*- mode: python ; coding: utf-8 -*-
"""Especificación de PyInstaller para empaquetar Blender Manager.

Genera un paquete "one-folder" (no un único archivo) porque es más rápido de
arrancar y más fácil de depurar que `--onefile`. En macOS además se crea el
bundle .app.

Uso:
    pyinstaller --clean --noconfirm packaging/blendermanager.spec \
        --distpath dist --workpath build
"""

import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / "src"

block_cipher = None

datas = [
    (str(SRC / "assets"), "assets"),
    (str(SRC / "views"), "views"),
]

a = Analysis(
    [str(SRC / "main.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BlenderManager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX puede romper algunas librerías de Kivy/SDL, así que lo desactivamos.
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="BlenderManager",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="BlenderManager.app",
        icon=None,
        bundle_identifier="org.zebus3d.blendermanager",
        info_plist={
            "NSHighResolutionCapable": True,
        },
    )
