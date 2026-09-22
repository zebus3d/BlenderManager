"""Piezas que comparten la ventana principal y sus partes.

``MainWindow`` está repartida en varios módulos por responsabilidad (Ajustes,
biblioteca de carpetas, descargas, actualizaciones). Todos necesitan las
mismas tablas y un par de widgets, y viven aquí y no en ``main_window``
porque si no cada parte tendría que importar la ventana y la ventana a cada
parte: importación circular.
"""

from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QSlider, QStyle, QStyleOptionSlider

from ui import theme as t


PLATFORMS = {"GNU/Linux": "linux", "Windows": "windows", "macOS": "darwin"}
PLATFORM_LABELS = {value: key for key, value in PLATFORMS.items()}
ARCH_LABELS = ["x86_64", "arm64"]
LANGUAGE_IDS = {"auto": "Automatic", "en": "English", "es": "Spanish"}
MIN_ZOOM, MAX_ZOOM = 0.6, 1.8

# Alto de la fila de filtros (la que lleva las pestañas de canal). Vive en el
# tema porque Ajustes y Migración lo usan para dejar sus pestañas a la misma
# altura que las de canal.
FILTERS_HEIGHT = t.FILTERS_HEIGHT
# Alto de los controles de la fila de filtros (pastillas de vista y combos):
# el mismo que los tags de canal, para que la fila quede a ras.
FILTER_CONTROL_HEIGHT = t.CONTROL_HEIGHT

# Vistas que solo se ven con las opciones experimentales (Ajustes > Avanzado).
# Recientes y Migración salieron de aquí cuando quedaron probadas (Migración
# tiene la batería de tests de UI más grande de la app y feedback de usuarios
# reales); el gestor de add-ons sigue en desarrollo (arranca Blender para leer
# el estado).
EXPERIMENTAL_VIEWS = ("addons",)
# Cuánto sube/baja el zoom con Ctrl +/-. El slider va en pasos de 1 %.
ZOOM_STEP = 0.1

# Tamaño con el que se abre la ventana la primera vez y al restablecerla, y el
# mínimo por debajo del cual la interfaz se recorta.
# El alto (760) no es redondo por gusto: con el zoom al 80 % y 3 columnas
# (1060 px de ancho), 3 filas de tarjetas miden 585 px de contenido y hacen
# falta ~741 de ventana (72+44+40 de cabecera/filtros/pie). Con los 680 de antes
# la tercera fila quedaba cortada. Medido con `_grid_height(0.8) == 179`.
DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT = 1060, 760
MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT = 880, 540

# Tooltips de los filtros de canal. Se explican para quien no sabe qué es una
# LTS o una compilación diaria; las claves de i18n son estos textos en inglés.
# Los saltos de línea (\n) se ven en el tooltip, así que pueden ser varias
# líneas.
# Canales de la barra de filtros, en el orden en que se enseñan. Son
# excluyentes (solo se ve uno a la vez), así que van en una barra de pestañas
# y no en pastillas sueltas. Aquí solo viven las **etiquetas**: las claves son
# las de ``services.channels.CHANNELS`` y un test vigila que no se separen.
CHANNELS = (
    ("all", "All"),
    ("lts", "LTS"),
    ("stable", "Stable"),
    ("daily", "Daily"),
    ("experimental", "Experimental"),
    ("favorites", "Favorites"),
)

# Título que se enseña en la cabecera según la vista. La cabecera lleva arriba
# "Blender Manager" y debajo esto, para saber en qué sección se está.
SECTION_TITLES = {
    "installed": "Local",
    "store": "Cloud",
    "recent": "Recent files",
    "addons": "Add-ons",
    "migrate": "Migration",
    "settings": "Settings",
}

CHANNEL_TOOLTIPS = {
    "all": "Show every version: stable, LTS, daily and alpha.",
    "lts": "LTS = Long Term Support.\nVersions maintained for years and the "
           "most stable.\nRecommended for everyday work.",
    "stable": "Stable versions that are not LTS.\nThey are the latest official "
              "releases, supported until the next one.",
    "daily": "Daily and alpha builds with the newest changes.\nThey can fail: "
             "for testing, not for work.",
    "experimental": "Branches with new features still in development.\nThey are "
                    "not ready for production and the list is usually empty.",
    "favorites": "Only the versions you marked with the star.",
}


def write_problem(folder) -> str:
    """Motivo por el que no se puede escribir en ``folder``, o "" si sí se puede.

    Crea la carpeta si falta (que es lo que hará la descarga igualmente) y
    escribe y borra un fichero de prueba. Existe por un caso real: con la
    carpeta de las LTS en otro disco, si no había permiso de escritura la
    descarga terminaba en un genérico "Fallo en la descarga" y no había forma
    de saber que era eso. Mejor decirlo antes de bajar cientos de MB.
    """
    path = Path(folder).expanduser()
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".blendermanager-write-test"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
    except OSError as error:
        return str(error)
    return ""



class WorkerBridge(QObject):
    """Reenvía callbacks de hilos de descarga al hilo de la interfaz.

    Tocar widgets desde un hilo que no es el de la interfaz cuelga Qt: el
    hilo emite estas señales y Qt las entrega en el hilo bueno.
    """

    progress = Signal(int, int)
    done = Signal(str)
    error = Signal(str)


class ZoomSlider(QSlider):
    """Slider del zoom que vuelve al valor por defecto con ``Ctrl`` + clic.

    ``QSlider`` no distingue el clic normal del clic con modificadores, así que
    hay que mirarlo en ``mousePressEvent``.

    Y en la ranura, ``QSlider`` da un ``pageStep`` (10 % de zoom, medido) en vez
    de llevar el tirador al punto pulsado. Aquí se mapea la coordenada a un valor
    —el tirador queda justo bajo el cursor, y sigue ahí mientras se arrastra—,
    que es lo que se espera de un deslizador. El dibujo sigue en ``qss.py``.
    """

    reset_requested = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # El tirador mide 16 px de alto, pero la diana la marca el widget: con
        # los 15 px por defecto queda por debajo del mínimo de 24 px (WCAG 2.5.8).
        # La fila de la cabecera ya mide 32 px, así que subirlo no mueve nada.
        self.setMinimumHeight(24)
        self._drag_active = False

    def _sub_rect(self, sub_control):
        """Rectángulo de una parte del slider (ranura o tirador) ya maquetado."""
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        return self.style().subControlRect(
            QStyle.CC_Slider, option, sub_control, self)

    def _value_at(self, x):
        """Valor cuyo tirador queda centrado en la coordenada ``x``."""
        groove = self._sub_rect(QStyle.SC_SliderGroove)
        handle = self._sub_rect(QStyle.SC_SliderHandle)
        span = groove.width() - handle.width()
        if span <= 0:
            return self.value()
        value = QStyle.sliderValueFromPosition(
            self.minimum(), self.maximum(),
            x - groove.left() - handle.width() // 2, span)
        return min(self.maximum(), max(self.minimum(), value))

    def mousePressEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            self.reset_requested.emit()
            event.accept()
            return
        self._drag_active = True
        self.setSliderDown(True)
        self.setValue(self._value_at(event.position().toPoint().x()))
        event.accept()

    def mouseMoveEvent(self, event):
        if not self._drag_active:
            super().mouseMoveEvent(event)
            return
        self.setValue(self._value_at(event.position().toPoint().x()))
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag_active:
            self._drag_active = False
            self.setSliderDown(False)
            event.accept()
            return
        super().mouseReleaseEvent(event)
