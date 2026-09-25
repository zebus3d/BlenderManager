"""Instalación de ``Blender.app`` a partir del ``.dmg`` de macOS.

En macOS la API de Blender solo publica ``.dmg``, que **no** es un archivo
comprimido: para "extraerlo" hay que **montarlo** (``hdiutil attach``), copiar el
``Blender.app`` de dentro a la carpeta destino y desmontarlo. La copia se hace
con ``ditto``, que preserva los metadatos y la firma del bundle (un
``shutil.copytree`` puede dejarlo con problemas de Gatekeeper), y después se le
quita el atributo de cuarentena con ``xattr`` por si el ``.dmg`` venía marcado.

Es el mismo patrón que usan Homebrew Cask, kitty o Zed (``hdiutil`` + ``ditto``)
y, para Blender en concreto, Blender Launcher V2 en su ``extractor.py``.

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

from model.build import FORK_BFORARTISTS
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


def extract_zip(zip_path, dest_folder) -> None:
    """Extrae un ``.zip`` con ``ditto``, no con ``zipfile``.

    **Importante**: ``zipfile`` de Python no restaura los bits de ejecución ni
    los enlaces simbólicos del bundle (y puede perder la firma), así que el
    ``.app`` extraído **no arranca**. En macOS la forma correcta de descomprimir
    un bundle es ``ditto -x -k``; es lo mismo que hace Blender Launcher V2 para
    este caso. Solo se usa al aplicar una actualización (el usuario descomprime
    el zip de la release con Finder, que ya lo hace bien).
    """
    dest = Path(dest_folder)
    dest.mkdir(parents=True, exist_ok=True)
    _run(["/usr/bin/ditto", "-x", "-k", str(zip_path), str(dest)])


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
            arch_hint: str = "", fork: str = "") -> Path:
    """Monta el ``.dmg``, copia el ``.app`` a ``dest_folder`` y devuelve su carpeta.

    ``fork`` decide el nombre del bundle que se busca (``Blender.app`` o
    ``Bforartists.app``) y el prefijo de la carpeta, para que una Bforartists
    5.2 en macOS no acabe en una carpeta llamada ``blender-5.2.0`` y se
    confunda con un Blender de verdad.

    Lanza ``DmgError`` si algo falla (dmg corrupto, sin ``.app``, sin permisos);
    quien llama decide entonces el plan B (revelar el fichero y avisar).
    """
    dmg = Path(dmg_path)
    dest = Path(dest_folder).expanduser()
    dest.mkdir(parents=True, exist_ok=True)
    prefix = "bforartists" if fork == FORK_BFORARTISTS else "blender"
    bundle_name = "Bforartists.app" if fork == FORK_BFORARTISTS else "Blender.app"
    mount = Path(tempfile.mkdtemp(prefix="blendermanager-dmg-"))
    try:
        _run(["/usr/bin/hdiutil", "attach", "-nobrowse", "-readonly",
              "-noautoopen", "-mountpoint", str(mount), str(dmg)])
        apps = sorted(mount.glob("*.app"))
        if not apps:
            raise DmgError("el .dmg no contiene ningún .app")
        # El bundle del programa; puede haber más de uno (p. ej.
        # BlenderPlayer.app), así que se copian todos y se lanza el que toca.
        main_app = next((a for a in apps if a.name == bundle_name), apps[0])
        version = _app_version(main_app, version_hint or "unknown")
        arch = arch_hint or platform.machine() or "arm64"
        folder = _unique(dest / f"{prefix}-{version}-macos-{arch}")
        folder.mkdir(parents=True)
        for bundle in apps:
            target_app = folder / bundle.name
            _run(["/usr/bin/ditto", str(bundle), str(target_app)])
            # Gatekeeper: si el .dmg venía marcado (p. ej. bajado antes con el
            # navegador), el bundle hereda el atributo de cuarentena y macOS no
            # deja ejecutarlo. Se quita; Blender está notarizado, así que no se
            # debilita nada real. Lo mismo que hace Blender Launcher V2.
            _run(["/usr/bin/xattr", "-r", "-d", "com.apple.quarantine",
                  str(target_app)], check=False)
        log(f"dmg instalado: {folder}")
        return folder
    finally:
        # Desmontar y limpiar SIEMPRE, aunque falle la copia: si no, el volumen
        # se queda montado y el siguiente intento falla con "resource busy".
        _run(["/usr/bin/hdiutil", "detach", str(mount), "-force"], check=False)
        shutil.rmtree(mount, ignore_errors=True)
