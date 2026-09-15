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
    StarButton,
    SwitchPill,
)
from ui.widgets.cards import (
    BuildCard,
    GridBuildCard,
    GridInstalledCard,
    InstalledCard,
)
from ui.widgets.labels import ElidedLabel
from ui.widgets.dialogs import (
    AppDialog,
    ProgressDialog,
    confirm,
    show_error,
    show_info,
    update_available,
)
from ui.widgets.main_window import MainWindow

__all__ = [
    "AppDialog",
    "BuildCard",
    "CardButton",
    "GridBuildCard",
    "ElidedLabel",
    "GridInstalledCard",
    "IconFlatButton",
    "IconLinkButton",
    "InstalledCard",
    "MainWindow",
    "Pill",
    "ProgressDialog",
    "SideButton",
    "StarButton",
    "SwitchPill",
    "confirm",
    "show_error",
    "show_info",
    "update_available",
]
