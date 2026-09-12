"""Paleta de colores, tipografías y registro de la fuente de iconos.

Todos los colores están en formato RGBA con valores entre 0 y 1, como espera
Kivy. El acento es el naranja característico de Blender.
"""

from kivy.core.text import LabelBase

from paths import ASSETS_DIR

# Fondos y superficies del tema oscuro.
BG = (0.129, 0.129, 0.129, 1)
SURFACE = (0.173, 0.173, 0.173, 1)
SURFACE_ALT = (0.224, 0.224, 0.224, 1)
BORDER = (0.290, 0.290, 0.290, 1)

# Texto.
TEXT = (0.929, 0.929, 0.929, 1)
MUTED = (0.620, 0.620, 0.620, 1)

# Colores de acento y de estado.
ACCENT = (0.918, 0.463, 0.000, 1)       # naranja Blender (descargar)
ACCENT_DARK = (0.737, 0.353, 0.000, 1)
SUCCESS = (0.361, 0.722, 0.361, 1)      # verde (lanzar)
DANGER = (0.863, 0.302, 0.243, 1)       # rojo (borrar)
INFO = (0.302, 0.600, 0.863, 1)         # azul (canal estable)
PURPLE = (0.557, 0.435, 0.875, 1)

# Fuente de iconos (Font Awesome Free). Se registra con un nombre lógico
# para poder usarla desde el .kv con font_name: "Icons".
ICON_FONT = "Icons"
ICON_TTF = str(ASSETS_DIR / "fonts" / "fa-solid-900.ttf")


def init() -> None:
    """Registra la fuente de iconos; debe llamarse antes de montar la interfaz."""
    LabelBase.register(name=ICON_FONT, fn_regular=ICON_TTF)
