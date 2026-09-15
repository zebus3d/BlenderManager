"""Preparación común de los tests.

Aquí solo se hace lo que tiene que pasar una vez para toda la suite: poner
``src/`` en el ``sys.path`` y silenciar el registro en fichero.
"""

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _silenciar_log() -> None:
    """Que los tests NO escriban en el log real del usuario.

    ``services.downloader.log`` es la herramienta de diagnóstico de la
    aplicación (``~/.cache/blendermanager/blendermanager.log``) y acababa con
    basura de cada ejecución de los tests: rutas ``/tmp/tmpXXXX``, un
    ``git pull failed: boom`` de un test que simula un fallo... Así, cuando de
    verdad hay que mirar el log para ayudar a alguien, no se sabe qué es real.

    Cada módulo hace ``from services.downloader import log``, así que el nombre
    queda copiado en su espacio: hay que sustituirlo en todos.
    """
    from services import api, downloader, updater

    for modulo in (downloader, updater, api):
        modulo.log = lambda *args, **kwargs: None


_silenciar_log()
