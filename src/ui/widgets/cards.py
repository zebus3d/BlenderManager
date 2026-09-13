"""Tarjetas de compilaciones: la tienda y las versiones instaladas.

Cada tarjeta existe en dos versiones, una para la vista en lista (una fila) y
otra para la vista en rejilla (icono grande). Las dos comparten una clase base
con las propiedades y la lógica de relleno de textos.
"""

from kivy.properties import (
    BooleanProperty,
    ListProperty,
    NumericProperty,
    ObjectProperty,
    StringProperty,
)
from kivy.uix.boxlayout import BoxLayout

from i18n import tr
from ui.theme import SURFACE
from ui.tooltip import HoverBehavior


class BaseBuildCard(HoverBehavior, BoxLayout):
    """Base común para las tarjetas de compilaciones (vista lista y rejilla)."""

    build = ObjectProperty(None, allownone=True)
    owner = ObjectProperty(None, allownone=True)
    title = StringProperty("")
    channel_text = StringProperty("")
    version_text = StringProperty("")
    meta_text = StringProperty("")
    # Plataforma de destino que se añade a la línea de metadatos (vacía si es
    # la misma que la del equipo, para no repetirla en cada tarjeta).
    platform_text = StringProperty("")
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
        if build.experimental:
            # Las experimentales se identifican por el nombre de su rama (por
            # ejemplo "geometry-nodes"), que es lo que le interesa al usuario.
            # No se traduce: es un nombre técnico.
            self.channel_text = build.branch
            self.is_lts = False
        elif build.patch:
            # Las builds de patch son de una propuesta de cambios concreta:
            # mostramos su número de pull request.
            self.channel_text = build.patch
            self.is_lts = False
        else:
            if build.is_lts:
                channel = "LTS"
            elif build.risk in ("alpha", "daily", "beta"):
                channel = {"alpha": "Alpha", "daily": "Daily", "beta": "Beta"}[build.risk]
            else:
                channel = "Stable"
            self.channel_text = tr(channel)
            self.is_lts = build.is_lts
        # En experimentales y patch el nombre de la rama ya se ve como etiqueta
        # de canal, así que no lo repetimos en la línea de metadatos.
        details = [build.human_size]
        if not build.experimental and not build.patch:
            details.append(build.branch)
        if self.platform_text:
            details.append(self.platform_text)
        details.append(build.arch)
        self.meta_text = "  ·  ".join(details)
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
    version_text = StringProperty("")
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
        self.version_text = entry.version
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
