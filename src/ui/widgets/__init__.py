"""Paquete de widgets de la interfaz.

Antes todo esto vivía en un único ``widgets.py`` de casi 1500 líneas. Ahora está
repartido por temas para que sea más fácil de leer:

* ``basic``     -> botones, pastillas, logo de la cabecera y zoom.
* ``spinners``  -> desplegables (plataforma, arquitectura, idioma).
* ``dialogs``   -> diálogos, barra de progreso y contenedores de ajustes.
* ``cards``     -> tarjetas de compilaciones (tienda e instaladas).
* ``root``      -> ``RootWidget``, el controlador de la pantalla principal.

Este ``__init__`` vuelve a exportar todo como si siguiera siendo un solo
módulo, de modo que ``from ui.widgets import RootWidget`` sigue funcionando
igual desde ``main.py`` y desde el resto del código.
"""

from ui.widgets.basic import (
    CardButton,
    FolderRow,
    HeaderLogo,
    HoverButton,
    IconLinkButton,
    Pill,
    SideButton,
    SwitchPill,
    ZoomSlider,
)
from ui.widgets.cards import (
    BaseBuildCard,
    BaseInstalledCard,
    BuildCard,
    GridBuildCard,
    GridInstalledCard,
    InstalledCard,
)
from ui.widgets.dialogs import (
    AppModalView,
    AppPopup,
    AppProgressBar,
    SettingsCard,
    SettingsHeader,
    SettingsInput,
)
from ui.widgets.root import RootWidget
from ui.widgets.spinners import AppDropDown, DarkSpinnerOption, HoverSpinner

__all__ = [
    "AppDropDown",
    "AppModalView",
    "AppPopup",
    "AppProgressBar",
    "BaseBuildCard",
    "BaseInstalledCard",
    "BuildCard",
    "CardButton",
    "DarkSpinnerOption",
    "FolderRow",
    "GridBuildCard",
    "GridInstalledCard",
    "HeaderLogo",
    "HoverButton",
    "HoverSpinner",
    "IconLinkButton",
    "InstalledCard",
    "Pill",
    "RootWidget",
    "SettingsCard",
    "SettingsHeader",
    "SettingsInput",
    "SideButton",
    "SwitchPill",
    "ZoomSlider",
]
