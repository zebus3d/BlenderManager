"""Detección del sistema operativo, la arquitectura y la sesión gráfica.

El resultado usa los mismos identificadores que la API de Blender:
plataforma 'linux' | 'windows' | 'darwin' y arquitectura 'x86_64' | 'amd64' | 'arm64'.
"""

import os
import platform
from typing import Mapping, NamedTuple

OS_IDS = {"Linux": "linux", "Windows": "windows", "Darwin": "darwin"}
OS_LABELS = {"linux": "GNU/Linux", "windows": "Windows", "darwin": "macOS"}


class SystemInfo(NamedTuple):
    """Sistema y arquitectura detectados, con los identificadores
    de Blender.
    """
    os_name: str
    arch: str
    label: str


def _arch(os_name: str) -> str:
    """Normaliza la arquitectura de la máquina al nombre que usa Blender."""
    machine = (platform.machine() or "").lower()
    if machine in ("x86_64", "amd64", "x64"):
        # Windows llama 'amd64' a la arquitectura de 64 bits.
        return "amd64" if os_name == "windows" else "x86_64"
    if machine in ("aarch64", "arm64"):
        return "arm64"
    if machine in ("i386", "i686", "x86", "i86pc"):
        return "x86"
    return machine


def detect() -> SystemInfo:
    """Detecta el sistema operativo y la arquitectura de este equipo."""
    system_name = platform.system()
    os_name = OS_IDS.get(system_name)
    if os_name is None:
        return SystemInfo("", "", system_name or "unknown")
    return SystemInfo(os_name, _arch(os_name), OS_LABELS[os_name])


def session_is_wayland(env: Mapping[str, str] | None = None) -> bool:
    """True si la sesión gráfica es Wayland (mira el entorno, no la UI)."""
    env = os.environ if env is None else env
    if "wayland" in (env.get("XDG_SESSION_TYPE") or "").lower():
        return True
    return bool(env.get("WAYLAND_DISPLAY"))


def xwayland_available(env: Mapping[str, str] | None = None) -> bool:
    """True si hay un servidor X accesible (XWayland, en una sesión Wayland).

    ``DISPLAY`` también está definido en sesiones X11 de verdad, pero eso da
    igual: la función solo se usa para saber si se puede caer a X11.
    """
    env = os.environ if env is None else env
    return bool(env.get("DISPLAY"))


def minimize_to_tray_supported(env: Mapping[str, str] | None = None) -> bool:
    """Si se puede detectar el minimizado del sistema en esta sesión.

    En Wayland el compositor **no** comunica al cliente que la ventana está
    minimizada: ese estado no existe en ``xdg-shell``, así que si el botón lo
    dibuja el compositor (KWin, decoraciones del servidor) la app no se entera
    (lo documentan SDL, Electron y KDE). La única salida es correr bajo
    XWayland; sin un ``DISPLAY`` no hay nada que hacer.
    """
    if session_is_wayland(env) and not xwayland_available(env):
        return False
    return True


def should_use_xwayland(minimize_to_tray: bool,
                        env: Mapping[str, str] | None = None) -> bool:
    """Si hay que forzar el backend X11 de Qt para que funcione la bandeja.

    Solo cuando el usuario pidió "minimizar a la bandeja" y está en Wayland con
    XWayland disponible: es lo mismo que hacen las apps Electron con
    ``--ozone-platform=x11``. El resto de usuarios siguen en Wayland nativo, y
    en Windows/macOS/X11 no se toca nada.
    """
    return (bool(minimize_to_tray) and session_is_wayland(env)
            and xwayland_available(env))
