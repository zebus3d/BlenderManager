"""Widgets básicos y reutilizables.

Son las "piezas pequeñas" con las que se monta la interfaz: botones, pastillas
y el logo de la cabecera. Aquí está el comportamiento; su aspecto (colores,
bordes, degradados) vive en el archivo de vista ``views/widgets.kv``.
"""

import threading
import webbrowser

from kivy.metrics import dp
from kivy.properties import (
    AliasProperty,
    BooleanProperty,
    ListProperty,
    NumericProperty,
    StringProperty,
)
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget

from ui.theme import ACCENT, BUTTON
from ui.tooltip import HoverBehavior


class Pill(HoverBehavior, ToggleButton):
    """Botón con forma de pastilla para los filtros y el selector de vista."""

    pass


class SideButton(HoverBehavior, Button):
    """Botón cuadrado de la barra lateral (tienda, instaladas, ajustes).

    No usamos ToggleButton: el estado "activo" es solo visual y lo marca
    ``active`` desde el .kv, así que un clic siempre dispara ``on_release``
    (con ToggleButton + grupo el primer clic podía quedarse en el toggle).
    """

    active = BooleanProperty(False)


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


class IconLinkButton(HoverBehavior, Button):
    """Icono de información de una tarjeta (abre las notas de la versión).

    Se dibuja como el clásico disco azul con la "i" blanca: el círculo lo pinta
    el .kv (la fuente de iconos es de un solo color) y el glifo va encima.
    ``disc`` es el diámetro de ese círculo, en píxeles.
    """

    disc = NumericProperty(0)


class HoverButton(HoverBehavior, Button):
    """Botón normal con tooltip (por ejemplo, actualizar o borrar)."""

    pass


# Página del proyecto: se abre al pulsar el logo/título de la cabecera.
REPO_URL = "https://github.com/zebus3d/BlenderManager"


class HeaderLogo(HoverBehavior, BoxLayout):
    """Logo y título de la cabecera: al pulsar abre el repositorio en el navegador."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.tooltip_text = REPO_URL

    def _open_repo(self):
        # En un hilo aparte: webbrowser.open puede tardar (arranca el navegador)
        # y congelaría la interfaz mientras tanto.
        def worker():
            try:
                webbrowser.open(REPO_URL)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def on_touch_down(self, touch):
        if self.disabled or not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        if getattr(touch, "button", "left") not in ("left", None):
            return super().on_touch_down(touch)
        touch.grab(self)
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            if self.collide_point(*touch.pos):
                self._open_repo()
            return True
        return super().on_touch_up(touch)


class FolderRow(HoverBehavior, Button):
    """Fila del selector de carpetas: icono + nombre, al estilo de la app."""

    icon = StringProperty("")


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
