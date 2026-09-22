"""Piezas de layout que se repetían en varias vistas.

Vaciar un layout, montar un área de scroll para una lista y poner una nota
apagada ("no hay nada todavía") se hacían a mano en Recientes, Add-ons,
Migración y la ventana principal, cada una con su pequeña variante. Aquí está
la única versión de cada una, con el porqué de sus detalles.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget


def clear_layout(layout, keep_stretch: bool = False) -> None:
    """Vacía un layout de widgets de verdad.

    Se **quita del layout y se oculta** además de ``deleteLater()``: el borrado
    diferido no es inmediato, así que sin el ``setParent(None)`` el widget viejo
    seguía ocupando su hueco (y salía duplicado) hasta que el bucle de eventos
    lo recogía. Con ``keep_stretch`` se respeta el hueco elástico del final
    (``addStretch``), que algunas listas usan para empujar sus filas arriba.
    """
    index = layout.count() - 1
    while index >= 0:
        item = layout.itemAt(index)
        widget = item.widget()
        if widget is None and keep_stretch:
            index -= 1
            continue
        layout.takeAt(index)
        if widget is not None:
            widget.setParent(None)
            widget.hide()
            widget.deleteLater()
        index -= 1


def list_scroll(scroll_name: str, body_name: str, spacing: int = 4,
                margins=(0, 0, 0, 0), align_top: bool = True):
    """Área de scroll vertical con un cuerpo en columna: ``(scroll, layout)``.

    Sin marco ni barra horizontal (las filas se recortan con ``ElidedLabel``,
    no se desplazan de lado) y con ``objectName`` en el área y en el cuerpo
    para que el QSS los ponga transparentes: un ``QScrollArea`` pinta su propio
    fondo y cortaría la tarjeta en la que va.
    """
    scroll = QScrollArea()
    scroll.setObjectName(scroll_name)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    body = QWidget()
    body.setObjectName(body_name)
    layout = QVBoxLayout(body)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    if align_top:
        layout.setAlignment(Qt.AlignTop)
    scroll.setWidget(body)
    return scroll, layout


def muted_note(text: str) -> QLabel:
    """Nota apagada y centrada para una lista vacía ("No hay recientes")."""
    label = QLabel(text)
    label.setObjectName("Muted")
    label.setWordWrap(True)
    label.setAlignment(Qt.AlignHCenter)
    return label
