"""Barra de progreso **indeterminada** para trabajos sin porcentaje.

Descargar una versión de Blender tiene un total de bytes y una barra con
porcentaje (la del pie). Pero pedir el listado a internet no: no se sabe cuánto
va a tardar ni cuánto queda. Para eso está esta barra: un segmento que recorre
el carril de un lado a otro, sin número, que solo dice "esto está trabajando".

Es una subclase de ``QWidget`` que se pinta a mano (no un ``QProgressBar`` con
``setRange(0, 0)``): el estilo global de las barras fija el color del *chunk* y
la animación nativa cambia según el motor de estilo del sistema, así que con
nuestro QSS no se movía. Aquí el vaivén lo lleva un ``QTimer`` propio y el color
sale del tema, para que se vea igual en las tres plataformas.
"""

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from ui import theme as t

# Milisegundos entre cuadros y velocidad del segmento. A 30 fps el movimiento
# es fluido y el coste es despreciable (es un rectángulo).
FRAME_MS = 33
# Cuánto recorre el segmento por cuadro, como fracción del carril.
STEP = 0.02
# Ancho del segmento, como fracción del carril. Ni una raya (parece una carga
# normal) ni el carril entero (no se vería moverse).
SEGMENT = 0.28


class BusyBar(QWidget):
    """Segmento que recorre el carril mientras dura un trabajo sin porcentaje.

    Solo se anima cuando está **visible**: el ``showEvent``/``hideEvent``
    arrancan y paran el temporizador, así que no gasta nada cuando no se ve.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BusyBar")
        self.setFixedHeight(4)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setToolTip("")
        self._position = 0.0
        self._direction = 1
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self._advance)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._timer.isActive():
            self._timer.start()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._timer.stop()

    def _advance(self) -> None:
        """Mueve el segmento de un lado a otro del carril (vaivén)."""
        self._position += STEP * self._direction
        if self._position >= 1.0:
            self._position = 1.0
            self._direction = -1
        elif self._position <= 0.0:
            self._position = 0.0
            self._direction = 1
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        radius = self.height() / 2
        # El carril de fondo, en el gris del campo.
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(t.FIELD))
        painter.drawRoundedRect(self.rect(), radius, radius)
        # El segmento, en el color de acento. En vez de un ``position`` que
        # recorre 0..1 y se sale, se mueve dentro de lo que le deja su ancho.
        span = self.width() * (1.0 - SEGMENT)
        x = span * self._position
        segment = QRectF(x, 0, self.width() * SEGMENT, self.height())
        painter.setBrush(QColor(t.ACCENT))
        painter.drawRoundedRect(segment, radius, radius)
        painter.end()
