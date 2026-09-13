# -*- mode: python ; coding: utf-8 -*-
"""Especificación de PyInstaller para empaquetar Blender Manager.

Genera un paquete "one-folder" (no un único archivo) porque es más rápido de
arrancar y más fácil de depurar que `--onefile`. En macOS además se crea el
bundle .app.

Uso:
    pyinstaller --clean --noconfirm packaging/blendermanager.spec \
        --distpath dist --workpath build
"""

import re
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / "src"

# La versión vive en src/version.py; el CI la reescribe desde el tag antes de
# compilar (packaging/inject_version.py) y genera el recurso de versión de
# Windows a partir de ella.
_version_match = re.search(
    r'__version__\s*=\s*"([^"]+)"',
    (SRC / "version.py").read_text(encoding="utf-8"),
)
APP_VERSION = _version_match.group(1) if _version_match else "0.0.0"
VERSION_INFO = ROOT / "packaging" / "version_info.txt"

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
    # Recurso de versión del .exe (solo aplica en Windows).
    version=str(VERSION_INFO) if VERSION_INFO.is_file() else None,
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
            "CFBundleShortVersionString": APP_VERSION,
            "CFBundleVersion": APP_VERSION,
        },
    )
