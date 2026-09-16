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
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QStyle,
    QStyleOptionSlider,
    QVBoxLayout,
    QWidget,
)

import i18n
import version
from i18n import tr
from services import (
    api,
    detector,
    installed as installed_service,
    opener,
    settings as settings_service,
    sources,
    updater,
)
from services.downloader import Downloader, log as download_log
from services.extractor import extract, is_archive
from services.launcher import Launcher
from ui import icons
from ui import theme as t
from ui.fonts import icon_font
from ui.widgets.buttons import CardButton, IconFlatButton, Pill, SideButton, SwitchPill
from ui.widgets.cards import (
    BuildCard,
    GridBuildCard,
    GridInstalledCard,
    InstalledCard,
    card_shadow,
    logo_shadow,
)
from ui.widgets.dialogs import AppDialog, confirm, show_error, update_available

PLATFORMS = {"GNU/Linux": "linux", "Windows": "windows", "macOS": "darwin"}
PLATFORM_LABELS = {value: key for key, value in PLATFORMS.items()}
ARCH_LABELS = ["x86_64", "arm64"]
LANGUAGE_IDS = {"auto": "Automatic", "en": "English", "es": "Spanish"}
MIN_ZOOM, MAX_ZOOM = 0.6, 1.8
# Cuánto sube/baja el zoom con Ctrl +/-. El slider va en pasos de 1 %.
ZOOM_STEP = 0.1


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
    update_result = Signal(str, object, bool)
    update_applied = Signal(str)
    source_chosen = Signal(object, object)   # build, Source
    source_update_done = Signal(bool, str)
    release_notes_result = Signal(bool)   # abierta o no

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{tr('Blender Downloads Manager')} {updater.app_version()}")
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
        self.dest_folder = self.settings.dest_folder
        self.launch_args = self.settings.launch_args
        self.delete_archive = bool(self.settings.delete_archive)
        self.auto_update = bool(self.settings.auto_update)
        self.layout_mode = (self.settings.layout_mode
                            if self.settings.layout_mode in ("grid", "list") else "grid")
        try:
            self.zoom = min(MAX_ZOOM, max(MIN_ZOOM, float(self.settings.zoom)))
        except (TypeError, ValueError):
            self.zoom = settings_service.DEFAULT_ZOOM

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
        self.installed = installed_service.scan(self.settings.dest_folder, self.platform)
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

        # Conectamos las señales de los hilos ANTES de montar la UI.
        self.builds_loaded.connect(self._on_builds_loaded)
        self.download_done.connect(self._on_download_done)
        self.download_error.connect(self._on_download_error)
        self.extract_done.connect(self._on_extract_done)
        self.update_result.connect(self._on_update_result)
        self.update_applied.connect(self._on_update_applied)
        self.source_update_done.connect(self._on_source_update_done)
        self.release_notes_result.connect(self._on_release_notes_result)
        self.source_chosen.connect(self._start_download)

        self._build_ui()
        QTimer.singleShot(100, lambda: self.refresh(force=False))

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        self.filters = self._build_filters()
        root.addWidget(self.filters)

        body = QHBoxLayout()
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_store_view())
        self.stack.addWidget(self._build_installed_view())
        self.stack.addWidget(self._build_settings_view())
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)

        root.addWidget(self._build_footer())
        self._set_view(self.view, animate=False)
        # La vista de instaladas no se rellena sola: hay que poblarla al arrancar
        # (si no, al abrir en esa pestaña se vería vacía hasta el primer refresco).
        self._rebuild_installed()
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
        self.title_label = QLabel(tr("Blender Downloads Manager"))
        self.title_label.setObjectName("HeaderTitle")
        lay.addWidget(logo)
        lay.addWidget(self.title_label)
        lay.addStretch()

        self.header_tools = QWidget()
        self.header_tools.setObjectName("HeaderTools")  # fondo transparente (QSS)
        # Sin esto el bloque se estira y reparte el hueco que sobra: a 1500 px de
        # ancho llegaban a verse ~97 px entre el botón de refrescar y el
        # buscador. Es el mismo caso que el zoom del pie.
        self.header_tools.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        tools = QHBoxLayout(self.header_tools)
        tools.setContentsMargins(0, 0, 0, 0)
        tools.setSpacing(10)
        refresh = IconFlatButton(icons.REFRESH, tr("Refresh the list of builds"))
        refresh.setFont(icon_font(16))
        refresh.clicked.connect(lambda: self.refresh(force=True))
        tools.addWidget(refresh)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("SearchField")
        self.search_input.setPlaceholderText(tr("Search..."))
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
        bar.setFixedHeight(44)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 6, 16, 6)
        lay.setSpacing(6)

        self.channel_group = QButtonGroup(bar)
        self.channel_group.setExclusive(True)
        self._channel_buttons = {}
        for key, label in (("all", "All"), ("lts", "LTS"), ("stable", "Stable"),
                           ("daily", "Daily"), ("experimental", "Experimental"),
                           ("favorites", "Favorites")):
            btn = Pill(tr(label), tr(f"Filter: {label.lower()}"))
            self.channel_group.addButton(btn)
            btn.clicked.connect(lambda _=False, k=key: self.set_channel(k))
            lay.addWidget(btn)
            self._channel_buttons[key] = btn
        # Marcamos el filtro con el que se arranca, que es el que se guardó.
        self._channel_buttons.get(self.channel,
                                  self._channel_buttons["all"]).setChecked(True)
        lay.addStretch()

        self.layout_group = QButtonGroup(bar)
        self.layout_group.setExclusive(True)
        self.grid_btn = Pill(icons.GRID, tr("Grid view"))
        self.grid_btn.setFont(icon_font(14))
        self.list_btn = Pill(icons.LIST, tr("List view"))
        self.list_btn.setFont(icon_font(14))
        for btn, mode in ((self.grid_btn, "grid"), (self.list_btn, "list")):
            self.layout_group.addButton(btn)
            btn.clicked.connect(lambda _=False, m=mode: self.set_layout_mode(m))
            lay.addWidget(btn)
        (self.grid_btn if self.layout_mode == "grid" else self.list_btn).setChecked(True)

        self.platform_combo = QComboBox()
        self.platform_combo.addItems(list(PLATFORMS.keys()))
        self.platform_combo.setCurrentText(self.platform_label)
        self.platform_combo.setFixedWidth(104)
        self.platform_combo.setToolTip(tr("Target operating system"))
        self.platform_combo.currentTextChanged.connect(self.set_platform)
        lay.addWidget(self.platform_combo)

        self.arch_combo = QComboBox()
        self.arch_combo.addItems(ARCH_LABELS)
        self.arch_combo.setCurrentText(self.arch_label)
        self.arch_combo.setFixedWidth(82)
        self.arch_combo.setToolTip(tr("Target architecture"))
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
            ("installed", icons.INSTALLED, tr("Show installed versions")),
            ("store", icons.STORE, tr("Show the store")),
        ):
            btn = SideButton(glyph, tip)
            btn.setFont(icon_font(20))
            self.side_group.addButton(btn)
            btn.clicked.connect(lambda _=False, k=key: self.set_view(k))
            lay.addWidget(btn)
            self.side_buttons[key] = btn
        lay.addStretch()
        settings_btn = SideButton(icons.SETTINGS, tr("Open settings"))
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

    def _build_store_view(self):
        self.store_scroll, self.store_grid = self._new_list_view()
        return self.store_scroll

    def _build_installed_view(self):
        self.installed_scroll, self.installed_grid = self._new_list_view()
        return self.installed_scroll

    def _build_settings_view(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)

        header = QHBoxLayout()
        header.addWidget(QLabel(tr("Settings")))
        header.addStretch()
        outer.addLayout(header)

        columns = QHBoxLayout()
        columns.setSpacing(16)
        columns.addWidget(self._settings_general_card(), 1)
        columns.addWidget(self._settings_launch_card(), 1)
        outer.addLayout(columns)
        outer.addStretch()
        return page

    def _settings_card(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("SettingsCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)
        label = QLabel(title)
        label.setObjectName("Muted")
        lay.addWidget(label)
        return card, lay

    def _settings_general_card(self) -> QFrame:
        card, lay = self._settings_card(tr("General"))
        lay.addWidget(QLabel(tr("Destination folder")))
        row = QHBoxLayout()
        self.dest_input = QLineEdit(self.dest_folder)
        self.dest_input.textChanged.connect(self._on_dest_changed)
        row.addWidget(self.dest_input, 1)
        browse = CardButton(tr("Browse..."), tooltip=tr("Choose destination folder"))
        browse.clicked.connect(self.browse_dest)
        row.addWidget(browse)
        lay.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel(tr("Delete archive after extraction")))
        row2.addStretch()
        self.archive_switch = SwitchPill(self.delete_archive, tr("Yes"), tr("No"))
        self.archive_switch.toggled.connect(self._on_archive_toggled)
        row2.addWidget(self.archive_switch)
        lay.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel(tr("Language")))
        row3.addStretch()
        self.language_combo = QComboBox()
        self.language_combo.addItems([tr(v) for v in LANGUAGE_IDS.values()])
        self.language_combo.setCurrentText(self.language_label)
        self.language_combo.currentTextChanged.connect(self._on_language_changed)
        row3.addWidget(self.language_combo)
        lay.addLayout(row3)
        return card

    def _settings_launch_card(self) -> QFrame:
        card, lay = self._settings_card(tr("Launch options"))
        lay.addWidget(QLabel(tr("Launch arguments")))
        self.args_input = QLineEdit(self.launch_args)
        self.args_input.setPlaceholderText("--background --python script.py")
        self.args_input.textChanged.connect(self._on_args_changed)
        lay.addWidget(self.args_input)

        sep = QFrame()
        sep.setObjectName("RowSeparator")
        sep.setFixedHeight(1)
        lay.addWidget(sep)

        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Check for updates automatically")))
        row.addStretch()
        self.update_switch = SwitchPill(self.auto_update, tr("Yes"), tr("No"))
        self.update_switch.toggled.connect(self.set_auto_update)
        row.addWidget(self.update_switch)
        lay.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel(tr("Version {version}", version=self.current_version)))
        row2.addStretch()
        check = CardButton(tr("Check now"), tooltip=tr("Check for updates now"))
        check.clicked.connect(lambda: self.check_updates(manual=True))
        row2.addWidget(check)
        lay.addLayout(row2)
        return card

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
        # Solo se muestra mientras hay una descarga en curso.
        self.progress.setVisible(False)
        progress_lay.addWidget(self.progress, 1)
        self.percent = QLabel("")
        self.percent.setVisible(False)
        progress_lay.addWidget(self.percent)
        self.cancel_btn = CardButton(tr("Cancel"))
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
        self.zoom_slider.setToolTip(tr("Zoom the icon size (Ctrl +/- / Ctrl+0)"))
        zoom_lay.addWidget(self.zoom_slider)
        self.zoom_label = QLabel()
        self.zoom_label.setObjectName("Muted")
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
        """Arquitectura tal y como la espera la API de Blender.

        En Linux/macOS la API usa ``x86_64``; solo Windows la llama ``amd64``.
        """
        if self.platform == "windows" and self.arch_label == "x86_64":
            return "amd64"
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
        self._rebuild_store()
        self._rebuild_installed()

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

    def _set_view(self, view: str, animate: bool = True) -> None:
        index = {"store": 0, "installed": 1, "settings": 2}.get(view, 0)
        self.stack.setCurrentIndex(index)
        for key, btn in self.side_buttons.items():
            btn.setChecked(key == view)
        show_filters = view != "settings"
        self.filters.setVisible(show_filters)
        self.header_tools.setVisible(show_filters)
        self.zoom_box.setVisible(view != "settings" and self.layout_mode == "grid")

    def set_layout_mode(self, mode: str) -> None:
        """Cambia entre rejilla y lista y recuerda la elección."""
        self.layout_mode = mode
        self.zoom_box.setVisible(self.view != "settings" and mode == "grid")
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
        self._rebuild_store()
        self._rebuild_installed()

    def _commit_zoom(self) -> None:
        """El slider lleva quieto: paramos y guardamos el ajuste una sola vez."""
        self._zoom_tick.stop()
        self._rebuild_zoom_views()
        self.settings.zoom = self.zoom
        self.settings.save()

    def _zoom_enabled(self) -> bool:
        """El zoom solo pinta algo en rejilla y fuera de los ajustes."""
        return self.view != "settings" and self.layout_mode == "grid"

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
        """Vuelve al zoom por defecto (Ctrl+0 o Ctrl+clic en el slider)."""
        if self._zoom_enabled():
            self._set_zoom_value(settings_service.DEFAULT_ZOOM)

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

    def closeEvent(self, event):
        """Vuelca el zoom pendiente: si se cierra mientras el slider se mueve,
        el guardado (que va con retardo) aún no ha corrido."""
        self._zoom_settle.stop()
        self._zoom_tick.stop()
        if self.zoom != self.settings.zoom:
            self.settings.zoom = self.zoom
            self.settings.save()
        super().closeEvent(event)

    def _reflow(self) -> None:
        if self.layout_mode == "grid":
            self._rebuild_store()
            self._rebuild_installed()

    def _clear_grid(self, grid: QGridLayout) -> None:
        while grid.count():
            item = grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # Sacarla del layout NO la oculta: sigue dibujándose en su
                # posición vieja hasta que el bucle procese el deleteLater, así
                # que durante un frame se veían las tarjetas viejas encima de
                # las nuevas. setParent(None) la desliga y desaparece ya.
                widget.setParent(None)
                widget.deleteLater()

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
        self._clear_grid(grid)
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
        self._clear_grid(self.store_grid)
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
            installed = any(e.version == build.version for e in self.installed)
            # La cebra es para la lista (filas contiguas); en rejilla las
            # tarjetas van sueltas sobre el fondo y alternar el gris solo
            # ensucia el conjunto.
            zebra = (not grid) and bool(index % 2)
            marked = build.favorite_key in self.settings.favorites
            if grid:
                card = GridBuildCard(build, installed, zebra, self.zoom, marked)
            else:
                card = BuildCard(build, installed, zebra, marked)
            card.action_clicked.connect(self.install_build)
            card.notes_clicked.connect(self.open_release_notes)
            card.favorite_toggled.connect(self.set_favorite)
            cards.append(card)
        self._fill_grid(self.store_grid, cards, columns)

    def refresh_installed(self) -> None:
        """Vuelve a escanear la carpeta y repinta las instaladas."""
        self.installed = installed_service.scan(self.settings.dest_folder, self.platform)
        self._recompute_updates()
        self._rebuild_installed()

    def _recompute_updates(self) -> None:
        """Recalcula qué instaladas tienen parche o serie nueva disponible.

        Las builds se filtran por plataforma/arquitectura (``available_for``)
        para no ofrecer un parche que no es para este sistema. Se guardan por
        ruta para que las tarjetas lo consulten al construirse.
        """
        builds = api.available_for(self.builds, self.platform, self.arch)
        updates = installed_service.available_updates(self.installed, builds)
        self.updates_by_path = {
            str(u.entry.path): u.build for u in updates if u.kind == "patch"}
        self.series_updates = [
            u for u in updates if u.kind == "series"]

    def _rebuild_installed(self) -> None:
        self._clear_grid(self.installed_grid)
        entries = self._filtered_installed()
        columns = self._grid_columns(self.installed_scroll, self.installed_grid, 0)
        if not entries:
            if self.channel == "favorites":
                text = tr("No favorites yet")
                hint = tr("Tap the star on a card to keep it here.")
            else:
                text = tr("No installed versions found")
                hint = tr("Download one from the store to see it here.")
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
            if grid:
                card = GridInstalledCard(entry, zebra, self.zoom, marked,
                                         update=update)
            else:
                card = InstalledCard(entry, zebra, marked, update=update)
            card.launch_clicked.connect(self.launch_installed)
            card.delete_clicked.connect(self.delete_installed)
            card.notes_clicked.connect(self.open_release_notes)
            card.favorite_toggled.connect(self.set_favorite)
            card.update_clicked.connect(self.offer_blender_update)
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
        QTimer.singleShot(250, self._reflow)
        if self.updates_by_path:
            self._show_message(
                tr("{count} Blender updates available",
                   count=len(self.updates_by_path)), 6)
        else:
            self._set_status(tr("Ready"), 2)
        # El salto de serie (5.2 -> 5.3) se ofrece aparte, en un diálogo.
        QTimer.singleShot(400, self._offer_series_update)
        if not self._auto_checked:
            self._auto_checked = True
            if self.auto_update:
                QTimer.singleShot(2000, lambda: self.check_updates(manual=False))

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

    def browse_dest(self) -> None:
        """Pide la carpeta de descargas con el diálogo del sistema."""
        folder = QFileDialog.getExistingDirectory(self, tr("Choose destination folder"),
                                                  self.dest_folder or str(Path.home()))
        if folder:
            self.dest_input.setText(folder)

    # ------------------------------------------------------- auto-guardado
    def _on_dest_changed(self, text: str) -> None:
        self.dest_folder = text
        self.settings.dest_folder = text
        self.settings.save()
        self.refresh_installed()

    def _on_archive_toggled(self, value: bool) -> None:
        self.delete_archive = value
        self.settings.delete_archive = value
        self.settings.save()

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

    def set_auto_update(self, active: bool) -> None:
        """Guarda si hay que buscar actualizaciones al arrancar."""
        self.auto_update = active
        self.settings.auto_update = active
        self.settings.save()

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
        self._set_status(tr("Downloading..."))
        download_log(f"downloading {build.filename} from {source.label}")
        self._bridge = _Bridge()
        self._bridge.progress.connect(self._set_progress)
        self._bridge.done.connect(lambda path: self._on_download_done(path, build))
        self._bridge.error.connect(self._on_download_error)
        self.downloader.start(
            source.url, str(Path(self.settings.dest_folder).expanduser()),
            build.filename, source.checksum,
            on_progress=lambda done, total: self._bridge.progress.emit(done, total),
            on_done=lambda path: self._bridge.done.emit(str(path)),
            on_error=lambda msg: self._bridge.error.emit(msg),
        )

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
        self._set_status(tr("Extracting..."))
        self._set_downloading(True)

        def worker():
            try:
                target = extract(path, Path(self.settings.dest_folder).expanduser())
                # Borrar el archivo comprimido solo si el usuario lo pidió.
                if self.delete_archive:
                    try:
                        Path(path).unlink()
                    except OSError:
                        pass
            except Exception as error:
                download_log(f"extract failed: {error}")
                self.download_error.emit(str(error))
                return
            self.extract_done.emit(str(target))

        threading.Thread(target=worker, daemon=True).start()

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
        los dos casos la decisión es la misma.
        """
        message = (
            tr("You have Blender {current} installed. Blender {new} is available.",
               current=entry.version, new=build.version)
            + "\n\n"
            + tr("Replace the installed version or download the new one as a copy?")
        )
        dialog = AppDialog(self, tr("Update available"), message)
        choice = {"replace": None}
        dialog.add_button(tr("Later"), on_click=dialog.reject)
        dialog.add_button(
            tr("Download as copy"),
            on_click=lambda: (choice.update(replace=False), dialog.accept()))
        dialog.add_button(
            tr("Replace"), variant="accent",
            on_click=lambda: (choice.update(replace=True), dialog.accept()))
        dialog.exec()
        if choice["replace"] is not None:
            self._start_blender_update(entry, build, choice["replace"])

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
        self._set_status(tr("Download failed"), 5)

    def launch_installed(self, entry) -> None:
        """Abre una versión instalada (Blender sigue vivo al
        cerrar el gestor).
        """
        try:
            args = shlex.split(self.launch_args or "")
            executable = getattr(entry, "executable", None)
            if executable is None:
                return
            self.launcher.launch(executable, args=args)
        except Exception as error:
            download_log(f"launch failed: {error}")

    def delete_installed(self, entry) -> None:
        """Borra una versión instalada, con confirmación.

        La confirmación dice **qué** se borra (con nombre y ruta) y el botón usa
        el verbo, no un "Aceptar" genérico. Ojo con dos cosas que se rompieron
        al portar desde Kivy: la ruta va convertida a texto (concatenar un
        ``Path`` a un ``str`` lanza ``TypeError``, y al saltar antes de crear el
        diálogo no se veía nada) y **nada de ``ignore_errors``**: si el borrado
        falla hay que decir por qué, no callarse.
        """
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
        later = dialog.add_button(tr("Later"), on_click=dialog.reject)
        update = dialog.add_button(tr("Update"), variant="accent")
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
        QTimer.singleShot(800, self._restart_from_source)

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
        self.close()

    def _show_update_available(self, tag: str, asset) -> None:
        update_available(self, tag, lambda: self._do_update(asset))

    def _do_update(self, asset) -> None:
        self._set_status(tr("Downloading..."))
        self._set_downloading(True)
        bridge = _Bridge()
        bridge.progress.connect(self._set_progress)
        bridge.done.connect(self._apply_update)
        bridge.error.connect(self._on_download_error)
        self._bridge = bridge
        self.update_downloader.start(
            asset["url"], str(updater.updates_dir()), asset["name"],
            on_progress=lambda done, total: bridge.progress.emit(done, total),
            on_done=lambda path: bridge.done.emit(str(path)),
            on_error=lambda msg: bridge.error.emit(msg),
        )

    def _apply_update(self, path: str) -> None:
        self._set_downloading(False)

        def worker():
            quit_app = updater.apply(path)
            if quit_app:
                self.update_applied.emit(path)

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_applied(self, path: str) -> None:
        self._set_status(tr("Restarting to install the update..."))
        QTimer.singleShot(1000, self.close)
