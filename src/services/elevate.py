"""Pedir permisos de administrador en Windows (el diálogo UAC).

En Windows, carpetas como ``C:\\Program Files`` solo las puede escribir un
administrador. Si el usuario elige una de esas (típicamente para las versiones
LTS), la descarga falla con "Permission denied" y no hay forma de escribir ahí
sin elevación.

Aquí se lanza **este mismo binario** con el verbo ``runas`` de Windows (lo que
dispara el UAC) y el argumento interno ``--grant-access CARPETA``. Ese segundo
proceso, ya elevado, crea la carpeta y le concede permiso de escritura al
usuario con ``icacls``; después termina. Así se pide permiso **una sola vez** y
la app sigue corriendo sin privilegios: no se relanza toda la aplicación como
administrador, que dejaría los ficheros a nombre de admin y luego no se podrían
borrar sin volver a elevarlos.

Solo se usa en Windows; en el resto de sistemas ``available()`` es False y ni se
ofrece.
"""

import ctypes
import getpass
import os
import subprocess
import sys
from pathlib import Path

from services.downloader import log

# ShellExecuteW devuelve un HINSTANCE: los valores <= 32 son error. El 5 es
# "acceso denegado" (el usuario cancela el UAC) y el 1223, rechazarlo.
SHELLEXECUTE_MIN_OK = 32


def available() -> bool:
    """True si se puede pedir elevación (solo Windows)."""
    return sys.platform.startswith("win")


def _command(args) -> list:
    """Comando para relanzar esta app con ``args``.

    Empaquetada es el propio ejecutable; en modo fuente, el intérprete con el
    ``main.py`` por delante (para que en Windows también se pueda probar sin
    compilar).
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]
    return [sys.executable, sys.argv[0], *args]


def relaunch_elevated(args) -> bool:
    """Relanza la app con permisos de administrador (UAC).

    Devuelve True si el usuario ha aceptado. No espera a que el proceso elevado
    termine (es rápido): quien llama decide cómo esperar, porque solo él sabe
    qué comprobar.
    """
    if not available():
        return False
    command = _command(args)
    parameters = subprocess.list2cmdline(command[1:])
    try:
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", command[0], parameters, None, 1)
    except Exception as error:
        log(f"elevation failed: {error}")
        return False
    if result <= SHELLEXECUTE_MIN_OK:
        log(f"elevation not accepted (code {result})")
        return False
    return True


def grant_write(folder) -> bool:
    """Crea ``folder`` y da permiso de escritura al usuario actual.

    Se ejecuta **dentro** del proceso elevado (``--grant-access``). Concede
    control total al usuario para que la app normal (sin privilegios) pueda
    descargar, extraer y borrar de esa carpeta sin volver a preguntar.
    """
    path = Path(folder)
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        log(f"grant-access: no se pudo crear {path}: {error}")
        return False
    user = os.environ.get("USERNAME") or getpass.getuser()
    try:
        result = subprocess.run(
            ["icacls", str(path), "/grant", f"{user}:(OI)(CI)M"],
            capture_output=True, text=True, timeout=60)
    except Exception as error:
        log(f"grant-access: icacls falló: {error}")
        return False
    if result.returncode != 0:
        log(f"grant-access: icacls devolvió {result.returncode}: "
            f"{result.stdout.strip()} {result.stderr.strip()}")
        return False
    return True
