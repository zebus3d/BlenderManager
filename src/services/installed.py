"""Escaneo de las versiones de Blender ya extraídas en la carpeta destino.

Las builds oficiales se descomprimen en carpetas con un nombre del estilo
``blender-4.5.13-linux-x64``. De ahí sacamos la versión y localizamos el
ejecutable, que cambia según la plataforma.
"""

import re
from pathlib import Path

from model.build import InstalledBuild, version_tuple

# Captura la versión del nombre de la carpeta, por ejemplo 4.5.13.
VERSION_RE = re.compile(r"blender[-_ ]?(\d+\.\d+(?:\.\d+)?)", re.IGNORECASE)


def _executable_for(directory: Path, platform: str):
    """Busca el ejecutable de Blender dentro de una carpeta (y sus subcarpetas)."""
    if not directory.is_dir():
        return None
    if platform == "windows":
        candidate = directory / "blender.exe"
    elif platform == "darwin":
        # En macOS el binario va dentro del bundle .app.
        candidate = directory / "Blender.app" / "Contents" / "MacOS" / "Blender"
        if not candidate.is_file():
            candidate = directory / "blender"
    else:
        candidate = directory / "blender"
    if candidate.is_file():
        return candidate
    # Algunas builds anidan la carpeta, así que descendemos un nivel.
    for child in sorted(directory.iterdir()):
        if child.is_dir():
            found = _executable_for(child, platform)
            if found is not None:
                return found
    return None


def scan(dest_folder, platform: str):
    """Devuelve las versiones instaladas, ordenadas de más nueva a más antigua."""
    root = Path(dest_folder).expanduser()
    results = []
    if not root.is_dir():
        return results
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        match = VERSION_RE.search(entry.name)
        if not match:
            # Ignoramos carpetas que no son de Blender (archivos temporales, etc.).
            continue
        executable = _executable_for(entry, platform)
        results.append(
            InstalledBuild(
                name=entry.name,
                path=entry,
                version=match.group(1),
                executable=executable,
            )
        )
    results.sort(key=lambda build: version_tuple(build.version), reverse=True)
    return results


def is_version_installed(installed, version: str) -> bool:
    """Comprueba si una versión concreta ya está instalada."""
    target = version_tuple(version)
    return any(version_tuple(build.version) == target for build in installed)
