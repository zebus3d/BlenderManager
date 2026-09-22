"""Ventana principal y controlador (versión PySide6).

Sustituye a ``ui/widgets/root.py`` + ``views/main.kv``. Aquí vive la lógica de
interfaz: ajustes, listado de compilaciones, filtros, descarga/extracción en
segundo plano, lanzamiento de versiones instaladas y navegación entre vistas.

Las descargas corren en hilos (``services.downloader``); sus callbacks se
marshalan al hilo de la interfaz con ``_Bridge`` (señales Qt), porque tocar
widgets desde otro hilo revienta Qt igual que reventaba Kivy.
"""

import os
import shlex
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QStyle,
    QTabBar,
    QTabWidget,
    QStyleOptionSlider,
    QVBoxLayout,
    QWidget,
)

import i18n
import version
from i18n import tr
from model.build import minor_of
from services import (
    api,
    autostart,
    channels,
    detector,
    elevate,
    installed as installed_service,
    macos_dmg,
    organizer,
    opener,
    settings as settings_service,
    sources,
    updater,
)
from services.downloader import Downloader, log as download_log
from services.extractor import extract, is_archive
from services import launcher
from services.launcher import Launcher
from ui import icons
from ui import theme as t
from ui.fonts import icon_font
from ui.widgets.buttons import CardButton, IconFlatButton, Pill, SideButton, SwitchPill
from ui.widgets.layouts import clear_layout, list_scroll
from ui.widgets.menus import card_menu
from ui.widgets.cards import (
    BuildCard,
    GridBuildCard,
    GridInstalledCard,
    InstalledCard,
    card_shadow,
    logo_shadow,
    settings_card,
)
from ui.widgets.dialogs import (
    AppDialog,
    ProgressDialog,
    confirm,
    show_error,
    show_info,
    update_available,
)
from ui.widgets.folders import MAX_VISIBLE_ROWS, TYPE_LABELS, FolderRow
from ui.widgets.labels import ElidedLabel
from ui.widgets.addons import AddonsView
from ui.widgets.migrate import MigrateView
from ui.widgets.recent import RecentView
from ui.widgets.tray import TrayIcon

PLATFORMS = {"GNU/Linux": "linux", "Windows": "windows", "macOS": "darwin"}
PLATFORM_LABELS = {value: key for key, value in PLATFORMS.items()}
ARCH_LABELS = ["x86_64", "arm64"]
LANGUAGE_IDS = {"auto": "Automatic", "en": "English", "es": "Spanish"}
MIN_ZOOM, MAX_ZOOM = 0.6, 1.8

# Alto de la fila de filtros (la que lleva las pestañas de canal). Vive en el
# tema porque Ajustes y Migración lo usan para dejar sus pestañas a la misma
# altura que las de canal.
FILTERS_HEIGHT = t.FILTERS_HEIGHT
# Alto de los controles de la fila de filtros (pastillas de vista y combos):
# el mismo que los tags de canal, para que la fila quede a ras.
FILTER_CONTROL_HEIGHT = t.CONTROL_HEIGHT

# Vistas que solo se ven con las opciones experimentales (Ajustes > Avanzado).
# Recientes y Migración salieron de aquí cuando quedaron probadas (Migración
# tiene la batería de tests de UI más grande de la app y feedback de usuarios
# reales); el gestor de add-ons sigue en desarrollo (arranca Blender para leer
# el estado).
EXPERIMENTAL_VIEWS = ("addons",)
# Cuánto sube/baja el zoom con Ctrl +/-. El slider va en pasos de 1 %.
ZOOM_STEP = 0.1

# Tamaño con el que se abre la ventana la primera vez y al restablecerla, y el
# mínimo por debajo del cual la interfaz se recorta.
# El alto (760) no es redondo por gusto: con el zoom al 80 % y 3 columnas
# (1060 px de ancho), 3 filas de tarjetas miden 585 px de contenido y hacen
# falta ~741 de ventana (72+44+40 de cabecera/filtros/pie). Con los 680 de antes
# la tercera fila quedaba cortada. Medido con `_grid_height(0.8) == 179`.
DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT = 1060, 760
MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT = 880, 540

# Tooltips de los filtros de canal. Se explican para quien no sabe qué es una
# LTS o una compilación diaria; las claves de i18n son estos textos en inglés.
# Los saltos de línea (\n) se ven en el tooltip, así que pueden ser varias
# líneas.
# Canales de la barra de filtros, en el orden en que se enseñan. Son
# excluyentes (solo se ve uno a la vez), así que van en una barra de pestañas
# y no en pastillas sueltas. Aquí solo viven las **etiquetas**: las claves son
# las de ``services.channels.CHANNELS`` y un test vigila que no se separen.
CHANNELS = (
    ("all", "All"),
    ("lts", "LTS"),
    ("stable", "Stable"),
    ("daily", "Daily"),
    ("experimental", "Experimental"),
    ("favorites", "Favorites"),
)

# Título que se enseña en la cabecera según la vista. La cabecera lleva arriba
# "Blender Manager" y debajo esto, para saber en qué sección se está.
SECTION_TITLES = {
    "installed": "Local",
    "store": "Cloud",
    "recent": "Recent files",
    "addons": "Add-ons",
    "migrate": "Migration",
    "settings": "Settings",
}

CHANNEL_TOOLTIPS = {
    "all": "Show every build: stable, LTS, daily and alpha.",
    "lts": "LTS = Long Term Support.\nVersions maintained for years and the "
           "most stable.\nRecommended for everyday work.",
    "stable": "Stable versions that are not LTS.\nThey are the latest official "
              "releases, supported until the next one.",
    "daily": "Daily and alpha builds with the newest changes.\nThey can fail: "
             "for testing, not for work.",
    "experimental": "Branches with new features still in development.\nThey are "
                    "not ready for production and the list is usually empty.",
    "favorites": "Only the builds you marked with the star.",
}


def _write_problem(folder) -> str:
    """Motivo por el que no se puede escribir en ``folder``, o "" si sí se puede.

    Crea la carpeta si falta (que es lo que hará la descarga igualmente) y
    escribe y borra un fichero de prueba. Existe por un caso real: con la
    carpeta de las LTS en otro disco, si no había permiso de escritura la
    descarga terminaba en un genérico "Fallo en la descarga" y no había forma
    de saber que era eso. Mejor decirlo antes de bajar cientos de MB.
    """
    path = Path(folder).expanduser()
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".blendermanager-write-test"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
    except OSError as error:
        return str(error)
    return ""



class _Bridge(QObject):
    """Reenvía callbacks de hilos de descarga al hilo de la interfaz."""

    progress = Signal(int, int)
    done = Signal(str)
    error = Signal(str)


class _ZoomSlider(QSlider):
    """Slider del zoom que vuelve al valor por defecto con ``Ctrl`` + clic.

    ``QSlider`` no distingue el clic normal del clic con modificadores, así que
    hay que mirarlo en ``mousePressEvent``.

    Y en la ranura, ``QSlider`` da un ``pageStep`` (10 % de zoom, medido) en vez
    de llevar el tirador al punto pulsado. Aquí se mapea la coordenada a un valor
    —el tirador queda justo bajo el cursor, y sigue ahí mientras se arrastra—,
    que es lo que se espera de un deslizador. El dibujo sigue en ``qss.py``.
    """

    reset_requested = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # El tirador mide 16 px de alto, pero la diana la marca el widget: con
        # los 15 px por defecto queda por debajo del mínimo de 24 px (WCAG 2.5.8).
        # La fila de la cabecera ya mide 32 px, así que subirlo no mueve nada.
        self.setMinimumHeight(24)
        self._drag_active = False

    def _sub_rect(self, sub_control):
        """Rectángulo de una parte del slider (ranura o tirador) ya maquetado."""
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        return self.style().subControlRect(
            QStyle.CC_Slider, option, sub_control, self)

    def _value_at(self, x):
        """Valor cuyo tirador queda centrado en la coordenada ``x``."""
        groove = self._sub_rect(QStyle.SC_SliderGroove)
        handle = self._sub_rect(QStyle.SC_SliderHandle)
        span = groove.width() - handle.width()
        if span <= 0:
            return self.value()
        value = QStyle.sliderValueFromPosition(
            self.minimum(), self.maximum(),
            x - groove.left() - handle.width() // 2, span)
        return min(self.maximum(), max(self.minimum(), value))

    def mousePressEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            self.reset_requested.emit()
            event.accept()
            return
        self._drag_active = True
        self.setSliderDown(True)
        self.setValue(self._value_at(event.position().toPoint().x()))
        event.accept()

    def mouseMoveEvent(self, event):
        if not self._drag_active:
            super().mouseMoveEvent(event)
            return
        self.setValue(self._value_at(event.position().toPoint().x()))
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag_active:
            self._drag_active = False
            self.setSliderDown(False)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class MainWindow(QWidget):
    """Pantalla principal: cabecera, filtros, listas y pie con progreso/zoom."""

    # Señales para marshar el resultado de los hilos al hilo de la interfaz.
    # (QTimer.singleShot desde un hilo de Python NO es fiable para esto.)
    builds_loaded = Signal(object)
    download_done = Signal(str, object)   # path, build
    download_error = Signal(str)
    extract_done = Signal(str)
    dmg_manual = Signal(str)   # macOS: no se pudo instalar, se revela a mano
    update_result = Signal(str, object, bool)
    update_applied = Signal(str)
    update_manual = Signal()   # descargada, pero hay que instalarla a mano
    source_chosen = Signal(object, object)   # build, Source
    source_update_done = Signal(bool, str)
    release_notes_result = Signal(bool)   # abierta o no
    folder_move_progress = Signal(int, int, str)   # hechas, total, nombre
    folder_move_done = Signal(int, int, str)       # movidas, fallidas, error

    # Índice de la pestaña "Carpetas" dentro de Ajustes (va la segunda, justo
    # después de Descargas, porque es lo que más se toca de las dos).
    FOLDERS_TAB = 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{tr('Blender Manager')} {updater.app_version()}")
        self.setMinimumSize(880, 540)

        self.settings = settings_service.Settings.load()
        i18n.set_language(self.settings.language)
        self.system = detector.detect()
        self.current_version = updater.app_version()

        detected_platform = PLATFORM_LABELS.get(self.system.os_name, "GNU/Linux")
        detected_arch = "x86_64" if self.system.arch in ("amd64", "x86_64") else self.system.arch
        self.platform_label = (
            self.settings.platform if self.settings.platform in PLATFORMS else detected_platform
        )
        self.arch_label = (
            self.settings.arch if self.settings.arch in ARCH_LABELS else detected_arch
        )
        self.language_label = tr(LANGUAGE_IDS.get(self.settings.language, "auto"))
        # Las carpetas NO se copian a atributos de la ventana: la lista de
        # ``settings.folders`` es la única fuente de verdad y las filas la leen
        # y la escriben directamente. Los espejos de antes (``dest_folder``,
        # ``lts_folder``...) eran cinco sitios donde el mismo dato podía
        # quedarse viejo.
        self.folder_rows = {}
        self._move_dialog = None
        self._move_cancel = None
        self.launch_args = self.settings.launch_args
        self.delete_archive = bool(self.settings.delete_archive)
        # Bandeja del sistema: dos decisiones independientes (cerrar y
        # minimizar). ``_tray`` se crea perezosamente (solo si hace falta).
        self.close_to_tray = bool(self.settings.close_to_tray)
        self.minimize_to_tray = bool(self.settings.minimize_to_tray)
        self.start_minimized = bool(self.settings.start_minimized)
        self._tray = None
        # Salidas de verdad (actualizar la app o reiniciar tras un git pull):
        # esas no pueden acabar escondidas en la bandeja.
        self._force_quit = False
        self.auto_update = bool(self.settings.auto_update)
        self.periodic_update = bool(self.settings.periodic_update)
        self.layout_mode = (self.settings.layout_mode
                            if self.settings.layout_mode in ("grid", "list") else "grid")
        try:
            self.zoom = min(MAX_ZOOM, max(MIN_ZOOM, float(self.settings.zoom)))
        except (TypeError, ValueError):
            self.zoom = settings_service.DEFAULT_ZOOM
        # Zoom al que vuelven Ctrl+0 y el Ctrl+clic del slider. Se acota aquí
        # (como ``zoom``) para que un settings.json editado a mano no deje la
        # rejilla en un valor imposible.
        try:
            self.settings.reset_zoom = min(
                MAX_ZOOM, max(MIN_ZOOM, float(self.settings.reset_zoom)))
        except (TypeError, ValueError):
            self.settings.reset_zoom = settings_service.DEFAULT_ZOOM

        self.view = "store"
        # A dónde vuelve el botón de ajustes al pulsarlo por segunda vez.
        self._previous_view = "store"
        # El filtro que estaba puesto la última vez (Favoritos incluido).
        self.channel = self.settings.channel
        self.search = ""

        self.downloader = Downloader()
        self.update_downloader = Downloader()
        self._update_assets = []
        self.launcher = Launcher()

        self.builds = []
        self.installed = installed_service.scan_folders(self.settings.scan_roots(),
                                                        self.platform)
        self.view = "installed" if self.installed else "store"
        # Actualizaciones de Blender detectadas para lo que ya tienes instalado:
        # un parche de la misma serie (botón en la tarjeta) o una serie nueva
        # (diálogo). Se recalculan al cargar compilaciones y al reescanear.
        self.updates_by_path = {}
        self.series_updates = []
        # Series ya ofrecidas en esta sesión: el diálogo no se repite cada vez
        # que se refresca el listado.
        self._series_offered = set()
        # Instalada que hay que borrar cuando acabe de extraerse la nueva
        # (cuando el usuario eligió "Reemplazar").
        self._replace_entry = None

        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(lambda: self._set_status(tr("Ready")))
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._apply_search)
        self._pending_search = ""
        # El zoom no reconstruye en cada tick del slider (eso era lo que hacia
        # parpadear la rejilla), pero tampoco espera a que sueltes: refresca
        # como mucho cada 80 ms y, cuando el slider lleva 250 ms quieto, para y
        # guarda. Medido: reconstruir la tienda entera cuesta ~7-25 ms.
        self._zoom_tick = QTimer(self)
        self._zoom_tick.setInterval(80)
        self._zoom_tick.timeout.connect(self._rebuild_zoom_views)
        self._zoom_settle = QTimer(self)
        self._zoom_settle.setSingleShot(True)
        self._zoom_settle.setInterval(250)
        self._zoom_settle.timeout.connect(self._commit_zoom)
        self._update_checking = False
        self._auto_checked = False
        self._source_dialog = None
        # Versión de la app de la que ya se avisó en esta sesión (para que el
        # chequeo periódico no repita el diálogo cada X minutos).
        self._offered_update_tag = ""
        # Chequeo periódico de la propia aplicación (BlenderManager).
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._periodic_update_check)
        self._apply_update_timer()

        # Cooldown del reescaneo al recuperar el foco: cambiar de ventana no
        # puede lanzar un escaneo de disco cada vez.
        self._focus_refresh = QTimer(self)
        self._focus_refresh.setSingleShot(True)
        self._focus_refresh.setInterval(2000)

        # Conectamos las señales de los hilos ANTES de montar la UI.
        self.builds_loaded.connect(self._on_builds_loaded)
        self.download_done.connect(self._on_download_done)
        self.download_error.connect(self._on_download_error)
        self.extract_done.connect(self._on_extract_done)
        self.dmg_manual.connect(self._on_dmg_manual)
        self.update_result.connect(self._on_update_result)
        self.update_applied.connect(self._on_update_applied)
        self.update_manual.connect(self._on_update_manual)
        self.source_update_done.connect(self._on_source_update_done)
        self.release_notes_result.connect(self._on_release_notes_result)
        self.folder_move_progress.connect(self._on_folder_move_progress)
        self.folder_move_done.connect(self._on_folder_move_done)
        self.source_chosen.connect(self._start_download)

        self._build_ui()
        # Los temporizadores llevan ``self`` de contexto: si la ventana se
        # destruye antes de que disparen (pasa en los tests, que crean y
        # borran ventanas a docenas), Qt no llama al callback en vez de
        # hacerlo sobre un objeto ya borrado.
        QTimer.singleShot(100, self, lambda: self.refresh(force=False))
        # Quien venga de una versión anterior merece enterarse de que ahora
        # puede repartir sus Blender por varias carpetas. Se enseña una sola
        # vez y **después** de que la ventana esté montada.
        if not self.settings.folders_hint_shown:
            QTimer.singleShot(400, self, self._show_folders_hint)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())
        # El stack principal tiene las tres zonas: las listas (Local y Nube),
        # Migración y Ajustes. Las listas llevan dentro su fila de filtros.
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_lists_view())
        self.migrate_view = MigrateView()
        self.migrate_view.set_system(self.system.os_name, self.system.arch)
        self.migrate_view.status_message.connect(self._show_message)
        self.migrate_view.snapshot_keep_changed.connect(self.set_snapshot_keep)
        self.migrate_view.set_snapshot_keep(self.settings.snapshot_keep)
        self.stack.addWidget(self.migrate_view)
        self.recent_view = RecentView(open_file=self.launch_installed)
        self.recent_view.set_system(self.system.os_name)
        self.recent_view.status_message.connect(self._show_message)
        self.stack.addWidget(self.recent_view)
        self.addons_view = AddonsView()
        self.addons_view.set_system(self.system.os_name, self.system.arch)
        self.addons_view.status_message.connect(self._show_message)
        self.stack.addWidget(self.addons_view)
        self.stack.addWidget(self._build_settings_view())
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)

        root.addWidget(self._build_footer())
        self._set_view(self.view, animate=False)
        # La vista de instaladas no se rellena sola: hay que poblarla al arrancar
        # (si no, al abrir en esa pestaña se vería vacía hasta el primer refresco).
        self._rebuild_installed()
        self.migrate_view.set_installed(self.installed)
        self.recent_view.set_installed(self.installed)
        self.addons_view.set_installed(self.installed)
        self._install_shortcuts()

    def _install_shortcuts(self) -> None:
        """Atajos del zoom. Ctrl+= es el mismo '+' sin pulsar Shift, y muchos
        teclados no mandan 'Ctrl++' al soltar; registramos los dos."""
        bindings = {
            "Ctrl++": self.zoom_in,
            "Ctrl+=": self.zoom_in,
            "Ctrl+-": self.zoom_out,
            "Ctrl+0": self.reset_zoom,
        }
        for keys, slot in bindings.items():
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.activated.connect(slot)

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("Chrome")
        header.setFixedHeight(72)
        lay = QHBoxLayout(header)
        lay.setContentsMargins(16, 10, 16, 8)
        lay.setSpacing(14)

        logo = QLabel()
        from PySide6.QtGui import QPixmap
        from paths import ASSETS_DIR

        pix = QPixmap(str(ASSETS_DIR / "images" / "app_icon.png"))
        if not pix.isNull():
            logo.setPixmap(pix.scaled(52, 52, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo_shadow(logo, 52)
        logo.setToolTip(tr("Blender Manager"))
        lay.addWidget(logo)

        # Dos líneas: la marca (grande) y la sección actual (un poco más
        # pequeña), para saber siempre dónde estás. La barra de título de la
        # ventana sigue llevando la marca + versión.
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.app_label = QLabel(tr("Blender Manager"))
        self.app_label.setObjectName("HeaderTitle")
        # La misma sombra suave que el logo (y las tarjetas): despega el texto
        # del gris de la cabecera.
        logo_shadow(self.app_label, 19)
        titles.addWidget(self.app_label)
        self.section_label = QLabel("")
        self.section_label.setObjectName("HeaderSection")
        logo_shadow(self.section_label, 17)
        titles.addWidget(self.section_label)
        lay.addLayout(titles)
        lay.addStretch()

        # El buscador va en la cabecera (a la derecha, como en cualquier app);
        # el botón de refrescar vive con los filtros, que es lo que refresca.
        self.header_tools = QWidget()
        self.header_tools.setObjectName("HeaderTools")  # fondo transparente (QSS)
        # Sin esto el bloque se estira y reparte el hueco que sobra. Es el mismo
        # caso que el zoom del pie.
        self.header_tools.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        tools = QHBoxLayout(self.header_tools)
        tools.setContentsMargins(0, 0, 0, 0)
        tools.setSpacing(10)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("SearchField")
        self.search_input.setPlaceholderText(tr("Search..."))
        self.search_input.setToolTip(tr(
            "Filter by version, branch or file name as you type."))
        self.search_input.setFixedWidth(240)
        self.search_input.textChanged.connect(self._on_search_text)
        # Icono de lupa dentro del campo, como en la versión original.
        from ui.fonts import glyph_icon

        self.search_input.addAction(
            glyph_icon(icons.SEARCH, 14, t.MUTED), QLineEdit.LeadingPosition)
        tools.addWidget(self.search_input)
        lay.addWidget(self.header_tools, 0, Qt.AlignRight)
        return header

    def _build_filters(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("Chrome")
        bar.setFixedHeight(FILTERS_HEIGHT)
        lay = QHBoxLayout(bar)
        # Sin margen a la izquierda (las pestañas van pegadas al borde) ni abajo
        # (tocan el fondo de la fila, como pestañas de verdad).
        lay.setContentsMargins(0, 6, 16, 0)
        lay.setSpacing(6)

        # Los canales son excluyentes, así que van en una barra de pestañas: es
        # lo que espera ver quien elige "solo uno de estos". No lleva páginas
        # (Tienda e Instaladas comparten el canal): al cambiar de pestaña se
        # refiltra la lista de debajo.
        self.channel_tabs = QTabBar()
        self.channel_tabs.setObjectName("ChannelTabs")
        self.channel_tabs.setExpanding(False)
        self.channel_tabs.setDrawBase(False)
        self.channel_tabs.setUsesScrollButtons(False)
        self.channel_tabs.setToolTip(tr(
            "Show only one kind of build at a time.\n"
            "\"All\" mixes them; the rest narrow the list down."))
        for index, (key, label) in enumerate(CHANNELS):
            self.channel_tabs.addTab(tr(label))
            self.channel_tabs.setTabToolTip(index, tr(CHANNEL_TOOLTIPS[key]))
        current = next((i for i, (key, _) in enumerate(CHANNELS)
                        if key == self.channel), 0)
        self.channel_tabs.setCurrentIndex(current)
        self.channel_tabs.currentChanged.connect(self._on_channel_tab_changed)
        lay.addWidget(self.channel_tabs, 0, Qt.AlignBottom)
        lay.addStretch()

        # Refrescar va junto a los controles de la lista (y no en la cabecera):
        # refresca **lo que se ve**, la nube o las instaladas, y el tooltip lo
        # dice según la vista (``_update_refresh_tooltip``).
        self.refresh_btn = IconFlatButton(icons.REFRESH)
        self.refresh_btn.setFont(icon_font(16))
        self.refresh_btn.clicked.connect(self.refresh_current)
        lay.addWidget(self.refresh_btn)

        self.layout_group = QButtonGroup(bar)
        self.layout_group.setExclusive(True)
        self.grid_btn = Pill(icons.GRID, tr("Show the builds as a grid of icons."))
        self.grid_btn.setFont(icon_font(14))
        self.list_btn = Pill(icons.LIST, tr("Show the builds as a list of rows."))
        self.list_btn.setFont(icon_font(14))
        for btn, mode in ((self.grid_btn, "grid"), (self.list_btn, "list")):
            self.layout_group.addButton(btn)
            # Misma altura que los tags de canal: la fila queda a ras.
            btn.setFixedHeight(FILTER_CONTROL_HEIGHT)
            btn.clicked.connect(lambda _=False, m=mode: self.set_layout_mode(m))
            lay.addWidget(btn)
        (self.grid_btn if self.layout_mode == "grid" else self.list_btn).setChecked(True)

        self.platform_combo = QComboBox()
        self.platform_combo.setObjectName("FilterCombo")
        self.platform_combo.addItems(list(PLATFORMS.keys()))
        self.platform_combo.setCurrentText(self.platform_label)
        self.platform_combo.setFixedHeight(FILTER_CONTROL_HEIGHT)
        self.platform_combo.setFixedWidth(104)
        self.platform_combo.setToolTip(tr(
            "System the build is for.\n"
            "Change it to download for another computer (for example, to copy "
            "it on a USB stick)."))
        self.platform_combo.currentTextChanged.connect(self.set_platform)
        lay.addWidget(self.platform_combo)

        self.arch_combo = QComboBox()
        self.arch_combo.setObjectName("FilterCombo")
        self.arch_combo.addItems(ARCH_LABELS)
        self.arch_combo.setCurrentText(self.arch_label)
        self.arch_combo.setFixedHeight(FILTER_CONTROL_HEIGHT)
        self.arch_combo.setFixedWidth(82)
        self.arch_combo.setToolTip(tr(
            "Processor type the build is for.\n"
            "x86_64 is the usual one on most PCs; arm64 is for Apple Silicon "
            "and ARM machines."))
        self.arch_combo.currentTextChanged.connect(self.set_arch)
        lay.addWidget(self.arch_combo)
        return bar

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(74)
        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(11, 14, 11, 14)
        lay.setSpacing(10)
        self.side_group = QButtonGroup(sidebar)
        self.side_group.setExclusive(True)
        self.side_buttons = {}
        for key, glyph, tip in (
            ("installed", icons.INSTALLED, tr(
                "Show the versions you already have on this computer.")),
            ("store", icons.STORE, tr(
                "Show the builds you can download from the cloud.")),
            ("recent", icons.CLOCK, tr(
                "Show the .blend files you opened recently, by Blender "
                "version.")),
            ("addons", icons.PUZZLE, tr(
                "Manage the add-ons and extensions of an installed version "
                "without opening Blender.")),
        ):
            # Con padre desde el principio: un widget sin padre al que se le
            # hace ``setVisible(True)`` antes de entrar en el layout se enseña
            # como una **ventana suelta** (se veía un cuadradito en el centro de
            # la pantalla al arrancar, que desaparecía al colocarse el botón).
            btn = SideButton(glyph, tip, parent=sidebar)
            btn.setFont(icon_font(20))
            self.side_group.addButton(btn)
            btn.clicked.connect(lambda _=False, k=key: self.set_view(k))
            lay.addWidget(btn)
            # El gestor de add-ons es nuevo: oculto hasta activar las opciones
            # experimentales (Ajustes > Avanzado), como Migración.
            if key == "addons":
                btn.setVisible(self.settings.experimental_features)
            self.side_buttons[key] = btn
        lay.addStretch()
        # Migración va abajo (encima de Ajustes): es una herramienta puntual, no
        # una pestaña de uso diario como la tienda o las instaladas.
        migrate_btn = SideButton(icons.MIGRATE, tr(
            "Copy add-ons, extensions and preferences from one Blender version "
            "to another."), parent=sidebar)
        migrate_btn.setFont(icon_font(20))
        self.side_group.addButton(migrate_btn)
        migrate_btn.clicked.connect(lambda: self.set_view("migrate"))
        lay.addWidget(migrate_btn)
        self.side_buttons["migrate"] = migrate_btn
        settings_btn = SideButton(icons.SETTINGS, tr("Settings."))
        settings_btn.setFont(icon_font(20))
        self.side_group.addButton(settings_btn)
        settings_btn.clicked.connect(lambda: self.set_view("settings"))
        lay.addWidget(settings_btn)
        self.side_buttons["settings"] = settings_btn
        return sidebar

    def _new_list_view(self):
        """Scroll + QGridLayout (1 columna en lista, N en rejilla)."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(14, 14, 14, 14)
        grid.setSpacing(10)
        grid.setAlignment(Qt.AlignTop)
        scroll.setWidget(content)
        return scroll, grid

    def _build_lists_view(self) -> QWidget:
        """Zona de listas (Local y Nube) con su fila de filtros encima.

        Los filtros solo tienen sentido aquí: en Migración y Ajustes no son
        listas de compilaciones. Al vivir con ellas, esas vistas usan el alto
        completo (antes se reservaba la fila de 44 px y se ocultaba su contenido
        para que la interfaz no diera un salto al cambiar de vista).
        """
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.filters = self._build_filters()
        lay.addWidget(self.filters)
        self.list_stack = QStackedWidget()
        self.list_stack.addWidget(self._build_store_view())
        self.list_stack.addWidget(self._build_installed_view())
        lay.addWidget(self.list_stack, 1)
        return page

    def _build_store_view(self):
        self.store_scroll, self.store_grid = self._new_list_view()
        return self.store_scroll

    def _build_installed_view(self):
        self.installed_scroll, self.installed_grid = self._new_list_view()
        return self.installed_scroll

    def _build_settings_view(self) -> QWidget:
        # Un tema por pestaña: con tantas opciones, las dos columnas ya no
        # cabían a la altura mínima de la ventana. Las tarjetas y el fondo gris
        # son los mismos que en Migración (objectName `SettingsPage`/`SettingsCard`).
        page = QWidget()
        page.setObjectName("SettingsPage")
        # Sin título: las pestañas van pegadas al borde izquierdo y a la misma
        # altura que las de canal (Local y Nube). Como el QTabWidget dibuja su
        # barra arriba del todo, se baja lo que mida de menos para que las dos
        # filas de pestañas terminen a la misma altura.
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        tabs = QTabWidget()
        tabs.setObjectName("SettingsTabs")
        self.settings_tabs = tabs
        tabs.addTab(self._settings_tab(self._settings_downloads_card()),
                    tr("Downloads"))
        # Las carpetas van en su propia pestaña y no dentro de "Descargas":
        # es una lista que crece, y ``_settings_tab`` no lleva scroll, así que
        # no cabría junto a los demás controles con la ventana en su mínimo.
        tabs.addTab(self._settings_tab(self._settings_folders_card()),
                    tr("Folders"))
        tabs.addTab(self._settings_tab(self._settings_interface_card()),
                    tr("Interface"))
        tabs.addTab(self._settings_tab(self._settings_launch_card()),
                    tr("Launch options"))
        tabs.addTab(self._settings_tab(self._settings_system_card()),
                    tr("System"))
        tabs.addTab(self._settings_tab(self._settings_updates_card()),
                    tr("Updates"))
        # Avanzado va al final: son opciones que la mayoría no toca.
        tabs.addTab(self._settings_tab(self._settings_advanced_card()),
                    tr("Advanced"))
        # Las pestañas se alinean por **arriba** con la barra lateral y con los
        # tags de canal (``TABS_TOP``).
        outer.setContentsMargins(0, t.TABS_TOP, 0, 0)
        outer.addWidget(tabs, 1)
        return page

    def _settings_tab(self, card: QFrame) -> QWidget:
        """Página de una pestaña de Ajustes: una sola tarjeta con sus márgenes.

        Cada tema cabe de sobra en su pestaña, así que no lleva scroll (como las
        de Migración); el mínimo de la ventana lo fija la pestaña más alta.
        """
        page = QWidget()
        # El contenido va oscuro (como las listas) y la tira de las pestañas se
        # queda el gris de panel; de ahí que la página tenga su propio objectName.
        page.setObjectName("SettingsTabPage")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(16)
        lay.addWidget(card)
        lay.addStretch()
        return page

    def _settings_downloads_card(self) -> QFrame:
        card, lay = settings_card("Downloads", spacing=10)

        # Resumen de a dónde va lo que se descargue ahora mismo. La lista de
        # carpetas vive en su pestaña; aquí solo se dice el resultado, que es
        # lo que interesa desde "Descargas".
        self.dest_summary = ElidedLabel("", Qt.ElideMiddle)
        self.dest_summary.setObjectName("Muted")
        lay.addWidget(self.dest_summary)

        row = QHBoxLayout()
        row.addStretch()
        folders_btn = CardButton(tr("Folders"), tooltip=tr(
            "Choose which folders your Blender versions live in, and which "
            "ones receive each kind of build."))
        folders_btn.clicked.connect(
            lambda: self.settings_tabs.setCurrentIndex(self.FOLDERS_TAB))
        row.addWidget(folders_btn)
        lay.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel(tr("Delete archive after extraction")))
        row2.addStretch()
        self.archive_switch = SwitchPill(
            self.delete_archive,
            tooltip=tr("Delete the downloaded .zip/.tar.xz after extracting it.\n"
                       "Saves disk space; you can download it again if you need it."))
        self.archive_switch.toggled.connect(self._on_archive_toggled)
        row2.addWidget(self.archive_switch)
        lay.addLayout(row2)
        self._refresh_dest_summary()
        return card

    # ------------------------------------------------- biblioteca de carpetas
    def _settings_folders_card(self) -> QFrame:
        """Tarjeta con la biblioteca de carpetas.

        Tiene dos caras y **no hay un interruptor que las cambie**: con una
        sola carpeta que se queda con todo se ve el campo de siempre (la app no
        estrena concepto a quien no lo ha pedido), y en cuanto hay dos aparece
        la lista. Es un estado real —cuántas carpetas hay— y no una preferencia
        guardada que pudiera desincronizarse de las carpetas de verdad.
        """
        card, lay = settings_card("Folders", spacing=10)

        self.folders_hint = ElidedLabel("", Qt.ElideRight)
        self.folders_hint.setObjectName("Muted")
        lay.addWidget(self.folders_hint)

        # Aviso de tipos sin carpeta. Es la contrapartida de no tener cadena de
        # reservas: si nadie recibe las diarias hay que decirlo AQUÍ, y no
        # cuando el usuario le dé a descargar una.
        self.folders_warning = ElidedLabel("", Qt.ElideRight)
        self.folders_warning.setObjectName("Warning")
        lay.addWidget(self.folders_warning)

        # --- modo simple: una carpeta, como siempre
        self.simple_box = QWidget()
        self.simple_box.setObjectName("FormRow")
        simple = QVBoxLayout(self.simple_box)
        simple.setContentsMargins(0, 0, 0, 0)
        simple.setSpacing(8)
        row = QHBoxLayout()
        self.dest_input = QLineEdit()
        self.dest_input.setToolTip(tr(
            "Folder where the Blender versions you download are stored.\n"
            "Each version goes in its own subfolder."))
        self.dest_input.editingFinished.connect(self._on_simple_folder_changed)
        row.addWidget(self.dest_input, 1)
        browse = CardButton(tr("Browse..."), tooltip=tr("Choose destination folder"))
        browse.clicked.connect(self.browse_dest)
        row.addWidget(browse)
        simple.addLayout(row)
        split_row = QHBoxLayout()
        split_row.addStretch()
        self.split_btn = CardButton(tr("Separate by channel..."), variant="accent",
                                    tooltip=tr(
            "Add a second folder and choose what goes in each one: for example "
            "the LTS versions on a fast drive and the rest on a big one."))
        self.split_btn.clicked.connect(self.add_folder)
        split_row.addWidget(self.split_btn)
        simple.addLayout(split_row)
        lay.addWidget(self.simple_box)

        # --- modo ramificado: la lista de carpetas
        self.folder_list, self.folder_body = list_scroll(
            "FolderList", "FolderListBody", spacing=6, align_top=False)
        self.folder_list.setMaximumHeight(
            MAX_VISIBLE_ROWS * FolderRow.HEIGHT + (MAX_VISIBLE_ROWS - 1) * 6)
        self.folder_body.addStretch()
        lay.addWidget(self.folder_list)

        add_row = QHBoxLayout()
        add_row.addStretch()
        # Vive FUERA del scroll a propósito: con muchas carpetas seguiría a mano
        # en vez de haber que bajar hasta el final para encontrarlo.
        self.add_folder_btn = CardButton(tr("Add folder"), variant="accent",
                                         tooltip=tr(
            "Add a folder where you already have Blender versions, or where "
            "you want to download them."))
        self.add_folder_btn.clicked.connect(self.add_folder)
        add_row.addWidget(self.add_folder_btn)
        lay.addLayout(add_row)

        self._rebuild_folder_rows()
        return card

    def _branched(self) -> bool:
        """True si hay que enseñar la lista en vez del campo de siempre."""
        folders = self.settings.folders
        if len(folders) != 1:
            return True
        return sorted(folders[0].types) != sorted(channels.BUILD_TYPES)

    def _rebuild_folder_rows(self) -> None:
        """Repinta la tarjeta entera (altas, bajas y cambio de modo)."""
        branched = self._branched()
        self.simple_box.setVisible(not branched)
        self.folder_list.setVisible(branched)
        self.add_folder_btn.setVisible(branched)
        self.folders_hint.setText(tr(
            "Each download goes to the folder that takes it. "
            "Locked folders are only scanned.") if branched
            else tr("Blender versions you download are stored here, each one "
                    "in its own subfolder."))

        if not branched:
            self.dest_input.blockSignals(True)
            self.dest_input.setText(self.settings.folders[0].path)
            self.dest_input.blockSignals(False)

        clear_layout(self.folder_body, keep_stretch=True)
        self.folder_rows = {}
        for index, folder in enumerate(self.settings.folders):
            row = FolderRow(folder, zebra=bool(index % 2),
                            missing=not self._folder_exists(folder.path))
            row.type_toggled.connect(self._on_folder_type_toggled)
            row.writable_toggled.connect(self._on_folder_writable_toggled)
            row.remove_requested.connect(self._on_folder_remove_requested)
            self.folder_body.insertWidget(self.folder_body.count() - 1, row)
            self.folder_rows[channels.normalize_path(folder.path)] = row
        self._refresh_folder_warning()
        self._refresh_dest_summary()

    @staticmethod
    def _folder_exists(path: str) -> bool:
        """``is_dir`` tolerante: una unidad desconectada no es un error."""
        try:
            return Path(path).expanduser().is_dir()
        except OSError:
            return False

    def _refresh_folder_warning(self) -> None:
        orphans = channels.orphan_types(self.settings.folders)
        if not orphans:
            self.folders_warning.setText("")
            self.folders_warning.setVisible(False)
            return
        names = ", ".join(tr(TYPE_LABELS[key]) for key in orphans)
        self.folders_warning.setText(
            tr("No folder for: {types}. Those builds cannot be downloaded "
               "until you tick one.", types=names))
        self.folders_warning.setVisible(True)

    def _refresh_dest_summary(self) -> None:
        if not hasattr(self, "dest_summary"):
            return
        folder = channels.owner_of(self.settings.folders, channels.TYPE_STABLE)
        folder = folder or next((f for f in self.settings.folders if f.types), None)
        self.dest_summary.setText(
            tr("New downloads go to: {folder}", folder=folder.path) if folder
            else tr("No folder is set to receive downloads."))

    def _show_folders_hint(self) -> None:
        """Presenta la biblioteca de carpetas a quien actualiza la app.

        Lo primero que dice es lo que más tranquiliza: que no hay que tocar
        nada y que no se ha movido ningún archivo. Lo segundo, para qué sirve.
        """
        self.settings.folders_hint_shown = True
        self.settings.save()
        folder = self.settings.folders[0].path if self.settings.folders else ""
        dialog = AppDialog(
            self, tr("Your Blender folders"),
            tr("Nothing has changed on disk and you do not have to set up "
               "anything: your versions are still in {folder} and keep working "
               "exactly as before.", folder=folder)
            + "\n\n"
            + tr("What is new is that you can now add more folders and choose "
                 "what goes in each one: for example the LTS versions on a "
                 "fast SSD and the daily builds on a big drive. You can also "
                 "point the app at folders where you already had Blender, and "
                 "lock them so nothing is ever written there."))
        choice = {"open": False}
        dialog.add_button(tr("Not now"), on_click=dialog.reject)
        dialog.add_button(
            tr("Show me"), variant="accent",
            on_click=lambda: (choice.update(open=True), dialog.accept()),
            tooltip=tr("Opens Settings > Folders, where you add folders and\n"
                       "tick what each one receives."))
        dialog.exec()
        if choice["open"]:
            self.set_view("settings")
            self.settings_tabs.setCurrentIndex(self.FOLDERS_TAB)

    # ------------------------------------------------------- reorganizar
    def _offer_reorg(self, root: str) -> None:
        """Si algo dejó de encajar en esa carpeta, ofrece moverlo.

        Se llama **después** de guardar el cambio: lo que se decide aquí es
        solo qué hacer con lo que ya estaba dentro, no si el cambio se aplica.
        Quedarse quieto es una respuesta válida y es la que se ofrece primero.
        """
        moves = organizer.misplaced(self.installed, self.settings.folders, root)
        if not moves:
            return
        counts = {}
        for move in moves:
            counts[move.build_type] = counts.get(move.build_type, 0) + 1
        detail = "\n".join(
            f"    · {tr(TYPE_LABELS[key])}: {value}"
            for key, value in counts.items())
        message = (root + "\n\n"
                   + tr("There are {count} versions here that this folder no "
                        "longer takes:", count=len(moves))
                   + "\n" + detail + "\n\n"
                   + tr("You can move them to the folder that takes them, or "
                        "leave them where they are."))
        dialog = AppDialog(self, tr("Folder contents"), message)
        choice = {"move": False}
        dialog.add_button(tr("Leave them here"), on_click=dialog.reject,
                          tooltip=tr(
            "Nothing is moved.\n"
            "Those versions stay in this folder and keep showing up in Local.\n"
            "Only new downloads follow the boxes you just ticked."))
        dialog.add_button(
            tr("Move them"), variant="accent",
            on_click=lambda: (choice.update(move=True), dialog.accept()),
            tooltip=tr(
                "Each version is moved to the folder that takes its kind of "
                "build.\n"
                "Nothing is deleted: a version is only removed from here once "
                "the copy is complete.\n"
                "With big folders on another drive this takes a while."))
        dialog.exec()
        if choice["move"]:
            self._start_move(moves)

    def _start_move(self, moves) -> None:
        """Mueve las versiones en un hilo, con barra de progreso.

        El diálogo es **modal** a propósito: mover carpetas por debajo de la
        lista de instaladas mientras se usa es pedir que el usuario lance algo
        que ya no está donde dice la tarjeta.
        """
        self._move_cancel = threading.Event()
        self._move_dialog = ProgressDialog(
            self, tr("Moving versions"), "",
            primary_text="", secondary_text=tr("Cancel"))
        self._move_dialog.set_text(
            tr("Moving {name} ({done} of {total})",
               name=moves[0].entry.name, done=1, total=len(moves)))

        def worker():
            moved = failed = 0
            last = ""
            for index, move in enumerate(moves):
                if self._move_cancel.is_set():
                    break
                self.folder_move_progress.emit(index, len(moves),
                                               move.entry.name)
                try:
                    organizer.move_build(
                        move, should_cancel=self._move_cancel.is_set)
                    moved += 1
                except organizer.OrganizerError as error:
                    if error.code == "cancelled":
                        break
                    # Que una build esté abierta no puede abortar las otras.
                    download_log(f"move failed ({move.entry.name}): {error}")
                    failed += 1
                    last = str(error)
            self.folder_move_done.emit(moved, failed, last)

        threading.Thread(target=worker, daemon=True).start()
        self._move_dialog.exec()

    def _on_folder_move_progress(self, done: int, total: int, name: str) -> None:
        if self._move_dialog is None:
            return
        self._move_dialog.set_progress(int(done * 100 / total) if total else 0)
        self._move_dialog.set_text(tr("Moving {name} ({done} of {total})",
                                      name=name, done=done + 1, total=total))

    def _on_folder_move_done(self, moved: int, failed: int, error: str) -> None:
        if self._move_dialog is not None:
            self._move_dialog.accept()
            self._move_dialog = None
        self.refresh_installed()
        if failed:
            show_error(self, tr("Moving versions"),
                       tr("{failed} versions could not be moved.", failed=failed)
                       + ("\n\n" + error if error else ""))
        elif moved:
            self._show_message(tr("{moved} versions moved", moved=moved), 6)

    def _save_folders(self) -> None:
        """Guarda y refresca todo lo que depende de las carpetas."""
        self.settings.save()
        self.refresh_installed()
        self._rebuild_store()
        self._refresh_folder_warning()
        self._refresh_dest_summary()

    def _settings_interface_card(self) -> QFrame:
        card, lay = settings_card("Interface", spacing=10)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel(tr("Language")))
        row3.addStretch()
        self.language_combo = QComboBox()
        self.language_combo.addItems([tr(v) for v in LANGUAGE_IDS.values()])
        self.language_combo.setCurrentText(self.language_label)
        self.language_combo.setToolTip(tr(
            "Language of the interface.\nIt changes when you restart the app."))
        self.language_combo.currentTextChanged.connect(self._on_language_changed)
        row3.addWidget(self.language_combo)
        lay.addLayout(row3)

        # Destino del "restablecer" (Ctrl+0 / Ctrl+clic en el slider del pie).
        # Es una preferencia, no el zoom actual: moverlo aquí NO cambia la
        # rejilla; solo decide a qué tamaño vuelve el reset. Por eso el slider
        # del pie sigue persistiendo lo que el usuario dejara la última sesión.
        row4 = QHBoxLayout()
        row4.addWidget(QLabel(tr("Reset zoom")))
        row4.addStretch()
        self.reset_zoom_slider = _ZoomSlider(Qt.Horizontal)
        self.reset_zoom_slider.setRange(int(MIN_ZOOM * 100), int(MAX_ZOOM * 100))
        self.reset_zoom_slider.setValue(round(self.settings.reset_zoom * 100))
        self.reset_zoom_slider.setFixedWidth(130)
        self.reset_zoom_slider.setToolTip(
            tr("Zoom the grid returns to (Ctrl+0 or Ctrl+click on the slider)"))
        self.reset_zoom_slider.valueChanged.connect(self._on_reset_zoom_changed)
        self.reset_zoom_slider.sliderReleased.connect(self._save_reset_zoom)
        self.reset_zoom_slider.reset_requested.connect(self._factory_reset_zoom)
        row4.addWidget(self.reset_zoom_slider)
        self.reset_zoom_label = QLabel(f"{round(self.settings.reset_zoom * 100)} %")
        self.reset_zoom_label.setObjectName("Muted")
        self.reset_zoom_label.setToolTip(
            tr("Size the grid returns to when you reset the zoom."))
        self.reset_zoom_label.setFixedWidth(40)
        self.reset_zoom_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row4.addWidget(self.reset_zoom_label)
        lay.addLayout(row4)

        # Tamaño de la ventana: vuelve al de fábrica y se centra. Útil si una
        # sesión la dejó enorme o en una esquina.
        row5 = QHBoxLayout()
        row5.addWidget(QLabel(tr("Window size")))
        row5.addStretch()
        reset_window = CardButton(
            tr("Reset"), tooltip=tr("Return the window to its default size and "
                                    "center it on the screen."))
        reset_window.clicked.connect(self.reset_window_size)
        row5.addWidget(reset_window)
        lay.addLayout(row5)
        return card

    def _settings_system_card(self) -> QFrame:
        card, lay = settings_card("System", spacing=10)

        # Bandeja del sistema: dos decisiones independientes (cerrar y
        # minimizar). Si el escritorio no la soporta se deshabilitan, porque
        # activarlas escondería la ventana sin un icono al que volver.
        tray_available = TrayIcon.available()
        tray_unavailable = tr("The system tray is not available on this desktop.")
        row_tray_close = QHBoxLayout()
        row_tray_close.addWidget(QLabel(tr("Close to the system tray")))
        row_tray_close.addStretch()
        self.close_tray_switch = SwitchPill(self.close_to_tray, tooltip=tr(
            "Keep BlenderManager running in the system tray when you close the "
            "window.\nClick the tray icon to open it again."))
        self.close_tray_switch.toggled.connect(self._on_close_to_tray_toggled)
        row_tray_close.addWidget(self.close_tray_switch)
        lay.addLayout(row_tray_close)

        minimize_tip = tr("Hide the window in the system tray when you minimize "
                          "it.\nClick the tray icon to bring it back.")
        if detector.session_is_wayland():
            # En Wayland el minimizado lo gestiona el compositor y no se puede
            # detectar salvo en modo X11 (XWayland). Avisamos antes de activarlo.
            minimize_tip = minimize_tip + "\n\n" + tr(
                "On Wayland this needs X11 compatibility mode (XWayland); "
                "restart the app to apply it.")
        row_tray_min = QHBoxLayout()
        row_tray_min.addWidget(QLabel(tr("Minimize to the system tray")))
        row_tray_min.addStretch()
        self.minimize_tray_switch = SwitchPill(self.minimize_to_tray,
                                               tooltip=minimize_tip)
        self.minimize_tray_switch.toggled.connect(
            self._on_minimize_to_tray_toggled)
        row_tray_min.addWidget(self.minimize_tray_switch)
        lay.addLayout(row_tray_min)
        if not tray_available:
            for switch in (self.close_tray_switch, self.minimize_tray_switch):
                switch.setEnabled(False)
                switch.setToolTip(tray_unavailable)
        elif not detector.minimize_to_tray_supported():
            # Wayland sin XWayland: no hay forma de enterarse de que se ha
            # minimizado, así que la opción ni se ofrece.
            self.minimize_tray_switch.setEnabled(False)
            self.minimize_tray_switch.setToolTip(tr(
                "Minimizing to the tray is not available on this desktop."))

        # Autoarranque con la sesión y arranque oculto. OJO: el autoarranque no
        # es un ajuste nuestro, vive en el sistema (XDG autostart, registro de
        # Windows, LaunchAgent), así que su estado se lee del sistema y no del
        # settings.json; lo que sí guardamos es si debe empezar en la bandeja.
        self.autostart_switch = SwitchPill(autostart.is_enabled(), tooltip=tr(
            "Open BlenderManager automatically when you sign in to your "
            "computer."))
        self.autostart_switch.toggled.connect(self._on_autostart_toggled)
        row_autostart = QHBoxLayout()
        row_autostart.addWidget(QLabel(tr("Start automatically at login")))
        row_autostart.addStretch()
        row_autostart.addWidget(self.autostart_switch)
        lay.addLayout(row_autostart)

        self.start_minimized_switch = SwitchPill(
            self.start_minimized,
            tooltip=tr("Start hidden in the system tray.\nRecommended if it "
                       "opens automatically at login."))
        self.start_minimized_switch.toggled.connect(
            self._on_start_minimized_toggled)
        row_start_min = QHBoxLayout()
        row_start_min.addWidget(QLabel(tr("Start minimized in the system tray")))
        row_start_min.addStretch()
        row_start_min.addWidget(self.start_minimized_switch)
        lay.addLayout(row_start_min)
        if not autostart.supported():
            self.autostart_switch.setEnabled(False)
            self.autostart_switch.setToolTip(
                tr("Automatic startup is not available on this system."))
        if not tray_available:
            # Sin bandeja no hay dónde arrancar oculta: se enseñaría la ventana
            # igual, así que no se ofrece un ajuste que no haría nada.
            self.start_minimized_switch.setEnabled(False)
            self.start_minimized_switch.setToolTip(tray_unavailable)
        return card

    def _settings_launch_card(self) -> QFrame:
        card, lay = settings_card("Launch options", spacing=10)

        # Lanzar con consola: se puede alternar también desde cada tarjeta
        # instalada; aquí queda el ajuste (el mismo) para dejarlo fijo. Es una
        # opción nueva, así que va tras las experimentales.
        self.console_row = QWidget()
        console_lay = QHBoxLayout(self.console_row)
        console_lay.setContentsMargins(0, 0, 0, 0)
        console_lay.addWidget(QLabel(tr("Launch with console")))
        console_lay.addStretch()
        self.console_switch = SwitchPill(
            self.settings.launch_console,
            tooltip=tr("Launch with the console visible: Python output and "
                       "script errors."))
        self.console_switch.toggled.connect(self._on_console_default_toggled)
        console_lay.addWidget(self.console_switch)
        # Primero al layout y luego la visibilidad (ver ``_build_sidebar``).
        lay.addWidget(self.console_row)
        self.console_row.setVisible(self.settings.experimental_features)

        lay.addWidget(QLabel(tr("Launch arguments")))
        self.args_input = QLineEdit(self.launch_args)
        self.args_input.setPlaceholderText("--background --python script.py")
        self.args_input.setToolTip(tr(
            "Extra arguments Blender receives when you launch it.\n"
            "Example: --background to start without the interface."))
        self.args_input.textChanged.connect(self._on_args_changed)
        lay.addWidget(self.args_input)
        return card

    def _settings_updates_card(self) -> QFrame:
        card, lay = settings_card("Updates", spacing=10)

        # Dos ajustes independientes: comprobar al arrancar, y comprobar cada X
        # rato. Apagar el primero NO apaga el segundo.
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Check for updates on startup")))
        row.addStretch()
        self.update_switch = SwitchPill(
            self.auto_update, tooltip=tr(
                "Check for new BlenderManager versions when the app starts.\n"
                "It only downloads one when you accept; checking is cheap."))
        self.update_switch.toggled.connect(self.set_auto_update)
        row.addWidget(self.update_switch)
        lay.addLayout(row)

        # Cada cuánto se comprueba sola (el "y luego se me olvida abrirlo").
        row_periodic = QHBoxLayout()
        row_periodic.addWidget(QLabel(tr("Check for updates periodically")))
        row_periodic.addStretch()
        self.periodic_switch = SwitchPill(self.periodic_update, tooltip=tr(
            "Look for new versions of BlenderManager every so often,\n"
            "even if the startup check is off."))
        self.periodic_switch.toggled.connect(self.set_periodic_update)
        row_periodic.addWidget(self.periodic_switch)
        lay.addLayout(row_periodic)

        row_interval = QHBoxLayout()
        row_interval.addWidget(QLabel(tr("Check for updates every")))
        row_interval.addStretch()
        self.update_interval_combo = QComboBox()
        for minutes in settings_service.UPDATE_INTERVALS:
            self.update_interval_combo.addItem(self._interval_text(minutes), minutes)
        index = self.update_interval_combo.findData(
            self.settings.update_interval_min)
        self.update_interval_combo.setCurrentIndex(index if index >= 0 else 0)
        self.update_interval_combo.setToolTip(tr(
            "How often BlenderManager looks for its own updates.\n"
            "It only downloads one when you accept; checking is cheap."))
        self.update_interval_combo.setEnabled(self.periodic_update)
        self.update_interval_combo.currentIndexChanged.connect(
            self._on_update_interval_changed)
        row_interval.addWidget(self.update_interval_combo)
        lay.addLayout(row_interval)

        row2 = QHBoxLayout()
        version_label = QLabel(tr("Version {version}", version=self.current_version))
        version_label.setToolTip(
            tr("Version of BlenderManager you are using right now."))
        row2.addWidget(version_label)
        row2.addStretch()
        check = CardButton(tr("Check now"), tooltip=tr("Check for updates now"))
        check.clicked.connect(lambda: self.check_updates(manual=True))
        row2.addWidget(check)
        lay.addLayout(row2)

        # Series de Blender silenciadas con "Nunca" en su aviso de actualización:
        # la fila solo se ve si hay alguna, para poder reactivarlas.
        self.muted_series_row = QWidget()
        muted_lay = QHBoxLayout(self.muted_series_row)
        muted_lay.setContentsMargins(0, 0, 0, 0)
        muted_lay.setSpacing(8)
        self.muted_series_label = QLabel("")
        self.muted_series_label.setObjectName("Muted")
        muted_lay.addWidget(self.muted_series_label)
        muted_lay.addStretch()
        reset_series = CardButton(tr("Reactivate"),
                                  tooltip=tr("Blender series you silenced with Never"))
        reset_series.clicked.connect(self.reset_blender_series)
        muted_lay.addWidget(reset_series)
        lay.addWidget(self.muted_series_row)
        self._update_blender_series_controls()
        return card

    def _update_blender_series_controls(self) -> None:
        """Enseña (u oculta) la fila de series de Blender silenciadas."""
        if not hasattr(self, "muted_series_row"):
            return
        series = self.settings.ignored_blender_series
        self.muted_series_row.setVisible(bool(series))
        if series:
            self.muted_series_label.setText(
                tr("Silenced: {series}", series=", ".join(series)))

    def _settings_advanced_card(self) -> QFrame:
        """Opciones avanzadas/experimentales (hoy solo la vista de Migración)."""
        card, lay = settings_card("Advanced", spacing=10)

        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Experimental options")))
        row.addStretch()
        self.experimental_switch = SwitchPill(
            self.settings.experimental_features,
            tooltip=tr("Show the experimental features: the Migration, Recent "
                       "files and Add-ons views, and launching Blender with "
                       "its console. They are still in development and may "
                       "change."))
        self.experimental_switch.toggled.connect(self._on_experimental_toggled)
        row.addWidget(self.experimental_switch)
        lay.addLayout(row)

        # El aviso va debajo, en apagado: el interruptor por sí solo no dice
        # que lo que se activa está a medias.
        hint = QLabel(tr(
            "Show the experimental features: the Migration, Recent files and "
            "Add-ons views, and launching Blender with its console. They are "
            "still in development and may change."))
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        return card

    def _on_experimental_toggled(self, value: bool) -> None:
        """Enseña u oculta las vistas nuevas, y sale de ellas si se apaga."""
        self.settings.experimental_features = value
        self.settings.save()
        for key in EXPERIMENTAL_VIEWS:
            self.side_buttons[key].setVisible(value)
        if hasattr(self, "console_row"):
            self.console_row.setVisible(value)
        # El botón de consola de las tarjetas depende de lo mismo.
        self._rebuild_installed()
        if not value and self.view in EXPERIMENTAL_VIEWS:
            self.set_view("installed" if self.installed else "store")

    def _build_footer(self) -> QFrame:
        footer = QFrame()
        footer.setObjectName("Chrome")
        footer.setFixedHeight(40)
        lay = QHBoxLayout(footer)
        lay.setContentsMargins(16, 4, 16, 4)
        lay.setSpacing(12)
        self.status_label = QLabel(tr("Ready"))
        self.status_label.setObjectName("Muted")
        lay.addWidget(self.status_label)

        # Progreso + porcentaje + cancelar van en su PROPIO contenedor con
        # stretch, y no sueltos en el pie: un widget OCULTO no aporta su stretch
        # al layout, así que si el progreso iba suelto, al ocultarse el zoom se
        # quedaba a la izquierda y el pie se descolocaba. Con el contenedor
        # (siempre visible) el zoom queda pegado a la derecha en los dos casos.
        self.progress_box = QWidget()
        self.progress_box.setObjectName("HeaderTools")  # fondo transparente
        progress_lay = QHBoxLayout(self.progress_box)
        progress_lay.setContentsMargins(0, 0, 0, 0)
        progress_lay.setSpacing(12)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setFixedHeight(12)
        self.progress.setValue(0)
        self.progress.setToolTip(tr("Download progress."))
        # Solo se muestra mientras hay una descarga en curso.
        self.progress.setVisible(False)
        progress_lay.addWidget(self.progress, 1)
        self.percent = QLabel("")
        self.percent.setToolTip(tr("Download progress."))
        self.percent.setVisible(False)
        progress_lay.addWidget(self.percent)
        self.cancel_btn = CardButton(tr("Cancel"),
                                     tooltip=tr("Stop the download running now."))
        self.cancel_btn.clicked.connect(self.cancel_download)
        self.cancel_btn.setVisible(False)
        progress_lay.addWidget(self.cancel_btn)
        lay.addWidget(self.progress_box, 1)

        # Zoom: slider + porcentaje, juntos y pegados al borde derecho.
        self.zoom_box = QWidget()
        self.zoom_box.setObjectName("HeaderTools")  # fondo transparente (QSS)
        self.zoom_box.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        zoom_lay = QHBoxLayout(self.zoom_box)
        zoom_lay.setContentsMargins(0, 0, 0, 0)
        zoom_lay.setSpacing(6)
        self.zoom_slider = _ZoomSlider(Qt.Horizontal)
        self.zoom_slider.setRange(int(MIN_ZOOM * 100), int(MAX_ZOOM * 100))
        self.zoom_slider.setValue(int(self.zoom * 100))
        self.zoom_slider.setFixedWidth(130)
        self.zoom_slider.valueChanged.connect(lambda v: self.set_zoom(v / 100.0))
        self.zoom_slider.reset_requested.connect(self.reset_zoom)
        self.zoom_slider.setToolTip(tr(
            "Size of the cards in the grid.\n"
            "Ctrl + and Ctrl - change it, Ctrl+0 resets it."))
        zoom_lay.addWidget(self.zoom_slider)
        self.zoom_label = QLabel()
        self.zoom_label.setObjectName("Muted")
        self.zoom_label.setToolTip(tr("Current zoom."))
        # Ancho fijo para que el pie no "baile" al pasar de 100 % a 180 %.
        self.zoom_label.setFixedWidth(40)
        self.zoom_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._update_zoom_label()
        zoom_lay.addWidget(self.zoom_label)
        lay.addWidget(self.zoom_box, 0, Qt.AlignRight)
        return footer

    def _update_zoom_label(self) -> None:
        self.zoom_label.setText(f"{round(self.zoom * 100)} %")

    # -------------------------------------------------------------- estado
    def _set_status(self, text: str, timeout: int = 0) -> None:
        self.status_label.setText(text)
        if timeout:
            self._status_timer.start(timeout * 1000)
        else:
            self._status_timer.stop()

    def _show_message(self, message: str, timeout: int = 4) -> None:
        self._set_status(message, timeout)

    def _set_downloading(self, active: bool) -> None:
        self.progress.setVisible(active)
        self.percent.setVisible(active)
        self.cancel_btn.setVisible(active)

    @property
    def platform(self) -> str:
        """Plataforma de destino elegida en la barra de filtros."""
        return PLATFORMS.get(self.platform_label, "linux")

    @property
    def arch(self) -> str:
        """Arquitectura de destino, tal y como la comparan las compilaciones.

        La barra ofrece ``x86_64``/``arm64`` y ``api.normalize_arch`` guarda las
        compilaciones con esos mismos nombres (Blender llama ``amd64`` a la de
        Windows), así que aquí se devuelve la etiqueta tal cual. Antes se
        traducía a ``amd64`` para Windows y la tienda salía **vacía**: las
        builds ya venían normalizadas a ``x86_64`` y no coincidían con el filtro.
        """
        return self.arch_label

    # ------------------------------------------------------------- filtros
    def set_channel(self, channel: str) -> None:
        """Cambia de canal: Todas, LTS, Estable, Diarias,
        Experimentales o Favoritos.
        """
        self.channel = channel
        # Se recuerda para la próxima vez que se abra la aplicación.
        self.settings.channel = channel
        self.settings.save()
        # Sincroniza la pestaña: el cambio puede venir de ella misma o de otro
        # sitio (por ejemplo, al restaurar el canal guardado).
        index = next((i for i, (key, _) in enumerate(CHANNELS)
                      if key == channel), 0)
        if self.channel_tabs.currentIndex() != index:
            self.channel_tabs.blockSignals(True)
            self.channel_tabs.setCurrentIndex(index)
            self.channel_tabs.blockSignals(False)
        self._rebuild_store()
        self._rebuild_installed()

    def _on_channel_tab_changed(self, index: int) -> None:
        if 0 <= index < len(CHANNELS):
            self.set_channel(CHANNELS[index][0])

    def _on_search_text(self, text: str) -> None:
        self._pending_search = text
        self._search_timer.start(250)

    def _apply_search(self) -> None:
        self.search = self._pending_search.strip().lower()
        self._rebuild_store()
        self._rebuild_installed()

    def set_view(self, view: str) -> None:
        """Cambia entre la tienda, las instaladas y los ajustes.

        El botón de ajustes funciona como un interruptor (igual que en la
        versión Kivy): la primera vez entra y la segunda vuelve a la vista en la
        que estabas. Entre tienda e instaladas no hay interruptor, el clic
        cambia de pestaña y ya.
        """
        if (view in EXPERIMENTAL_VIEWS
                and not self.settings.experimental_features):
            # Esas vistas están ocultas (opciones experimentales apagadas): su
            # botón no se ve, pero cualquier llamada debe quedar sin efecto.
            view = "installed" if self.installed else "store"
        if view == "settings" and self.view == "settings":
            # Segundo clic en ajustes: volvemos a donde estábamos.
            view = self._previous_view
        elif view != "settings":
            # Recordamos la última vista que no eran ajustes.
            self._previous_view = view
        self.view = view
        self._set_view(view)
        if view == "installed":
            self.refresh_installed()
        elif view == "store":
            # El zoom en vivo solo reconstruye la vista visible, así que la
            # tienda puede haberse quedado con el tamaño viejo.
            self._rebuild_store()
        elif view == "migrate":
            # Las instaladas pueden haber cambiado desde la última vez.
            self.migrate_view.set_installed(self.installed)
        elif view == "recent":
            # Los recientes se leen al entrar: Blender puede haber abierto
            # ficheros desde la última vez.
            self.recent_view.set_installed(self.installed)
        elif view == "addons":
            # Los addons se leen al entrar (arranca Blender): no tiene sentido
            # hacerlo al abrir la app si el usuario no va a mirarlos.
            self.addons_view.set_installed(self.installed)
            self.addons_view.read()

    def _set_view(self, view: str, animate: bool = True) -> None:
        # Tienda e Instaladas comparten la zona de listas (con sus filtros); lo
        # que cambia entre ellas es la página del sub-stack.
        if view in ("store", "installed"):
            self.stack.setCurrentIndex(0)
            self.list_stack.setCurrentIndex(0 if view == "store" else 1)
            show_tools = True
        else:
            self.stack.setCurrentIndex(
                {"migrate": 1, "recent": 2, "addons": 3,
                 "settings": 4}.get(view, 0))
            show_tools = False
        for key, btn in self.side_buttons.items():
            btn.setChecked(key == view)
        if hasattr(self, "section_label"):
            self.section_label.setText(tr(SECTION_TITLES.get(view, "")))
        # El buscador y el zoom del pie solo aplican a las listas; en Migración,
        # Recientes y Ajustes se ocultan (no arrastran salto: van en la cabecera
        # y el pie).
        self.header_tools.setVisible(show_tools)
        self.zoom_box.setVisible(show_tools and self.layout_mode == "grid")
        self._update_refresh_tooltip()

    def _update_refresh_tooltip(self) -> None:
        """El botón de refrescar explica qué va a refrescar en esta vista."""
        if self.view == "installed":
            text = tr("Look for the installed Blender versions again.\n"
                      "Use it if you added or removed one outside this app.")
        else:
            text = tr("Read the Blender versions available to download again.\n"
                      "Use it if something looks out of date.")
        self.refresh_btn.setToolTip(text)

    def refresh_current(self) -> None:
        """Refresca la lista que está a la vista: instaladas o nube."""
        if self.view == "installed":
            self.refresh_installed()
        else:
            self.refresh(force=True)

    def set_layout_mode(self, mode: str) -> None:
        """Cambia entre rejilla y lista y recuerda la elección."""
        self.layout_mode = mode
        self.zoom_box.setVisible(
            self.view not in ("settings", "migrate", "recent", "addons")
            and mode == "grid")
        (self.grid_btn if mode == "grid" else self.list_btn).setChecked(True)
        self.settings.layout_mode = mode
        self.settings.save()
        self._rebuild_store()
        self._rebuild_installed()

    def set_zoom(self, value: float) -> None:
        """Fija el tamaño de la rejilla: la etiqueta va al instante y
        la rejilla se reconstruye cuando el slider se para.
        """
        self.zoom = min(MAX_ZOOM, max(MIN_ZOOM, float(value)))
        self._update_zoom_label()
        # En vivo, pero con tope: si no, se reconstruye en cada pixel de
        # arrastre (parpadeo) y el JSON se escribe decenas de veces por segundo.
        if not self._zoom_tick.isActive():
            self._zoom_tick.start()
        self._zoom_settle.start()

    def _rebuild_zoom_views(self) -> None:
        """Refresco en vivo del zoom: solo la vista que se está viendo.

        Reconstruir la otra pestaña (que no se ve) no aporta nada y, con muchas
        tarjetas, suma a que la interfaz se quede sin responder un momento —en
        Windows eso termina sacando la ventana fantasma de "no responde" encima
        de la app. Al soltar el slider se reconstruyen las dos (``_commit_zoom``).
        """
        if self.view == "installed":
            self._rebuild_installed()
        elif self.view == "store":
            self._rebuild_store()

    def _commit_zoom(self) -> None:
        """El slider lleva quieto: paramos y guardamos el ajuste una sola vez."""
        self._zoom_tick.stop()
        self._rebuild_store()
        self._rebuild_installed()
        self.settings.zoom = self.zoom
        self.settings.save()

    def _zoom_enabled(self) -> bool:
        """El zoom solo pinta algo en rejilla y fuera de ajustes/migración."""
        return (self.view not in ("settings", "migrate", "recent", "addons")
                and self.layout_mode == "grid")

    def _set_zoom_value(self, value: float) -> None:
        """Fija el zoom pasando por el slider, para que UI y valor no se separen.

        El porcentaje es entero (el slider va de 1 en 1), así que redondeamos y
        bloqueamos la señal para no llamar dos veces a ``set_zoom``.
        """
        percent = int(round(min(MAX_ZOOM, max(MIN_ZOOM, float(value))) * 100))
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(percent)
        self.zoom_slider.blockSignals(False)
        self.set_zoom(percent / 100.0)

    def zoom_in(self) -> None:
        """Sube un paso el zoom (Ctrl +)."""
        if self._zoom_enabled():
            self._set_zoom_value(self.zoom + ZOOM_STEP)

    def zoom_out(self) -> None:
        """Baja un paso el zoom (Ctrl -)."""
        if self._zoom_enabled():
            self._set_zoom_value(self.zoom - ZOOM_STEP)

    def reset_zoom(self) -> None:
        """Vuelve al zoom de restablecimiento elegido en los ajustes (Ctrl+0)."""
        if self._zoom_enabled():
            self._set_zoom_value(self.settings.reset_zoom)

    def set_favorite(self, item, marked: bool) -> None:
        """Marca o desmarca una serie como favorita (estrella de una tarjeta).

        Se fija el estado que trae la señal en vez de alternarlo: así la estrella
        y el ajuste no se pueden desincronizar aunque llegue dos veces el evento.
        """
        key = getattr(item, "favorite_key", "")
        if not self.settings.set_favorite(key, marked):
            return
        self.settings.save()
        # En el canal de favoritos la lista cambia (la tarjeta entra o sale);
        # en los demás la rejilla sería la misma, así que no la repintamos para
        # no perder la posición del scroll.
        if self.channel == "favorites":
            self._rebuild_store()
            self._rebuild_installed()

    def set_platform(self, label: str) -> None:
        """Cambia la plataforma de destino y repinta."""
        self.platform_label = label
        self.settings.platform = label
        self.settings.save()
        self._rebuild_store()
        self.refresh_installed()

    def set_arch(self, label: str) -> None:
        """Cambia la arquitectura de destino y repinta."""
        self.arch_label = label
        self.settings.arch = label
        self.settings.save()
        self._rebuild_store()

    def _filtered(self):
        """Aplica plataforma, arquitectura, canal y búsqueda a las compilaciones.

        Usamos ``api.filter_builds`` (función pura y testeada) en vez de
        reimplementar el filtrado aquí: la primera versión del port lo repetía a
        mano y los filtros de canal no filtraban nada.
        """
        builds = api.available_for(self.builds, self.platform, self.arch)
        return api.filter_builds(builds, self.channel, self.search,
                                 self.settings.favorites)

    def _filtered_installed(self):
        """Aplica canal y búsqueda a las versiones instaladas.

        Igual que en la tienda, usamos la función pura y testeada
        (``installed_service.filter_installed``) en vez de reimplementarla: la
        primera versión del port solo miraba la búsqueda y las pastillas de
        canal no filtraban nada en esta pestaña.
        """
        return installed_service.filter_installed(self.installed, self.channel,
                                                  self.search,
                                                  self.settings.favorites)

    def resizeEvent(self, event):
        """Refluye la rejilla al cambiar el ancho (recalcula columnas)."""
        super().resizeEvent(event)
        if not hasattr(self, "_resize_timer"):
            self._resize_timer = QTimer(self)
            self._resize_timer.setSingleShot(True)
            self._resize_timer.timeout.connect(self._reflow)
        self._resize_timer.start(200)

    def changeEvent(self, event):
        """Minimizar a la bandeja, si el usuario lo pidió.

        El evento llega **antes** de que el gestor de ventanas termine de
        minimizar, así que el ocultado se difiere al siguiente ciclo: esconder
        la ventana en el acto hacía que algunos escritorios volvieran a
        mostrarla. Si la bandeja no está disponible no se hace nada: minimizar
        sin un icono al que volver dejaría la app inaccesible.
        """
        super().changeEvent(event)
        # ``getattr`` por si un cambio de estado llega durante el propio
        # ``__init__`` de QWidget, antes de que existan los atributos.
        if (event.type() == QEvent.WindowStateChange and self.isMinimized()
                and getattr(self, "minimize_to_tray", False)
                and not getattr(self, "_force_quit", False)
                and TrayIcon.available()):
            QTimer.singleShot(0, self, self._hide_to_tray)
        if (event.type() == QEvent.ActivationChange
                and getattr(self, "_focus_refresh", None) is not None
                and self.isActiveWindow()):
            self._refresh_on_focus()

    def _refresh_on_focus(self) -> None:
        """Reescanea las instaladas al recuperar el foco, con un cooldown.

        Blender puede haber instalado o renombrado algo fuera de la app. No se
        repite si se acaba de hacer (``_focus_refresh``) ni mientras hay una
        descarga o una actualización en curso: sería pisarla.
        """
        if (self.downloader.running or self.update_downloader.running
                or self._focus_refresh.isActive()):
            return
        self._focus_refresh.start()
        self.refresh_installed()

    # ------------------------------------------------------------- bandeja
    def _ensure_tray(self) -> TrayIcon:
        """Crea el icono de la bandeja la primera vez que se necesita.

        El objeto se reutiliza entre ocultados: crear y destruir el icono en
        cada uno era el camino a más de un fantasma en la bandeja.
        """
        if self._tray is None:
            self._tray = TrayIcon(self)
            self._tray.restore_requested.connect(self._restore_from_tray)
            self._tray.quit_requested.connect(self._quit_from_tray)
        return self._tray

    def _hide_to_tray(self) -> None:
        """Oculta la ventana y deja el icono en la bandeja.

        El aviso de "sigue en la bandeja" se enseña **una sola vez** (y se
        recuerda en los ajustes): sin él, esconder la ventana es indistinguible
        de que la app se haya cerrado.
        """
        tray = self._ensure_tray()
        tray.show()
        self.hide()
        if not self.settings.tray_hint_shown:
            tray.notify(
                tr("Still running in the system tray"),
                tr("BlenderManager keeps running in the tray. Click its icon to "
                   "bring the window back."))
            self.settings.tray_hint_shown = True
            self.settings.save()

    def _restore_from_tray(self) -> None:
        """Vuelve a mostrar la ventana y retira el icono (solo está mientras
        está oculta)."""
        if self._tray is not None:
            self._tray.hide()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_from_tray(self) -> None:
        """Salir de verdad desde el menú de la bandeja."""
        self._force_quit = True
        self._quit_app()

    def _quit_app(self) -> None:
        """Cierra la ventana saltándose el "cerrar a la bandeja".

        Lo usan el menú de la bandeja y los reinicios internos (tras aplicar una
        actualización o un ``git pull``), que sin esto se quedarían escondidos
        en la bandeja en vez de terminar.
        """
        if self._tray is not None:
            self._tray.hide()
        self.close()
        QApplication.quit()

    def closeEvent(self, event):
        """Vuelca el zoom pendiente y el tamaño de la ventana.

        El zoom va con retardo, así que si se cierra mientras el slider se mueve
        el guardado aún no ha corrido. El tamaño de la ventana se guarda aquí
        (y no en cada ``resizeEvent``) para no escribir el JSON a cada tirón del
        borde; la próxima vez ``main.py`` arranca con estas medidas.

        Si el usuario activó "cerrar a la bandeja", la X **no** cierra: se
        ignora el evento y la ventana se oculta (los ajustes ya se han guardado
        arriba). Solo se hace si la bandeja existe; si no, cerrar cierra.
        """
        self._zoom_settle.stop()
        self._zoom_tick.stop()
        changed = False
        if self.zoom != self.settings.zoom:
            self.settings.zoom = self.zoom
            changed = True
        width, height = self._normal_size()
        if (width, height) != (self.settings.window_width,
                               self.settings.window_height):
            self.settings.window_width = width
            self.settings.window_height = height
            changed = True
        if changed:
            self.settings.save()
        if (self.close_to_tray and not self._force_quit
                and TrayIcon.available()):
            event.ignore()
            self._hide_to_tray()
            return
        super().closeEvent(event)

    def _normal_size(self):
        """Tamaño con el que reabrir: el de la ventana, no el de maximizada.

        Si se cierra maximizada (o a pantalla completa) se guarda el tamaño
        "normal" anterior, para no arrancar siempre con la ventana a pantalla
        completa sin estarlo de verdad.
        """
        if self.isMaximized() or self.isFullScreen():
            geometry = self.normalGeometry()
        else:
            geometry = self.geometry()
        return geometry.width(), geometry.height()

    def center_on_screen(self) -> None:
        """Centra la ventana en el monitor, sea cual sea su tamaño.

        Se centra el **marco** (``frameGeometry``), no solo el área de cliente,
        para que quede bien con la barra de título y los bordes del gestor de
        ventanas.
        """
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        frame = self.frameGeometry()
        frame.moveCenter(screen.availableGeometry().center())
        self.move(frame.topLeft())

    def reset_window_size(self) -> None:
        """Devuelve la ventana al tamaño por defecto y la centra.

        Se pone a ``0`` en los ajustes para que, al volver a abrir, se use otra
        vez el tamaño de fábrica (es lo mismo que hace ``main.py``).
        """
        self.settings.window_width = 0
        self.settings.window_height = 0
        self.settings.save()
        self.showNormal()
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self.center_on_screen()

    def _reflow(self) -> None:
        if self.layout_mode == "grid":
            self._rebuild_store()
            self._rebuild_installed()

    def _columns_for(self, scroll: QScrollArea, card_width: int) -> int:
        """Número de columnas que caben en el ancho visible (mínimo 1).

        OJO: usamos el ancho del ``QStackedWidget``, no el del ``viewport`` de la
        página. Un ``QStackedWidget`` da a las páginas NO activas un tamaño
        reducido (la de ajustes mide 640 en una ventana de 1060), así que el
        viewport de la tienda miente mientras no está delante.
        """
        width = self.stack.width() if self.stack.width() > 0 else self.width() - 74
        available = width - 28  # margins 14+14
        return max(1, available // max(1, card_width + 10))

    # Ancho MÍNIMO que necesita una tarjeta de rejilla para no recortarse
    # (medido: 227 px con el logo, las etiquetas y el botón). Si se piden más
    # columnas que las que caben a ese ancho, la última se sale del viewport.
    MIN_CARD_WIDTH = 230

    def _grid_columns(self, scroll: QScrollArea, grid: QGridLayout, list_width: int) -> int:
        """En modo lista, 1 columna a todo lo ancho; en rejilla, las que quepan."""
        if self.layout_mode == "list":
            return 1
        # Ancho objetivo de una tarjeta de rejilla escalada por el zoom, pero
        # nunca por debajo del mínimo que necesita el contenido.
        target = max(int(300 * self.zoom), self.MIN_CARD_WIDTH)
        return self._columns_for(scroll, target)

    def _fill_grid(self, grid: QGridLayout, cards: list, columns: int) -> None:
        """Coloca las tarjetas en la rejilla, repartiendo el ancho a partes iguales.

        Al dar a todas las columnas el mismo ``stretch`` y NO fijar un ancho a
        las tarjetas, cada una se estira para llenar su celda: la rejilla se
        adapta al ancho de la ventana en vez de dejar huecos a la derecha.
        """
        clear_layout(grid)
        # Reseteamos stretches de una rejilla anterior con más columnas.
        for col in range(24):
            grid.setColumnStretch(col, 1 if col < columns else 0)
        for index, card in enumerate(cards):
            grid.addWidget(card, index // columns, index % columns)

    def _placeholder(self, text: str, hint: str = "") -> QFrame:
        frame = QFrame()
        frame.setObjectName("Card")
        card_shadow(frame)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(20, 24, 20, 24)
        label = QLabel(text)
        label.setObjectName("Muted")
        label.setAlignment(Qt.AlignCenter)
        lay.addWidget(label)
        if hint:
            hint_label = QLabel(hint)
            hint_label.setObjectName("Muted")
            hint_label.setAlignment(Qt.AlignCenter)
            lay.addWidget(hint_label)
        return frame

    def _rebuild_store(self) -> None:
        clear_layout(self.store_grid)
        builds = self._filtered()
        columns = self._grid_columns(self.store_scroll, self.store_grid, 0)
        if not builds:
            # Cada canal vacío tiene su explicación, en vez del genérico.
            if self.channel == "experimental":
                text, hint = tr("No experimental builds right now"), ""
            elif self.channel == "favorites":
                text = tr("No favorites yet")
                hint = tr("Tap the star on a card to keep it here.")
            else:
                text = tr("No builds found")
                hint = tr("Try clearing the search or another channel filter.")
            self._fill_grid(self.store_grid, [self._placeholder(text, hint)],
                            columns)
            return
        grid = self.layout_mode == "grid"
        cards = []
        for index, build in enumerate(builds):
            entry = next((e for e in self.installed
                          if e.version == build.version), None)
            installed = entry is not None
            # La cebra es para la lista (filas contiguas); en rejilla las
            # tarjetas van sueltas sobre el fondo y alternar el gris solo
            # ensucia el conjunto.
            zebra = (not grid) and bool(index % 2)
            marked = build.favorite_key in self.settings.favorites
            # Una versión instalada se lanza desde aquí igual que desde Local,
            # así que lleva el mismo botón de consola (misma clave: la serie).
            console = (self._console_state(entry)
                       if installed and self.settings.experimental_features
                       else None)
            if grid:
                card = GridBuildCard(build, installed, zebra, self.zoom, marked,
                                     console=console)
            else:
                card = BuildCard(build, installed, zebra, marked, console=console)
            card.action_clicked.connect(self.install_build)
            card.notes_clicked.connect(self.open_release_notes)
            card.favorite_toggled.connect(self.set_favorite)
            card.console_toggled.connect(self.set_console_for)
            card.setContextMenuPolicy(Qt.CustomContextMenu)
            card.customContextMenuRequested.connect(
                lambda pos, b=build, c=card: self._show_store_menu(b, c, pos))
            cards.append(card)
        self._fill_grid(self.store_grid, cards, columns)

    def _installed_menu(self, entry) -> QMenu:
        """Menú contextual de una tarjeta instalada (sin mostrarlo).

        Se separa de ``_show_installed_menu`` para poder comprobarlo sin abrir
        un menú modal (que en un test se queda esperando).
        """
        menu = card_menu(self)
        launch = menu.addAction(tr("Launch"))
        launch.triggered.connect(lambda: self.launch_installed(entry))
        if self.settings.experimental_features:
            console = menu.addAction(tr("Launch with console"))
            console.triggered.connect(lambda: self._launch_with_console(entry))
        menu.addSeparator()
        open_folder = menu.addAction(tr("Open folder"))
        open_folder.triggered.connect(lambda: opener.open_path(entry.path))
        copy = menu.addAction(tr("Copy path"))
        copy.triggered.connect(
            lambda: QApplication.clipboard().setText(str(entry.path)))
        menu.addSeparator()
        remove = menu.addAction(tr("Uninstall"))
        remove.triggered.connect(lambda: self.delete_installed(entry))
        return menu

    def _show_installed_menu(self, entry, card, pos) -> None:
        self._installed_menu(entry).exec(card.mapToGlobal(pos))

    def _launch_with_console(self, entry) -> None:
        """Lanza esa versión con consola sin cambiar el ajuste guardado."""
        executable = getattr(entry, "executable", None)
        if not executable:
            return
        try:
            args = shlex.split(self.launch_args or "")
            self.launcher.launch(executable, args=args, console=True)
        except Exception as error:
            download_log(f"launch failed: {error}")

    def _store_menu(self, build) -> QMenu:
        """Menú contextual de una tarjeta de la tienda (sin mostrarlo)."""
        menu = card_menu(self)
        install = menu.addAction(tr("Download and install"))
        install.triggered.connect(lambda: self.install_build(build))
        notes = menu.addAction(tr("Release notes"))
        notes.triggered.connect(lambda: self.open_release_notes(build.version))
        menu.addSeparator()
        copy = menu.addAction(tr("Copy download link"))
        copy.triggered.connect(
            lambda: QApplication.clipboard().setText(build.url))
        return menu

    def _show_store_menu(self, build, card, pos) -> None:
        self._store_menu(build).exec(card.mapToGlobal(pos))

    def refresh_installed(self) -> None:
        """Vuelve a escanear las carpetas y repinta las instaladas."""
        self.installed = installed_service.scan_folders(self.settings.scan_roots(),
                                                        self.platform)
        self._recompute_updates()
        self._rebuild_installed()
        self.migrate_view.set_installed(self.installed)
        self.recent_view.set_installed(self.installed)
        self.addons_view.set_installed(self.installed)

    def _recompute_updates(self) -> None:
        """Recalcula qué instaladas tienen parche o serie nueva disponible.

        Las builds se filtran por plataforma/arquitectura (``available_for``)
        para no ofrecer un parche que no es para este sistema. Se guardan por
        ruta para que las tarjetas lo consulten al construirse.
        """
        builds = api.available_for(self.builds, self.platform, self.arch)
        updates = installed_service.available_updates(self.installed, builds)
        # Las series que el usuario silenció con "Nunca" no se ofrecen (ni el
        # parche de la tarjeta ni el aviso de salto de serie).
        muted = set(self.settings.ignored_blender_series)
        if muted:
            updates = [u for u in updates
                       if minor_of(u.entry.version) not in muted]
        self.updates_by_path = {
            str(u.entry.path): u.build for u in updates if u.kind == "patch"}
        self.series_updates = [
            u for u in updates if u.kind == "series"]

    def _rebuild_installed(self) -> None:
        clear_layout(self.installed_grid)
        entries = self._filtered_installed()
        columns = self._grid_columns(self.installed_scroll, self.installed_grid, 0)
        if not entries:
            if self.channel == "favorites":
                text = tr("No favorites yet")
                hint = tr("Tap the star on a card to keep it here.")
            else:
                text = tr("No local versions found")
                hint = tr("Download one from the cloud to see it here.")
            self._fill_grid(self.installed_grid, [self._placeholder(text, hint)],
                            columns)
            return
        grid = self.layout_mode == "grid"
        cards = []
        for index, entry in enumerate(entries):
            # Igual que en la tienda: cebra solo en modo lista.
            zebra = (not grid) and bool(index % 2)
            marked = entry.favorite_key in self.settings.favorites
            update = self.updates_by_path.get(str(entry.path))
            # El botón de consola solo se enseña con las opciones experimentales.
            console = (self._console_state(entry)
                       if self.settings.experimental_features else None)
            if grid:
                card = GridInstalledCard(entry, zebra, self.zoom, marked,
                                         update=update, console=console)
            else:
                card = InstalledCard(entry, zebra, marked, update=update,
                                     read_only=self._is_read_only(entry),
                                     console=console)
            card.launch_clicked.connect(self.launch_installed)
            card.delete_clicked.connect(self.delete_installed)
            card.notes_clicked.connect(self.open_release_notes)
            card.favorite_toggled.connect(self.set_favorite)
            card.update_clicked.connect(self.offer_blender_update)
            card.rename_requested.connect(self.rename_installed)
            card.console_toggled.connect(self.set_console_for)
            card.setContextMenuPolicy(Qt.CustomContextMenu)
            card.customContextMenuRequested.connect(
                lambda pos, e=entry, c=card: self._show_installed_menu(e, c, pos))
            cards.append(card)
        self._fill_grid(self.installed_grid, cards, columns)

    # ------------------------------------------------------------- refresco
    def refresh(self, force: bool = False) -> None:
        """Pide el listado de compilaciones y lo pinta cuando llega."""
        self._set_status(tr("Loading..."))

        def worker():
            try:
                builds = api.get_builds(force=force)
            except Exception as error:  # red, JSON roto...
                download_log(f"refresh failed: {error}")
                builds = []
            self.builds_loaded.emit(builds)

        threading.Thread(target=worker, daemon=True).start()

    def _on_builds_loaded(self, builds) -> None:
        self.builds = builds
        self._recompute_updates()
        self._rebuild_store()
        # Las instaladas también llevan el aviso de parche, y ese aviso depende
        # del listado que acaba de llegar.
        self._rebuild_installed()
        # La ventana puede no tener todavía su ancho final: refloweamos en
        # cuanto el layout esté asentado para calcular bien las columnas.
        QTimer.singleShot(250, self, self._reflow)
        if self.updates_by_path:
            self._show_message(
                tr("{count} Blender updates available",
                   count=len(self.updates_by_path)), 6)
        else:
            self._set_status(tr("Ready"), 2)
        # El salto de serie (5.2 -> 5.3) se ofrece aparte, en un diálogo.
        QTimer.singleShot(400, self, self._offer_series_update)
        if not self._auto_checked:
            self._auto_checked = True
            if self.auto_update:
                QTimer.singleShot(2000, self, lambda: self.check_updates(manual=False))

    # -------------------------------------------------------------- acciones
    def open_release_notes(self, version_text: str) -> None:
        """Abre en el navegador las notas de esa serie de Blender.

        La URL la construye ``api.release_notes_url`` (va por serie, no por
        versión exacta: de "5.2.1" sale .../release_notes/5.2/). El port la
        sustituyó por una URL a mano que no existe, y por eso el icono dejó de
        abrir nada útil.

        ``opener.open_url`` puede tardar (arranca el navegador), así que corre
        en un hilo y el resultado vuelve por señal.
        """
        url = api.release_notes_url(version_text)
        self._show_message(tr("Opening the release notes..."))

        def worker():
            try:
                opened = opener.open_url(url)
            except Exception:
                opened = False
            self.release_notes_result.emit(bool(opened))

        threading.Thread(target=worker, daemon=True).start()

    def _on_release_notes_result(self, opened: bool) -> None:
        if not opened:
            self._show_message(tr("Could not open the browser"))

    def _choose_folder(self, current: str, title: str) -> str:
        """Abre el diálogo de carpetas del sistema y devuelve la elegida (o "")."""
        return QFileDialog.getExistingDirectory(self, title,
                                                current or str(Path.home()))

    def browse_dest(self) -> None:
        """Pide la carpeta de descargas con el diálogo del sistema (modo simple)."""
        current = self.settings.folders[0].path if self.settings.folders else ""
        folder = self._choose_folder(current, tr("Choose destination folder"))
        if folder:
            self.dest_input.setText(folder)
            self._on_simple_folder_changed()

    def _on_simple_folder_changed(self) -> None:
        """Cambia la ruta de la única carpeta (modo simple)."""
        text = self.dest_input.text().strip()
        if not text or not self.settings.folders:
            return
        if channels.normalize_path(text) == channels.normalize_path(
                self.settings.folders[0].path):
            return
        self.settings.folders[0].path = text
        self._save_folders()

    # -------------------------------------------- biblioteca de carpetas
    def add_folder(self) -> None:
        """Da de alta una carpeta nueva en la biblioteca.

        Propone marcarle los tipos que **nadie** recibe todavía: es lo que hace
        que el primer clic en "Separar por canales" deje algo útil sin tener
        que explicar nada. Si ya están todos repartidos entra sin tipos (solo
        se escanea), que es lo menos invasivo.
        """
        folder = self._choose_folder("", tr("Choose a folder with Blender versions"))
        if not folder:
            return
        problem = self._folder_problem(folder)
        if problem == "duplicate":
            show_info(self, tr("Folders"),
                      tr("That folder is already in the list."))
            return

        writable = not _write_problem(folder)
        types = channels.orphan_types(self.settings.folders) if writable else []
        self.settings.folders.append(
            settings_service.Folder(path=folder, types=types, writable=writable))
        self._save_folders()
        self._rebuild_folder_rows()
        if not writable:
            self._show_message(tr(
                "Added as read-only: that folder does not allow writing."), 6)

    def _folder_problem(self, candidate: str) -> str:
        """Por qué no se puede añadir esa carpeta, o "" si sí se puede.

        Lo único que se rechaza es **la misma carpeta dos veces**. Anidar sí se
        permite, y es una petición razonable: tener ``Blender 3D`` de raíz y
        ``Blender 3D/Experimentales`` dentro es de las formas más naturales de
        organizarse. No duplica nada porque ``installed._scan_root`` solo mira
        los hijos **directos** de cada raíz y descarta los que no parecen una
        build, así que la carpeta hija no se cuenta dos veces (lo fija
        ``test_una_subcarpeta_no_duplica_las_versiones``).

        Se compara con ``resolve()`` y no por texto: si no, en Windows
        ``C:\\Blender`` y ``c:\\blender`` entrarían como dos carpetas
        distintas y todas sus versiones saldrían duplicadas en Local.
        """
        def resolved(path):
            try:
                return Path(path).expanduser().resolve()
            except OSError:
                return Path(path).expanduser()

        target = resolved(candidate)
        for folder in self.settings.folders:
            if resolved(folder.path) == target:
                return "duplicate"
        return ""

    def _on_folder_type_toggled(self, path: str, build_type: str,
                                marked: bool) -> None:
        """Marca o desmarca un tipo, respetando que solo tenga un dueño."""
        folder = self.settings.folder_for(path)
        if folder is None:
            return
        previous = (channels.owner_of(self.settings.folders, build_type)
                    if marked else None)
        if marked:
            for other in self.settings.folders:
                if build_type in other.types and other is not folder:
                    other.types = [item for item in other.types
                                   if item != build_type]
            if build_type not in folder.types:
                folder.types = [item for item in channels.BUILD_TYPES
                                if item in folder.types or item == build_type]
        else:
            folder.types = [item for item in folder.types if item != build_type]
        self._save_folders()
        # Solo se repintan las filas afectadas: reconstruir la lista entera
        # desde la señal de una de sus casillas destruiría el widget que la
        # acaba de emitir.
        for target in {path, previous.path if previous else None}:
            row = self.folder_rows.get(channels.normalize_path(target or ""))
            entry = self.settings.folder_for(target or "")
            if row is not None and entry is not None:
                row.set_folder(entry)
        if previous is not None:
            self._show_message(tr(
                "{type} builds now go to {folder}",
                type=tr(TYPE_LABELS[build_type]), folder=folder.path), 6)
        # Al desmarcar, lo que ya estaba dentro puede dejar de encajar; al
        # marcar, es la carpeta que pierde el tipo la que se queda con builds
        # que ya no recibe.
        self._offer_reorg(previous.path if previous is not None else path)

    def _on_folder_writable_toggled(self, path: str, writable: bool) -> None:
        """Abre o cierra el candado de una carpeta.

        Cerrarlo apaga sus casillas: no se puede recibir una descarga donde la
        aplicación no escribe (es la invariante de ``settings.Folder``).
        """
        folder = self.settings.folder_for(path)
        if folder is None:
            return
        folder.writable = writable
        if not writable:
            folder.types = []
        elif not folder.types:
            # Al abrir el candado se le devuelven los tipos que no tenga nadie.
            # Antes se quedaba vacía, así que cerrar y volver a abrir dejaba la
            # carpeta sin recibir nada --y si era la única, la aplicación sin
            # sitio donde descargar-- sin que el usuario hubiera tocado ninguna
            # casilla. Es la misma regla que al añadir una carpeta nueva.
            folder.types = channels.orphan_types(self.settings.folders)
        self._save_folders()
        row = self.folder_rows.get(channels.normalize_path(path))
        if row is not None:
            row.set_folder(folder)
        if not writable:
            # Cerrar el candado deja la carpeta sin recibir nada: lo de dentro
            # puede tener ahora otra casa. Pero de aquí no se saca nada (lo
            # impide ``organizer.plan_reorg``), así que no saldrá diálogo.
            self._offer_reorg(path)

    def _on_folder_remove_requested(self, path: str) -> None:
        """Quita una carpeta de la lista (sin tocar el disco)."""
        folder = self.settings.folder_for(path)
        if folder is None:
            return
        if not confirm(self, tr("Remove folder"),
                       tr("Remove {folder} from the list?", folder=path)
                       + "\n\n"
                       + tr("Nothing is deleted from disk: the versions there "
                            "just stop being shown."),
                       accept_text=tr("Remove")):
            return
        self.settings.folders = [item for item in self.settings.folders
                                 if item is not folder]
        self._save_folders()
        self._rebuild_folder_rows()

    def _destination_for(self, build) -> str:
        """Carpeta donde va esta compilación, o "" si nadie recibe su tipo.

        Se delega en ``Settings.destination_for`` para que la regla viva con
        los ajustes (y se pueda probar sin montar la ventana).
        """
        return self.settings.destination_for(build)

    # ------------------------------------------------------- auto-guardado
    def _on_archive_toggled(self, value: bool) -> None:
        self.delete_archive = value
        self.settings.delete_archive = value
        self.settings.save()

    def _on_close_to_tray_toggled(self, value: bool) -> None:
        self.close_to_tray = value
        self.settings.close_to_tray = value
        self.settings.save()

    def _on_minimize_to_tray_toggled(self, value: bool) -> None:
        self.minimize_to_tray = value
        self.settings.minimize_to_tray = value
        self.settings.save()
        if detector.session_is_wayland():
            # El backend (Wayland o XWayland) se elige al arrancar: activar o
            # desactivar esto no surte efecto hasta reiniciar.
            self._show_message(
                tr("Restart BlenderManager to apply the change."), 8)

    def _on_start_minimized_toggled(self, value: bool) -> None:
        self.start_minimized = value
        self.settings.start_minimized = value
        self.settings.save()

    def _on_autostart_toggled(self, value: bool) -> None:
        """Registra (o quita) el autoarranque en el propio sistema.

        No se guarda en ``settings.json``: el estado vive en el sistema, así
        que si falla se relee y se deja el interruptor como estaba (si no, la
        interfaz diría una cosa y el sistema otra).
        """
        ok = autostart.enable() if value else autostart.disable()
        if ok:
            return
        show_error(self, tr("Automatic startup"),
                   tr("Could not change the automatic startup."))
        self.autostart_switch.blockSignals(True)
        self.autostart_switch.setChecked(autostart.is_enabled())
        self.autostart_switch.blockSignals(False)

    def _on_args_changed(self, text: str) -> None:
        self.launch_args = text
        self.settings.launch_args = text
        self.settings.save()

    def _on_language_changed(self, label: str) -> None:
        for lang_id, english in LANGUAGE_IDS.items():
            if tr(english) == label:
                self.settings.language = lang_id
                self.settings.save()
                break

    def _on_reset_zoom_changed(self, percent: int) -> None:
        """Mueve el destino del reset: etiqueta en vivo, guardado al soltar.

        No escribimos el JSON en cada píxel del arrastre (como con el slider
        del pie): aquí no hay nada que reconstruir, así que basta con esperar a
        que el usuario suelte el tirador (o use el teclado).
        """
        self.settings.reset_zoom = min(MAX_ZOOM, max(MIN_ZOOM, percent / 100.0))
        self.reset_zoom_label.setText(f"{percent} %")
        if not self.reset_zoom_slider.isSliderDown():
            self._save_reset_zoom()

    def _save_reset_zoom(self) -> None:
        self.settings.save()

    def _factory_reset_zoom(self) -> None:
        """Ctrl+clic en el slider del ajuste: vuelve al valor de fábrica."""
        self.reset_zoom_slider.setValue(round(settings_service.DEFAULT_ZOOM * 100))

    def set_auto_update(self, active: bool) -> None:
        """Guarda si hay que comprobar actualizaciones al arrancar.

        Es independiente del chequeo periódico: apagarlo no lo toca.
        """
        self.auto_update = active
        self.settings.auto_update = active
        self.settings.save()

    def set_periodic_update(self, active: bool) -> None:
        """Apaga/enciende el chequeo periódico (independiente del de arranque)."""
        self.periodic_update = active
        self.settings.periodic_update = active
        self.settings.save()
        if hasattr(self, "update_interval_combo"):
            self.update_interval_combo.setEnabled(active)
        self._apply_update_timer()

    def _apply_update_timer(self) -> None:
        """(Re)programa el chequeo periódico de la app según los ajustes."""
        minutes = self.settings.update_interval_min
        if self.periodic_update and minutes > 0:
            self._update_timer.start(minutes * 60 * 1000)
        else:
            self._update_timer.stop()

    def _periodic_update_check(self) -> None:
        """Chequeo automático de la app cada ``update_interval_min`` minutos.

        No interrumpe: si hay una descarga en curso o un diálogo abierto se salta
        esta vuelta, y si ya se avisó de una versión en esta sesión tampoco la
        repite (darle a "Más tarde" no puede sacar el aviso cada X minutos).
        """
        if self.downloader.running or self.update_downloader.running:
            return
        if QApplication.activeModalWidget() is not None:
            return
        if self._offered_update_tag:
            return
        self.check_updates(manual=False)

    @staticmethod
    def _interval_text(minutes: int) -> str:
        """Etiqueta del intervalo (el valor guardado van en minutos enteros)."""
        if minutes <= 0:
            return tr("Never")
        if minutes == 1:
            return tr("Every minute")
        if minutes < 60:
            return tr("{count} minutes", count=minutes)
        if minutes == 60:
            return tr("Every hour")
        return tr("Every {count} hours", count=minutes // 60)

    def _on_update_interval_changed(self, index: int) -> None:
        minutes = self.update_interval_combo.itemData(index)
        if minutes is None:
            return
        self.settings.update_interval_min = int(minutes)
        self.settings.save()
        self._apply_update_timer()

    # ----------------------------------------------------- descarga / instalación
    def install_build(self, build) -> None:
        """Descarga e instala una compilación (progreso y SHA-256)."""
        installed = next((e for e in self.installed if e.version == build.version), None)
        if installed is not None:
            self.launch_installed(installed)
            return
        if self.downloader.running:
            return
        self._set_downloading(True)
        self.progress.setValue(0)
        # Primero se elige de qué fuente bajar (el CDN o el release oficial). Es
        # una medición de red, así que va en un hilo y vuelve por señal: en el
        # hilo de la interfaz congelaría la ventana un par de segundos.
        self._set_status(tr("Choosing the fastest source..."))

        def worker():
            self.source_chosen.emit(build, sources.choose(build))

        threading.Thread(target=worker, daemon=True).start()

    def _start_download(self, build, source) -> None:
        """Arranca la descarga desde la fuente ya elegida."""
        target = self._destination_for(build)
        if not target:
            # Nadie ha marcado ese tipo en ninguna carpeta. Es el precio de no
            # tener cadena de reservas, y es el precio bueno: mejor decirlo que
            # dejarle la build en una carpeta que no eligió.
            self._set_downloading(False)
            self._no_folder_for(channels.type_of_build(build))
            return
        destination = str(Path(target).expanduser())
        # La carpeta puede no dejar escribir (la de las LTS suele estar en otro
        # disco y a veces es una de sistema). Comprobarlo ahora evita bajar
        # cientos de MB para nada y, sobre todo, explica el motivo.
        problem = _write_problem(destination)
        if problem:
            # En vez de rendirnos, ofrecemos elegir otra carpeta y reintentar:
            # carpetas como "C:\Program Files" solo dejan escribir a un
            # administrador, y eso el usuario no lo puede cambiar desde aquí.
            if self._ask_other_folder(build, destination, problem):
                self._start_download(build, source)
                return
            self._set_downloading(False)
            self._set_status(tr("Download failed"), 6)
            return
        self._set_status(tr("Downloading..."))
        download_log(f"downloading {build.filename} from {source.label}")
        self._bridge = _Bridge()
        self._bridge.progress.connect(self._set_progress)
        self._bridge.done.connect(lambda path: self._on_download_done(path, build))
        self._bridge.error.connect(self._on_download_error)
        self.downloader.start(
            source.url, destination,
            build.filename, source.checksum,
            on_progress=lambda done, total: self._bridge.progress.emit(done, total),
            on_done=lambda path: self._bridge.done.emit(str(path)),
            on_error=lambda msg: self._bridge.error.emit(msg),
        )

    def _no_folder_for(self, build_type: str) -> None:
        """Avisa de que nadie recibe ese tipo y lleva a arreglarlo."""
        dialog = AppDialog(
            self, tr("Download"),
            tr("No folder is set to receive {type} builds.",
               type=tr(TYPE_LABELS[build_type]))
            + "\n\n"
            + tr("Open Settings and tick {type} on the folder where you want "
                 "them.", type=tr(TYPE_LABELS[build_type])))
        choice = {"open": False}
        dialog.add_button(tr("Close"), on_click=dialog.reject)
        dialog.add_button(
            tr("Open folder settings"), variant="accent",
            on_click=lambda: (choice.update(open=True), dialog.accept()),
            tooltip=tr("Takes you to Settings > Folders, where you choose "
                       "which folder\nreceives each kind of build."))
        dialog.exec()
        if choice["open"]:
            self.set_view("settings")
            self.settings_tabs.setCurrentIndex(self.FOLDERS_TAB)

    def _ask_other_folder(self, build, destination: str, problem: str) -> bool:
        """Ofrece arreglar la carpeta cuando no se puede escribir en ella.

        Devuelve True si al final se puede escribir ahí (porque el usuario ha
        elegido otra carpeta o ha dado permiso de administrador), para que la
        descarga se reintente sola. La carpeta nueva se da de alta con **el
        tipo de esta compilación**, así que el arreglo dura: antes se adivinaba
        cuál era la carpeta afectada comparando cadenas de rutas y, de paso, se
        cambiaba la carpeta global por defecto por un fallo puntual.
        """
        message = (tr("Could not write to the destination folder:")
                   + "\n\n" + destination + "\n\n" + problem
                   + "\n\n" + tr("Windows protects folders like Program Files. "
                                 "Pick a folder you can write to, such as "
                                 "Documents or another drive."))
        dialog = AppDialog(self, tr("Download failed"), message)
        choice = {"other": False, "admin": False}
        dialog.add_button(tr("Close"), on_click=dialog.reject)
        dialog.add_button(
            tr("Choose another folder"), variant="accent",
            on_click=lambda: (choice.update(other=True), dialog.accept()))
        if elevate.available():
            dialog.add_button(
                tr("Grant permission (admin)"),
                on_click=lambda: (choice.update(admin=True), dialog.accept()))
        dialog.exec()

        if choice["admin"]:
            # Windows: pedir el UAC una vez para dar permiso de escritura sobre
            # esta carpeta al usuario, en vez de cambiar de sitio.
            if self._grant_permission(destination):
                return True
            show_error(self, tr("Download failed"),
                       tr("The folder still could not be made writable."))
            return False
        if not choice["other"]:
            return False
        build_type = channels.type_of_build(build)
        folder = self._choose_folder(destination, tr("Choose destination folder"))
        if not folder:
            return False
        existing = self.settings.folder_for(folder)
        if existing is None:
            existing = settings_service.Folder(path=folder, types=[],
                                               writable=True)
            self.settings.folders.append(existing)
        existing.writable = True
        # El tipo cambia de dueño: solo puede estar en una carpeta.
        for other in self.settings.folders:
            if other is not existing:
                other.types = [item for item in other.types if item != build_type]
        existing.types = [item for item in channels.BUILD_TYPES
                          if item in existing.types or item == build_type]
        self._save_folders()
        self._rebuild_folder_rows()
        return True

    def _grant_permission(self, destination: str) -> bool:
        """Pide el UAC y espera a poder escribir en ``destination``.

        Lanza este mismo binario elevado con ``--grant-access`` (ver
        ``services.elevate``). El proceso elevado es rápido, así que se espera
        un poco comprobando si la carpeta ya deja escribir; mientras, se
        procesan eventos para que la ventana no se quede congelada.
        """
        if not elevate.available():
            return False
        if not elevate.relaunch_elevated(["--grant-access", destination]):
            # El usuario ha cancelado el UAC.
            self._show_message(tr("The permission request was cancelled."), 5)
            return False
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if not _write_problem(destination):
                return True
            QApplication.processEvents()
            time.sleep(0.2)
        return False

    def _set_progress(self, downloaded: int, total: int) -> None:
        value = int(downloaded * 100 / total) if total else 0
        self.progress.setValue(value)
        self.percent.setText(f"{value} %")

    def cancel_download(self) -> None:
        """Cancela la descarga en curso."""
        self.downloader.cancel()
        # Si la descarga era un "Reemplazar", ya no se borra nada.
        self._replace_entry = None
        self._set_status(tr("Cancelled"))

    def _on_download_done(self, path: str, build) -> None:
        archive = Path(path)
        # El .dmg de macOS no es un archivo comprimido, pero sí se puede
        # montar y copiar el Blender.app a la carpeta destino: así la build se
        # puede lanzar desde la app como cualquier otra (antes se dejaba el
        # fichero y había que instalarla a mano, sin forma de abrirla luego).
        if (not is_archive(archive)
                and archive.suffix.lower() == ".dmg"
                and self.system.os_name == "darwin"
                and macos_dmg.available()):
            self._install_dmg(archive, build)
            return
        if not is_archive(archive):
            # Otro fichero que no sabemos abrir (o un .dmg bajado desde otro
            # sistema para un Mac): se deja donde está y se avisa, en vez de
            # fingir un fallo de descarga.
            self._on_dmg_manual(str(archive))
            return
        self._set_status(tr("Extracting..."))
        self._set_downloading(True)

        # El archivo ya está bajado, así que se extrae **junto a él**: es la
        # carpeta que recibió la descarga. Preguntar otra vez por el destino
        # daría "" si el usuario acaba de quitar esa carpeta de la lista, y
        # ``Path("")`` es el directorio actual: extraeríamos dentro de la app.
        destination = archive.parent

        def worker():
            try:
                target = extract(archive, destination)
                # El nombre de la carpeta extraída no lleva el hash de la
                # compilación, así que lo anotamos nosotros: es lo único que
                # distingue dos diarias de la misma versión bajadas en días
                # distintos (ver ``services.installed``). Si no apareció una
                # carpeta nueva (target == destino) no hay dónde anotarlo.
                if Path(target) != destination:
                    installed_service.write_marker(target, build)
                # Borrar el archivo comprimido solo si el usuario lo pidió.
                if self.delete_archive:
                    try:
                        archive.unlink()
                    except OSError:
                        pass
            except Exception as error:
                download_log(f"extract failed: {error}")
                self.download_error.emit(str(error))
                return
            self.extract_done.emit(str(target))

        threading.Thread(target=worker, daemon=True).start()

    def _install_dmg(self, archive: Path, build) -> None:
        """Monta el .dmg e instala el ``Blender.app`` en un hilo de trabajo.

        Montar y copiar un bundle son operaciones lentas, así que van fuera del
        hilo de la interfaz. El resultado vuelve por ``extract_done`` (el mismo
        camino que una extracción normal, así el "Reemplazar" y el refresco
        funcionan igual) o por ``dmg_manual`` si no se pudo.
        """
        self._set_status(tr("Installing..."))
        self._set_downloading(True)
        # Igual que al extraer: el .dmg ya está en la carpeta que lo recibió.
        destination = archive.parent

        def worker():
            try:
                target = macos_dmg.install(archive, destination,
                                           build.version, build.arch)
                installed_service.write_marker(target, build)
                if self.delete_archive:
                    try:
                        archive.unlink()
                    except OSError:
                        pass
            except Exception as error:
                download_log(f"dmg install failed: {error}")
                self.dmg_manual.emit(str(archive))
                return
            self.extract_done.emit(str(target))

        threading.Thread(target=worker, daemon=True).start()

    def _on_dmg_manual(self, path: str) -> None:
        """Plan B de macOS (o fichero que no sabemos abrir): revelar y avisar.

        La descarga ha ido bien, así que no es un "Download failed": se deja el
        fichero donde está y se explica que hay que instalarlo a mano.
        """
        archive = Path(path)
        # No hubo extracción, así que no hay "Reemplazar" que completar: sin
        # esto la carpeta vieja se borraría en la siguiente extracción.
        self._replace_entry = None
        self._set_downloading(False)
        self.progress.setValue(0)
        self.percent.setText("")
        opener.reveal(archive)
        self._show_message(
            tr("Downloaded to {folder}", folder=archive.parent)
            + "  ·  "
            + tr("Open it to install Blender manually."),
            10,
        )

    def _on_extract_done(self, target: str) -> None:
        self._set_downloading(False)
        self.progress.setValue(0)
        self.percent.setText("")
        self._set_status(tr("Ready"), 3)
        self.refresh_installed()
        # "Reemplazar": ahora que la nueva está extraída, se borra la vieja.
        # Si el borrado falla, la nueva queda igualmente instalada y se avisa.
        if self._replace_entry is not None:
            old, self._replace_entry = self._replace_entry, None
            try:
                shutil.rmtree(old.path)
            except OSError as error:
                download_log(f"replace failed ({old.path}): {error}")
                show_error(self, tr("Uninstall"), str(error))
            else:
                self._show_message(tr("Replaced {name}", name=old.name), 5)
                self.refresh_installed()
        self._rebuild_store()

    # ---------------------------------------------------- updates de Blender
    def offer_blender_update(self, entry, build) -> None:
        """Pregunta si reemplazar la instalada o bajar la nueva como copia.

        Es el mismo diálogo para el parche de la misma serie (botón de la
        tarjeta) y para el salto de serie (aviso al cargar compilaciones): en
        los dos casos la decisión es la misma. "Nunca" silencia esa serie de
        Blender (ver ``mute_blender_series``).
        """
        message = (
            tr("You have Blender {current} installed. Blender {new} is available.",
               current=entry.version, new=build.version)
            + "\n\n"
            + tr("Replace the installed version or download the new one as a copy?")
        )
        dialog = AppDialog(self, tr("Update available"), message)
        choice = {"replace": None, "never": False}
        dialog.add_button(tr("Later"), on_click=dialog.reject,
                          tooltip=tr("Ask me again another time."))
        dialog.add_button(
            tr("Download as copy"),
            on_click=lambda: (choice.update(replace=False), dialog.accept()),
            tooltip=tr("Keep the version you have and add the new one next to "
                       "it."))
        dialog.add_button(
            tr("Replace"), variant="accent",
            on_click=lambda: (choice.update(replace=True), dialog.accept()),
            tooltip=tr("Delete the installed version and put the new one in its "
                       "place."))
        dialog.add_button(
            tr("Never"),
            on_click=lambda: (choice.update(never=True), dialog.reject()),
            tooltip=tr("Never offer updates for this Blender series again.\n"
                       "You can undo it in Settings."))
        dialog.exec()
        if choice["never"]:
            self.mute_blender_series(entry)
            return
        if choice["replace"] is not None:
            self._start_blender_update(entry, build, choice["replace"])

    def mute_blender_series(self, entry) -> None:
        """No volver a ofrecer actualizar esta serie de Blender instalada.

        Se guarda la serie (mayor.menor) y se recalcula: desaparecen tanto el
        botón de parche de la tarjeta como el aviso de salto de serie. Se puede
        reactivar desde Ajustes.
        """
        series = minor_of(entry.version)
        if series and series not in self.settings.ignored_blender_series:
            self.settings.ignored_blender_series = [
                *self.settings.ignored_blender_series, series]
            self.settings.save()
        self._recompute_updates()
        self._rebuild_installed()
        self._update_blender_series_controls()
        self._show_message(
            tr("You will not be reminded about Blender {series} updates.",
               series=series), 8)

    def reset_blender_series(self) -> None:
        """Vuelve a avisar de las series de Blender silenciadas con "Nunca"."""
        if not self.settings.ignored_blender_series:
            return
        self.settings.ignored_blender_series = []
        self.settings.save()
        self._recompute_updates()
        self._rebuild_installed()
        self._update_blender_series_controls()

    def _start_blender_update(self, entry, build, replace: bool) -> None:
        """Descarga la build nueva; si ``replace``, borra la vieja al extraer."""
        if self.downloader.running:
            self._show_message(tr("A download is already in progress"), 4)
            return
        if installed_service.is_version_installed(self.installed, build.version):
            # Ya la tienes (quizá la bajaste antes como copia): no hay parche
            # que aplicar ni nada que reemplazar.
            self._show_message(tr("This version is already installed"), 4)
            return
        self._replace_entry = entry if replace else None
        self.install_build(build)

    def _offer_series_update(self) -> None:
        """Ofrece el salto de serie una vez por sesión y por serie."""
        for update in self.series_updates:
            key = update.build.favorite_key
            if key in self._series_offered:
                continue
            self._series_offered.add(key)
            self.offer_blender_update(update.entry, update.build)
            return

    def _on_download_error(self, message: str) -> None:
        self._set_downloading(False)
        self.progress.setValue(0)
        self.percent.setText("")
        # Si falló el "Reemplazar", la instalada vieja se queda como estaba.
        self._replace_entry = None
        if message == "cancelled":
            # Cancelar no es un fallo: el estado ya lo puso ``cancel_download``.
            self._set_status(tr("Cancelled"), 5)
            return
        # El motivo real, a la vista: antes solo se veía un "Fallo en la
        # descarga" genérico y no había forma de saber si era red, checksum o
        # permisos de la carpeta (justo el caso de las LTS en Windows).
        download_log(f"download failed: {message}")
        reason = tr("Checksum error") if message == "checksum" else message
        self._set_status(tr("Download failed"), 8)
        show_error(self, tr("Download failed"), reason)

    def launch_installed(self, entry, blend_file=None) -> bool:
        """Abre una versión instalada (Blender sigue vivo al cerrar el gestor).

        Es el **único** camino para lanzar Blender desde la interfaz: aplica
        los argumentos de Ajustes > Launch y la consola de esa versión. Con
        ``blend_file`` abre ese fichero (lo usa Recientes). Devuelve si
        arrancó.
        """
        executable = getattr(entry, "executable", None)
        if executable is None:
            return False
        try:
            args = shlex.split(self.launch_args or "")
            if blend_file is not None:
                args.append(str(blend_file))
            console = self._console_state(entry)
            if console and not launcher.terminal_available():
                self._set_status(tr("No terminal found; launching without "
                                    "console."), 6)
            self.launcher.launch(executable, args=args, console=console)
        except Exception as error:
            download_log(f"launch failed: {error}")
            self._set_status(tr("Could not launch Blender: {error}",
                                error=error), 8)
            return False
        return True

    def set_snapshot_keep(self, value: int) -> None:
        """Recuerda cuántas copias guardadas se conservan por versión."""
        self.settings.snapshot_keep = int(value)
        self.settings.save()

    def _console_state(self, entry) -> bool:
        """Si esa versión concreta se lanza con consola.

        El botón de cada tarjeta manda sobre esa versión; el ajuste de
        Ajustes > Launch es el valor por defecto de las que no tienen elección.
        """
        key = getattr(entry, "favorite_key", "") or str(
            getattr(entry, "path", ""))
        overrides = self.settings.launch_console_overrides
        return bool(overrides.get(key, self.settings.launch_console))

    def set_console_for(self, entry, value: bool) -> None:
        """Recuerda la consola de **esa** versión y repinta las tarjetas.

        No es un ajuste global: encenderlo en una tarjeta no toca las demás.
        """
        key = getattr(entry, "favorite_key", "") or str(
            getattr(entry, "path", ""))
        if not key:
            return
        self.settings.launch_console_overrides[key] = bool(value)
        self.settings.save()
        # Las dos listas enseñan el botón (la tienda, en las ya instaladas).
        self._rebuild_installed()
        self._rebuild_store()

    def _on_console_default_toggled(self, value: bool) -> None:
        """Cambió el valor por defecto (Ajustes > Launch)."""
        self.settings.launch_console = value
        self.settings.save()
        self._rebuild_installed()
        self._rebuild_installed()

    def _is_read_only(self, entry) -> bool:
        """True si esa instalación vive en una carpeta con el candado cerrado."""
        folder = self.settings.folder_for(getattr(entry, "root", None))
        return folder is not None and not folder.writable

    @staticmethod
    def _read_only_message() -> str:
        return (tr("This version is in a read-only folder.")
                + "\n\n"
                + tr("Open the lock in Settings > Folders, or use your file "
                     "manager."))

    def rename_installed(self, entry, new_name: str) -> None:
        """Renombra la carpeta de una instalación (doble clic en el nombre).

        Cambia la carpeta **real** en disco y vuelve a escanear. Si el nombre no
        vale o el disco no deja (en Windows, Blender abierto desde esa carpeta la
        bloquea), se avisa con el motivo y se deja el nombre viejo.
        """
        if self._is_read_only(entry):
            show_error(self, tr("Rename folder"), self._read_only_message())
            return
        reason = installed_service.rename_failure(entry.path, new_name)
        if reason:
            show_error(self, tr("Rename folder"), self._rename_error(reason))
            return
        try:
            installed_service.rename(entry.path, new_name, entry.version,
                                     entry.branch, entry.build_hash)
        except OSError as error:
            download_log(f"rename failed ({entry.path}): {error}")
            show_error(self, tr("Rename folder"), str(error))
            return
        self._show_message(tr("Renamed to {name}", name=new_name), 5)
        self.refresh_installed()

    @staticmethod
    def _rename_error(reason: str) -> str:
        """Traduce el código de ``installed.rename_failure`` a un texto."""
        return {
            "empty": tr("The name cannot be empty."),
            "invalid": tr('The name cannot contain \\ / : * ? " < > |.'),
            "same": tr("That is already the name."),
            "exists": tr("There is already a folder with that name."),
        }.get(reason, tr("The name is not valid."))

    def delete_installed(self, entry) -> None:
        """Borra una versión instalada, con confirmación.

        La confirmación dice **qué** se borra (con nombre y ruta) y el botón usa
        el verbo, no un "Aceptar" genérico. Ojo con dos cosas que se rompieron
        al portar desde Kivy: la ruta va convertida a texto (concatenar un
        ``Path`` a un ``str`` lanza ``TypeError``, y al saltar antes de crear el
        diálogo no se veía nada) y **nada de ``ignore_errors``**: si el borrado
        falla hay que decir por qué, no callarse.
        """
        if self._is_read_only(entry):
            # "Solo lectura" no admite excepciones: si se pudiera borrar pero
            # no instalar, el candado no significaría nada.
            show_error(self, tr("Uninstall"), self._read_only_message())
            return
        if not confirm(self, tr("Uninstall"),
                       tr("Delete {name}?", name=entry.name)
                       + "\n\n" + tr("This will remove the folder permanently.")
                       + "\n\n" + str(entry.path),
                       accept_text=tr("Uninstall"), danger=True):
            return
        try:
            shutil.rmtree(entry.path)
        except OSError as error:
            download_log(f"uninstall failed ({entry.path}): {error}")
            show_error(self, tr("Uninstall"), str(error))
            return
        self._show_message(tr("Deleted {name}", name=entry.name))
        self.refresh_installed()

    # ------------------------------------------------------------- updates
    def check_updates(self, manual: bool = False) -> None:
        # Modo fuente: lo que corre es el checkout y compararlo con una release
        # no dice nada (una rama de desarrollo va por delante del último tag).
        # Al arrancar no avisamos; si el usuario lo pide a mano, ofrecemos
        # ``git pull``, que es la actualización de verdad. Sin ``.git`` no hay
        # nada que actualizar: tampoco avisamos.
        """Comprueba si hay versión nueva, en un hilo aparte."""
        if not getattr(sys, "frozen", False) and not manual:
            return
        if self._update_checking:
            return
        self._update_checking = True

        def worker():
            tag, assets = updater.latest_release(force=manual) or ("", [])
            self.update_result.emit(tag, assets, manual)

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_result(self, tag: str, assets, manual: bool) -> None:
        self._update_checking = False
        if not getattr(sys, "frozen", False):
            if updater.source_root() is not None:
                # Checkout git: sin binario que reemplazar, git pull + reinicio.
                self._show_source_update(tag)
            elif manual and tag:
                # Sin git no hay nada que aplicar: al menos, la release abierta.
                self._show_message(
                    tr("A new version is available: {version}", version=tag), 8)
                updater.open_releases()
            return
        if not tag:
            # La comprobación falló (sin red, TLS, cuota de la API...). Decir
            # aquí "ya tienes la última versión" confunde: es justo lo que hizo
            # pensar que no había actualización cuando sí la había.
            if manual:
                self._show_message(tr("Update check failed"), 5)
            return
        asset_name = updater.asset_for(self.system)
        asset = next((a for a in assets if a["name"] == asset_name), None)
        if asset is None:
            if manual:
                self._show_message(tr("No update for this platform"), 5)
            return
        nueva = updater.is_newer(self.current_version, tag)
        # Queda en el log qué se comparó: si alguien dice "no me avisa", se ve
        # en un segundo si es que iba al día o si la comprobación no llegó.
        download_log(f"update check: instalada={self.current_version} "
                     f"ultima={tag} hay_nueva={nueva}")
        if nueva:
            self._update_assets = assets
            # El usuario puede haber pedido no volver a saber de esta versión:
            # los chequeos automáticos la callan (el manual la muestra igual).
            silenced = not manual and tag == self.settings.skipped_version
            # Un aviso por versión y sesión: el chequeo periódico comprueba a
            # menudo, pero no puede sacar el diálogo una y otra vez si le diste
            # a "Más tarde". Si sale una versión aún más nueva, sí se avisa.
            if not silenced and (manual or tag != self._offered_update_tag):
                self._offered_update_tag = tag
                self._show_update_available(tag, asset)
        elif manual:
            self._show_message(tr("You already have the latest version ({version}).",
                                 version=self.current_version), 6)

    def _show_source_update(self, tag: str) -> None:
        """Actualización de un checkout en modo fuente: ``git pull`` + reinicio."""
        if not tag:
            self._show_message(tr("Update check failed"), 5)
            return
        if not updater.is_newer(self.current_version, tag):
            self._show_message(tr("You already have the latest version ({version}).",
                                 version=self.current_version), 6)
            return
        message = (tr("A new version is available: {version}", version=tag)
                   + "\n\n"
                   + tr("Running from source: the app will run git pull and restart."))
        dialog = AppDialog(self, tr("Update available"), message)
        later = dialog.add_button(tr("Later"), on_click=dialog.reject,
                                  tooltip=tr("Ask me again another time."))
        update = dialog.add_button(
            tr("Update"), variant="accent",
            tooltip=tr("Run git pull and restart the app."))
        update.clicked.connect(lambda: self._do_source_update(dialog, update, later))
        dialog.exec()

    def _do_source_update(self, dialog, update_btn, later_btn) -> None:
        self._source_dialog = dialog
        update_btn.setEnabled(False)
        later_btn.setEnabled(False)
        dialog.body_label.setText(tr("Updating..."))

        def worker():
            ok, reason = updater.source_update()
            self.source_update_done.emit(ok, reason)

        threading.Thread(target=worker, daemon=True).start()

    def _on_source_update_done(self, ok: bool, reason: str) -> None:
        dialog = getattr(self, "_source_dialog", None)
        if not ok or reason == "up-to-date":
            if not ok and reason == "dirty":
                text = tr("You have local changes. Commit or stash them and try again.")
            elif not ok:
                text = tr("Could not update. Run git pull manually.")
            else:
                text = tr("You already have the latest version.")
            if dialog is not None:
                dialog.body_label.setText(text)
                for button in dialog.findChildren(QPushButton):
                    button.setEnabled(True)
            return
        if dialog is not None:
            dialog.body_label.setText(tr("Restarting..."))
        self._set_status(tr("Restarting..."))
        # El diálogo es modal: hay que cerrarlo para que ``exec()`` devuelva y
        # el cierre de la ventana llegue a terminar el bucle de eventos.
        QTimer.singleShot(800, self, self._restart_from_source)

    def _restart_from_source(self) -> None:
        dialog = getattr(self, "_source_dialog", None)
        if not updater.relaunch_source():
            if dialog is not None:
                dialog.body_label.setText(tr("Update downloaded. Restart the app."))
                for button in dialog.findChildren(QPushButton):
                    button.setEnabled(True)
            return
        if dialog is not None:
            dialog.accept()
        # Reiniciar es salir de verdad: no puede quedarse en la bandeja.
        self._force_quit = True
        self.close()

    def _show_update_available(self, tag: str, asset) -> None:
        update_available(self, tag, lambda: self._do_update(asset),
                         on_skip=lambda: self.skip_update_version(tag))

    def skip_update_version(self, tag: str) -> None:
        """No volver a avisar de esta versión en los chequeos automáticos.

        El chequeo manual ("Buscar ahora") la muestra igual, y una versión más
        nueva sí se ofrece: se guarda el tag exacto.
        """
        self.settings.skipped_version = tag
        self.settings.save()
        self._show_message(
            tr("You will not be reminded about {version}.", version=tag), 8)

    def _do_update(self, asset) -> None:
        self._set_status(tr("Downloading..."))
        self._set_downloading(True)
        bridge = _Bridge()
        bridge.progress.connect(self._set_progress)
        bridge.done.connect(self._apply_update)
        # El error de la actualización no es el de una descarga de Blender: aquí
        # hay que ofrecer la salida manual, no un "Download failed" a secas.
        bridge.error.connect(self._on_update_download_error)
        self._bridge = bridge
        self.update_downloader.start(
            asset["url"], str(updater.updates_dir()), asset["name"],
            on_progress=lambda done, total: bridge.progress.emit(done, total),
            on_done=lambda path: bridge.done.emit(str(path)),
            on_error=lambda msg: bridge.error.emit(msg),
        )

    def _on_update_download_error(self, message: str) -> None:
        """No se pudo bajar la actualización: ofrecer instalarla a mano.

        Un "Download failed" genérico deja al usuario sin salida. En macOS hay
        que sustituir el ``.app`` a mano de todos modos, y si lo que falla es el
        CDN de GitHub (handshake TLS, red que lo bloquea...) el navegador sigue
        siendo una vía. En vez de rendirnos, abrimos la página de releases.
        """
        self._set_downloading(False)
        self.progress.setValue(0)
        self.percent.setText("")
        if message == "cancelled":
            self._set_status(tr("Cancelled"), 5)
            return
        download_log(f"update download failed: {message}")
        self._set_status(tr("Download failed"), 8)
        dialog = AppDialog(
            self, tr("Download failed"),
            tr("Could not download the update automatically:")
            + "\n\n" + message + "\n\n"
            + tr("You can download it from the releases page and install it manually."))
        dialog.add_button(tr("Close"), on_click=dialog.reject)
        dialog.add_button(
            tr("Open the releases page"), variant="accent",
            on_click=lambda: (dialog.accept(), updater.open_releases()))
        dialog.exec()

    def _apply_update(self, path: str) -> None:
        self._set_downloading(False)

        def worker():
            quit_app = updater.apply(path)
            if quit_app:
                self.update_applied.emit(path)
            else:
                # macOS (y cualquier caso en el que no haya reemplazo en
                # caliente): ``apply`` ya reveló el fichero; solo falta decirlo.
                self.update_manual.emit()

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_manual(self) -> None:
        self._show_message(tr("Update downloaded. Install it manually."), 8)

    def _on_update_applied(self, path: str) -> None:
        self._set_status(tr("Restarting to install the update..."))
        # Salida de verdad: no puede acabar escondida en la bandeja.
        QTimer.singleShot(1000, self, self._quit_app)
