"""Controlador principal de la pantalla (``RootWidget``).

Aquí vive toda la lógica de la interfaz: carga de ajustes, listado de
compilaciones de Blender, filtros, descarga/extracción en segundo plano,
lanzamiento de versiones instaladas y la navegación entre vistas.

Ojo: Kivy aplica las reglas del archivo .kv durante el ``__init__`` del widget,
antes de que se ejecute el cuerpo de nuestro constructor. Por eso los datos que
consume la vista (carpeta destino, idioma, etc.) se exponen como propiedades
Kivy con valores por defecto y se rellenan después de ``super().__init__``.
"""

import os
import shlex
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import (
    AliasProperty,
    BooleanProperty,
    ListProperty,
    NumericProperty,
    StringProperty,
)
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import NoTransition, SlideTransition
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget

import i18n
import version
from i18n import tr
from services import (
    api,
    detector,
    installed as installed_service,
    settings as settings_service,
    updater,
)
from services.downloader import Downloader, log as download_log
from services.extractor import extract, is_archive
from services.launcher import Launcher
from ui import icons
from ui import theme as theme_module
from ui.theme import (
    ACCENT,
    ACCENT_DARK,
    CARD_DIM,
    CARD_DIM_ALT,
    DANGER,
    DANGER_DARK,
    ICON_FONT,
    MUTED,
    ROW_ALT,
    SURFACE,
)
from ui.widgets.basic import CardButton, FolderRow
from ui.widgets.cards import BuildCard, GridBuildCard, GridInstalledCard, InstalledCard
from ui.widgets.dialogs import AppModalView, AppPopup, AppProgressBar

# Etiquetas visibles del selector de sistema operativo -> identificador interno
# que usan tanto la API de Blender como el escáner de versiones instaladas.
PLATFORMS = {"GNU/Linux": "linux", "Windows": "windows", "macOS": "darwin"}
PLATFORM_LABELS = {value: key for key, value in PLATFORMS.items()}
ARCH_LABELS = ["x86_64", "arm64"]
LANGUAGE_IDS = {"auto": "Automatic", "en": "English", "es": "Spanish"}

# Límites de la barra de zoom (la misma que usa Dolphin para el tamaño de iconos).
MIN_ZOOM = 0.6
MAX_ZOOM = 1.8


class RootWidget(BoxLayout):
    """Pantalla principal: cabecera, filtros, listas y pie con progreso/zoom."""

    # Al cambiar el idioma se reconstruye la pantalla entera (``_reload_ui``);
    # sin esta marca de clase, cada reconstrucción volvería a buscar
    # actualizaciones y podría reabrir el diálogo encima del trabajo del usuario.
    _auto_checked = False

    # Propiedades reactivas que la vista .kv observa para redibujarse.
    view = StringProperty("store")
    channel = StringProperty("all")
    search = StringProperty("")
    layout_mode = StringProperty("grid")
    zoom = NumericProperty(1.0)
    platform_label = StringProperty("GNU/Linux")
    arch_label = StringProperty("x86_64")
    platform_labels = ListProperty(list(PLATFORMS.keys()))
    arch_labels = ListProperty(list(ARCH_LABELS))
    status_text = StringProperty("")
    language_label = StringProperty("")
    dest_folder = StringProperty("")
    launch_args = StringProperty("")
    delete_archive = BooleanProperty(True)
    busy = BooleanProperty(False)
    downloading = BooleanProperty(False)
    progress = NumericProperty(0)
    builds = ListProperty([])
    has_builds = BooleanProperty(False)
    has_installed = BooleanProperty(False)
    auto_update = BooleanProperty(True)
    current_version = StringProperty(version.__version__)

    def _get_show_filters(self):
        """Los filtros solo tienen sentido fuera de la pantalla de ajustes."""
        return self.view != "settings"

    # Controla la visibilidad de la búsqueda, el refresco y la barra de filtros.
    show_filters = AliasProperty(_get_show_filters, bind=("view",))

    def _get_show_zoom(self):
        """La barra de zoom (tamaño de icono) solo aplica en rejilla y sin ajustes."""
        return self.view != "settings" and self.layout_mode == "grid"

    show_zoom = AliasProperty(_get_show_zoom, bind=("view", "layout_mode"))

    def __init__(self, **kwargs):
        # Al llamar a super() se aplican ya las reglas del .kv, así que las
        # propiedades de arriba deben tener valores por defecto válidos.
        super().__init__(**kwargs)
        self.settings = settings_service.Settings.load()
        i18n.set_language(self.settings.language)
        self.system = detector.detect()
        # En modo fuente version.py vale 0.0.0: mostramos el último tag del repo.
        self.current_version = updater.app_version()
        # Plataforma y arquitectura de destino: por defecto las del equipo, pero
        # recordamos la última que eligió el usuario en la barra de filtros (así
        # no hay que volver a seleccionarla para bajar builds de otra plataforma).
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
        self.delete_archive = self.settings.delete_archive
        self.auto_update = bool(self.settings.auto_update)
        self.layout_mode = self.settings.layout_mode if self.settings.layout_mode in ("grid", "list") else "grid"
        try:
            self.zoom = min(MAX_ZOOM, max(MIN_ZOOM, float(self.settings.zoom)))
        except (TypeError, ValueError):
            self.zoom = 1.0
        self.downloader = Downloader()
        self.update_downloader = Downloader()
        self._update_assets = []
        self.launcher = Launcher()
        # Escaneo inicial: si ya hay versiones instaladas abrimos esa pestaña;
        # si no hay ninguna, abrimos la tienda de descargas.
        self.installed = installed_service.scan(self.settings.dest_folder, self.platform)
        self.view = "installed" if self.installed else "store"
        # Vista a la que volver al cerrar los ajustes (interruptor).
        self._previous_view = self.view if self.view != "settings" else "store"
        # on_kv_post ya se ejecutó (durante super().__init__) y dejó la pantalla
        # en "store"; aplicamos ahora la vista inicial correcta SIN animación,
        # para que al abrir no se vea ningún deslizamiento.
        manager = self.ids.get("view_manager")
        if manager is not None:
            manager.transition = NoTransition()
            manager.current = self.view
        self._status_event = None
        self._zoom_save_event = None
        self._search_event = None
        self._pending_search = ""
        self._update_checking = False
        # Cada vez que cambia un filtro o el modo de vista volvemos a montar la lista.
        self.bind(builds=lambda *_: self._rebuild_store(),
                  channel=lambda *_: self._on_filter_changed(),
                  search=lambda *_: self._on_filter_changed(),
                  layout_mode=lambda *_: self._on_layout_mode_changed(),
                  zoom=lambda *_: self._apply_zoom(),
                  platform_label=lambda *_: self._rebuild_store(),
                  arch_label=lambda *_: self._rebuild_store())
        self.status_text = tr("Ready")

    def on_kv_post(self, base_widget):
        # Se ejecuta al terminar de aplicar el .kv: aquí ya existen los ids.
        container = self.ids.get("store_list")
        if container is not None:
            # Al redimensionar la ventana recalculamos el número de columnas.
            container.bind(width=lambda *_: self._update_cols())
        installed_container = self.ids.get("installed_list")
        if installed_container is not None:
            installed_container.bind(width=lambda *_: self._update_installed_cols())
        dest_input = self.ids.get("dest_input")
        if dest_input is not None:
            # El texto ya está puesto por el .kv: lo dejamos al principio.
            self.reset_input_scroll(dest_input)
        Clock.schedule_once(lambda dt: self.refresh(force=False), 0.1)
        Clock.schedule_once(lambda dt: self.refresh_installed(), 0.2)
        # Limpiamos restos de una actualización ya aplicada y, si está activado,
        # comprobamos si hay versión nueva al arrancar.
        Clock.schedule_once(lambda dt: updater.cleanup_staging(), 0.5)
        Clock.schedule_once(
            lambda dt: updater.cleanup_partials(self.settings.dest_folder), 0.6)
        Clock.schedule_once(lambda dt: self._auto_check_updates(), 2.0)

    def _on_layout_mode_changed(self):
        # El modo cuadrícula/lista afecta tanto a la tienda como a las instaladas.
        self._rebuild_store()
        self._rebuild_installed()

    def _on_filter_changed(self):
        # Los filtros (canal y búsqueda) afectan a la tienda y a las instaladas.
        self._rebuild_store()
        self._rebuild_installed()

    @property
    def platform(self):
        """Identificador de SO ('linux', 'windows', 'darwin')."""
        return PLATFORMS.get(self.platform_label, "linux")

    @property
    def arch(self):
        """Arquitectura tal y como la espera la API de Blender."""
        if self.platform == "windows" and self.arch_label == "x86_64":
            return "amd64"
        return self.arch_label

    @property
    def platform_text(self):
        """Plataforma de destino, pero solo si no es la del propio equipo.

        Si estás en Linux y miras builds de Linux, repetir "GNU/Linux" en cada
        tarjeta sobra. Cuando eliges otra plataforma (por ejemplo Windows, para
        copiar Blender en un USB), sí lo mostramos para que no haya dudas.
        """
        if self.platform == self.system.os_name:
            return ""
        return detector.OS_LABELS.get(self.platform, self.platform)

    def set_platform(self, label):
        """Cambia la plataforma de destino y la recuerda para el próximo arranque."""
        if label not in PLATFORMS:
            return
        self.platform_label = label
        # Durante la construcción del widget el .kv puede disparar este método
        # antes de que exista ``self.settings``; lo comprobamos con getattr.
        settings = getattr(self, "settings", None)
        if settings is not None and settings.platform != label:
            settings.platform = label
            settings.save()

    def set_arch(self, label):
        """Cambia la arquitectura de destino y la recuerda para el próximo arranque."""
        if label not in ARCH_LABELS:
            return
        self.arch_label = label
        settings = getattr(self, "settings", None)
        if settings is not None and settings.arch != label:
            settings.arch = label
            settings.save()

    def set_channel(self, channel):
        self.channel = channel

    def set_search(self, text):
        """Filtra por texto, pero no en cada pulsación de tecla.

        Cada cambio de ``search`` reconstruye las dos listas enteras (destruye
        y vuelve a crear todas las tarjetas), así que esperamos a que el
        usuario deje de escribir.
        """
        self._pending_search = text
        if self._search_event is not None:
            self._search_event.cancel()
        self._search_event = Clock.schedule_once(self._apply_search, 0.2)

    def _apply_search(self, dt):
        self._search_event = None
        self.search = self._pending_search

    def set_view(self, view):
        """Cambia entre la tienda, las instaladas y los ajustes.

        El botón de ajustes funciona como un interruptor: si ya estamos en
        ajustes, vuelve a la vista anterior. Solo al entrar y salir de ajustes
        hay deslizamiento (hacia abajo al entrar, hacia arriba al salir); entre
        la tienda y las instaladas el cambio es instantáneo, sin deslizar.
        """
        previous = self.view
        if view == "settings" and previous == "settings":
            # Segundo clic en ajustes: regresamos a donde estábamos.
            view = self._previous_view
        elif view != "settings":
            # Recordamos la última vista que no era ajustes.
            self._previous_view = view
        manager = self.ids.get("view_manager")
        if manager is not None and hasattr(manager, "transition"):
            if view == "settings":
                manager.transition = SlideTransition(direction="down")
            elif previous == "settings":
                manager.transition = SlideTransition(direction="up")
            else:
                # Tienda <-> instaladas: sin animación.
                manager.transition = NoTransition()
            manager.current = view
        self.view = view
        if view == "installed":
            self.refresh_installed()

    def _filtered(self):
        """Aplica plataforma, arquitectura, canal y búsqueda a las compilaciones."""
        builds = api.available_for(self.builds, self.platform, self.arch)
        return api.filter_builds(builds, self.channel, self.search)

    def set_layout_mode(self, mode):
        if mode not in ("grid", "list") or mode == self.layout_mode:
            return
        self.layout_mode = mode
        self.settings.layout_mode = mode
        self.settings.save()

    def set_zoom(self, value):
        """Ajusta el tamaño de las tarjetas; guarda con un pequeño retardo."""
        new_zoom = min(MAX_ZOOM, max(MIN_ZOOM, float(value)))
        if abs(new_zoom - self.zoom) < 0.001:
            return
        self.zoom = new_zoom
        self.settings.zoom = new_zoom
        # Evitamos escribir en disco en cada movimiento del deslizador.
        if self._zoom_save_event is not None:
            self._zoom_save_event.cancel()
        self._zoom_save_event = Clock.schedule_once(lambda dt: self.settings.save(), 0.6)

    def _apply_zoom(self):
        """Propaga el zoom a las tarjetas ya creadas y recalcula columnas."""
        container = self.ids.get("store_list")
        if container is not None:
            for card in container.children:
                if isinstance(card, (BuildCard, GridBuildCard)):
                    card.zoom = self.zoom
        installed_container = self.ids.get("installed_list")
        if installed_container is not None:
            for card in installed_container.children:
                if isinstance(card, (InstalledCard, GridInstalledCard)):
                    card.zoom = self.zoom
        self._update_cols()
        self._update_installed_cols()

    def _columns_for(self, container, has_items):
        """Número de columnas para una rejilla según ancho, zoom y modo."""
        if container is None:
            return 1
        if self.layout_mode == "list" or not has_items:
            return 1
        available = max(0, container.width - dp(28))
        cell = max(dp(140), dp(240) * self.zoom)
        return max(1, int(available // cell))

    def _update_cols(self):
        """Recalcula las columnas de la tienda."""
        container = self.ids.get("store_list")
        if container is not None:
            container.cols = self._columns_for(container, self.has_builds)

    def _update_installed_cols(self):
        """Recalcula las columnas de la lista de instaladas."""
        container = self.ids.get("installed_list")
        if container is not None:
            container.cols = self._columns_for(container, self.has_installed)

    def _row_color(self, installed, index, zebra=False):
        """Color de fondo de una tarjeta.

        El salteado (cebra) es opcional: solo se usa en la pestaña de
        instaladas y en modo lista, para no confundir con las que aún no se
        han descargado.
        """
        base = SURFACE if installed else CARD_DIM
        if zebra and self.layout_mode == "list":
            alternate = ROW_ALT if installed else CARD_DIM_ALT
            return list(alternate if index % 2 else base)
        return list(base)

    def _rebuild_store(self):
        """Reconstruye la lista de compilaciones disponibles."""
        container = self.ids.get("store_list")
        if container is None:
            return
        container.clear_widgets()
        builds = self._filtered()
        self.has_builds = bool(builds)
        self._update_cols()
        if not builds:
            container.cols = 1
            if self.channel == "experimental":
                # El listado de ramas experimentales suele estar vacío: casi
                # siempre no hay ninguna rama abierta, así que lo explicamos.
                container.add_widget(self._placeholder(
                    tr("No experimental builds right now"),
                    tr("Feature branches with new features still in development.")))
            else:
                container.add_widget(self._placeholder(
                    tr("No builds found"),
                    tr("Try clearing the search or another channel filter.")))
            return
        card_class = BuildCard if self.layout_mode == "list" else GridBuildCard
        for index, build in enumerate(builds):
            is_installed = installed_service.find_installed(self.installed, build) is not None
            card = card_class()
            card.owner = self
            card.zoom = self.zoom
            # La tienda no lleva salteado; solo la pestaña de instaladas.
            card.row_color = self._row_color(is_installed, index)
            card.installed = is_installed
            # Hay que fijarlo ANTES de asignar `build`: al asignarlo se calcula
            # la línea de metadatos y ya debe conocer la plataforma de destino.
            card.platform_text = self.platform_text
            card.build = build
            container.add_widget(card)

    def refresh_installed(self):
        """Escanea la carpeta destino y monta la pestaña de versiones instaladas."""
        self.installed = installed_service.scan(self.settings.dest_folder, self.platform)
        self.has_installed = bool(self.installed)
        self._rebuild_installed()
        # Al cambiar las instaladas también cambian los botones de la tienda.
        self._rebuild_store()

    def _filtered_installed(self):
        """Aplica el canal y la búsqueda a las versiones instaladas."""
        return installed_service.filter_installed(self.installed, self.channel, self.search)

    def _rebuild_installed(self):
        """Construye la lista de instaladas según filtros y modo cuadrícula/lista."""
        container = self.ids.get("installed_list")
        if container is None:
            return
        entries = self._filtered_installed()
        container.clear_widgets()
        self.has_installed = bool(entries)
        self._update_installed_cols()
        if not entries:
            container.cols = 1
            container.add_widget(self._placeholder(
                tr("No installed versions found"),
                tr("Download one from the store to see it here.")))
            return
        card_class = InstalledCard if self.layout_mode == "list" else GridInstalledCard
        for index, entry in enumerate(entries):
            card = card_class()
            card.owner = self
            card.zoom = self.zoom
            card.row_color = self._row_color(True, index, zebra=True)
            card.entry = entry
            container.add_widget(card)

    def _placeholder(self, text, hint=""):
        """Bloque que se muestra cuando una lista está vacía.

        Un aviso a secas ("No se encontraron compilaciones") deja al usuario
        sin saber qué hacer, así que va con un icono y una segunda línea que
        dice cómo volver a ver algo.
        """
        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=[0, dp(50), 0, 0])
        box.size_hint_y = None
        box.height = dp(190)
        icon = Label(text=icons.SEARCH, font_name=theme_module.ICON_FONT,
                     font_size="34sp", color=(MUTED[0], MUTED[1], MUTED[2], 0.55))
        icon.size_hint_y = None
        icon.height = dp(46)
        box.add_widget(icon)
        title = Label(text=text, color=MUTED, font_size="16sp")
        title.size_hint_y = None
        title.height = dp(28)
        box.add_widget(title)
        if hint:
            subtitle = Label(text=hint, color=(MUTED[0], MUTED[1], MUTED[2], 0.75),
                             font_size="13sp")
            subtitle.size_hint_y = None
            subtitle.height = dp(22)
            box.add_widget(subtitle)
        return box

    def refresh(self, force=False):
        """Descarga el listado de compilaciones sin bloquear la interfaz."""
        if self.busy:
            return
        self.busy = True
        self.status_text = tr("Loading...")

        def worker():
            # Fuera del hilo de la interfaz: la red puede tardar.
            builds = api.get_builds(force=force)
            # Volvemos al hilo de Kivy para tocar la interfaz.
            Clock.schedule_once(lambda dt: self._on_builds_loaded(builds), 0)

        threading.Thread(target=worker, daemon=True).start()

    def _on_builds_loaded(self, builds):
        self.builds = builds
        self.busy = False
        self.status_text = tr("Ready")

    def _show_message(self, message, timeout=4):
        """Muestra un mensaje temporal en la barra de estado."""
        self.status_text = message
        if self._status_event is not None:
            self._status_event.cancel()
        self._status_event = Clock.schedule_once(
            lambda dt: setattr(self, "status_text", tr("Ready")), timeout
        )

    def open_release_notes(self, version):
        """Abre en el navegador las notas de la versión de esa serie de Blender.

        Se lanza en un hilo porque ``webbrowser.open`` puede tardar en volver
        (arranca el navegador) y congelaría la interfaz mientras tanto.
        """
        url = api.release_notes_url(version)
        self._show_message(tr("Opening the release notes..."))

        def worker():
            try:
                opened = webbrowser.open(url)
            except Exception:
                opened = False
            if not opened:
                Clock.schedule_once(
                    lambda dt: self._show_message(tr("Could not open the browser")), 0
                )

        threading.Thread(target=worker, daemon=True).start()

    def _set_progress(self, downloaded, total):
        if total:
            self.progress = max(0.0, min(100.0, downloaded * 100.0 / total))

    def install_build(self, build):
        """Descarga e instala una compilación, o lanza la ya instalada."""
        if build is None:
            return
        # Si esa compilación concreta ya está instalada, simplemente la lanzamos.
        match = installed_service.find_installed(self.installed, build)
        if match is not None:
            if match.can_launch:
                self.launch_installed(match)
            else:
                self._show_message(tr("No executable found"))
            return
        # Solo hay un hilo de descarga: sin esta guarda pondríamos la interfaz
        # en modo "descargando" para una descarga que nunca arranca.
        if self.downloader.running:
            self._show_message(tr("A download is already in progress"))
            return
        self.busy = True
        self.downloading = True
        self.progress = 0
        self.status_text = tr("Downloading {name}", name=build.filename)
        self.downloader.start(
            build.url,
            self.settings.dest_folder,
            build.filename,
            build.checksum,
            # Todas las llamadas de vuelta se reenvían al hilo de la interfaz.
            on_progress=lambda downloaded, total: Clock.schedule_once(
                lambda dt: self._set_progress(downloaded, total), 0),
            on_done=lambda path: Clock.schedule_once(
                lambda dt: self._on_download_done(path, build), 0),
            on_error=lambda message: Clock.schedule_once(
                lambda dt: self._on_download_error(message), 0),
        )

    def cancel_download(self):
        self.downloader.cancel()

    def _on_download_done(self, path, build):
        archive = Path(path)
        # En macOS la API solo publica .dmg, que no es un contenedor que
        # sepamos abrir. La descarga ha ido bien: dejamos el archivo donde
        # está (sin borrarlo) y le decimos al usuario qué hacer con él, en vez
        # de fingir un fallo de descarga.
        if not is_archive(archive):
            self.busy = False
            self.downloading = False
            self.progress = 0
            self._reveal(archive)
            self._show_message(
                tr("Downloaded to {folder}", folder=archive.parent)
                + "  ·  "
                + tr("Open it to install Blender manually."),
                timeout=10,
            )
            return
        self.status_text = tr("Extracting {name}", name=archive.name)

        def worker():
            try:
                target = extract(archive, self.settings.dest_folder)
                if self.settings.delete_archive:
                    archive.unlink(missing_ok=True)
                Clock.schedule_once(lambda dt: self._on_extract_done(target, build), 0)
            except Exception as error:
                Clock.schedule_once(lambda dt: self._on_download_error(str(error)), 0)

        threading.Thread(target=worker, daemon=True).start()

    def _reveal(self, path):
        """Abre el gestor de archivos en la carpeta donde quedó la descarga."""
        folder = Path(path).parent
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(path)])
            elif sys.platform.startswith("win"):
                os.startfile(str(folder))  # noqa: S606 (solo Windows)
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as error:
            download_log(f"reveal failed: {error}")

    def _on_extract_done(self, target, build=None):
        self.busy = False
        self.downloading = False
        self.progress = 0
        # El nombre de la carpeta extraída no lleva el hash de la compilación,
        # así que lo anotamos nosotros: es lo único que distingue dos diarias
        # de la misma versión bajadas en días distintos.
        destination = Path(self.settings.dest_folder).expanduser()
        if build is not None and Path(target) != destination:
            installed_service.write_marker(target, build)
        self.refresh_installed()
        self._show_message(tr("Extraction complete"))

    def _on_download_error(self, message):
        self.busy = False
        self.downloading = False
        self.progress = 0
        if message == "cancelled":
            self._show_message(tr("Cancelled"))
        elif message == "checksum":
            self._show_message(tr("Checksum error"))
        else:
            self._show_message(tr("Download failed"))
            self._show_error(message)

    def _dialog_button(self, text, color=None, pressed=None):
        """Botón de diálogo con el mismo aspecto que el resto de la interfaz."""
        button = CardButton(text=text)
        button.size_hint_x = 1
        button.height = dp(36)
        if color is not None:
            button.button_color = list(color)
        if pressed is not None:
            button.pressed_color = list(pressed)
        return button

    def _wrapped_label(self, text):
        """Etiqueta que parte el texto en varias líneas dentro del diálogo.

        Sin ``text_size`` un mensaje de error largo se sale del popup por los
        lados en lugar de partirse.
        """
        label = Label(text=str(text), halign="center", valign="middle")
        label.bind(size=lambda widget, value: setattr(widget, "text_size", value))
        return label

    def _show_error(self, message):
        """Ventana modal con el detalle técnico de un error."""
        content = BoxLayout(orientation="vertical", padding=12, spacing=8)
        content.add_widget(self._wrapped_label(message))
        # Un único botón a todo el ancho del diálogo desentona con el resto
        # (los demás diálogos reparten dos): lo dejamos centrado y estrecho.
        row = BoxLayout(size_hint_y=None, height=dp(40))
        button = self._dialog_button(tr("Close"))
        button.size_hint_x = None
        button.width = dp(150)
        row.add_widget(Widget())
        row.add_widget(button)
        row.add_widget(Widget())
        content.add_widget(row)
        popup = AppPopup(title=tr("Error"), content=content,
                         size_hint=(0.7, None), height=dp(210))
        button.bind(on_release=popup.dismiss)
        popup.open()

    def launch_installed(self, entry):
        if entry is None or not entry.can_launch:
            self._show_message(tr("No executable found"))
            return
        # shlex respeta las comillas, igual que lo haría el intérprete de comandos.
        args = shlex.split(self.settings.launch_args) if self.settings.launch_args else []
        try:
            self.launcher.launch(entry.executable, args)
        except OSError as error:
            self._show_error(str(error))
            return
        self._show_message(tr("Launching {name}", name=entry.name))

    def delete_installed(self, entry):
        """Borra una versión instalada previa confirmación del usuario."""
        if entry is None:
            return

        def confirm(dt=None):
            try:
                shutil.rmtree(entry.path)
            except OSError as error:
                self._show_error(str(error))
                return
            self._show_message(tr("Deleted {name}", name=entry.name))
            self.refresh_installed()

        self._confirm(
            tr("Delete {name}?", name=entry.name),
            tr("This will remove the folder permanently."),
            confirm,
        )

    def _confirm(self, title, message, on_confirm):
        """Ventana de confirmación reutilizable para acciones destructivas."""
        content = BoxLayout(orientation="vertical", padding=12, spacing=10)
        content.add_widget(self._wrapped_label(message))
        buttons = BoxLayout(size_hint_y=None, height=dp(40), spacing=8)
        cancel = self._dialog_button(tr("Cancel"))
        accept = self._dialog_button(tr("Delete"), DANGER, DANGER_DARK)
        buttons.add_widget(cancel)
        buttons.add_widget(accept)
        content.add_widget(buttons)
        popup = AppPopup(title=title, content=content,
                         size_hint=(0.6, None), height=dp(190))
        cancel.bind(on_release=popup.dismiss)

        def _accept(*_):
            popup.dismiss()
            on_confirm()

        accept.bind(on_release=_accept)
        popup.open()

    def reset_input_scroll(self, widget):
        """Deja un campo de texto mostrando el principio, no el final.

        Con una ruta larga el TextInput se queda desplazado al final y se lee
        "...cargas/Blenders" en vez de la carpeta. Hay que esperar un fotograma:
        el desplazamiento se recalcula después de colocar el texto.
        """
        def _reset(dt):
            widget.cursor = (0, 0)
            widget.scroll_x = 0

        Clock.schedule_once(_reset, 0)

    def browse_dest(self):
        """Abre el explorador y deja la carpeta elegida en el campo de texto."""
        input_widget = self.ids.get("dest_input")
        current = input_widget.text if input_widget is not None else self.settings.dest_folder

        def on_select(path):
            if input_widget is not None:
                input_widget.text = path

        self.browse_folder(current, on_select)

    def browse_folder(self, current, on_select):
        """Selector de carpetas propio, con el aspecto de la app.

        Kivy no trae uno nativo en el escritorio y el FileChooser de serie
        desentona con el tema, así que montamos una lista de carpetas sencilla:
        se navega haciendo clic y se confirma con "Elegir esta carpeta".
        """
        view = AppModalView(size_hint=(0.82, 0.82))
        layout = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(10))

        start = Path(current).expanduser()
        if not start.is_dir():
            start = start.parent
        state = {"path": start}

        # Cabecera: subir, ir al inicio y la ruta actual.
        header = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(8))
        up = self._icon_button(icons.ARROW_UP, tr("Parent folder"))
        up.bind(on_release=lambda *_: navigate(state["path"].parent))
        home = self._icon_button(icons.HOME, tr("Home folder"))
        home.bind(on_release=lambda *_: navigate(Path.home()))
        path_label = Label(color=MUTED, halign="left", valign="middle", shorten=True)
        path_label.bind(size=lambda widget, value: setattr(widget, "text_size", value))
        header.add_widget(up)
        header.add_widget(home)
        header.add_widget(path_label)

        scroll = ScrollView()
        container = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(2))
        container.bind(minimum_height=lambda widget, value: setattr(widget, "height", value))
        scroll.add_widget(container)

        footer = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
        cancel = self._dialog_button(tr("Cancel"))
        select = self._dialog_button(tr("Use this folder"), ACCENT, ACCENT_DARK)
        footer.add_widget(cancel)
        footer.add_widget(select)

        layout.add_widget(header)
        layout.add_widget(scroll)
        layout.add_widget(footer)
        view.add_widget(layout)

        def populate():
            container.clear_widgets()
            path = state["path"]
            if path.parent != path:
                row = FolderRow(text="..", icon=icons.ARROW_UP)
                row.bind(on_release=lambda *_: navigate(path.parent))
                container.add_widget(row)
            try:
                entries = sorted(
                    (entry for entry in os.scandir(path)
                     if entry.is_dir() and not entry.name.startswith(".")),
                    key=lambda entry: entry.name.lower(),
                )
            except OSError:
                entries = []
            for entry in entries:
                row = FolderRow(text=entry.name, icon=icons.FOLDER)
                row.bind(on_release=lambda *_, target=entry.path: navigate(Path(target)))
                container.add_widget(row)
            path_label.text = str(path)
            scroll.scroll_y = 1

        def navigate(target):
            candidate = Path(target)
            if candidate.is_dir():
                state["path"] = candidate
                populate()

        def _select(*_):
            view.dismiss()
            on_select(str(state["path"]))

        cancel.bind(on_release=view.dismiss)
        select.bind(on_release=_select)
        populate()
        view.open()

    def _icon_button(self, glyph, tooltip=""):
        """Botón cuadrado con un icono, para la cabecera de diálogos."""
        button = CardButton(text=glyph)
        button.font_name = ICON_FONT
        button.tooltip_text = tooltip
        button.size_hint_x = None
        button.width = dp(40)
        return button

    def language_values(self):
        return [tr(LANGUAGE_IDS[key]) for key in LANGUAGE_IDS]

    def language_id_for(self, label):
        for key, value in LANGUAGE_IDS.items():
            if tr(value) == label:
                return key
        return "auto"

    def save_settings(self, dest, language_label, delete_archive, launch_args):
        previous_language = i18n.get_language()
        self.settings.dest_folder = str(Path(dest).expanduser())
        self.settings.language = self.language_id_for(language_label)
        self.settings.delete_archive = bool(delete_archive)
        self.settings.auto_update = self.auto_update
        self.settings.launch_args = launch_args or ""
        self.settings.save()
        i18n.set_language(self.settings.language)
        # Los textos del .kv se evalúan al construirse; si cambia el idioma
        # hay que volver a montar la interfaz para que se retraduzca.
        if i18n.get_language() != previous_language:
            if self.downloader.running:
                # Recargar la interfaz cambia la raíz de la aplicación y los
                # avisos de la descarga en curso irían al widget viejo: el
                # progreso dejaría de verse. Mejor esperar al reinicio.
                self._show_message(tr("The language will change when you restart"), timeout=6)
                return
            self._reload_ui()
            return
        self.set_view("store")
        self.refresh_installed()
        self._show_message(tr("Ready"))

    # --- Actualizaciones ---------------------------------------------------

    def set_auto_update(self, active):
        """Guarda si hay que buscar actualizaciones al arrancar."""
        self.auto_update = bool(active)
        self.settings.auto_update = self.auto_update
        self.settings.save()

    def _auto_check_updates(self):
        if not self.auto_update or RootWidget._auto_checked:
            return
        RootWidget._auto_checked = True
        # En modo fuente sin checkout git no hay nada que actualizar; si no,
        # ofrecería en cada arranque una descarga que además no se puede aplicar.
        if not getattr(sys, "frozen", False) and updater.source_root() is None:
            return
        self.check_updates(manual=False)

    def check_updates(self, manual=False):
        """Comprueba en segundo plano si hay una versión nueva publicada."""
        if self._update_checking:
            return
        self._update_checking = True
        if manual:
            self.status_text = tr("Checking for updates...")

        def worker():
            # Fuera del hilo de la interfaz: la red puede tardar.
            result = updater.latest_release(force=manual)
            # En modo fuente no hay versión empaquetada (0.0.0), así que
            # comparamos con el último tag del checkout para no ofrecer la
            # misma actualización en cada arranque.
            source = None
            if not getattr(sys, "frozen", False):
                source = updater.source_tag() or None
            Clock.schedule_once(lambda dt: self._on_update_result(result, manual, source), 0)

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_result(self, result, manual, source=None):
        self._update_checking = False
        if result is None:
            if manual:
                self._show_message(tr("Update check failed"))
            return
        tag, assets = result
        current = source or self.current_version
        if not updater.is_newer(current, tag):
            if manual:
                self._show_message(tr("You are up to date"))
            return
        # Modo fuente: con checkout git se hace git pull; sin él no hay nada que
        # reemplazar, así que (solo si lo pidió el usuario) abrimos la release.
        if not getattr(sys, "frozen", False):
            if updater.source_root() is not None:
                self._show_source_update(tag)
            elif manual:
                # Sin checkout git no hay nada que reemplazar: que al menos vea
                # la release en el navegador, y que sepa por qué se ha abierto.
                self._show_message(
                    tr("A new version is available: {version}", version=tag), timeout=8)
                updater.open_releases()
            return
        asset_name = updater.asset_for(self.system)
        asset = next((item for item in assets if item["name"] == asset_name), None)
        if asset is None:
            if manual:
                self._show_message(tr("No update for this platform"))
            return
        self._update_assets = assets
        self._show_update_available(tag, asset)

    def _update_explanation(self):
        """Qué hará la app tras descargar, según cómo esté instalada."""
        if self.system.os_name == "windows" or (
            self.system.os_name == "linux" and os.environ.get("APPIMAGE")
        ):
            return tr("It will be installed and the app will restart automatically.")
        return tr("It will be downloaded. You will have to install it manually.")

    def _show_source_update(self, tag):
        """Actualización de un checkout en modo fuente: git pull + reinicio."""
        content = BoxLayout(orientation="vertical", padding=12, spacing=10)
        content.add_widget(Label(text=tr("A new version is available: {version}", version=tag)))
        info = self._wrapped_label(
            tr("Running from source: the app will run git pull and restart."))
        content.add_widget(info)
        buttons = BoxLayout(size_hint_y=None, height=dp(40), spacing=8)
        secondary = self._dialog_button(tr("Later"))
        primary = self._dialog_button(tr("Update"), ACCENT, ACCENT_DARK)
        buttons.add_widget(secondary)
        buttons.add_widget(primary)
        content.add_widget(buttons)
        popup = AppPopup(title=tr("Update available"), content=content,
                         size_hint=(0.68, None), height=dp(230), auto_dismiss=True)

        def _error_text(reason):
            if reason == "dirty":
                return tr("You have local changes. Commit or stash them and try again.")
            return tr("Could not update. Run git pull manually.")

        def _done(ok, reason):
            if not ok:
                info.text = _error_text(reason)
                popup.auto_dismiss = True
                primary.disabled = False
                secondary.disabled = False
                secondary.text = tr("Close")
                return
            info.text = tr("Restarting...")
            from kivy.app import App
            app = App.get_running_app()
            if updater.relaunch_source() and app is not None:
                Clock.schedule_once(lambda dt: app.stop(), 0.8)
            else:
                info.text = tr("Update downloaded. Restart the app.")

        def _start(*_):
            primary.disabled = True
            secondary.disabled = True
            popup.auto_dismiss = False  # git pull en marcha: no se cierra
            info.text = tr("Updating...")

            def worker():
                ok, reason = updater.source_update()
                Clock.schedule_once(lambda dt: _done(ok, reason), 0)

            threading.Thread(target=worker, daemon=True).start()

        secondary.bind(on_release=popup.dismiss)
        primary.bind(on_release=_start)
        popup.open()

    def _show_update_available(self, tag, asset):
        """Diálogo para descargar e instalar la versión nueva."""
        state = {"downloading": False, "cancelled": False}
        content = BoxLayout(orientation="vertical", padding=12, spacing=10)
        content.add_widget(Label(text=tr("A new version is available: {version}", version=tag)))
        info = self._wrapped_label(self._update_explanation())
        content.add_widget(info)
        progress = AppProgressBar(max=100, value=0)
        progress.size_hint_y = None
        progress.height = dp(10)
        progress.opacity = 0
        content.add_widget(progress)
        buttons = BoxLayout(size_hint_y=None, height=dp(40), spacing=8)
        secondary = self._dialog_button(tr("Later"))
        primary = self._dialog_button(tr("Update"), ACCENT, ACCENT_DARK)
        buttons.add_widget(secondary)
        buttons.add_widget(primary)
        content.add_widget(buttons)
        # Mientras se descarga o se instala, auto_dismiss se apaga: un clic
        # fuera (o Esc) no debe dejar el proceso en marcha sin interfaz que lo
        # cuente. Antes de empezar, en cambio, se cierra como cualquier aviso.
        popup = AppPopup(title=tr("Update available"), content=content,
                         size_hint=(0.7, None), height=dp(250), auto_dismiss=True)

        def _reset():
            state["downloading"] = False
            popup.auto_dismiss = True
            progress.opacity = 0
            primary.disabled = False
            secondary.disabled = False
            secondary.text = tr("Close")

        def _on_secondary(*_):
            if state["downloading"]:
                # Puede que aún estemos pidiendo el checksum y la descarga no
                # haya arrancado: lo anotamos para no arrancarla después.
                state["cancelled"] = True
                self.update_downloader.cancel()
                Clock.schedule_once(lambda dt: _on_error("cancelled"), 0)
            else:
                popup.dismiss()

        def _on_progress(downloaded, total):
            Clock.schedule_once(
                lambda dt: setattr(progress, "value", (downloaded * 100.0 / total) if total else 0),
                0,
            )

        def _on_done(path):
            # No cerramos el diálogo: aquí mismo informamos de la instalación y
            # del reinicio, que es lo que antes no quedaba claro.
            state["downloading"] = False
            popup.auto_dismiss = False  # instalando: que no se cierre solo
            progress.opacity = 0
            primary.disabled = True
            secondary.disabled = True
            info.text = tr("Installing the update...")

            def worker():
                quit_app = updater.apply(path)
                Clock.schedule_once(lambda dt: _finish(quit_app, path), 0)

            threading.Thread(target=worker, daemon=True).start()

        def _finish(quit_app, path):
            if quit_app:
                info.text = tr("Restarting to install the update...")
                from kivy.app import App
                app = App.get_running_app()
                if app is not None:
                    Clock.schedule_once(lambda dt: app.stop(), 1.0)
                return
            _reset()
            # Ya está descargada: no tiene sentido volver a descargarla.
            primary.disabled = True
            info.text = (
                tr("Downloaded to {folder}", folder=Path(path).parent)
                + "  ·  " + tr("Open it to install the new version.")
            )

        def _on_error(message):
            _reset()
            if message == "cancelled":
                info.text = tr("Cancelled")
            elif message == "checksum":
                info.text = tr("Checksum error")
            else:
                info.text = tr("Download failed")

        def _start(*_):
            state["downloading"] = True
            state["cancelled"] = False
            popup.auto_dismiss = False
            info.text = tr("Downloading...")
            progress.opacity = 1
            primary.disabled = True
            secondary.disabled = False
            secondary.text = tr("Cancel")

            def worker():
                # checksum_for hace su propia petición HTTP (hasta 15 s de
                # espera): en el hilo de Kivy dejaría la ventana clavada.
                checksum = updater.checksum_for(self._update_assets, asset["name"])
                if state["cancelled"]:
                    # Cancelado mientras pedíamos el checksum: no arrancamos
                    # (start() limpiaría el aviso de cancelación).
                    return
                self.update_downloader.start(
                    asset["url"],
                    str(updater.updates_dir()),
                    asset["name"],
                    checksum,
                    on_progress=_on_progress,
                    on_done=lambda path: Clock.schedule_once(lambda dt: _on_done(path), 0),
                    on_error=lambda message: Clock.schedule_once(lambda dt: _on_error(message), 0),
                )

            threading.Thread(target=worker, daemon=True).start()

        secondary.bind(on_release=_on_secondary)
        primary.bind(on_release=_start)
        popup.open()

    def _reload_ui(self):
        """Sustituye la raíz de la aplicación por una nueva, ya traducida."""
        from kivy.app import App
        from kivy.core.window import Window

        app = App.get_running_app()
        if app is None:
            return
        old_root = app.root
        new_root = RootWidget()
        app.root = new_root
        if old_root is not None:
            Window.remove_widget(old_root)
        Window.add_widget(new_root)
