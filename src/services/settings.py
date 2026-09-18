"""Ajustes persistentes de la aplicación.

Prioridad de ubicación:

1. **Modo portable**: si hay un archivo marcador (``portable``, ``portable.txt``
   o ``.portable``) junto al ejecutable, los ajustes viven ahí. Ideal para
   llevar la aplicación en un pendrive.
2. **Modo normal**: en la carpeta de configuración del usuario
   (XDG en Linux, AppData en Windows, Application Support en macOS).
"""

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from paths import APP_DIR

APP_NAME = "BlenderManager"
PORTABLE_MARKERS = ("portable", "portable.txt", ".portable")


def write_json_atomic(path: Path, payload, indent=None) -> Path:
    """Guarda un JSON sin dejar el archivo a medias si algo falla.

    Escribimos primero en un ``.tmp`` al lado y solo entonces lo movemos encima
    del definitivo: ``os.replace`` es atómico dentro del mismo sistema de
    archivos, así que un corte de luz o un disco lleno dejan intacto el
    contenido anterior en lugar de un JSON truncado.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=indent), encoding="utf-8")
    os.replace(temporary, path)
    return path


def config_dir() -> Path:
    """Devuelve la carpeta donde se guardan los ajustes."""
    for marker in PORTABLE_MARKERS:
        if (APP_DIR / marker).exists():
            return APP_DIR
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    if sys.platform.startswith("darwin"):
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_NAME.lower()


def is_portable() -> bool:
    """True si hay un marcador ``portable`` junto al ejecutable."""
    return config_dir() == APP_DIR


def cache_dir() -> Path:
    """Carpeta para el caché del listado y los registros (logs)."""
    if is_portable():
        return APP_DIR / "cache"
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_NAME / "cache"
    if sys.platform.startswith("darwin"):
        return Path.home() / "Library" / "Caches" / APP_NAME
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / APP_NAME.lower()


# Carpeta conocida "Descargas" de Windows (FOLDERID_Downloads). El usuario puede
# haberla movido a otro disco, y eso lo dice el registro, no %USERPROFILE%.
_WINDOWS_DOWNLOADS_GUID = "{374DE290-123F-4565-9164-39C4925E467B}"
_WINDOWS_SHELL_FOLDERS = (
    r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")


def _downloads_dir() -> Path:
    """Carpeta de Descargas del usuario, tal y como la ve el sistema.

    * **Windows**: se lee la carpeta conocida del registro y se expanden las
      variables (``%USERPROFILE%``); así funciona aunque la hayan movido a otro
      disco. Si no se puede leer, ``~/Downloads``.
    * **macOS**: siempre ``~/Downloads``.
    * **Linux**: ``~/Downloads`` y, si no existe, ``~/Descargas`` (los
      directorios XDG pueden estar en el idioma del usuario).
    """
    home = Path.home()
    if sys.platform.startswith("win"):
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                _WINDOWS_SHELL_FOLDERS) as key:
                value, _ = winreg.QueryValueEx(key, _WINDOWS_DOWNLOADS_GUID)
            moved = Path(os.path.expandvars(value))
            if moved.is_dir():
                return moved
        except OSError:
            pass
        return home / "Downloads"
    downloads = home / "Downloads"
    if not downloads.exists() and (home / "Descargas").exists():
        downloads = home / "Descargas"
    return downloads


def default_destination() -> Path:
    """Carpeta de descargas propuesta la primera vez."""
    return _downloads_dir() / "Blenders"


# Zoom con el que arranca la rejilla y valor de fábrica del "restablecer".
# El usuario puede elegir a qué zoom vuelven Ctrl+0 y el clic con Ctrl en el
# slider (``reset_zoom``); esto solo es lo que se propone la primera vez.
DEFAULT_ZOOM = 0.8

# Filtros de canal que ofrece la barra. Son los que entiende
# ``api.filter_builds``/``installed.filter_installed``; aquí solo se usan para
# validar el que se guardó la última vez.
CHANNELS = ("all", "lts", "stable", "daily", "experimental", "favorites")

# Cada cuánto se comprueba si hay una versión nueva de la propia aplicación (en
# minutos). Las comprobaciones repetidas usan el ETag de GitHub, así que cuando
# nada ha cambiado la respuesta es un 304 y **no gasta cuota** de la API.
UPDATE_INTERVALS = (1, 5, 15, 30, 60, 180)
DEFAULT_UPDATE_INTERVAL = 30


def _clean_string_list(value) -> list[str]:
    """Normaliza una lista de textos del JSON: solo cadenas, sin repetir.

    Un settings.json editado a mano no debería tumbar la app ni colar un tipo
    raro en una lista que se recorre en cada repintado.
    """
    if not isinstance(value, list):
        return []
    cleaned = []
    for item in value:
        if isinstance(item, str) and item and item not in cleaned:
            cleaned.append(item)
    return cleaned


@dataclass
class Settings:
    """Ajustes persistentes (por usuario, o por carpeta en modo
    portable).
    """
    dest_folder: str = ""
    # Carpeta opcional solo para las versiones LTS. Mucha gente tiene el disco
    # de trabajo (a menudo un SSD, "C:") separado del de datos ("D:"), y le
    # interesa tener ahí las versiones de soporte largo sin mover el resto.
    # ``separate_lts`` es el interruptor: la carpeta se recuerda aunque lo
    # apagues, para no perder la ruta elegida.
    lts_folder: str = ""
    separate_lts: bool = False
    language: str = "auto"
    delete_archive: bool = True
    launch_args: str = ""
    layout_mode: str = "grid"
    zoom: float = DEFAULT_ZOOM
    # Valor al que vuelve la rejilla con Ctrl+0 o Ctrl+clic en el slider. Es
    # distinto de ``zoom`` (que es "lo que tengo puesto ahora"): este es el
    # destino del "restablecer", que el usuario puede elegir en los ajustes.
    reset_zoom: float = DEFAULT_ZOOM
    auto_update: bool = True
    # Interruptor propio del chequeo periódico (independiente del de arranque):
    # así se puede seguir avisando al abrir sin repetir cada X minutos.
    periodic_update: bool = True
    # Cada cuántos minutos se busca una versión nueva de la app.
    update_interval_min: int = DEFAULT_UPDATE_INTERVAL
    # Versión (tag) de la que el usuario pidió no volver a avisar desde el
    # diálogo de actualización. El chequeo manual ("Buscar ahora") la muestra
    # igual, y una versión más nueva sí se ofrece: esto solo silencia las
    # automáticas. Se guarda el tag exacto, así que un lanzamiento posterior no
    # queda tapado por haber saltado el anterior.
    skipped_version: str = ""
    # Series de Blender (mayor.menor, p. ej. "5.2") para las que el usuario
    # pulsó "Nunca" en el aviso de actualización: no se le vuelve a ofrecer
    # actualizar esas instaladas. Se puede reactivar desde Ajustes.
    ignored_blender_series: list[str] = field(default_factory=list)
    window_width: int = 0
    window_height: int = 0
    # Bandeja del sistema. Son dos decisiones independientes: cerrar la ventana
    # (la X) es lo que más molesta si la app se cierra sin querer, así que viene
    # activado; minimizar a la bandeja es más agresivo y viene apagado (muchos
    # usuarios esperan que minimizar mande a la barra de tareas).
    close_to_tray: bool = True
    minimize_to_tray: bool = False
    # Si ya se enseñó el aviso "sigue en la bandeja" la primera vez que se
    # ocultó. Se guarda para no repetirlo en cada apertura.
    tray_hint_shown: bool = False
    # Arrancar directamente en la bandeja, sin enseñar la ventana. Es lo que
    # hace útil el autoarranque: la app queda a mano sin molestar al iniciar
    # la sesión. No confundir con el autoarranque en sí, que no es un ajuste
    # nuestro sino que vive en el sistema (ver ``services/autostart.py``).
    start_minimized: bool = False
    # Plataforma y arquitectura de destino elegidas en la barra de filtros.
    # Vacías = usar las del propio equipo (lo detecta ``detector``). Se guardan
    # para poder descargar builds de otra plataforma de forma repetida, por
    # ejemplo para copiarlas en un USB.
    platform: str = ""
    arch: str = ""
    # Filtro de canal que estaba puesto al cerrar: al abrir se vuelve a él
    # (p. ej. si lo dejaste en Favoritos, sigues en Favoritos).
    channel: str = "all"
    # Series marcadas como favoritas (claves de ``model.build.favorite_key``:
    # "rama|versión"). En la lista se permiten las que ya no existan: si Blender
    # deja de publicar una rama, el favorito no estorba.
    favorites: list[str] = field(default_factory=list)

    @classmethod
    def load(cls) -> "Settings":
        """Lee los ajustes del disco.

        Si el JSON falta o está roto se usan los valores por defecto:
        preferimos eso a no arrancar.
        """
        path = config_dir() / "settings.json"
        data = {}
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                # Si el archivo está corrupto preferimos valores por defecto
                # antes que impedir el arranque.
                data = {}
        try:
            interval = int(data.get("update_interval_min", DEFAULT_UPDATE_INTERVAL))
        except (TypeError, ValueError):
            # Un valor no numérico editado a mano no puede impedir el arranque.
            interval = DEFAULT_UPDATE_INTERVAL
        settings = cls(
            dest_folder=str(data.get("dest_folder") or ""),
            lts_folder=str(data.get("lts_folder") or ""),
            separate_lts=bool(data.get("separate_lts", False)),
            language=str(data.get("language") or "auto"),
            delete_archive=bool(data.get("delete_archive", True)),
            launch_args=str(data.get("launch_args") or ""),
            layout_mode=str(data.get("layout_mode") or "grid"),
            zoom=float(data.get("zoom") or DEFAULT_ZOOM),
            reset_zoom=float(data.get("reset_zoom") or DEFAULT_ZOOM),
            auto_update=bool(data.get("auto_update", True)),
            periodic_update=bool(data.get("periodic_update", True)),
            update_interval_min=interval,
            skipped_version=str(data.get("skipped_version") or ""),
            ignored_blender_series=_clean_string_list(
                data.get("ignored_blender_series")),
            close_to_tray=bool(data.get("close_to_tray", True)),
            minimize_to_tray=bool(data.get("minimize_to_tray", False)),
            tray_hint_shown=bool(data.get("tray_hint_shown", False)),
            start_minimized=bool(data.get("start_minimized", False)),
            window_width=int(data.get("window_width") or 0),
            window_height=int(data.get("window_height") or 0),
            platform=str(data.get("platform") or ""),
            arch=str(data.get("arch") or ""),
            channel=str(data.get("channel") or "all"),
            favorites=_clean_string_list(data.get("favorites")),
        )
        if not settings.dest_folder:
            settings.dest_folder = str(default_destination())
        if settings.channel not in CHANNELS:
            # Ajustes editados a mano (o de una versión con otros filtros).
            settings.channel = "all"
        if settings.update_interval_min not in UPDATE_INTERVALS:
            # Un valor raro (editado a mano) no puede dejar el temporizador con
            # un intervalo absurdo o negativo.
            settings.update_interval_min = DEFAULT_UPDATE_INTERVAL
        return settings

    def destination_for(self, is_lts: bool) -> str:
        """Carpeta donde se instala una compilación, según sea LTS o no.

        Si el usuario separó las LTS en otra carpeta, ahí van; todo lo demás (y
        todo si la opción está apagada o la carpeta está vacía) a la de siempre.
        La decisión vive aquí, y no en la interfaz, para poder probarla sin Qt.
        """
        lts = self.lts_folder.strip()
        if is_lts and self.separate_lts and lts:
            return lts
        return self.dest_folder

    def folders(self) -> list[str]:
        """Todas las carpetas donde puede haber versiones instaladas.

        Si las LTS viven aparte hay que escanear las dos. La carpeta LTS se
        incluye aunque el interruptor esté apagado: si se desactiva, las LTS ya
        instaladas ahí no deben desaparecer de la lista, solo se dejan de
        mandar las nuevas. Cuando coincide con la de destino no se repite.
        """
        folders = [self.dest_folder]
        lts = self.lts_folder.strip()
        if lts and lts != self.dest_folder:
            folders.append(lts)
        return folders

    def set_favorite(self, key: str, marked: bool) -> bool:
        """Marca o desmarca una serie y devuelve si ha cambiado algo.

        Se fija el estado en vez de alternarlo para que la interfaz no dependa
        de en qué orden lleguen las señales: si la estrella ya estaba así, esto
        no hace nada.
        """
        if not key:
            return False
        current = list(self.favorites)
        if marked and key not in current:
            current.append(key)
        elif not marked and key in current:
            current.remove(key)
        else:
            return False
        self.favorites = current
        return True

    def save(self) -> Path:
        """Guarda los ajustes de forma atómica (un temporal y luego
        ``os.replace``).
        """
        return write_json_atomic(config_dir() / "settings.json", asdict(self), indent=2)
