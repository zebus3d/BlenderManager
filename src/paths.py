"""Rutas de la aplicación, tanto en código fuente como empaquetada.

Distinguimos dos ubicaciones:

* ``APP_DIR``: carpeta del ejecutable. En modo portable los ajustes se
  guardan aquí (junto al binario).
* ``RESOURCE_DIR``: carpeta de recursos (``assets``). Cuando el programa va
  empaquetado con PyInstaller, los datos se extraen a ``_MEIPASS``.
"""

import sys
from pathlib import Path


def _app_dir() -> Path:
    # Con PyInstaller, sys.executable es el binario ya compilado.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    # En código fuente: src/paths.py -> subimos dos niveles (src -> raíz).
    return Path(__file__).resolve().parent.parent


def _resource_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", _app_dir()))
    return Path(__file__).resolve().parent


APP_DIR = _app_dir()
RESOURCE_DIR = _resource_dir()
ASSETS_DIR = RESOURCE_DIR / "assets"
