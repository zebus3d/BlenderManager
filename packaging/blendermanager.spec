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
]

# Módulos de Qt que NO usamos. PySide6-Essentials trae muchos; excluirlos evita
# que PyInstaller arrastre ~100 MB de más (WebEngine, QML, Multimedia...).
# Solo usamos QtCore, QtGui y QtWidgets.
QT_EXCLUDES = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel", "PySide6.QtWebSockets",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.QtQuick3D", "PySide6.QtQuickControls2",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSql",
    "PySide6.QtTest", "PySide6.QtBluetooth", "PySide6.QtNfc",
    "PySide6.QtPositioning", "PySide6.QtSerialPort", "PySide6.QtSensors",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtUiTools",
    "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtStateMachine",
    "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech", "PySide6.QtHttpServer",
    "shiboken6.Shiboken",
]

a = Analysis(
    [str(SRC / "main.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=QT_EXCLUDES,
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
    # UPX puede romper librerías nativas (Qt sobre todo), así que lo desactivamos.
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
