"""Escaneo de las versiones de Blender ya extraídas en la carpeta destino.

Las builds oficiales se descomprimen en carpetas con un nombre del estilo
``blender-4.5.13-linux-x64``. De ahí sacamos la versión y localizamos el
ejecutable, que cambia según la plataforma.

Ese nombre **no** incluye el hash de la compilación, así que dos alfa de
``main`` bajadas en días distintos producen exactamente la misma carpeta. Para
poder distinguirlas dejamos un marcador propio (``MARKER_NAME``) dentro de la
carpeta al instalar, con el hash que nos dio la API.
"""

import json
import re
from collections import namedtuple
from pathlib import Path

from model.build import InstalledBuild, minor_of, version_tuple

# Actualización disponible para una versión instalada.
#   kind == "patch":  misma serie con parche más nuevo (5.2.0 -> 5.2.2).
#   kind == "series": serie estable superior (5.2.x -> 5.3.0).
Update = namedtuple("Update", "entry build kind")

# Captura la versión del nombre de la carpeta, por ejemplo 4.5.13.
VERSION_RE = re.compile(r"blender[-_ ]?(\d+\.\d+(?:\.\d+)?)", re.IGNORECASE)

# Marcador que escribimos al instalar para recordar qué compilación es.
MARKER_NAME = ".blendermanager.json"


def write_marker(folder, build) -> None:
    """Anota dentro de la carpeta instalada de qué compilación viene.

    Si no se puede escribir (carpeta de solo lectura, disco lleno) no pasa
    nada: sin marcador se compara solo por versión, como antes.
    """
    payload = {
        "version": build.version,
        "risk": build.risk,
        "branch": build.branch,
        "hash": build.build_hash,
        "filename": build.filename,
    }
    try:
        (Path(folder) / MARKER_NAME).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass


def read_marker(folder) -> dict:
    """Lee el marcador ``.blendermanager.json`` de una build
    instalada.
    """
    path = Path(folder) / MARKER_NAME
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _executable_for(directory: Path, platform: str, depth: int = 1):
    """Busca el ejecutable de Blender dentro de una carpeta.

    ``depth`` limita cuántos niveles descendemos: el ejecutable está en la
    raíz de la carpeta (o un nivel más adentro si la build viene anidada), y
    sin tope acabaríamos recorriendo el árbol entero de Blender —miles de
    archivos— desde el hilo de la interfaz.
    """
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
    if depth <= 0:
        return None
    # Algunas builds anidan la carpeta, así que descendemos un nivel.
    try:
        children = sorted(directory.iterdir())
    except OSError:
        return None
    for child in children:
        if child.is_dir():
            found = _executable_for(child, platform, depth - 1)
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
        marker = read_marker(entry)
        results.append(
            InstalledBuild(
                name=entry.name,
                path=entry,
                version=str(marker.get("version") or match.group(1)),
                executable=executable,
                build_hash=str(marker.get("hash") or ""),
                branch=str(marker.get("branch") or ""),
            )
        )
    results.sort(key=lambda build: version_tuple(build.version), reverse=True)
    return results


def find_installed(installed, build):
    """Devuelve la instalación que corresponde a ``build``, o None.

    Las estables se identifican por versión: 4.5.13 es 4.5.13 y punto. Las
    diarias/alfa, en cambio, comparten número de versión durante meses, así
    que solo cuentan como instaladas si además coincide el hash anotado en su
    marcador. Una carpeta sin marcador (instalada antes de que existiera) se
    compara solo por versión, como se hacía siempre.
    """
    target = version_tuple(build.version)
    for entry in installed:
        if version_tuple(entry.version) != target:
            continue
        if build.risk != "stable" and entry.build_hash and build.build_hash:
            if entry.build_hash != build.build_hash:
                continue
        return entry
    return None


def is_version_installed(installed, version: str) -> bool:
    """Comprueba si una versión concreta ya está instalada."""
    target = version_tuple(version)
    return any(version_tuple(build.version) == target for build in installed)


def is_experimental(entry) -> bool:
    """True si la instalación viene de una rama experimental.

    Las ramas normales se llaman ``main`` (diarias) o ``v45``, ``v52``...
    (estables). Cualquier otro nombre es una rama de funciones nuevas. Las
    instalaciones antiguas no tienen rama anotada (``""``), así que se tratan
    como normales.
    """
    branch = (entry.branch or "").strip()
    if not branch:
        return False
    return branch != "main" and not branch.startswith("v")


def filter_installed(entries, channel: str, search: str = "", favorites=()):
    """Aplica el filtro de canal y la búsqueda a las versiones instaladas.

    Es el equivalente de ``api.filter_builds`` para la pestaña de instaladas:
    las experimentales solo salen en su canal y el resto de canales las
    excluyen. Como las instaladas no guardan el "riesgo" de la compilación, lo
    deducimos de su nombre (las diarias llevan 'alpha', 'beta' o 'main').

    Los favoritos comparten clave con la tienda
    (``model.build.favorite_key``), así que marcar una versión en la tienda la
    marca también aquí.
    """
    if channel == "favorites":
        marked = set(favorites or ())
        selected = [entry for entry in entries if entry.favorite_key in marked]
    elif channel == "experimental":
        selected = [entry for entry in entries if is_experimental(entry)]
    else:
        selected = [entry for entry in entries if not is_experimental(entry)]
        if channel == "lts":
            selected = [entry for entry in selected if entry.is_lts]
        elif channel == "stable":
            selected = [entry for entry in selected if not entry.is_lts]
        elif channel == "daily":
            tokens = ("alpha", "beta", "main")
            selected = [
                entry for entry in selected
                if any(token in entry.name.lower() for token in tokens)
            ]
    # "all" y "lts_stable" muestran todas las que no son experimentales.
    text = (search or "").strip().lower()
    if text:
        selected = [
            entry for entry in selected
            if text in entry.name.lower() or text in entry.version.lower()
        ]
    return selected


def _is_stable_install(entry) -> bool:
    """True si la instalación es una versión estable (no diaria/alfa).

    Los marcadores guardan la rama, y las diarias la llaman ``main``. Las
    instalaciones antiguas (o sin marcador) no traen rama: se dan por estables,
    que es lo razonable. Las ramas experimentales quedan fuera.
    """
    branch = (entry.branch or "").strip()
    if branch == "main":
        return False
    if branch and not branch.startswith("v"):
        return False
    name = (entry.name or "").lower()
    return not any(token in name for token in ("alpha", "beta", "daily"))


def _minor_tuple(version: str):
    """Serie de una versión como tupla ordenable: '5.2.1' -> (5, 2)."""
    return version_tuple(minor_of(version))


def available_updates(installed, builds):
    """Empareja cada instalada con las actualizaciones que le corresponden.

    ``builds`` debe venir ya filtrada por plataforma y arquitectura (es lo que
    hace ``api.available_for``): no tendría sentido ofrecer un parche para otra
    plataforma. Solo se miran instaladas estables y compilaciones ``stable``;
    las diarias/alfa se renumeran solas y aquí serían ruido.

    El aviso es **por serie**, no por cada carpeta: se coge la instalada más
    nueva de cada serie, porque avisar en la 5.2.0 después de bajarte la 5.2.2
    como copia es ruido. Y si esa versión nueva ya está instalada, tampoco se
    ofrece (de ahí ``installed_versions``).

    Devuelve una lista de ``Update(entry, build, kind)`` donde ``kind`` es
    ``"patch"`` (misma serie, número mayor) o ``"series"`` (serie superior). Una
    misma instalada puede salir dos veces si hay parche *y* salto de serie; son
    dos avisos distintos (el botón de la tarjeta y el diálogo de salto).
    """
    stable_builds = [build for build in builds if build.risk == "stable"]
    entries = [entry for entry in installed if _is_stable_install(entry)]
    installed_versions = {version_tuple(entry.version) for entry in entries}

    # La instalada más nueva de cada serie: sobre esa se avisa.
    newest_in_series = {}
    for entry in entries:
        key = _minor_tuple(entry.version)
        current = newest_in_series.get(key)
        if current is None or version_tuple(entry.version) > version_tuple(current.version):
            newest_in_series[key] = entry

    updates = []
    for series_key, entry in newest_in_series.items():
        entry_version = version_tuple(entry.version)
        patch = None
        series = None
        for build in stable_builds:
            build_version = version_tuple(build.version)
            if build_version in installed_versions:
                # Ya la tienes (p. ej. bajada como copia): no hay nada que avisar.
                continue
            build_minor = _minor_tuple(build.version)
            if build_minor == series_key:
                if build_version > entry_version and (
                        patch is None or build.sort_key > patch.sort_key):
                    patch = build
            elif build_minor > series_key:
                if series is None or build.sort_key > series.sort_key:
                    series = build
        if patch is not None:
            updates.append(Update(entry, patch, "patch"))
        if series is not None:
            updates.append(Update(entry, series, "series"))
    return updates
