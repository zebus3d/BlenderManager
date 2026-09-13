"""Diálogos, barra de progreso y contenedores de la pantalla de ajustes.

Kivy trae unos widgets por defecto (Popup, ProgressBar...) con un aspecto claro
que desentona con el tema oscuro de la app. Aquí heredamos de ellos para poder
darles nuestro estilo desde los archivos .kv.
"""

from kivy.properties import NumericProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.modalview import ModalView
from kivy.uix.popup import Popup
from kivy.uix.widget import Widget


class AppPopup(Popup):
    """Popup con el fondo, el título y el borde del tema de la app.

    El aspecto vive en la regla ``<AppPopup>`` de ``views/dialogs.kv``; aquí
    solo heredamos de Popup para que Kivy use esa regla en vez de la genérica.
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


class SettingsCard(BoxLayout):
    """Tarjeta de sección de la pantalla de ajustes."""

    pass


class SettingsHeader(BoxLayout):
    """Cabecera de una tarjeta de ajustes: icono + título."""

    icon = StringProperty("")
    title = StringProperty("")


class SettingsInput(BoxLayout):
    """Envoltorio redondeado de un campo de texto (igual que el buscador)."""

    pass
