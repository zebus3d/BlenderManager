"""Vista de los ``.blend`` abiertos recientemente, por versión de Blender.

Lee la lista que Blender deja en ``<config>/recent-files.txt`` (ver
``services/recent.py``) y la enseña agrupada por serie. Un clic abre el fichero
en la versión más nueva de su serie; el botón ``⋯`` deja elegir cualquier
versión instalada; el clic derecho revela el fichero en el explorador.

No es una pestaña de compilaciones, así que la fila de filtros y el buscador se
ocultan (lo decide ``MainWindow._set_view``).
"""

from pathlib import Path

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from i18n import tr
from model.build import minor_of
from services import opener
from services import recent as recent_service
from services.launcher import Launcher
from ui import icons
from ui import theme as t
from ui.widgets.buttons import IconFlatButton
from ui.widgets.labels import ElidedLabel


def _menu(parent) -> QMenu:
    """Menú contextual con el aspecto de la app (el mismo que el de la bandeja)."""
    menu = QMenu(parent)
    menu.setObjectName("CardMenu")
    return menu


def _clear(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()


class _RecentRow(QFrame):
    """Fila de un fichero reciente: nombre, carpeta y abrir en una versión."""

    def __init__(self, path, versions, on_open, on_reveal, parent=None):
        super().__init__(parent)
        self.path = Path(path)
        self._versions = list(versions)
        self._on_open = on_open
        self._on_reveal = on_reveal
        self.setObjectName("RecentRow")
        self.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 8, 6)
        lay.setSpacing(8)

        info = QVBoxLayout()
        info.setSpacing(1)
        name = ElidedLabel(self.path.name, Qt.ElideRight)
        name.setToolTip(str(self.path))
        info.addWidget(name)
        folder = ElidedLabel(str(self.path.parent), Qt.ElideMiddle)
        folder.setObjectName("Muted")
        info.addWidget(folder)
        lay.addLayout(info, 1)

        self._menu_btn = IconFlatButton(
            icons.ELLIPSIS, tr("Open in another version"))
        self._menu_btn.clicked.connect(self._show_versions)
        lay.addWidget(self._menu_btn)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._versions:
            self._on_open(self.path, self._versions[0])

    def contextMenuEvent(self, event) -> None:
        menu = _menu(self)
        action = menu.addAction(tr("Open file location"))
        action.triggered.connect(lambda: self._on_reveal(self.path))
        menu.exec(event.globalPos())

    def _show_versions(self) -> None:
        menu = _menu(self)
        if not self._versions:
            menu.addAction(tr("No installed versions.")).setEnabled(False)
        for entry in self._versions:
            action = menu.addAction(
                tr("Open in Blender {version}", version=entry.version))
            action.triggered.connect(
                lambda _=False, e=entry: self._on_open(self.path, e))
        menu.exec(self._menu_btn.mapToGlobal(
            QPoint(0, self._menu_btn.height())))


class RecentView(QWidget):
    """Pantalla con los ficheros recientes agrupados por versión de Blender."""

    status_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        # objectName para el QSS (fondo como las listas) y WA_StyledBackground
        # porque una SUBCLASE de QWidget no pinta el fondo del QSS sin él.
        self.setObjectName("RecentView")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.platform = ""
        self.installed = []
        self.launcher = Launcher()
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Fila de cabecera de 44 px (como la de filtros de las listas): así esta
        # vista empieza a la misma altura que las demás al cambiar de pantalla.
        header = QFrame()
        header.setObjectName("Chrome")
        header.setFixedHeight(t.FILTERS_HEIGHT)
        head_lay = QHBoxLayout(header)
        head_lay.setContentsMargins(16, 4, 16, 4)
        title = QLabel(tr("Recent files"))
        head_lay.addWidget(title)
        head_lay.addStretch()
        root.addWidget(header)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("RecentScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("RecentBody")
        self.body = QVBoxLayout(body)
        self.body.setContentsMargins(14, 14, 14, 14)
        self.body.setSpacing(6)
        self.body.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(body)
        root.addWidget(self.scroll, 1)

    def set_system(self, platform: str, arch: str) -> None:
        """Fija el SO de este equipo (de dónde cuelga la config de cada versión)."""
        self.platform = platform or ""

    def set_installed(self, installed) -> None:
        """Recibe las versiones instaladas y repinta la lista."""
        self.installed = list(installed or [])
        self._rebuild()

    def _rebuild(self) -> None:
        _clear(self.body)
        if not self.installed:
            self._placeholder(tr("No installed Blender versions."))
            return
        groups = recent_service.grouped(self.installed, self.platform)
        if not groups:
            self._placeholder(tr("No recent files yet."))
            return
        for group in groups:
            versions = [entry for entry in self.installed
                        if minor_of(getattr(entry, "version", "") or "")
                        == group.series]
            header = QLabel(tr("Blender {version}", version=group.version))
            header.setObjectName("Muted")
            self.body.addWidget(header)
            for path in group.files:
                self.body.addWidget(
                    _RecentRow(path, versions, self._open, self._reveal))

    def _placeholder(self, text: str) -> None:
        label = QLabel(text)
        label.setObjectName("Muted")
        label.setAlignment(Qt.AlignHCenter)
        label.setWordWrap(True)
        self.body.addWidget(label)

    def _open(self, path, entry) -> None:
        """Abre el fichero en esa versión de Blender."""
        executable = getattr(entry, "executable", None)
        if entry is None or not executable:
            self.status_message.emit(tr("That version has no executable."))
            return
        try:
            self.launcher.launch(executable, args=[str(path)])
        except OSError as error:
            self.status_message.emit(str(error))
            return
        self.status_message.emit(
            tr("Opening {name} in Blender {version}",
               name=Path(path).name, version=entry.version))

    def _reveal(self, path) -> None:
        opener.reveal(path)
