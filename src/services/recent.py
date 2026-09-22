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
class RecentFile:
    """Un ``.blend`` de la lista de recientes.

    ``missing`` marca los que ya no están en esa ruta (movidos o borrados). Se
    devuelven igualmente: si desaparecieran sin más, el usuario no sabría si
    Blender no tiene recientes o si sus ficheros han cambiado de sitio.
    """

    path: Path
    missing: bool = False


@dataclass
class RecentGroup:
    """Los recientes de una serie de Blender.

    ``version`` es la más nueva instalada de esa serie (las versiones de una
    serie comparten carpeta de configuración, así que la lista es la misma).
    """

    series: str
    version: str
    files: list = field(default_factory=list)   # de ``RecentFile``


def recent_files(config) -> list:
    """``RecentFile`` de esa config, el más nuevo primero.

    Se saltan las líneas vacías y las relativas al fichero (``//``). Las rutas
    que ya no existen se devuelven marcadas con ``missing`` (ver
    ``RecentFile``), no se ocultan.
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
        files.append(RecentFile(candidate, missing=not candidate.is_file()))
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
