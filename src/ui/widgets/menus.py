"""Menús contextuales con el aspecto de la app.

Un ``QMenu`` pelado sale con el estilo nativo (claro) y desentona con el tema
oscuro: el ``objectName`` es lo que engancha las reglas de ``ui/qss.py``. Las
tarjetas, los add-ons y los recientes lo montaban cada uno por su cuenta.
"""

from PySide6.QtWidgets import QMenu


def card_menu(parent=None) -> QMenu:
    """Menú contextual de una fila o tarjeta (mismo aspecto que el de la bandeja)."""
    menu = QMenu(parent)
    menu.setObjectName("CardMenu")
    # Qt no enseña los tooltips de las acciones de un menú si no se le pide.
    menu.setToolTipsVisible(True)
    return menu
