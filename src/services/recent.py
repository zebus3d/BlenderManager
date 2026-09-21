"""Ficheros ``.blend`` abiertos recientemente, por versión de Blender.

Blender guarda esa lista en ``<config>/recent-files.txt``: una ruta absoluta por
línea, la más reciente primero. Es texto plano, así que se puede leer sin
arrancar Blender. Aquí solo se localiza y se agrupa por serie; abrir el fichero,
revelarlo o lanzarlo es cosa de la interfaz.

Es un módulo de ``services/``: no importa Qt.
"""

from dataclasses import dataclass, field
from pathlib import Path

from model.build import minor_of
from services import blender_config as bc

RECENT_FILE = "recent-files.txt"


@dataclass
class RecentGroup:
    """Los recientes de una serie de Blender.

    ``version`` es la más nueva instalada de esa serie (las versiones de una
    serie comparten carpeta de configuración, así que la lista es la misma).
    """

    series: str
    version: str
    files: list = field(default_factory=list)


def recent_files(config) -> list:
    """Rutas de los ``.blend`` recientes de esa config, la más nueva primero.

    Se saltan las líneas vacías, las relativas al fichero (``//``) y las que ya
    no existen: una lista con ficheros borrados no ayuda a nadie.
    """
    path = Path(config.config_dir) / RECENT_FILE
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    files = []
    for line in text.splitlines():
        entry = line.strip()
        if not entry or entry.startswith("//"):
            continue
        candidate = Path(entry)
        if candidate.is_file():
            files.append(candidate)
    return files


def grouped(installed, platform: str, env=None) -> list:
    """Recientes agrupados por serie, de la más nueva a la más vieja.

    De cada serie se usa la versión más nueva instalada y se lee su config una
    sola vez. Solo se devuelven las series con algún fichero reciente.
    """
    seen = set()
    groups = []
    for entry in installed or []:
        series = minor_of(getattr(entry, "version", "") or "")
        if not series or series in seen:
            continue
        seen.add(series)
        config = bc.config_for(entry.version, platform, env)
        files = recent_files(config)
        if files:
            groups.append(RecentGroup(series=series, version=entry.version,
                                      files=files))
    return groups
