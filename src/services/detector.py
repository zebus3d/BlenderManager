"""Detección del sistema operativo y la arquitectura.

El resultado usa los mismos identificadores que la API de Blender:
plataforma 'linux' | 'windows' | 'darwin' y arquitectura 'x86_64' | 'amd64' | 'arm64'.
"""

import platform
from typing import NamedTuple

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
