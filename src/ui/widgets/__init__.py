"""Paquete de widgets de la interfaz (versión PySide6).

* ``buttons``      -> botones, pastillas, interruptores e iconos.
* ``cards``        -> tarjetas de compilaciones (tienda e instaladas).
* ``main_window``  -> ``MainWindow``, el controlador de la pantalla principal.

El aspecto vive en ``ui/qss.py`` (equivalente a los antiguos ``views/*.kv``).
"""

from ui.widgets.buttons import (
    CardButton,
    IconFlatButton,
    IconLinkButton,
    Pill,
    SideButton,
    SwitchPill,
)
from ui.widgets.cards import (
    BuildCard,
    GridBuildCard,
    GridInstalledCard,
    InstalledCard,
)
from ui.widgets.main_window import MainWindow

__all__ = [
    "BuildCard",
    "CardButton",
    "GridBuildCard",
    "GridInstalledCard",
    "IconFlatButton",
    "IconLinkButton",
    "InstalledCard",
    "MainWindow",
    "Pill",
    "SideButton",
    "SwitchPill",
]
