"""Widgets básicos reutilizables (versión PySide6).

Sustituyen a ``ui/widgets/basic.py`` + ``ui/widgets/spinners.py`` de la era
Kivy. El aspecto vive en ``ui/qss.py``; aquí está solo el comportamiento y los
puntos de enganche (``objectName`` y propiedades dinámicas) que el QSS usa.
"""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QPushButton

from ui import icons
from ui import theme as t


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
        """Cambia el color del botón y lo repinta."""
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


class StarButton(QPushButton):
    """Estrella de favorito (marca y desmarca).

    El glifo es el mismo en los dos estados; lo que cambia es el color, que lo
    pone el QSS según ``:checked`` (no tenemos la variante de contorno de la
    fuente: solo se empaqueta la sólida).
    """

    def __init__(self, marked: bool = False, tooltip_on: str = "",
                 tooltip_off: str = "", parent=None):
        super().__init__(icons.STAR, parent)
        self.setObjectName("StarButton")
        self.setCheckable(True)
        self.setChecked(bool(marked))
        self.setCursor(Qt.PointingHandCursor)
        self._tooltip_on = tooltip_on
        self._tooltip_off = tooltip_off
        self._update_tooltip()
        self.toggled.connect(lambda _: self._update_tooltip())

    def _update_tooltip(self) -> None:
        self.setToolTip(self._tooltip_on if self.isChecked() else self._tooltip_off)


class IconFlatButton(QPushButton):
    """Botón de icono plano sin fondo (refrescar, etc.)."""

    def __init__(self, glyph: str, tooltip: str = "", parent=None):
        super().__init__(glyph, parent)
        self.setObjectName("IconFlat")
        self.setCursor(Qt.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)


class SwitchPill(QPushButton):
    """Interruptor de sí/no con forma de *toggle* (pista + bolita).

    Qt no trae un interruptor y un ``QCheckBox`` con ``::indicator`` no deja
    mover la bolita ni animarla desde el QSS, así que se pinta a mano. Sigue
    siendo un botón *checkable*: emite ``toggled`` y responde a clic y a teclado
    (Tab + Espacio) igual que antes, solo que ya no muestra "Sí"/"No" — el
    estado se ve por la posición de la bolita y el color de la pista.
    """

    WIDTH = 46
    HEIGHT = 24
    MARGIN = 3

    def __init__(self, checked: bool = False, tooltip: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Switch")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setChecked(checked)
        if tooltip:
            self.setToolTip(tooltip)

    def _track_color(self) -> QColor:
        """Color de la pista según estado y hover."""
        if not self.isEnabled():
            # Apagado pero visible: no puede parecer que está encendido.
            return QColor(t.FIELD)
        if self.isChecked():
            return QColor(t.ACCENT_DARK if self.underMouse() else t.ACCENT)
        return QColor(t.BUTTON if self.underMouse() else t.SURFACE_ALT)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = rect.height() / 2
        painter.setPen(QPen(QColor(t.BORDER), 1))
        painter.setBrush(self._track_color())
        painter.drawRoundedRect(rect, radius, radius)

        diameter = self.HEIGHT - 2 * self.MARGIN
        offset = (rect.width() - self.MARGIN - diameter) if self.isChecked() \
            else self.MARGIN
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(t.TEXT_SEL if self.isEnabled() else t.MUTED))
        painter.drawEllipse(QRectF(rect.x() + offset, rect.y() + self.MARGIN,
                                   diameter, diameter))

        if self.hasFocus():
            # Aro de foco para quien navega con el teclado.
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(t.ACCENT), 2))
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1),
                                    radius - 1, radius - 1)
        painter.end()

    def enterEvent(self, event):
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.update()
