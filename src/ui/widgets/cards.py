"""Tarjetas de compilaciones: la tienda y las versiones instaladas.

Sustituyen a ``ui/widgets/cards.py`` + ``views/cards.kv``. Cada tarjeta existe
en versión lista (una fila) y rejilla (icono grande). En vez de llamar
directamente al controlador, emiten señales; la ventana principal las conecta.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from i18n import tr
from paths import ASSETS_DIR
from ui import icons
from ui.widgets.buttons import CardButton, IconLinkButton

_LOGO = ASSETS_DIR / "images" / "blender_logo.png"


def _icon_font() -> QFont:
    from ui.fonts import icon_font

    return icon_font()


def _logo_label(size: int, dim: bool) -> QLabel:
    label = QLabel()
    pix = QPixmap(str(_LOGO))
    if not pix.isNull():
        label.setPixmap(pix.scaled(size, size, Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation))
    if dim:
        label.setStyleSheet("opacity: 0.32;")
    return label


class _HoverCard:
    """Resalta la tarjeta al pasar el ratón.

    No basta con ``QFrame#Card:hover`` en el QSS: cuando el ratón está encima de
    un hijo (una etiqueta o un botón), el padre puede no recibir el estado
    hover. Aquí lo marcamos a mano con una propiedad dinámica que el QSS lee.
    """

    def enterEvent(self, event):
        super().enterEvent(event)
        self._set_hover(True)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._set_hover(False)

    def _set_hover(self, on: bool) -> None:
        self.setProperty("hover", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class BaseBuildCard(_HoverCard, QFrame):
    """Base común de las tarjetas de compilaciones."""

    action_clicked = Signal(object)   # build
    notes_clicked = Signal(str)       # version

    def __init__(self, build, installed: bool, zebra: bool, zoom: float = 1.0,
                 parent=None):
        super().__init__(parent)
        self.build = build
        self.installed = installed
        self.setObjectName("Card")
        self.setProperty("zebra", "true" if zebra else "false")
        self.setProperty("installed", "true" if installed else "false")
        self.setAttribute(Qt.WA_Hover, True)

        self.title_text = build.version
        self.version = build.version
        if build.experimental:
            self.channel_text = build.branch
            self.is_lts = False
        else:
            if build.is_lts:
                channel = "LTS"
            elif build.risk in ("alpha", "daily", "beta"):
                channel = {"alpha": "Alpha", "daily": "Daily", "beta": "Beta"}[build.risk]
            else:
                channel = "Stable"
            self.channel_text = tr(channel)
            self.is_lts = build.is_lts

        details = [build.human_size]
        if not build.experimental:
            details.append(build.branch)
        details.append(build.arch)
        self.meta_text = "  ·  ".join(details)

    def _badge(self) -> QLabel:
        label = QLabel(self.channel_text)
        label.setObjectName("Warning" if self.is_lts else "Info")
        return label

    def _info(self) -> IconLinkButton:
        btn = IconLinkButton(icons.INFO, tr("Read the release notes for this version"))
        btn.setFont(_icon_font())
        btn.clicked.connect(lambda: self.notes_clicked.emit(self.version))
        return btn


class BuildCard(BaseBuildCard):
    """Tarjeta en modo lista (una fila por compilación)."""

    def __init__(self, build, installed: bool, zebra: bool, parent=None):
        super().__init__(build, installed, zebra, parent=parent)
        self.setFixedHeight(78)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 11, 12, 11)
        lay.setSpacing(12)
        lay.addWidget(_logo_label(44, dim=not installed))

        text_col = QVBoxLayout()
        text_col.setSpacing(3)
        top = QHBoxLayout()
        top.setSpacing(10)
        title = QLabel(f"Blender {self.version}")
        title.setObjectName("Title")
        if not installed:
            title.setStyleSheet("color: rgba(230,230,230,0.6);")
        top.addWidget(title)
        top.addWidget(self._badge())
        top.addStretch()
        text_col.addLayout(top)
        meta = QLabel(self.meta_text)
        meta.setObjectName("Muted")
        meta.setTextInteractionFlags(Qt.NoTextInteraction)
        if not installed:
            meta.setStyleSheet("color: rgba(152,152,152,0.6);")
        text_col.addWidget(meta)
        lay.addLayout(text_col, 1)

        lay.addWidget(self._info())

        action = CardButton(
            tr("Launch") if installed else tr("Download"),
            variant="neutral" if installed else "accent",
            tooltip=tr("Launch this installed version") if installed
            else tr("Download and install this version"),
        )
        action.clicked.connect(lambda: self.action_clicked.emit(self.build))
        lay.addWidget(action)


class GridBuildCard(BaseBuildCard):
    """Tarjeta en modo rejilla (icono grande y botón debajo)."""

    def __init__(self, build, installed: bool, zebra: bool, zoom: float = 1.0,
                 parent=None):
        super().__init__(build, installed, zebra, zoom, parent=parent)
        self.setFixedHeight(int(196 * zoom))
        lay = QVBoxLayout(self)
        m = int(14 * zoom)
        lay.setContentsMargins(m, m, m, m)
        lay.setSpacing(int(6 * zoom))

        logo = _logo_label(int(68 * zoom), dim=not installed)
        logo.setAlignment(Qt.AlignHCenter)
        lay.addWidget(logo)

        title = QLabel(f"Blender {self.version}")
        title.setObjectName("Title")
        title.setAlignment(Qt.AlignHCenter)
        if not installed:
            title.setStyleSheet("color: rgba(230,230,230,0.6);")
        lay.addWidget(title)

        sub = QLabel(f"{self.channel_text}  ·  {self.meta_text}")
        sub.setObjectName("Warning" if self.is_lts else "Info")
        sub.setAlignment(Qt.AlignHCenter)
        lay.addWidget(sub)

        if installed:
            tag = QLabel(tr("Installed build"))
            tag.setObjectName("Success")
            tag.setAlignment(Qt.AlignHCenter)
            lay.addWidget(tag)

        lay.addStretch()

        row = QHBoxLayout()
        row.setSpacing(int(6 * zoom))
        row.addStretch()
        row.addWidget(self._info())
        action = CardButton(
            tr("Launch") if installed else tr("Download"),
            variant="neutral" if installed else "accent",
            tooltip=tr("Launch this installed version") if installed
            else tr("Download and install this version"),
        )
        action.clicked.connect(lambda: self.action_clicked.emit(self.build))
        row.addWidget(action)
        row.addStretch()
        lay.addLayout(row)


class InstalledCard(_HoverCard, QFrame):
    """Versión ya instalada (lanzar / desinstalar) en modo lista."""

    launch_clicked = Signal(object)   # entry
    delete_clicked = Signal(object)   # entry
    notes_clicked = Signal(str)       # version

    def __init__(self, entry, zebra: bool, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.setObjectName("Card")
        self.setProperty("zebra", "true" if zebra else "false")
        self.setProperty("installed", "true")
        self.setAttribute(Qt.WA_Hover, True)
        self.setFixedHeight(66)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 12, 10)
        lay.setSpacing(10)
        lay.addWidget(_logo_label(40, dim=False))

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title = QLabel(entry.name)
        title.setObjectName("Title")
        text_col.addWidget(title)
        meta = QLabel(f"Blender {entry.version}   ·   {entry.path}")
        meta.setObjectName("Muted")
        text_col.addWidget(meta)
        lay.addLayout(text_col, 1)

        info = IconLinkButton(icons.INFO, tr("Read the release notes for this version"))
        info.setFont(_icon_font())
        info.clicked.connect(lambda: self.notes_clicked.emit(entry.version))
        lay.addWidget(info)

        launch = CardButton(f"{icons.LAUNCH}  {tr('Launch')}", variant="neutral",
                            tooltip=tr("Launch this installed version"))
        launch.clicked.connect(lambda: self.launch_clicked.emit(entry))
        lay.addWidget(launch)

        delete = CardButton(icons.DELETE, variant="danger",
                            tooltip=tr("Remove this installed version"))
        delete.setFont(_icon_font())
        delete.setFixedWidth(46)
        delete.clicked.connect(lambda: self.delete_clicked.emit(entry))
        lay.addWidget(delete)


class GridInstalledCard(_HoverCard, QFrame):
    """Versión instalada en cuadrícula (icono grande y botones debajo)."""

    launch_clicked = Signal(object)
    delete_clicked = Signal(object)
    notes_clicked = Signal(str)

    def __init__(self, entry, zebra: bool, zoom: float = 1.0, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.setObjectName("Card")
        self.setProperty("zebra", "true" if zebra else "false")
        self.setProperty("installed", "true")
        self.setAttribute(Qt.WA_Hover, True)
        self.setFixedHeight(int(188 * zoom))

        lay = QVBoxLayout(self)
        m = int(12 * zoom)
        lay.setContentsMargins(m, m, m, m)
        lay.setSpacing(int(6 * zoom))

        logo = _logo_label(int(64 * zoom), dim=False)
        logo.setAlignment(Qt.AlignHCenter)
        lay.addWidget(logo)

        title = QLabel(entry.name)
        title.setObjectName("Title")
        title.setAlignment(Qt.AlignHCenter)
        lay.addWidget(title)

        meta = QLabel(f"Blender {entry.version}")
        meta.setObjectName("Muted")
        meta.setAlignment(Qt.AlignHCenter)
        lay.addWidget(meta)

        lay.addStretch()

        row = QHBoxLayout()
        row.setSpacing(int(6 * zoom))
        info = IconLinkButton(icons.INFO, tr("Read the release notes for this version"))
        info.setFont(_icon_font())
        info.clicked.connect(lambda: self.notes_clicked.emit(entry.version))
        row.addWidget(info)
        launch = CardButton(tr("Launch"), variant="neutral",
                            tooltip=tr("Launch this installed version"))
        launch.clicked.connect(lambda: self.launch_clicked.emit(entry))
        row.addWidget(launch, 1)
        delete = CardButton(icons.DELETE, variant="danger",
                            tooltip=tr("Remove this installed version"))
        delete.setFont(_icon_font())
        delete.setFixedWidth(int(42 * zoom))
        delete.clicked.connect(lambda: self.delete_clicked.emit(entry))
        row.addWidget(delete)
        lay.addLayout(row)
