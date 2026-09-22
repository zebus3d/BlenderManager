"""La ventana principal: su cáscara y las listas de versiones.

Aquí viven la cabecera, la barra lateral, la fila de filtros, el pie, la
navegación entre vistas y las dos listas (Nube y Local) con su rejilla y su
zoom. Lo demás está repartido por responsabilidad en módulos vecinos, que se
montan como **mixins** de esta clase:

* ``settings_view.py`` — la pantalla de Ajustes y sus controles.
* ``folder_library.py`` — la biblioteca de carpetas (dónde vive cada versión).
* ``downloads.py`` — descargar, instalar, lanzar y borrar versiones de Blender.
* ``updates.py`` — actualizar BlenderManager.
* ``shell.py`` — las tablas y los widgets que comparten todos.

Son mixins y no objetos independientes porque todos trabajan sobre el estado
de **esta misma ventana** (``self.settings``, el estado, las listas): meterlos
en otro objeto solo movería el acoplo de sitio. Lo que se gana es que cada
fichero se pueda leer entero; lo que de verdad no depende de la interfaz ya
está en ``services/``.
"""

import threading

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

import i18n
from i18n import tr
from model.build import minor_of
from services import api, detector, opener, updater
from services import installed as installed_service
from services import settings as settings_service
from services.downloader import Downloader, log as download_log
from services.launcher import Launcher
from ui import icons
from ui import theme as t
from ui.fonts import icon_font
from ui.widgets.addons import AddonsView
from ui.widgets.buttons import CardButton, IconFlatButton, Pill, SideButton
from ui.widgets.cards import (BuildCard, GridBuildCard, GridInstalledCard,
                              InstalledCard, card_shadow, logo_shadow)
from ui.widgets.downloads import DownloadFlowMixin
from ui.widgets.folder_library import FolderLibraryMixin
from ui.widgets.layouts import clear_layout
from ui.widgets.menus import card_menu
from ui.widgets.migrate import MigrateView
from ui.widgets.recent import RecentView
from ui.widgets.settings_view import SettingsViewMixin
from ui.widgets.shell import (ARCH_LABELS, CHANNEL_TOOLTIPS, CHANNELS,
                              LANGUAGE_IDS,
                              DEFAULT_WINDOW_HEIGHT, DEFAULT_WINDOW_WIDTH,
                              EXPERIMENTAL_VIEWS, FILTER_CONTROL_HEIGHT,
                              FILTERS_HEIGHT, MAX_ZOOM, MIN_WINDOW_HEIGHT,
                              MIN_WINDOW_WIDTH, MIN_ZOOM, PLATFORM_LABELS,
                              PLATFORMS, SECTION_TITLES, ZOOM_STEP, ZoomSlider)
from ui.widgets.tray import TrayIcon
from ui.widgets.updates import UpdateFlowMixin

class MainWindow(SettingsViewMixin, FolderLibraryMixin, DownloadFlowMixin,
                 UpdateFlowMixin, QWidget):
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
        self.installed = installed_service.scan_folders(self.settings.library_roots(),
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
            "Show only one kind of version at a time.\n"
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
        self.grid_btn = Pill(icons.GRID, tr("Show the versions as a grid of icons."))
        self.grid_btn.setFont(icon_font(14))
        self.list_btn = Pill(icons.LIST, tr("Show the versions as a list of rows."))
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
            "System the version is for.\n"
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
            "Processor type the version is for.\n"
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
                "Show the versions you can download from the cloud.")),
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
        self.zoom_slider = ZoomSlider(Qt.Horizontal)
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
                text = tr("No versions found")
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
        launch.setToolTip(tr("Launch this installed version"))
        launch.triggered.connect(lambda: self.launch_installed(entry))
        if self.settings.experimental_features:
            console = menu.addAction(tr("Launch with console"))
            console.setToolTip(tr("Launch this version with the console visible: Python "
                            "output and script errors."))
            console.triggered.connect(lambda: self._launch_with_console(entry))
        menu.addSeparator()
        open_folder = menu.addAction(tr("Open folder"))
        open_folder.setToolTip(tr("Open the folder where this version is installed."))
        open_folder.triggered.connect(lambda: opener.open_path(entry.path))
        copy = menu.addAction(tr("Copy path"))
        copy.setToolTip(tr("Copy the path of this version to the clipboard."))
        copy.triggered.connect(
            lambda: QApplication.clipboard().setText(str(entry.path)))
        menu.addSeparator()
        remove = menu.addAction(tr("Uninstall"))
        remove.setToolTip(tr("Remove this installed version"))
        remove.triggered.connect(lambda: self.delete_installed(entry))
        return menu

    def _show_installed_menu(self, entry, card, pos) -> None:
        self._installed_menu(entry).exec(card.mapToGlobal(pos))


    def _store_menu(self, build) -> QMenu:
        """Menú contextual de una tarjeta de la tienda (sin mostrarlo)."""
        menu = card_menu(self)
        install = menu.addAction(tr("Download and install"))
        install.setToolTip(tr("Download and install this version"))
        install.triggered.connect(lambda: self.install_build(build))
        notes = menu.addAction(tr("Release notes"))
        notes.setToolTip(tr("Read the release notes for this version"))
        notes.triggered.connect(lambda: self.open_release_notes(build.version))
        menu.addSeparator()
        copy = menu.addAction(tr("Copy download link"))
        copy.setToolTip(tr("Copy the download link to the clipboard."))
        copy.triggered.connect(
            lambda: QApplication.clipboard().setText(build.url))
        return menu

    def _show_store_menu(self, build, card, pos) -> None:
        self._store_menu(build).exec(card.mapToGlobal(pos))

    def refresh_installed(self) -> None:
        """Vuelve a escanear las carpetas y repinta las instaladas."""
        self.installed = installed_service.scan_folders(self.settings.library_roots(),
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














































    def set_snapshot_keep(self, value: int) -> None:
        """Recuerda cuántas copias guardadas se conservan por versión."""
        self.settings.snapshot_keep = int(value)
        self.settings.save()





















