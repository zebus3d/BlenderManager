"""Desplegables (spinners) con el aspecto de la app.

Los usamos para elegir la plataforma, la arquitectura y el idioma.
"""

from kivy.properties import BooleanProperty
from kivy.uix.dropdown import DropDown
from kivy.uix.spinner import Spinner, SpinnerOption

from ui.tooltip import HoverBehavior


class HoverSpinner(HoverBehavior, Spinner):
    """Selector desplegable con tooltip (plataforma, arquitectura, idioma)."""

    def on_is_open(self, instance, value):
        """Marca la opción que está activa al abrir la lista.

        El Spinner de Kivy no distingue la opción actual de las demás, así que
        al desplegar no se sabe cuál está puesta. Aquí se lo decimos a cada
        fila y el .kv la pinta con el azul apagado del tema.
        """
        super_on_is_open = getattr(super(), "on_is_open", None)
        if super_on_is_open is not None:
            super_on_is_open(instance, value)
        if not value:
            return
        dropdown = getattr(self, "_dropdown", None)
        container = getattr(dropdown, "container", None) if dropdown else None
        if container is None:
            return
        for option in container.children:
            if hasattr(option, "selected"):
                option.selected = option.text == self.text


class AppDropDown(DropDown):
    """Lista desplegable de un ``HoverSpinner`` con el aspecto de la app.

    La de Kivy es un panel negro sin borde con opciones muy altas; esta se
    dibuja como un menú de Blender: panel hundido, borde fino y filas
    compactas (el aspecto vive en la regla ``<AppDropDown>`` del .kv).
    """

    pass


class DarkSpinnerOption(HoverBehavior, SpinnerOption):
    """Fila de un desplegable. ``selected`` marca la opción activa."""

    selected = BooleanProperty(False)
