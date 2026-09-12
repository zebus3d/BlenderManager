"""Widgets de la interfaz y controlador principal de la aplicación.

Aquí vive toda la lógica de la pantalla: carga de ajustes, listado de
compilaciones de Blender, filtros, descarga/extracción en segundo plano,
lanzamiento de versiones instaladas y la navegación entre vistas.

Ojo: Kivy aplica las reglas del archivo .kv durante el __init__ del widget,
antes de que se ejecute el cuerpo de nuestro constructor. Por eso los datos
que consume la vista (carpeta destino, idioma, etc.) se exponen como
propiedades Kivy con valores por defecto y se rellenan después de super().__init__.
"""

import shlex
import shutil
import threading
from pathlib import Path

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import (
    AliasProperty,
    BooleanProperty,
    ListProperty,
    NumericProperty,
    ObjectProperty,
    StringProperty,
)
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner, SpinnerOption
from kivy.uix.screenmanager import NoTransition, SlideTransition
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget

import i18n
from i18n import tr
from model.build import version_tuple
from services import api, detector, installed as installed_service, settings as settings_service
from services.downloader import Downloader
from services.extractor import extract
from services.launcher import Launcher
from ui.theme import ACCENT, BUTTON, CARD_DIM, CARD_DIM_ALT, MUTED, ROW_ALT, SURFACE
from ui.tooltip import HoverBehavior

# Etiquetas visibles del selector de sistema operativo -> identificador interno
# que usan tanto la API de Blender como el escáner de versiones instaladas.
PLATFORMS = {"GNU/Linux": "linux", "Windows": "windows", "macOS": "darwin"}
PLATFORM_LABELS = {value: key for key, value in PLATFORMS.items()}
ARCH_LABELS = ["x86_64", "arm64"]
LANGUAGE_IDS = {"auto": "Automatic", "en": "English", "es": "Spanish"}

# Límites de la barra de zoom (la misma que usa Dolphin para el tamaño de iconos).
MIN_ZOOM = 0.6
MAX_ZOOM = 1.8


class Pill(HoverBehavior, ToggleButton):
    """Botón con forma de pastilla para los filtros y el selector de vista."""

    pass


class SideButton(HoverBehavior, ToggleButton):
    """Botón cuadrado de la barra lateral (tienda, instaladas, ajustes)."""

    pass


class CardButton(HoverBehavior, Button):
    """Botón de acción dentro de las tarjetas (descargar, lanzar, examinar...)."""

    # Colores configurables: por defecto un botón neutro oscuro (como las
    # pestañas de Blender) que se ilumina en azul al pulsarlo. Descargar,
    # lanzar y desinstalar sobrescriben ambos colores.
    button_color = ListProperty(list(BUTTON))
    pressed_color = ListProperty(list(ACCENT))
    # El degradado claro solo se usa en los botones de color (descargar/lanzar);
    # en los grises enturbia el texto blanco.
    use_gradient = BooleanProperty(False)


class HoverButton(HoverBehavior, Button):
    """Botón normal con tooltip (por ejemplo, actualizar o borrar)."""

    pass


class SwitchPill(HoverBehavior, ToggleButton):
    """Interruptor de sí/no con el mismo aspecto que los botones del tema.

    ToggleButton trabaja con `state` ('normal'/'down'); exponemos además un
    booleano `active` para que sea cómodo de usar desde el .kv y los ajustes.
    """

    active = BooleanProperty(False)

    def on_state(self, *_):
        self.active = self.state == "down"

    def on_active(self, *_):
        self.state = "down" if self.active else "normal"


class HoverSpinner(HoverBehavior, Spinner):
    """Selector con tooltip (sistema operativo y arquitectura)."""

    pass


class DarkSpinnerOption(HoverBehavior, SpinnerOption):
    """Opción del desplegable de un Spinner, con el estilo oscuro de la app."""

    pass


class ZoomSlider(HoverBehavior, Widget):
    """Barra de zoom propia, dibujada con el estilo del resto de la interfaz.

    No usamos el Slider de Kivy porque trae una "bolita" con su propio aspecto.
    Aquí pintamos una pista, la parte rellena y un tirador redondeado.
    """

    min = NumericProperty(0.6)
    max = NumericProperty(1.8)
    value = NumericProperty(1.0)
    step = NumericProperty(0.0)
    thumb_size = NumericProperty(dp(16))
    dragging = BooleanProperty(False)

    def _get_thumb_x(self):
        span = max(0.0001, self.max - self.min)
        fraction = min(1.0, max(0.0, (self.value - self.min) / span))
        usable = max(0.0, self.width - self.thumb_size)
        return self.x + fraction * usable

    # Posición horizontal del tirador; se recalcula al cambiar valor o tamaño.
    thumb_x = AliasProperty(
        _get_thumb_x, None,
        bind=("value", "min", "max", "width", "x", "thumb_size"),
    )

    def _set_from_x(self, x):
        usable = max(1.0, self.width - self.thumb_size)
        fraction = min(1.0, max(0.0, (x - self.x - self.thumb_size / 2.0) / usable))
        value = self.min + fraction * (self.max - self.min)
        if self.step:
            value = round(value / self.step) * self.step
        self.value = min(self.max, max(self.min, value))

    def on_touch_down(self, touch):
        if self.disabled or not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        touch.grab(self)
        self.dragging = True
        self._set_from_x(touch.x)
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            self._set_from_x(touch.x)
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            self.dragging = False
            return True
        return super().on_touch_up(touch)


class BaseBuildCard(HoverBehavior, BoxLayout):
    """Base común para las tarjetas de compilaciones (vista lista y rejilla)."""

    build = ObjectProperty(None, allownone=True)
    owner = ObjectProperty(None, allownone=True)
    title = StringProperty("")
    channel_text = StringProperty("")
    version_text = StringProperty("")
    meta_text = StringProperty("")
    action_text = StringProperty("")
    is_lts = BooleanProperty(False)
    installed = BooleanProperty(False)
    zoom = NumericProperty(1.0)
    # Fondo normal de la tarjeta (sin contar el resaltado al pasar el ratón).
    # Se calcula en Python para poder alternar filas claras/oscuras en modo lista.
    row_color = ListProperty(list(SURFACE))

    def on_build(self, *_):
        """Traduce los datos del modelo a las cadenas que pinta la tarjeta."""
        build = self.build
        if build is None:
            return
        self.title = build.version
        self.version_text = build.version
        if build.is_lts:
            channel = "LTS"
        elif build.risk in ("alpha", "daily", "beta"):
            channel = {"alpha": "Alpha", "daily": "Daily", "beta": "Beta"}[build.risk]
        else:
            channel = "Stable"
        self.channel_text = tr(channel)
        self.is_lts = build.is_lts
        self.meta_text = f"{build.human_size}  ·  {build.branch}  ·  {build.arch}"
        self.refresh_action()

    def refresh_action(self):
        """El botón dice 'Lanzar' si esa versión ya está instalada y 'Descargar' si no."""
        self.action_text = tr("Launch") if self.installed else tr("Download")


class BuildCard(BaseBuildCard):
    """Tarjeta en modo lista (una fila por compilación)."""

    pass


class GridBuildCard(BaseBuildCard):
    """Tarjeta en modo rejilla (icono grande y botón debajo)."""

    pass


class BaseInstalledCard(HoverBehavior, BoxLayout):
    """Base común para las tarjetas de versiones instaladas (lista y rejilla)."""

    entry = ObjectProperty(None, allownone=True)
    owner = ObjectProperty(None, allownone=True)
    title = StringProperty("")
    meta_text = StringProperty("")
    action_text = StringProperty("")
    is_lts = BooleanProperty(False)
    can_launch = BooleanProperty(False)
    zoom = NumericProperty(1.0)
    row_color = ListProperty(list(SURFACE))

    def on_entry(self, *_):
        entry = self.entry
        if entry is None:
            return
        self.title = entry.name
        self.meta_text = f"Blender {entry.version}   ·   {entry.path}"
        self.is_lts = entry.is_lts
        self.can_launch = entry.can_launch
        self.action_text = tr("Launch")


class InstalledCard(BaseInstalledCard):
    """Versión instalada en modo lista (una fila)."""

    pass


class GridInstalledCard(BaseInstalledCard):
    """Versión instalada en modo rejilla (icono grande y botones debajo)."""

    pass


class RootWidget(BoxLayout):
    """Pantalla principal: cabecera, filtros, listas y pie con progreso/zoom."""

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

    def __init__(self, **kwargs):
        # Al llamar a super() se aplican ya las reglas del .kv, así que las
        # propiedades de arriba deben tener valores por defecto válidos.
        super().__init__(**kwargs)
        self.settings = settings_service.Settings.load()
        i18n.set_language(self.settings.language)
        self.system = detector.detect()
        self.platform_label = PLATFORM_LABELS.get(self.system.os_name, "GNU/Linux")
        # En Windows la API llama "amd64" a la arquitectura de 64 bits.
        self.arch_label = "x86_64" if self.system.arch in ("amd64", "x86_64") else self.system.arch
        self.language_label = tr(LANGUAGE_IDS.get(self.settings.language, "auto"))
        self.dest_folder = self.settings.dest_folder
        self.launch_args = self.settings.launch_args
        self.delete_archive = self.settings.delete_archive
        self.layout_mode = self.settings.layout_mode if self.settings.layout_mode in ("grid", "list") else "grid"
        try:
            self.zoom = min(MAX_ZOOM, max(MIN_ZOOM, float(self.settings.zoom)))
        except (TypeError, ValueError):
            self.zoom = 1.0
        self.downloader = Downloader()
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
        Clock.schedule_once(lambda dt: self.refresh(force=False), 0.1)
        Clock.schedule_once(lambda dt: self.refresh_installed(), 0.2)

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

    def set_platform(self, label):
        self.platform_label = label

    def set_arch(self, label):
        self.arch_label = label

    def set_channel(self, channel):
        self.channel = channel

    def set_search(self, text):
        self.search = text

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
        channel = self.channel
        if channel == "lts":
            # Solo las versiones con soporte de larga duración.
            builds = [build for build in builds if build.is_lts]
        elif channel == "stable":
            # Estables que no son LTS.
            builds = [build for build in builds if build.risk == "stable" and not build.is_lts]
        elif channel == "lts_stable":
            # LTS y estables a la vez (todo lo estable).
            builds = [build for build in builds if build.risk == "stable"]
        elif channel == "daily":
            builds = [build for build in builds if build.risk != "stable"]
        text = (self.search or "").strip().lower()
        if text:
            builds = [
                build for build in builds
                if text in build.version.lower() or text in build.branch.lower()
            ]
        return builds

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
            container.add_widget(self._placeholder(tr("No builds found")))
            return
        card_class = BuildCard if self.layout_mode == "list" else GridBuildCard
        for index, build in enumerate(builds):
            is_installed = installed_service.is_version_installed(self.installed, build.version)
            card = card_class()
            card.owner = self
            card.zoom = self.zoom
            # La tienda no lleva salteado; solo la pestaña de instaladas.
            card.row_color = self._row_color(is_installed, index)
            card.installed = is_installed
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
        """Aplica el canal y la búsqueda a las versiones instaladas.

        Las instaladas no guardan el "riesgo" de la compilación, así que lo
        deducimos del nombre de la carpeta: las de builder/diarias llevan
        'alpha', 'beta' o 'main'; el resto son estables.
        """
        entries = self.installed
        channel = self.channel
        if channel == "lts":
            entries = [entry for entry in entries if entry.is_lts]
        elif channel == "stable":
            entries = [entry for entry in entries if not entry.is_lts]
        elif channel == "daily":
            tokens = ("alpha", "beta", "main")
            entries = [
                entry for entry in entries
                if any(token in entry.name.lower() for token in tokens)
            ]
        # "all" y "lts_stable" muestran todas las instaladas.
        text = (self.search or "").strip().lower()
        if text:
            entries = [
                entry for entry in entries
                if text in entry.name.lower() or text in entry.version.lower()
            ]
        return entries

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
            container.add_widget(self._placeholder(tr("No installed versions found")))
            return
        card_class = InstalledCard if self.layout_mode == "list" else GridInstalledCard
        for index, entry in enumerate(entries):
            card = card_class()
            card.owner = self
            card.zoom = self.zoom
            card.row_color = self._row_color(True, index, zebra=True)
            card.entry = entry
            container.add_widget(card)

    def _placeholder(self, text):
        """Etiqueta que se muestra cuando una lista está vacía."""
        label = Label(text=text, color=MUTED, font_size="16sp")
        label.size_hint_y = None
        label.height = dp(80)
        return label

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

    def _set_progress(self, downloaded, total):
        if total:
            self.progress = max(0.0, min(100.0, downloaded * 100.0 / total))

    def install_build(self, build):
        """Descarga e instala una compilación, o lanza la ya instalada."""
        if build is None:
            return
        # Si esa versión concreta ya está instalada, simplemente la lanzamos.
        if installed_service.is_version_installed(self.installed, build.version):
            match = next(
                (entry for entry in self.installed
                 if version_tuple(entry.version) == version_tuple(build.version)),
                None,
            )
            if match is not None and match.can_launch:
                self.launch_installed(match)
            else:
                self._show_message(tr("No executable found"))
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
        self.status_text = tr("Extracting {name}", name=archive.name)

        def worker():
            try:
                target = extract(archive, self.settings.dest_folder)
                if self.settings.delete_archive:
                    archive.unlink(missing_ok=True)
                Clock.schedule_once(lambda dt: self._on_extract_done(target), 0)
            except Exception as error:
                Clock.schedule_once(lambda dt: self._on_download_error(str(error)), 0)

        threading.Thread(target=worker, daemon=True).start()

    def _on_extract_done(self, target):
        self.busy = False
        self.downloading = False
        self.progress = 0
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

    def _show_error(self, message):
        """Ventana modal con el detalle técnico de un error."""
        content = BoxLayout(orientation="vertical", padding=12, spacing=8)
        content.add_widget(Label(text=str(message)))
        button = Button(text=tr("Close"), size_hint_y=None, height=40)
        content.add_widget(button)
        popup = Popup(title=tr("Error"), content=content, size_hint=(0.7, 0.4))
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
        content.add_widget(Label(text=message))
        buttons = BoxLayout(size_hint_y=None, height=40, spacing=8)
        cancel = Button(text=tr("Cancel"))
        accept = Button(text=tr("Delete"))
        buttons.add_widget(cancel)
        buttons.add_widget(accept)
        content.add_widget(buttons)
        popup = Popup(title=title, content=content, size_hint=(0.6, 0.35))
        cancel.bind(on_release=popup.dismiss)

        def _accept(*_):
            popup.dismiss()
            on_confirm()

        accept.bind(on_release=_accept)
        popup.open()

    def browse_dest(self):
        """Abre el explorador y deja la carpeta elegida en el campo de texto."""
        input_widget = self.ids.get("dest_input")
        current = input_widget.text if input_widget is not None else self.settings.dest_folder

        def on_select(path):
            if input_widget is not None:
                input_widget.text = path

        self.browse_folder(current, on_select)

    def browse_folder(self, current, on_select):
        """Selector de carpetas (Kivy no trae uno nativo en el escritorio)."""
        view = ModalView(size_hint=(0.9, 0.9))
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)
        chooser = FileChooserListView(path=str(Path(current).expanduser().parent), dirselect=True)
        layout.add_widget(chooser)
        buttons = BoxLayout(size_hint_y=None, height=44, spacing=8)
        cancel = Button(text=tr("Cancel"))
        select = Button(text=tr("Save"))
        buttons.add_widget(cancel)
        buttons.add_widget(select)
        layout.add_widget(buttons)
        view.add_widget(layout)

        def _select(*_):
            selection = chooser.selection
            target = selection[0] if selection else chooser.path
            view.dismiss()
            on_select(target)

        cancel.bind(on_release=view.dismiss)
        select.bind(on_release=_select)
        view.open()

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
        self.settings.launch_args = launch_args or ""
        self.settings.save()
        i18n.set_language(self.settings.language)
        # Los textos del .kv se evalúan al construirse; si cambia el idioma
        # hay que volver a montar la interfaz para que se retraduzca.
        if i18n.get_language() != previous_language:
            self._reload_ui()
            return
        self.set_view("store")
        self.refresh_installed()
        self._show_message(tr("Ready"))

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
