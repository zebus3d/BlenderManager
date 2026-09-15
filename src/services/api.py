"""Acceso a la API de compilaciones de Blender.

Blender publica un JSON con todas las compilaciones (estables por rama y
alfa de ``main``). Es mucho más fiable que hacer scraping del HTML, que es
lo que hacían los primeros prototipos.

Endpoint: https://builder.blender.org/download/daily/?format=json&v=2

Solo usamos la biblioteca estándar (urllib) para no añadir dependencias
extra al empaquetado.
"""

import json
import re
import time
import urllib.request
from dataclasses import asdict, fields

from model.build import Build
from services.downloader import log
from services.settings import cache_dir, write_json_atomic

API_URL = "https://builder.blender.org/download/daily/?format=json&v=2"
# Las ramas experimentales (sección "Branch" del builder) publican en su
# propio listado, el mismo que Blender Launcher usa para "experimental". Solo
# aparece contenido cuando el equipo de Blender abre ramas de funciones nuevas;
# la mayor parte del tiempo está vacío (y entonces la app lo explica en la
# tienda).
EXPERIMENTAL_URL = "https://builder.blender.org/download/experimental/?format=json&v=2"
CACHE_MAX_AGE = 3600  # una hora de validez para el caché en disco

# Extensiones descargables que nos interesan (descartamos .sha256, .msi, etc.).
VALID_EXTENSIONS = {"xz", "zip", "dmg", "tar", "gz", "bz2"}

# Preferimos un formato de archivo por plataforma: tar.xz en Linux, zip portable
# en Windows y dmg en macOS.
PREFERRED_EXTENSION = {"linux": "xz", "windows": "zip", "darwin": "dmg"}

USER_AGENT = "BlenderManager/0.2 (+https://github.com/zebus3d/BlenderManager)"


def cache_path():
    return cache_dir() / "builds.json"


def _fetch_json(url: str, timeout: int = 20):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _to_build(entry: dict, experimental: bool = False) -> Build:
    """Convierte una entrada del JSON en un objeto Build."""
    return Build(
        version=str(entry.get("version") or ""),
        branch=str(entry.get("branch") or ""),
        risk=str(entry.get("risk_id") or ""),
        platform=str(entry.get("platform") or ""),
        arch=str(entry.get("architecture") or ""),
        url=str(entry.get("url") or ""),
        filename=str(entry.get("file_name") or ""),
        size=int(entry.get("file_size") or 0),
        checksum=entry.get("checksum"),
        mtime=int(entry.get("file_mtime") or 0),
        build_hash=str(entry.get("hash") or ""),
        experimental=experimental,
    )


def _fetch_builds_from(url: str, timeout: int, experimental: bool):
    """Descarga un listado y se queda con las extensiones que sabemos abrir."""
    entries = _fetch_json(url, timeout=timeout)
    builds = []
    for entry in entries:
        if entry.get("file_extension") not in VALID_EXTENSIONS:
            continue
        builds.append(_to_build(entry, experimental=experimental))
    return builds


def fetch_builds(timeout: int = 20):
    """Descarga el listado completo: diarias + ramas experimentales.

    El listado experimental va en su propio try: casi siempre está vacío y eso
    no debe impedir que se vean las compilaciones normales.
    """
    builds = _fetch_builds_from(API_URL, timeout, experimental=False)
    try:
        builds += _fetch_builds_from(EXPERIMENTAL_URL, timeout, experimental=True)
    except Exception as error:
        log(f"experimental builds unavailable: {error}")
    return builds


def save_cache(builds) -> None:
    payload = {"saved_at": int(time.time()), "builds": [asdict(build) for build in builds]}
    write_json_atomic(cache_path(), payload)


def load_cache(max_age=CACHE_MAX_AGE):
    """Lee el caché en disco. Con ``max_age=None`` lo acepta aunque esté caducado."""
    path = cache_path()
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if max_age is not None and time.time() - payload.get("saved_at", 0) > max_age:
        return []
    # Un caché escrito por una versión anterior puede traer campos que ya no
    # existen (o faltarle alguno nuevo): nos quedamos solo con los que conoce
    # el modelo, en vez de descartar la entrada entera.
    known = {field.name for field in fields(Build)}
    builds = []
    for item in payload.get("builds", []):
        try:
            builds.append(Build(**{key: value for key, value in item.items() if key in known}))
        except TypeError:
            continue
    return builds


def get_builds(force: bool = False):
    """Listado de compilaciones: usa caché y, si falla la red, cae al caché antiguo."""
    if not force:
        cached = load_cache()
        if cached:
            return cached
    try:
        builds = fetch_builds()
        save_cache(builds)
        return builds
    except Exception:
        # Sin conexión: mejor mostrar algo (aunque esté caducado) que nada.
        return load_cache(max_age=None)


def available_for(builds, platform: str, arch: str):
    """Filtra por plataforma y arquitectura, quedándose con un archivo por versión."""
    preferred = PREFERRED_EXTENSION.get(platform)
    filtered = [build for build in builds if build.platform == platform and build.arch == arch]
    if preferred:
        matching = [build for build in filtered if build.filename.endswith("." + preferred)]
        if matching:
            filtered = matching
    # Puede haber varias entradas de la misma versión/rama; nos quedamos con la más reciente.
    best = {}
    for build in filtered:
        key = (build.version, build.branch, build.risk)
        current = best.get(key)
        if current is None or build.mtime > current.mtime:
            best[key] = build
    return sorted(best.values(), key=lambda build: build.sort_key, reverse=True)


def filter_builds(builds, channel: str, search: str = "", favorites=()):
    """Aplica el filtro de canal y la búsqueda a las compilaciones de la tienda.

    Las ramas experimentales solo se ven en su propio canal ("experimental"):
    así no se cuelan entre las estables o las diarias y no confunden a quien
    solo quiere una versión normal de Blender.

    ``favorites`` es la lista de claves marcadas por el usuario
    (``model.build.favorite_key``). Con el canal "favorites" se muestran solo
    esas, sin excluir las experimentales: ahí manda lo que haya marcado.
    """
    if channel == "favorites":
        marked = set(favorites or ())
        selected = [build for build in builds if build.favorite_key in marked]
    elif channel == "experimental":
        selected = [build for build in builds if build.experimental]
    else:
        selected = [build for build in builds if not build.experimental]
        if channel == "lts":
            # Solo las versiones con soporte de larga duración.
            selected = [build for build in selected if build.is_lts]
        elif channel == "stable":
            # Estables que no son LTS.
            selected = [build for build in selected
                        if build.risk == "stable" and not build.is_lts]
        elif channel == "lts_stable":
            # LTS y estables a la vez (todo lo estable).
            selected = [build for build in selected if build.risk == "stable"]
        elif channel == "daily":
            selected = [build for build in selected if build.risk != "stable"]
    text = (search or "").strip().lower()
    if text:
        selected = [
            build for build in selected
            if text in build.version.lower() or text in build.branch.lower()
        ]
    return selected


# Notas de versión de Blender. Cada serie tiene su propia página:
# https://developer.blender.org/docs/release_notes/4.2/
RELEASE_NOTES_URL = "https://developer.blender.org/docs/release_notes/"
# La serie más antigua que tiene página propia publicada.
OLDEST_RELEASE_NOTES = (2, 79)


def release_notes_url(version: str) -> str:
    """Devuelve la URL de las notas de versión de una compilación.

    Las páginas van por serie (mayor.menor), así que de "4.2.1" o de
    "5.2.0-alpha" nos quedamos con "4.2" y "5.2". Si la versión no se entiende
    o es anterior a las notas publicadas, abrimos el índice general.
    """
    match = re.search(r"(\d+)\.(\d+)", version or "")
    if not match:
        return RELEASE_NOTES_URL
    series = (int(match.group(1)), int(match.group(2)))
    if series < OLDEST_RELEASE_NOTES:
        return RELEASE_NOTES_URL
    return f"{RELEASE_NOTES_URL}{series[0]}.{series[1]}/"
