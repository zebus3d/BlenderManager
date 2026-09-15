"""Diálogos con el aspecto de la aplicación (versión PySide6).

Sustituyen a ``ui/widgets/dialogs.py`` + ``views/dialogs.kv``. Qt trae
``QMessageBox`` y ``QDialog``, pero con el estilo claro/nativo del escritorio
desentonan con el tema oscuro; aquí heredamos de ``QDialog`` y los montamos con
nuestros propios botones (``CardButton``), que ya llevan el QSS de la app.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from i18n import tr
from ui.widgets.buttons import CardButton


class AppDialog(QDialog):
    """Diálogo base: fondo SURFACE, título, cuerpo y fila de botones."""

    def __init__(self, parent=None, title: str = "", message: str = "",
                 width: int = 440):
        super().__init__(parent)
        self.setWindowTitle(title or tr("Blender Downloads Manager"))
        self.setModal(True)
        self.setMinimumWidth(width)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(12)

        if title:
            heading = QLabel(title)
            heading.setObjectName("DialogTitle")
            heading.setWordWrap(True)
            lay.addWidget(heading)

        if message:
            body = QLabel(message)
            body.setWordWrap(True)
            self.body_label = body
            lay.addWidget(body)

        self._buttons = QHBoxLayout()
        self._buttons.setSpacing(8)
        self._buttons.addStretch()
        lay.addLayout(self._buttons)

    def add_button(self, text: str, variant: str = "neutral",
                   on_click=None) -> CardButton:
        """Añade un botón a la fila inferior y lo devuelve."""
        button = CardButton(text, variant=variant)
        if on_click is not None:
            button.clicked.connect(on_click)
        self._buttons.addWidget(button)
        return button


def confirm(parent, title: str, message: str, confirm_text: str | None = None,
            accept_text: str | None = None, danger: bool = False) -> bool:
    """Diálogo de confirmación. Devuelve True si el usuario acepta.

    ``accept_text`` es el texto del botón que continúa; por convención las
    acciones destructivas lo dicen con el verbo ("Desinstalar"), no con un
    "Aceptar" genérico.
    """
    dialog = AppDialog(parent, title, message)
    dialog.add_button(tr("Cancel"), on_click=dialog.reject)
    dialog.add_button(accept_text or confirm_text or tr("Accept"),
                      variant="danger" if danger else "accent",
                      on_click=dialog.accept)
    return dialog.exec() == QDialog.Accepted


def show_error(parent, title: str, message: str) -> None:
    """Aviso de error (bloqueante)."""
    dialog = AppDialog(parent, title, message)
    dialog.add_button(tr("Close"), variant="accent", on_click=dialog.accept)
    dialog.exec()


def show_info(parent, title: str, message: str) -> None:
    """Aviso informativo."""
    show_error(parent, title, message)


class ProgressDialog(AppDialog):
    """Diálogo con barra de progreso propia (descarga de actualizaciones)."""

    def __init__(self, parent=None, title: str = "", message: str = ""):
        super().__init__(parent, title, message)

        from PySide6.QtWidgets import QProgressBar

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedHeight(10)
        # Este se inserta antes de la fila de botones (que ya existe al final).
        layout = self.layout()
        layout.insertWidget(layout.count() - 1, self.progress)
        self._primary = self.add_button(tr("Update"), variant="accent")
        self._secondary = self.add_button(tr("Later"))
        self._secondary.clicked.connect(self.reject)

    def set_progress(self, value: int) -> None:
        """Mueve la barra de progreso (0-100)."""
        self.progress.setValue(max(0, min(100, value)))

    def set_text(self, text: str) -> None:
        """Cambia el mensaje del diálogo, para ir contando qué pasa."""
        if hasattr(self, "body_label"):
            self.body_label.setText(text)


def update_available(parent, tag: str, on_update) -> bool:
    """Diálogo de actualización disponible. ``on_update`` se llama si acepta."""
    message = (tr("A new version is available: {version}", version=tag)
               + "\n\n" + tr("It will be installed and the app will restart automatically."))
    dialog = AppDialog(parent, tr("Update available"), message)
    dialog.add_button(tr("Later"), on_click=dialog.reject)
    dialog.add_button(tr("Update"), variant="accent", on_click=dialog.accept)
    accepted = dialog.exec() == QDialog.Accepted
    if accepted:
        on_update()
    return accepted
