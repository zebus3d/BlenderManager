"""Sistema de tooltips (textos de ayuda al pasar el ratón).

Kivy no incluye tooltips nativos, así que montamos uno sencillo:

* ``Tooltip`` es la etiqueta flotante que se dibuja sobre la ventana.
* ``TooltipManager`` es un singleton que coloca y muestra/oculta esa etiqueta.
* ``HoverBehavior`` es el mixin que se añade a nuestros widgets: detecta
  cuándo el ratón entra o sale usando ``Window.mouse_pos`` y, tras un pequeño
  retardo, pide al gestor que muestre el texto.

Se enlaza y desenlaza del ratón en ``on_parent`` para que los widgets que se
reconstruyen (por ejemplo al cambiar un filtro) no dejen referencias colgando.
"""

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivy.uix.label import Label


class Tooltip(Label):
    """Etiqueta con fondo redondeado que se muestra junto al cursor."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (None, None)
        self.padding = (dp(9), dp(5))
        self.font_size = "13sp"
        self.color = (1, 1, 1, 1)
        self.opacity = 0
        self.disabled = True  # que no capture clics
        with self.canvas.before:
            Color(0.09, 0.09, 0.09, 0.96)
            self._background = RoundedRectangle(radius=[dp(6)])
        self.bind(texture_size=self._resize, pos=self._move)

    def _resize(self, *_):
        self.size = (
            self.texture_size[0] + self.padding[0] * 2,
            self.texture_size[1] + self.padding[1] * 2,
        )
        self._background.size = self.size

    def _move(self, *_):
        self._background.pos = self.pos


class TooltipManager:
    """Singleton que gobierna el tooltip compartido de toda la aplicación."""

    _instance = None

    @classmethod
    def get(cls) -> "TooltipManager":
        if cls._instance is None:
            cls._instance = TooltipManager()
        return cls._instance

    def __init__(self):
        self.tooltip = Tooltip()
        Window.add_widget(self.tooltip)

    def show(self, text: str, position) -> None:
        self.tooltip.text = text
        self.tooltip.texture_update()
        self.tooltip.opacity = 1
        self.tooltip.disabled = True
        # Nos aseguramos de que quede por encima del resto de widgets.
        if not Window.children or Window.children[0] is not self.tooltip:
            Window.remove_widget(self.tooltip)
            Window.add_widget(self.tooltip)
        self._place(position)

    def _place(self, position) -> None:
        offset = dp(16)
        x = position[0] + offset
        y = position[1] + offset
        if x + self.tooltip.width > Window.width:
            x = Window.width - self.tooltip.width - dp(6)
        if y + self.tooltip.height > Window.height:
            y = Window.height - self.tooltip.height - dp(6)
        self.tooltip.pos = (max(dp(4), x), max(dp(4), y))

    def hide(self) -> None:
        self.tooltip.opacity = 0
        self.tooltip.disabled = True


class HoverBehavior:
    """Mixin para widgets que muestran un tooltip al pasar el ratón por encima.

    Uso:
        class MiBoton(HoverBehavior, Button):
            pass
        # y en el .kv:  tooltip_text: tr("...")
    """

    tooltip_text = StringProperty("")
    tooltip_delay = NumericProperty(0.45)
    _hovering = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._tooltip_event = None
        self._tooltip_bound = False

    def on_parent(self, widget, parent):
        # Al entrar en el árbol enlazamos; al salir, desenlazamos y ocultamos.
        if parent is None:
            self._unbind_tooltip()
            self._hovering = False
            self._cancel_tooltip()
            TooltipManager.get().hide()
        else:
            self._bind_tooltip()

    def _bind_tooltip(self):
        if not self._tooltip_bound:
            Window.bind(mouse_pos=self._on_mouse_pos)
            self._tooltip_bound = True

    def _unbind_tooltip(self):
        if self._tooltip_bound:
            try:
                Window.unbind(mouse_pos=self._on_mouse_pos)
            except (ValueError, KeyError):
                pass
            self._tooltip_bound = False

    def _on_mouse_pos(self, window, position):
        if not self.get_root_window():
            return
        try:
            inside = self.collide_point(*self.to_widget(*position))
        except Exception:
            inside = False
        if inside:
            if not self._hovering:
                self._hovering = True
                self._schedule_tooltip()
        elif self._hovering:
            self._hovering = False
            self._cancel_tooltip()
            TooltipManager.get().hide()

    def _schedule_tooltip(self):
        self._cancel_tooltip()
        self._tooltip_event = Clock.schedule_once(self._display_tooltip, self.tooltip_delay)

    def _display_tooltip(self, dt):
        self._tooltip_event = None
        if self._hovering and self.tooltip_text:
            TooltipManager.get().show(self.tooltip_text, Window.mouse_pos)

    def _cancel_tooltip(self):
        if self._tooltip_event is not None:
            self._tooltip_event.cancel()
            self._tooltip_event = None
