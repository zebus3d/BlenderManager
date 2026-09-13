"""Lanzamiento de Blender como proceso externo.

Blender se ejecuta en un proceso aparte y **desacoplado** del gestor:
en Linux/macOS se inicia en su propia sesión (``start_new_session``) y en
Windows en un grupo de procesos propio. Así, aunque cierres Blender Manager,
los Blender que hayas lanzado desde él siguen abiertos.

Guardamos las referencias a los procesos lanzados solo para poder descartar
los que ya han terminado y no acumularlas indefinidamente.
"""

import subprocess
import sys
from pathlib import Path


class Launcher:
    def __init__(self):
        self._processes = []

    def launch(self, executable, args=None, cwd=None):
        executable = Path(executable)
        command = [str(executable)]
        command.extend(args or [])

        # Opciones para desacoplar el proceso hijo del gestor.
        kwargs = {
            "cwd": str(cwd or executable.parent),
            # Sin entrada estándar y descartando la salida, para que al cerrar
            # el gestor el hijo no dependa de su terminal.
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if sys.platform.startswith("win"):
            # Grupo de procesos propio y sin consola asociada.
            kwargs["creationflags"] = (
                subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            # Nueva sesión: no recibe el SIGHUP del terminal ni del gestor.
            kwargs["start_new_session"] = True

        process = subprocess.Popen(command, **kwargs)
        self._processes.append(process)
        self._processes = [item for item in self._processes if item.poll() is None]
        return process
