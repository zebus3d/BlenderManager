"""Paleta de colores y tipografías (versión PySide6).

Los colores imitan el *tema oscuro por defecto* de Blender. La idea de
profundidad es la de Blender:

* el **fondo** de la ventana es el gris más oscuro;
* las **barras** (cabecera, barra lateral y de estado) y los **paneles/tarjetas**
  van un escalón por encima;
* los **botones** neutros son gris oscuro, como las pestañas de Blender;
* los **campos de texto** quedan hundidos (más oscuros que su panel).

Los valores van como cadenas ``#RRGGBB`` (para QSS) y se exponen helpers para
obtener ``QColor`` cuando hace falta pintar a mano.

Cambio respecto a la era Kivy (medido con la fórmula de contraste WCAG):
las constantes ``ACCENT``/``DANGER`` se usan para **bordes e indicadores**
(solo necesitan 3:1), y los **rellenos de botón** usan ``ACCENT_BTN`` /
``DANGER_BTN``, que dejan el texto claro por encima de 4,5:1 (AA).
"""

from PySide6.QtGui import QColor

# --- Jerarquía de grises (de más profundo a más elevado) ---
BG = "#1D1D1D"          # fondo de la ventana (el más oscuro)
FIELD = "#171717"       # campos de texto (hundidos)
BUTTON = "#585858"      # botones neutros
BUTTON_HOVER = "#6A6A6A"  # botones neutros con texto, al pasar el ratón
FILTER = "#1D1D1D"      # botones de filtro
SURFACE = "#303030"     # paneles y tarjetas
CHROME = "#303030"      # cabecera, barra lateral y de estado
CARD_DIM = "#262626"    # por descargar (clara; se distingue del BG, pero
                        # queda por debajo de SURFACE, que son las instaladas)
CARD_DIM_ALT = "#202020"  # por descargar (oscura)
ROW_ALT = "#2A2A2A"     # instalada (oscura)
SURFACE_ALT = "#3D3D3D"  # hover / contornos suaves
BORDER = "#3D3D3D"
# Tarjeta **encima de un canvas gris**, un escalón por encima de SURFACE.
# Comparte valor con SURFACE_ALT a propósito: es el mismo escalón de
# profundidad del tema. Hoy no lo usa ninguna vista (Migración y Ajustes
# pasaron a fondo oscuro con tarjetas en SURFACE), pero se queda como parte de
# la escala de grises.
SURFACE_HIGH = "#3D3D3D"

# --- Texto ---
TEXT = "#E6E6E6"
MUTED = "#989898"
TEXT_SEL = "#FFFFFF"

# --- Acentos y estados ---
ACCENT = "#5085B1"          # azul de selección/resaltado (bordes e indicadores)
ACCENT_DARK = "#3F6F96"     # hover
ACCENT_BTN = "#356089"      # relleno de botón primario (TEXT = 5,28:1, AA)
DANGER = "#B84A4A"          # rojo para bordes/indicadores
DANGER_DARK = "#9C3C3C"     # hover
DANGER_BTN = "#9C3C3C"      # relleno del botón borrar (TEXT = 5,38:1, AA)
DANGER_EDGE = "#F0A0A0"     # borde claro del realce de la papelera: sobre el
                            # rojo vivo (#B84A4A) el borde oscuro no se veía
DANGER_ICON = "#FFC0C0"     # glifo de la papelera al pasar por encima: blanco
                            # teñido de rojo, para que el realce avise de verdad
                            # (sobre DANGER = 3,3:1, suficiente para un icono)
WARNING = "#FFAF23"         # naranja (LTS)
SUCCESS_TEXT = "#6FCF7A"    # verde claro para texto
INFO_TEXT = "#7AA7E0"       # azul claro para texto
INFO_DISC = "#45729B"       # disco del icono de información

# Colores con alfa (para QSS: rgba)
OVERLAY = "rgba(0,0,0,0.6)"

# --- Métricas de la interfaz ---
# Alto de la fila de filtros (la de las pestañas de canal). Migración y Ajustes
# lo usan para bajar su tira de pestañas y que las tres filas terminen a la
# misma altura al cambiar de vista.
FILTERS_HEIGHT = 50
# Margen superior de las tiras de pestañas (Migración y Ajustes) para que su
# **borde de arriba** quede a la altura del primer botón de la barra lateral y
# de los tags de canal. Se alinea por arriba, no por abajo: las pestañas y los
# tags no miden lo mismo.
TABS_TOP = 14
# Alto de los controles de la fila de filtros (pastillas de canal, rejilla/lista,
# desplegables) **y** de las pestañas de Migración y Ajustes: todo lo que se
# lee como "una pestaña o un filtro" mide lo mismo, aunque viva en filas
# distintas. Antes cada una salía de su padding y las de Migración/Ajustes
# quedaban 1 px más bajas que las pastillas.
CONTROL_HEIGHT = 28

# --- Tipografía ---
FONT_SIZE = 13
FONT_FAMILY = "sans-serif"

# --- Fuente de iconos (Font Awesome Free) ---
ICON_FONT_FILE = "fa-solid-900.ttf"


def luminance(token: str) -> float:
    """Luminancia relativa WCAG de un ``#RRGGBB``."""
    token = token.lstrip("#")
    channels = [int(token[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    channels = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                for c in channels]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast(a: str, b: str) -> float:
    """Ratio de contraste WCAG entre dos ``#RRGGBB`` (para tests)."""
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)
