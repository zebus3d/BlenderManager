"""Widgets de la interfaz y controlador principal de la aplicación.

Aquí vive toda la lógica de la pantalla: carga de ajustes, listado de
compilaciones de Blender, filtros, descarga/extracción en segundo plano,
lanzamiento de versiones instaladas y la navegación entre vistas.

Ojo: Kivy aplica las reglas del archivo .kv durante el __init__ del widget,
antes de que se ejecute el cuerpo de nuestro constructor. Por eso los datos
que consume la vista (carpeta destino, idioma, etc.) se exponen como
propiedades Kivy con valores por defecto y se rellenan después de super().__init__.
"""

import os
import shlex
import shutil
import subprocess
import sys
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
import version
from i18n import tr
from services import api, detector, installed as installed_service, settings as settings_service, updater
from services.downloader import Downloader, log as download_log
from services.extractor import extract, is_archive
from services.launcher import Launcher
from ui.theme import (
    ACCENT,
    ACCENT_DARK,
    BUTTON,
    CARD_DIM,
    CARD_DIM_ALT,
    DANGER,
    DANGER_DARK,
    MUTED,
    ROW_ALT,
    SURFACE,
)
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


class AppPopup(Popup):
    """Popup con el fondo, el título y el borde del tema de la app.

    El aspecto vive en la regla ``<AppPopup>`` de ``gui.kv``; aquí solo
    heredamos de Popup para que Kivy use esa regla en vez de la genérica.
    """

    pass


class AppModalView(ModalView):
    """ModalView con el fondo del tema (lo usa el selector de carpetas)."""

    pass


class AppProgressBar(Widget):
    """Barra de progreso con el aspecto del tema (no la de Kivy).

    No heredamos de ``ProgressBar`` porque su regla por defecto dibujaría el
    relleno verde de Kivy *además* del nuestro. Aquí solo exponemos las dos
    propiedades que se usan (``value`` y ``max``); el dibujo va en el .kv.
    """

    value = NumericProperty(0)
    max = NumericProperty(100)


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
        self.platform_label = PLATFORM_LABELS.get(self.system.os_name, "GNU/Linux")
        # En Windows la API llama "amd64" a la arquitectura de 64 bits.
        self.arch_label = "x86_64" if self.system.arch in ("amd64", "x86_64") else self.system.arch
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

    def set_platform(self, label):
        self.platform_label = label

    def set_arch(self, label):
        self.arch_label = label

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
            is_installed = installed_service.find_installed(self.installed, build) is not None
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
        button = self._dialog_button(tr("Close"))
        content.add_widget(button)
        popup = AppPopup(title=tr("Error"), content=content, size_hint=(0.7, 0.4))
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
        popup = AppPopup(title=title, content=content, size_hint=(0.6, 0.35))
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
        view = AppModalView(size_hint=(0.9, 0.9))
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)
        chooser = FileChooserListView(path=str(Path(current).expanduser().parent), dirselect=True)
        layout.add_widget(chooser)
        buttons = BoxLayout(size_hint_y=None, height=44, spacing=8)
        cancel = self._dialog_button(tr("Cancel"))
        select = self._dialog_button(tr("Save"), ACCENT, ACCENT_DARK)
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
        # También en modo fuente: ahora la comprobación usa el último tag del
        # checkout, así que ofrecerá git pull en vez de descargar un binario.
        if self.auto_update:
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
        # Modo fuente sobre un checkout git: se actualiza con git pull, sin
        # descargar ningún binario.
        if source is not None and updater.source_root() is not None:
            self._show_source_update(tag)
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
                         size_hint=(0.68, 0.45), auto_dismiss=False)

        def _error_text(reason):
            if reason == "dirty":
                return tr("You have local changes. Commit or stash them and try again.")
            return tr("Could not update. Run git pull manually.")

        def _done(ok, reason):
            if not ok:
                info.text = _error_text(reason)
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
        # auto_dismiss=False: mientras se descarga o se instala, un clic fuera
        # no debe dejar el proceso en marcha sin interfaz que lo cuente.
        popup = AppPopup(title=tr("Update available"), content=content,
                         size_hint=(0.7, 0.5), auto_dismiss=False)

        def _reset():
            state["downloading"] = False
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
