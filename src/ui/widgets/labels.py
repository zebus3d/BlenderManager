"""Etiquetas que recortan el texto en vez de ensanchar su columna.

``QLabel`` pide como ancho mínimo el texto completo. En una tarjeta eso es una
trampa: el nombre de una carpeta instalada
(``blender-5.3.0-alpha+main.1fd06ddba680-linux.x86_64-release``) mide 483 px, así
que su tarjeta pedía 507 px mientras las de al lado se quedaban en 249 y la
columna de la rejilla salía más ancha que las demás. En modo lista, el meta con
la ruta pedía 666 px y la tarjeta entera 974 px en una ventana de 900.
"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QLabel, QSizePolicy


class ElidedLabel(QLabel):
    """``QLabel`` que pinta el texto recortado con ``…`` cuando no cabe.

    - El texto completo sigue disponible en ``text()`` y en el **tooltip**, que
      solo se pone mientras se está recortando de verdad. Como el tooltip va en
      la propia etiqueta, aparece al pasar el ratón por encima del texto.
    - ``minimumSizeHint().width()`` es 0 y la política de tamaño es ``Ignored``:
      la etiqueta nunca pide más sitio del que hay, así que no deforma la
      rejilla.
    - El recorte se decide al pintar, con el ancho del momento: ``ElideMiddle``
      para nombres de fichero (conserva el principio y el final, que es lo que
      identifica: ``blender-5.3.0-alpha+main…x86_64-release``) y ``ElideRight``
      para textos donde lo importante va delante.
    """

    # Por defecto a la derecha, que es lo prudente para un texto cualquiera.
    _mode = Qt.ElideRight

    def __init__(self, text: str = "", mode=Qt.ElideRight, parent=None):
        super().__init__(text, parent)
        self._mode = mode
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._actualizar_tooltip()

    def minimumSizeHint(self) -> QSize:
        """Alto el de siempre, ancho 0: el texto no manda sobre el layout."""
        hint = super().minimumSizeHint()
        return QSize(0, hint.height())

    def displayed_text(self) -> str:
        """Lo que se está viendo ahora mismo (recortado, si hace falta)."""
        return self.fontMetrics().elidedText(self.text(), self._mode,
                                             self.contentsRect().width())

    def is_elided(self) -> bool:
        """True si el texto no cabe y se está mostrando recortado."""
        return self.displayed_text() != self.text()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Cambia el ancho (o el zoom, que rehace la tarjeta): el tooltip deja de
        # tener sentido en cuanto el nombre se ve entero.
        self._actualizar_tooltip()

    def setText(self, text: str) -> None:  # noqa: N802 (API de Qt)
        super().setText(text)
        self._actualizar_tooltip()

    def _actualizar_tooltip(self) -> None:
        self.setToolTip(self.text() if self.is_elided() else "")

    def paintEvent(self, event):
        """Se pinta con el estilo, no con un ``QPainter`` a mano.

        Así siguen mandando el color del QSS (``Title``, ``Muted``, ``Info``...) y
        hasta el ``setStyleSheet`` puntual que llevan algunas tarjetas, que es
        exactamente lo que hace un ``QLabel`` normal.
        """
        painter = QPainter(self)
        self.style().drawItemText(
            painter, self.contentsRect(), int(self.alignment()),
            self.palette(), self.isEnabled(), self.displayed_text(),
            self.foregroundRole())
        painter.end()
