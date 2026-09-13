"""Ajustes persistentes de la aplicación.

Prioridad de ubicación:

1. **Modo portable**: si hay un archivo marcador (``portable``, ``portable.txt``
   o ``.portable``) junto al ejecutable, los ajustes viven ahí. Ideal para
   llevar la aplicación en un pendrive.
2. **Modo normal**: en la carpeta de configuración del usuario
   (XDG en Linux, AppData en Windows, Application Support en macOS).
"""

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from paths import APP_DIR

APP_NAME = "BlenderManager"
PORTABLE_MARKERS = ("portable", "portable.txt", ".portable")


def write_json_atomic(path: Path, payload, indent=None) -> Path:
    """Guarda un JSON sin dejar el archivo a medias si algo falla.

    Escribimos primero en un ``.tmp`` al lado y solo entonces lo movemos encima
    del definitivo: ``os.replace`` es atómico dentro del mismo sistema de
    archivos, así que un corte de luz o un disco lleno dejan intacto el
    contenido anterior en lugar de un JSON truncado.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=indent), encoding="utf-8")
    os.replace(temporary, path)
    return path


def config_dir() -> Path:
    """Devuelve la carpeta donde se guardan los ajustes."""
    for marker in PORTABLE_MARKERS:
        if (APP_DIR / marker).exists():
            return APP_DIR
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    if sys.platform.startswith("darwin"):
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_NAME.lower()


def is_portable() -> bool:
    return config_dir() == APP_DIR


def cache_dir() -> Path:
    """Carpeta para el caché del listado y los registros (logs)."""
    if is_portable():
        return APP_DIR / "cache"
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_NAME / "cache"
    if sys.platform.startswith("darwin"):
        return Path.home() / "Library" / "Caches" / APP_NAME
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / APP_NAME.lower()


def default_destination() -> Path:
    """Carpeta de descargas propuesta la primera vez."""
    return Path.home() / "Descargas" / "Blenders"


@dataclass
class Settings:
    dest_folder: str = ""
    language: str = "auto"
    delete_archive: bool = True
    launch_args: str = ""
    layout_mode: str = "grid"
    zoom: float = 1.0
    auto_update: bool = True
    window_width: int = 0
    window_height: int = 0

    @classmethod
    def load(cls) -> "Settings":
        path = config_dir() / "settings.json"
        data = {}
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                # Si el archivo está corrupto preferimos valores por defecto
                # antes que impedir el arranque.
                data = {}
        settings = cls(
            dest_folder=str(data.get("dest_folder") or ""),
            language=str(data.get("language") or "auto"),
            delete_archive=bool(data.get("delete_archive", True)),
            launch_args=str(data.get("launch_args") or ""),
            layout_mode=str(data.get("layout_mode") or "grid"),
            zoom=float(data.get("zoom") or 1.0),
            auto_update=bool(data.get("auto_update", True)),
            window_width=int(data.get("window_width") or 0),
            window_height=int(data.get("window_height") or 0),
        )
        if not settings.dest_folder:
            settings.dest_folder = str(default_destination())
        return settings

    def save(self) -> Path:
        return write_json_atomic(config_dir() / "settings.json", asdict(self), indent=2)
