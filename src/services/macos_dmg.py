"""Instalación de ``Blender.app`` a partir del ``.dmg`` de macOS.

En macOS la API de Blender solo publica ``.dmg``, que **no** es un archivo
comprimido: para "extraerlo" hay que **montarlo** (``hdiutil attach``), copiar el
``Blender.app`` de dentro a la carpeta destino y desmontarlo. La copia se hace
con ``ditto``, que preserva los metadatos y la firma del bundle (un
``shutil.copytree`` puede dejarlo con problemas de Gatekeeper).

Así la build queda igual que las de Linux/Windows: dentro de su carpeta, lista
para que ``services.installed`` la escanee, ``services.launcher`` la abra y la
aplicación la pueda desinstalar o renombrar.

Es un módulo de ``services/``: **no importa Qt**. Y todo lo externo se lanza con
el entorno limpio (``services.opener.clean_env``), como manda el proyecto: si no,
los binarios del bundle heredan el ``LD_LIBRARY_PATH`` de PyInstaller.
"""

import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from services.downloader import log
from services.opener import clean_env


def available() -> bool:
    """True solo en macOS, que es donde existen ``hdiutil`` y ``ditto``."""
    return sys.platform == "darwin"


class DmgError(Exception):
    """Fallo montando o copiando el ``.dmg``, con el motivo listo para el log."""


def _run(command, check: bool = True):
    """Ejecuta un comando del sistema con el entorno limpio.

    ``hdiutil`` y ``ditto`` son programas de fuera: hay que pasarles
    ``clean_env()`` o cargarían las librerías del bundle (ver ``services.opener``).
    """
    try:
        result = subprocess.run(command, env=clean_env(),
                                stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, check=False)
    except OSError as error:
        raise DmgError(f"no se pudo ejecutar {command[0]}: {error}") from error
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise DmgError(f"{command[0]} falló ({result.returncode}): {detail}")
    return result


def _app_version(app: Path, fallback: str) -> str:
    """Versión del bundle (``CFBundleShortVersionString``), o ``fallback``.

    El marcador guarda la versión exacta de todas formas; esto es para que el
    **nombre de la carpeta** también la lleve y el escaneo no dependa del
    marcador.
    """
    try:
        with (app / "Contents" / "Info.plist").open("rb") as handle:
            data = plistlib.load(handle)
        return str(data.get("CFBundleShortVersionString") or fallback)
    except (OSError, plistlib.InvalidFileException, ValueError):
        return fallback


def _unique(folder: Path) -> Path:
    """Devuelve ``folder`` o el primer ``folder-2``, ``folder-3``... libre."""
    candidate = folder
    index = 2
    while candidate.exists():
        candidate = folder.with_name(f"{folder.name}-{index}")
        index += 1
    return candidate


def install(dmg_path, dest_folder, version_hint: str = "",
            arch_hint: str = "") -> Path:
    """Monta el ``.dmg``, copia el ``Blender.app`` a ``dest_folder`` y devuelve su carpeta.

    Lanza ``DmgError`` si algo falla (dmg corrupto, sin ``.app``, sin permisos);
    quien llama decide entonces el plan B (revelar el fichero y avisar).
    """
    dmg = Path(dmg_path)
    dest = Path(dest_folder).expanduser()
    dest.mkdir(parents=True, exist_ok=True)
    mount = Path(tempfile.mkdtemp(prefix="blendermanager-dmg-"))
    try:
        _run(["hdiutil", "attach", "-nobrowse", "-readonly", "-noautoopen",
              "-mountpoint", str(mount), str(dmg)])
        apps = sorted(mount.glob("*.app"))
        if not apps:
            raise DmgError("el .dmg no contiene ningún .app")
        app = apps[0]
        version = _app_version(app, version_hint or "unknown")
        arch = arch_hint or platform.machine() or "arm64"
        folder = _unique(dest / f"blender-{version}-macos-{arch}")
        folder.mkdir(parents=True)
        _run(["ditto", str(app), str(folder / app.name)])
        log(f"dmg instalado: {folder}")
        return folder
    finally:
        # Desmontar y limpiar SIEMPRE, aunque falle la copia: si no, el volumen
        # se queda montado y el siguiente intento falla con "resource busy".
        _run(["hdiutil", "detach", str(mount), "-force"], check=False)
        shutil.rmtree(mount, ignore_errors=True)
