"""Widgets básicos reutilizables (versión PySide6).

Sustituyen a ``ui/widgets/basic.py`` + ``ui/widgets/spinners.py`` de la era
Kivy. El aspecto vive en ``ui/qss.py``; aquí está solo el comportamiento y los
puntos de enganche (``objectName`` y propiedades dinámicas) que el QSS usa.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QPushButton


class Pill(QPushButton):
    """Botón con forma de pastilla para filtros y selector de vista."""

    def __init__(self, text: str = "", tooltip: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("Pill")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)


class SideButton(QPushButton):
    """Botón cuadrado de la barra lateral (tienda, instaladas, ajustes)."""

    def __init__(self, glyph: str = "", tooltip: str = "", parent=None):
        super().__init__(glyph, parent)
        self.setObjectName("SideButton")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)


class CardButton(QPushButton):
    """Botón de acción dentro de las tarjetas (descargar, lanzar, borrar...).

    ``variant`` selecciona el color de relleno desde el QSS:
    ``neutral`` (gris), ``accent`` (azul primario) o ``danger`` (rojo).
    """

    def __init__(self, text: str = "", variant: str = "neutral",
                 tooltip: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("CardButton")
        self.setProperty("variant", variant)
        self.setCursor(Qt.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)

    def set_variant(self, variant: str) -> None:
        self.setProperty("variant", variant)
        self.style().unpolish(self)
        self.style().polish(self)


class IconLinkButton(QPushButton):
    """Icono de información de una tarjeta (abre las notas de la versión).

    Diana de 24x24 (mínimo AA, WCAG 2.5.8): en la era Kivy medía 22 px.
    """

    def __init__(self, glyph: str, tooltip: str = "", parent=None):
        super().__init__(glyph, parent)
        self.setObjectName("IconLink")
        self.setCursor(Qt.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)


class IconFlatButton(QPushButton):
    """Botón de icono plano sin fondo (refrescar, etc.)."""

    def __init__(self, glyph: str, tooltip: str = "", parent=None):
        super().__init__(glyph, parent)
        self.setObjectName("IconFlat")
        self.setCursor(Qt.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)


class SwitchPill(QPushButton):
    """Interruptor de sí/no con el mismo aspecto que los botones.

    El texto ("Sí"/"No") se actualiza solo al cambiar de estado.
    """

    toggled = Signal(bool)

    def __init__(self, checked: bool = False, yes: str = "Yes", no: str = "No",
                 tooltip: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Switch")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self._yes, self._no = yes, no
        self.setChecked(checked)
        self._refresh_text()
        if tooltip:
            self.setToolTip(tooltip)
        # QPushButton ya emite toggled; nos colgamos para refrescar el texto.
        super().toggled.connect(self._refresh_text)

    def _refresh_text(self, *_):
        self.setText(self._yes if self.isChecked() else self._no)
