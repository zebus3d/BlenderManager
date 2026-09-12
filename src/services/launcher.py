"""Lanzamiento de Blender como proceso externo.

Guardamos las referencias a los procesos vivos para poder informar de cuántas
instancias están en marcha (y limpiar las que ya han terminado).
"""

import subprocess
from pathlib import Path


class Launcher:
    def __init__(self):
        self._processes = []

    def launch(self, executable, args=None, cwd=None):
        executable = Path(executable)
        command = [str(executable)]
        command.extend(args or [])
        # Ejecutamos desde la carpeta de Blender para que encuentre sus recursos.
        process = subprocess.Popen(command, cwd=str(cwd or executable.parent))
        self._processes.append(process)
        self._processes = [item for item in self._processes if item.poll() is None]
        return process

    @property
    def running(self) -> int:
        """Número de instancias de Blender lanzadas que siguen vivas."""
        self._processes = [item for item in self._processes if item.poll() is None]
        return len(self._processes)
