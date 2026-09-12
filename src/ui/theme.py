"""Paleta de colores, tipografías y registro de la fuente de iconos.

Los colores imitan el *tema oscuro por defecto* de Blender (definido en el
archivo ``userdef_default_theme.c`` de su código fuente).

La idea de profundidad es la de Blender:

* el **fondo** de la ventana es el gris más oscuro;
* las **barras** (cabecera, barra lateral y de estado) y los **paneles/tarjetas**
  van un escalón por encima;
* los **botones** neutros son gris oscuro, como las pestañas de Blender;
* los **campos de texto** quedan hundidos (más oscuros que su panel).

Todos los valores van en RGBA entre 0 y 1, como espera Kivy.
"""

from kivy.core.text import LabelBase

from paths import ASSETS_DIR

# --- Jerarquía de grises (de más profundo a más elevado) ---
BG = (0x1D / 255, 0x1D / 255, 0x1D / 255, 1)        # fondo de la ventana (el más oscuro)
FIELD = (0x14 / 255, 0x14 / 255, 0x14 / 255, 1)     # campos de texto (hundidos)
BUTTON = (0x1D / 255, 0x1D / 255, 0x1D / 255, 1)    # botones neutros (como pestañas de Blender)
SURFACE = (0x30 / 255, 0x30 / 255, 0x30 / 255, 1)   # paneles y tarjetas
CHROME = (0x30 / 255, 0x30 / 255, 0x30 / 255, 1)    # cabecera, barra lateral y de estado
SURFACE_ALT = (0x3D / 255, 0x3D / 255, 0x3D / 255, 1)  # hover / contornos suaves
BORDER = (0x3D / 255, 0x3D / 255, 0x3D / 255, 1)

# --- Texto ---
TEXT = (0xE6 / 255, 0xE6 / 255, 0xE6 / 255, 1)
MUTED = (0x98 / 255, 0x98 / 255, 0x98 / 255, 1)
TEXT_SEL = (1.0, 1.0, 1.0, 1)

# --- Acentos y estados (tomados de Blender) ---
ACCENT = (0x47 / 255, 0x72 / 255, 0xB3 / 255, 1)      # azul de selección
ACCENT_DARK = (0x3A / 255, 0x5F / 255, 0x96 / 255, 1)
SUCCESS = (0x18 / 255, 0x86 / 255, 0x25 / 255, 1)     # verde (lanzar)
SUCCESS_DARK = (0x0F / 255, 0x5A / 255, 0x19 / 255, 1)
DANGER = (0x99 / 255, 0x16 / 255, 0x16 / 255, 1)      # rojo (desinstalar)
DANGER_DARK = (0x6E / 255, 0x10 / 255, 0x10 / 255, 1)
INFO = (0x28 / 255, 0x48 / 255, 0x7D / 255, 1)        # azul apagado (fondos)
WARNING = (0xFF / 255, 0xAF / 255, 0x23 / 255, 1)     # naranja (LTS)

# Variantes claras de verde/azul para usar como TEXTO sobre fondo oscuro
# (las de arriba son demasiado oscuras para leerlas en una tarjeta).
SUCCESS_TEXT = (0x6F / 255, 0xCF / 255, 0x7A / 255, 1)
INFO_TEXT = (0x7A / 255, 0xA7 / 255, 0xE0 / 255, 1)

# Fuente de iconos (Font Awesome Free). Se registra con un nombre lógico
# para poder usarla desde el .kv con font_name: "Icons".
ICON_FONT = "Icons"
ICON_TTF = str(ASSETS_DIR / "fonts" / "fa-solid-900.ttf")


def init() -> None:
    """Registra la fuente de iconos; debe llamarse antes de montar la interfaz."""
    LabelBase.register(name=ICON_FONT, fn_regular=ICON_TTF)
