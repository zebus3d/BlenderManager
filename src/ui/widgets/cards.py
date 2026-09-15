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
from ui import theme as t
from ui.widgets.buttons import CardButton, IconLinkButton, StarButton
from ui.widgets.labels import ElidedLabel

_LOGO = ASSETS_DIR / "images" / "blender_logo.png"

# Ancho minimo de un boton que solo lleva un icono (la papelera de la rejilla):
# con el padding corto del QSS ([iconOnly]) el glifo de 13 px necesita ~21 px.
MIN_ICON_BUTTON_WIDTH = 26


def _icon_font(size: int | None = None) -> QFont:
    from ui.fonts import icon_font

    return icon_font(size)


def _icon_only(button) -> None:
    """Marca un CardButton que solo lleva un icono.

    El QSS le quita el padding lateral (``[iconOnly="true"]``): con el normal,
    a zoom bajo el ancho fijo se queda por debajo del padding y la papelera
    salía como un recuadro rojo vacío. Vale con poner la propiedad antes de que
    el widget se muestre (igual que ``zebra`` o ``installed``): el primer
    *polish* ya la lee.
    """
    button.setProperty("iconOnly", "true")


def _launch_icon():
    """Icono de "play" verde como QIcon.

    En Kivy el icono se pintaba dentro del texto del botón (mezclando fuentes en
    el markup); en Qt hay que pasarlo como QIcon.
    """
    return _action_icon(icons.LAUNCH, "#22C55E")


def _download_icon():
    """Icono blanco de descarga (flecha hacia abajo), como el original."""
    return _action_icon(icons.DOWNLOAD, t.TEXT_SEL)


def _action_icon(glyph: str, color: str):
    from ui.fonts import glyph_icon

    return glyph_icon(glyph, 12, color)


def logo_shadow(widget, size: int):
    """Sombra negra suave bajo el logo: el `drop-shadow` de CSS, versión Qt.

    Qt repinta el widget a un pixmap y lo difumina (efecto de software), asi que
    se paga al pintar. Medido: con los logos de las tarjetas (40-120 px) la
    rejilla completa sube ~1 ms, nada al lado de lo que cuesta reconstruirla.

    El radio y el desplazamiento escalan con el tamaño para que la sombra no se
    coma el icono cuando el zoom es bajo ni quede ridicula cuando es alto. Va
    desplazada abajo a la derecha y con poco contraste: solo busca despegar el
    logo del fondo, no dibujar un contorno marcado.
    """
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QGraphicsDropShadowEffect

    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(max(3.0, size * 0.14))
    offset = max(1.0, size * 0.04)
    effect.setOffset(offset, offset)
    effect.setColor(QColor(0, 0, 0, 120))
    widget.setGraphicsEffect(effect)
    return effect


def card_shadow(widget) -> None:
    """Sombra sutil de la tarjeta entera, para despegarla del fondo.

    Misma dirección y contraste que la del logo (abajo a la derecha y leve),
    pero con desplazamiento fijo y no proporcional al zoom: la tarjeta es mucho
    más grande que el icono, así que unos pocos píxeles ya se leen como relieve
    aunque la ampliación suba y no acaban manchando el borde.

    OJO: instalar un ``QGraphicsDropShadowEffect`` obliga a pintar la tarjeta a
    un pixmap y difuminarlo en cada repintado (incluido el hover), así que se
    paga. Medido al pintar 60 tarjetas de rejilla de golpe: ~36 ms sin sombra
    frente a ~63 ms con ella. En uso normal solo se repinta la tarjeta que está
    bajo el ratón, así que es medio milisegundo, pero conviene saberlo antes de
    añadir más efectos.
    """
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QGraphicsDropShadowEffect

    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(10.0)
    effect.setOffset(2.0, 2.0)
    effect.setColor(QColor(0, 0, 0, 110))
    widget.setGraphicsEffect(effect)


def _favorite_star(marked: bool, on_toggle) -> StarButton:
    """Estrella de favorito de una tarjeta (misma diana que la "i": 24x24)."""
    star = StarButton(marked, tooltip_on=tr("Remove from favorites"),
                      tooltip_off=tr("Mark as favorite"))
    star.setFont(_icon_font())
    star.toggled.connect(on_toggle)
    return star


def _with_opacity(pix: QPixmap, opacity: float) -> QPixmap:
    """Devuelve el pixmap con esa opacidad.

    En Qt el ``opacity`` del QSS **no hace nada** sobre un QLabel con pixmap
    (comprobado: el canal alfa sale igual), asi que el atenuado de las builds
    que no tienes instaladas -que en la version Kivy si se veia- hay que
    pintarlo aqui.
    """
    from PySide6.QtGui import QPainter

    result = QPixmap(pix.size())
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.setOpacity(opacity)
    painter.drawPixmap(0, 0, pix)
    painter.end()
    return result


def _logo_label(size: int, dim: bool) -> QLabel:
    label = QLabel()
    pix = QPixmap(str(_LOGO))
    if not pix.isNull():
        scaled = pix.scaled(size, size, Qt.KeepAspectRatio,
                            Qt.SmoothTransformation)
        if dim:
            scaled = _with_opacity(scaled, 0.32)
        label.setPixmap(scaled)
    logo_shadow(label, size)
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
    favorite_toggled = Signal(object, bool)   # build, marcada

    def __init__(self, build, installed: bool, zebra: bool, zoom: float = 1.0,
                 marked: bool = False, parent=None):
        super().__init__(parent)
        self.build = build
        self.installed = installed
        self.setObjectName("Card")
        self.setProperty("zebra", "true" if zebra else "false")
        self.setProperty("installed", "true" if installed else "false")
        self.setAttribute(Qt.WA_Hover, True)
        card_shadow(self)

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

    def _star(self, marked: bool) -> StarButton:
        return _favorite_star(
            marked, lambda on: self.favorite_toggled.emit(self.build, on))


class BuildCard(BaseBuildCard):
    """Tarjeta en modo lista (una fila por compilación)."""

    def __init__(self, build, installed: bool, zebra: bool,
                 marked: bool = False, parent=None):
        super().__init__(build, installed, zebra, marked=marked, parent=parent)
        self.setFixedHeight(78)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 11, 12, 11)
        lay.setSpacing(12)
        lay.addWidget(_logo_label(44, dim=not installed))

        text_col = QVBoxLayout()
        text_col.setSpacing(3)
        top = QHBoxLayout()
        top.setSpacing(10)
        title = ElidedLabel(f"Blender {self.version}", Qt.ElideMiddle)
        title.setObjectName("Title")
        if not installed:
            title.setStyleSheet("color: rgba(230,230,230,0.6);")
        top.addWidget(title)
        top.addWidget(self._badge())
        top.addStretch()
        text_col.addLayout(top)
        meta = ElidedLabel(self.meta_text, Qt.ElideRight)
        meta.setObjectName("Muted")
        if not installed:
            meta.setStyleSheet("color: rgba(152,152,152,0.6);")
        text_col.addWidget(meta)
        lay.addLayout(text_col, 1)

        lay.addWidget(self._star(marked))
        lay.addWidget(self._info())

        action = CardButton(
            tr("Launch") if installed else tr("Download"),
            variant="dark" if installed else "accent",
            tooltip=tr("Launch this installed version") if installed
            else tr("Download and install this version"),
        )
        # El icono depende de la accion: flecha verde para lanzar (si ya la
        # tienes) y flecha blanca hacia abajo para descargar. En Kivy se pintaba
        # dentro del texto; en Qt hace falta un QIcon.
        action.setIcon(_launch_icon() if installed else _download_icon())
        action.clicked.connect(lambda: self.action_clicked.emit(self.build))
        lay.addWidget(action)


def _grid_height(zoom: float, with_badge: bool = True) -> int:
    """Alto de una tarjeta de rejilla para un ``zoom`` dado.

    No es ``196 * zoom``: las etiquetas (título, meta, "Instalada"...) NO
    escalan con el zoom, así que con poca ampliación se recortaban. Medido:
    el contenido mide ~120·zoom + 110 px (con insignia), y usamos un poco de
    holgura para que nunca se corte.
    """
    base = 118 if with_badge else 96
    return int(120 * zoom + base)


class GridBuildCard(BaseBuildCard):
    """Tarjeta en modo rejilla (icono grande y botón debajo)."""

    def __init__(self, build, installed: bool, zebra: bool, zoom: float = 1.0,
                 marked: bool = False, parent=None):
        super().__init__(build, installed, zebra, zoom, marked=marked,
                         parent=parent)
        # La fila de la insignia ("Instalada") se reserva SIEMPRE, aunque la
        # compilación no esté instalada: en el Kivy original la etiqueta existía
        # con el texto vacío y así todas las tarjetas de la tienda medían lo
        # mismo. Al ahorrársela a las descargables, estas salían 22 px más bajas
        # que las instaladas y la rejilla quedaba desigual.
        self.setFixedHeight(_grid_height(zoom, with_badge=True))
        lay = QVBoxLayout(self)
        m = int(14 * zoom)
        lay.setContentsMargins(m, m, m, m)
        lay.setSpacing(int(6 * zoom))

        logo = _logo_label(int(68 * zoom), dim=not installed)
        logo.setAlignment(Qt.AlignHCenter)
        lay.addWidget(logo)

        title = ElidedLabel(f"Blender {self.version}", Qt.ElideMiddle)
        title.setObjectName("Title")
        title.setAlignment(Qt.AlignHCenter)
        if not installed:
            title.setStyleSheet("color: rgba(230,230,230,0.6);")
        lay.addWidget(title)

        sub = ElidedLabel(f"{self.channel_text}  ·  {self.meta_text}",
                          Qt.ElideRight)
        sub.setObjectName("Warning" if self.is_lts else "Info")
        sub.setAlignment(Qt.AlignHCenter)
        lay.addWidget(sub)

        tag = QLabel(tr("Installed build") if installed else "")
        tag.setObjectName("Success")
        tag.setAlignment(Qt.AlignHCenter)
        lay.addWidget(tag)

        lay.addStretch()

        row = QHBoxLayout()
        row.setSpacing(int(6 * zoom))
        row.addStretch()
        row.addWidget(self._star(marked))
        row.addWidget(self._info())
        action = CardButton(
            tr("Launch") if installed else tr("Download"),
            variant="dark" if installed else "accent",
            tooltip=tr("Launch this installed version") if installed
            else tr("Download and install this version"),
        )
        action.setIcon(_launch_icon() if installed else _download_icon())
        action.clicked.connect(lambda: self.action_clicked.emit(self.build))
        row.addWidget(action)
        row.addStretch()
        lay.addLayout(row)


class InstalledCard(_HoverCard, QFrame):
    """Versión ya instalada (lanzar / desinstalar) en modo lista."""

    launch_clicked = Signal(object)   # entry
    delete_clicked = Signal(object)   # entry
    notes_clicked = Signal(str)       # version
    favorite_toggled = Signal(object, bool)   # entry, marcada

    def __init__(self, entry, zebra: bool, marked: bool = False, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.setObjectName("Card")
        self.setProperty("zebra", "true" if zebra else "false")
        self.setProperty("installed", "true")
        self.setAttribute(Qt.WA_Hover, True)
        card_shadow(self)
        self.setFixedHeight(66)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 12, 10)
        lay.setSpacing(10)
        lay.addWidget(_logo_label(40, dim=False))

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title = ElidedLabel(entry.name, Qt.ElideMiddle)
        title.setObjectName("Title")
        text_col.addWidget(title)
        meta = ElidedLabel(f"Blender {entry.version}   ·   {entry.path}",
                           Qt.ElideRight)
        meta.setObjectName("Muted")
        text_col.addWidget(meta)
        lay.addLayout(text_col, 1)

        lay.addWidget(_favorite_star(
            marked, lambda on: self.favorite_toggled.emit(entry, on)))
        info = IconLinkButton(icons.INFO, tr("Read the release notes for this version"))
        info.setFont(_icon_font())
        info.clicked.connect(lambda: self.notes_clicked.emit(entry.version))
        lay.addWidget(info)

        launch = CardButton(tr("Launch"), variant="dark",
                            tooltip=tr("Launch this installed version"))
        launch.setIcon(_launch_icon())
        launch.clicked.connect(lambda: self.launch_clicked.emit(entry))
        lay.addWidget(launch)

        delete = CardButton(icons.DELETE, variant="danger",
                            tooltip=tr("Remove this installed version"))
        _icon_only(delete)
        delete.setFont(_icon_font())
        delete.setFixedWidth(46)
        delete.clicked.connect(lambda: self.delete_clicked.emit(entry))
        lay.addWidget(delete)


class GridInstalledCard(_HoverCard, QFrame):
    """Versión instalada en cuadrícula (icono grande y botones debajo)."""

    launch_clicked = Signal(object)
    delete_clicked = Signal(object)
    notes_clicked = Signal(str)
    favorite_toggled = Signal(object, bool)   # entry, marcada

    def __init__(self, entry, zebra: bool, zoom: float = 1.0,
                 marked: bool = False, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.setObjectName("Card")
        self.setProperty("zebra", "true" if zebra else "false")
        self.setProperty("installed", "true")
        self.setAttribute(Qt.WA_Hover, True)
        card_shadow(self)
        self.setFixedHeight(_grid_height(zoom, with_badge=False))

        lay = QVBoxLayout(self)
        m = int(12 * zoom)
        lay.setContentsMargins(m, m, m, m)
        lay.setSpacing(int(6 * zoom))

        logo = _logo_label(int(64 * zoom), dim=False)
        logo.setAlignment(Qt.AlignHCenter)
        lay.addWidget(logo)

        title = ElidedLabel(entry.name, Qt.ElideMiddle)
        title.setObjectName("Title")
        title.setAlignment(Qt.AlignHCenter)
        lay.addWidget(title)

        meta = ElidedLabel(f"Blender {entry.version}", Qt.ElideRight)
        meta.setObjectName("Muted")
        meta.setAlignment(Qt.AlignHCenter)
        lay.addWidget(meta)

        lay.addStretch()

        row = QHBoxLayout()
        row.setSpacing(int(6 * zoom))
        row.addWidget(_favorite_star(
            marked, lambda on: self.favorite_toggled.emit(entry, on)))
        info = IconLinkButton(icons.INFO, tr("Read the release notes for this version"))
        info.setFont(_icon_font())
        info.clicked.connect(lambda: self.notes_clicked.emit(entry.version))
        row.addWidget(info)
        launch = CardButton(tr("Launch"), variant="dark",
                            tooltip=tr("Launch this installed version"))
        launch.setIcon(_launch_icon())
        launch.clicked.connect(lambda: self.launch_clicked.emit(entry))
        row.addWidget(launch, 1)
        delete = CardButton(icons.DELETE, variant="danger",
                            tooltip=tr("Remove this installed version"))
        _icon_only(delete)
        # El ancho acompana al zoom, pero nunca por debajo de lo que necesita el
        # glifo: a 0.6 salia un recuadro rojo vacio (el icono no cabia). El
        # tamano del icono no se puede escalar con setFont: el `font-size` del
        # QSS global (13 px) pisa lo que ponga el widget, y da igual, porque el
        # resto del texto de la tarjeta tampoco escala.
        delete.setFont(_icon_font())
        delete.setFixedWidth(max(int(42 * zoom), MIN_ICON_BUTTON_WIDTH))
        delete.clicked.connect(lambda: self.delete_clicked.emit(entry))
        row.addWidget(delete)
        lay.addLayout(row)
