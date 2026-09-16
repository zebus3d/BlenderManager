"""Abertura de URLs y carpetas con programas externos.

El problema que resuelve este módulo es propio de los binarios empaquetados
(sobre todo el AppImage). PyInstaller mete la carpeta ``_internal`` en
``LD_LIBRARY_PATH`` para que el ejecutable encuentre sus bibliotecas, y **ese
entorno se hereda al lanzar cualquier hijo**: ``xdg-open`` y, detrás, el
navegador o el gestor de ficheros cargan las ``libstdc++``, ``libssl``,
``libglib``... del AppImage en vez de las del sistema y no arrancan (a menudo en
silencio, porque el lanzamiento sí se produce). En modo fuente no hay
contaminación, así que el fallo solo se veía en el binario.

Aquí saneamos el entorno antes de lanzar nada externo: PyInstaller deja el valor
original de ``LD_LIBRARY_PATH`` en ``LD_LIBRARY_PATH_ORIG``, y además quitamos
las variables de Qt que también inyecta el empaquetado.

Es un módulo de ``services/``, así que **no importa Qt**.
"""

import os
import subprocess
import sys
from pathlib import Path

from services.downloader import log

# Variables que inyecta PyInstaller/Qt y que no deben llegar a un programa
# externo (navegador, Blender, gestor de ficheros).
_POLLUTED_VARS = (
    "LD_PRELOAD",
    "QT_PLUGIN_PATH",
    "QML2_IMPORT_PATH",
    "QT_QPA_PLATFORM_PLUGIN_PATH",
)


def clean_env() -> dict:
    """Copia del entorno sin la contaminación del binario empaquetado.

    Restaura ``LD_LIBRARY_PATH`` al valor que tenía antes de que PyInstaller lo
    tocara (``LD_LIBRARY_PATH_ORIG``); si no lo guardó, lo elimina para no pasar
    al hijo rutas que apuntan dentro del AppImage.
    """
    env = dict(os.environ)
    original = env.pop("LD_LIBRARY_PATH_ORIG", None)
    if original:
        env["LD_LIBRARY_PATH"] = original
    else:
        env.pop("LD_LIBRARY_PATH", None)
    for name in _POLLUTED_VARS:
        env.pop(name, None)
    return env


def _spawn(command, env: dict) -> bool:
    """Lanza un comando externo descartando sus salidas y devuelve si lo logró."""
    try:
        subprocess.Popen(
            command,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except OSError as error:
        log(f"opener: no se pudo lanzar {command[0]!r}: {error}")
        return False


def open_url(url: str) -> bool:
    """Abre una URL en el navegador predeterminado.

    Devuelve True si se pudo lanzar el abridor (no garantiza que el navegador
    llegue a pintar la página).
    """
    env = clean_env()
    if sys.platform.startswith("win"):
        try:
            os.startfile(url)  # noqa: S606 (solo Windows)
            return True
        except OSError as error:
            log(f"opener: no se pudo abrir {url!r}: {error}")
            return False
    if sys.platform == "darwin":
        return _spawn(["open", url], env)
    return _spawn(["xdg-open", url], env)


def open_path(path) -> bool:
    """Abre una carpeta (o un fichero) con la aplicación predeterminada."""
    target = str(Path(path))
    env = clean_env()
    if sys.platform.startswith("win"):
        try:
            os.startfile(target)  # noqa: S606 (solo Windows)
            return True
        except OSError as error:
            log(f"opener: no se pudo abrir {target!r}: {error}")
            return False
    if sys.platform == "darwin":
        return _spawn(["open", target], env)
    return _spawn(["xdg-open", target], env)


def reveal(path) -> bool:
    """Deja al usuario delante de un fichero descargado.

    En macOS lo selecciona en el Finder (``open -R``); en el resto abre su
    carpeta, que es lo más parecido a "aquí está lo que has bajado".
    """
    target = Path(path)
    if not target.exists():
        return False
    if sys.platform == "darwin":
        return _spawn(["open", "-R", str(target)], clean_env())
    return open_path(target.parent)
