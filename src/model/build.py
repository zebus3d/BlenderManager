"""Modelos de datos: compilaciones disponibles e instaladas.

Se usan dataclasses sencillas para que el resto de la aplicación trabaje con
objetos claros en lugar de diccionarios sueltos.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Versiones de Blender con soporte de larga duración (Long Term Support).
# Las LTS reciben mantenimiento durante varios años, así que merece la pena
# destacarlas en la tienda.
LTS_MINORS = {"2.83", "2.93", "3.3", "3.6", "4.2", "4.5", "5.2"}


def version_tuple(version: str):
    """Convierte '5.2.1' en (5, 2, 1) para poder ordenar y comparar versiones."""
    parts = re.findall(r"\d+", version or "")
    return tuple(int(part) for part in parts) if parts else (0,)


def minor_of(version: str) -> str:
    """Devuelve la rama menor: '5.2.1' -> '5.2' (la clave de las LTS)."""
    parts = (version or "").split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else (version or "")


def human_size(size) -> str:
    """Convierte bytes a un texto legible (por ejemplo, '359.8 MB')."""
    value = float(size or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{value:.0f} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


@dataclass
class Build:
    """Una compilación concreta publicada en los servidores de Blender."""

    version: str
    branch: str
    risk: str
    platform: str
    arch: str
    url: str
    filename: str
    size: int = 0
    checksum: Optional[str] = None
    mtime: int = 0
    # Hash corto del commit con el que se compiló (lo da la API en "hash").
    # Es lo único que distingue dos compilaciones diarias del mismo día a día:
    # todas las alfa de 'main' comparten número de versión.
    build_hash: str = ""

    @property
    def is_lts(self) -> bool:
        # Solo las estables pueden ser LTS.
        return self.risk == "stable" and minor_of(self.version) in LTS_MINORS

    @property
    def sort_key(self):
        # Orden por versión y, a igualdad, por fecha de compilación.
        return (version_tuple(self.version), self.mtime)

    @property
    def human_size(self) -> str:
        return human_size(self.size)


@dataclass
class InstalledBuild:
    """Una versión ya descargada y extraída en la carpeta destino."""

    name: str
    path: Path
    version: str
    executable: Optional[Path] = None
    # Hash de la compilación, leído del marcador que dejamos al instalar.
    # Las carpetas instaladas antes de que existiera el marcador lo traen
    # vacío, y entonces se compara solo por versión (como se hacía siempre).
    build_hash: str = ""

    @property
    def is_lts(self) -> bool:
        return minor_of(self.version) in LTS_MINORS

    @property
    def can_launch(self) -> bool:
        return self.executable is not None
