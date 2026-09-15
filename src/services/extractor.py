"""Extracción segura de los archivos comprimidos de Blender.

Soportamos .tar.xz / .tar.gz / .tar.bz2 (Linux y macOS) y .zip (Windows)
con la biblioteca estándar. Antes de extraer validamos que ninguna entrada
intente salirse de la carpeta destino (ataque "zip slip").
"""

import tarfile
import zipfile
from pathlib import Path

ARCHIVE_SUFFIXES = (".tar.xz", ".tar.gz", ".tar.bz2", ".tgz", ".tbz2", ".zip")


def is_archive(path) -> bool:
    """True si el fichero parece un comprimido que sabemos abrir."""
    name = str(path).lower()
    return name.endswith(".zip") or any(name.endswith(suffix) for suffix in ARCHIVE_SUFFIXES)


def _within(base: Path, target: Path) -> bool:
    """Comprueba que ``target`` está dentro de ``base``."""
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _safe_extract_tar(archive: tarfile.TarFile, dest: Path) -> None:
    for member in archive.getmembers():
        target = dest / member.name
        if not _within(dest, target):
            raise ValueError("unsafe path in archive: " + member.name)
        # También validamos los enlaces simbólicos.
        if member.issym() or member.islnk():
            link_target = target.parent / member.linkname
            if not _within(dest, link_target):
                raise ValueError("unsafe link in archive: " + member.name)
    # Pedimos el filtro "data" explícitamente: sin él, Python 3.12/3.13 usan
    # "fully_trusted" (con DeprecationWarning) y 3.14 ya usa "data" por
    # defecto, así que el comportamiento cambiaría según con qué versión se
    # empaquete. Nuestras comprobaciones de arriba siguen siendo la primera
    # barrera; esta es la segunda.
    archive.extractall(dest, filter="data")


def _safe_extract_zip(archive: zipfile.ZipFile, dest: Path) -> None:
    for member in archive.infolist():
        target = dest / member.filename
        if not _within(dest, target):
            raise ValueError("unsafe path in archive: " + member.filename)
    archive.extractall(dest)


def extract(archive_path, dest_folder) -> Path:
    """Extrae el archivo y devuelve la carpeta creada (o la destino si hubo varias)."""
    archive = Path(archive_path)
    dest = Path(dest_folder).expanduser()
    dest.mkdir(parents=True, exist_ok=True)
    before = {entry.name for entry in dest.iterdir() if entry.is_dir()}

    if archive.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive) as zf:
            _safe_extract_zip(zf, dest)
    else:
        # "r:*" detecta automáticamente la compresión (xz, gz, bz2...).
        with tarfile.open(archive, "r:*") as tf:
            _safe_extract_tar(tf, dest)

    after = {entry.name for entry in dest.iterdir() if entry.is_dir()}
    created = after - before
    # Si solo apareció una carpeta nueva, es la de Blender.
    if len(created) == 1:
        return dest / created.pop()
    return dest
