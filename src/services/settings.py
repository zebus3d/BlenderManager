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
from services import channels

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
DEFAULT_ZOOM = 0.6

# Filtros de canal que ofrece la barra. Se reexportan desde ``channels``, que
# es donde viven: aquí solo hacen falta para validar el que se guardó la última
# vez, y tener una segunda copia era pedir que se desincronizaran.
CHANNELS = channels.CHANNELS

# Cada cuánto se comprueba si hay una versión nueva de la propia aplicación (en
# minutos). Las comprobaciones repetidas usan el ETag de GitHub, así que cuando
# nada ha cambiado la respuesta es un 304 y **no gasta cuota** de la API.
UPDATE_INTERVALS = (1, 5, 15, 30, 60, 180)
DEFAULT_UPDATE_INTERVAL = 30


# Versión del esquema de ``settings.json``. Sube cuando cambia la forma del
# fichero y hay que convertir el de la versión anterior. Sirve para distinguir
# "esto viene de una app vieja" de "el usuario se quedó sin carpetas": sin el
# número, una lista vacía legítima se volvería a migrar en cada arranque.
SETTINGS_VERSION = 2


@dataclass
class Folder:
    """Una carpeta de la biblioteca: dónde está, qué recibe y si se escribe.

    ``types`` son los tipos de compilación que se descargan aquí (un
    subconjunto de ``channels.BUILD_TYPES``); vacío significa "solo se escanea,
    aquí no baja nada". ``writable`` es el candado: en falso, la aplicación no
    escribe **nada** en esta carpeta —ni descarga, ni borra, ni renombra, ni
    limpia parciales—, aunque sus versiones se sigan viendo y lanzando.

    **Invariante**: si ``writable`` es falso, ``types`` está vacío. No se puede
    recibir una descarga en una carpeta donde no se escribe, así que cerrar el
    candado apaga las casillas. Gracias a eso los dos controles no se pisan:
    las casillas dicen *qué se descarga aquí* y el candado *si se puede tocar
    algo aquí*.
    """

    path: str = ""
    types: list[str] = field(default_factory=list)
    writable: bool = True

    def expanded(self) -> Path:
        """La ruta con el ``~`` ya expandido."""
        return Path(self.path).expanduser()

    def takes(self, build_type: str) -> bool:
        """True si las compilaciones de ese tipo se descargan aquí."""
        return self.writable and build_type in self.types


def folder_from_dict(data) -> "Folder | None":
    """Reconstruye una ``Folder`` del JSON, o ``None`` si no hay nada que sacar.

    ``asdict`` sabe bajar la lista de dataclasses al guardar, pero la vuelta hay
    que hacerla a mano, igual que con el resto de campos.
    """
    if not isinstance(data, dict):
        return None
    path = str(data.get("path") or "").strip()
    if not path:
        return None
    writable = bool(data.get("writable", True))
    types = [item for item in _clean_string_list(data.get("types"))
             if item in channels.BUILD_TYPES]
    return Folder(path=path, types=types if writable else [], writable=writable)


def clean_folders(raw) -> list[Folder]:
    """Sanea la lista de carpetas del JSON.

    Es la única puerta de entrada, y existe por lo mismo que
    ``_clean_string_list``: un ``settings.json`` editado a mano (o de una
    versión futura) no puede tumbar la aplicación ni, peor aún, dejar dos
    carpetas peleándose por el mismo tipo y que las descargas acaben en una u
    otra según el orden.

    Por eso aquí se aplica la **exclusión mutua**: cada tipo tiene un único
    dueño y, si dos carpetas lo marcan, se lo queda la primera. La interfaz ya
    impide llegar a ese estado; esto es la red de seguridad.
    """
    if not isinstance(raw, list):
        return []
    folders: list[Folder] = []
    seen: set[str] = set()
    taken: set[str] = set()
    for item in raw:
        folder = folder_from_dict(item)
        if folder is None:
            continue
        key = channels.normalize_path(folder.path)
        if key in seen:
            continue
        seen.add(key)
        folder.types = [build_type for build_type in channels.BUILD_TYPES
                        if build_type in folder.types
                        and build_type not in taken]
        taken.update(folder.types)
        folders.append(folder)
    return folders


def folders_from_legacy(data: dict) -> list[Folder]:
    """Convierte los tres campos sueltos del esquema 1 en la biblioteca.

    **Regla de oro: no se mueve ni un byte.** Cada carpeta que hoy se escanea
    se sigue escaneando, y cada tipo de compilación acaba exactamente en la
    misma carpeta en la que acababa antes.

    La carpeta de las LTS se decide **antes** que la de siempre, aunque vaya
    después en la lista: la de siempre se queda con "todo lo que no tenga
    carpeta propia", que es literalmente lo que hacía
    ``destination_for(is_lts)``. Hacerlo al revés —darle los cuatro tipos y
    confiar en que la siguiente le quite el suyo— no funciona, porque la
    exclusión mutua de ``clean_folders`` es "el primero se lo queda" y la
    carpeta de las LTS se quedaba sin su tipo.

    Dos matices que se pierden a propósito, porque con una lista ya no hacen
    falta: una carpeta LTS con el interruptor apagado pasa a ser una carpeta
    sin tipos (se escanea, no recibe), y una carpeta extra apagada desaparece
    (volver a añadirla es un clic, y guardar rutas que nadie mira era una
    herencia de no tener lista).
    """
    entries = []
    lts = str(data.get("lts_folder") or "").strip()
    destination = str(data.get("dest_folder") or "").strip()
    # Apuntar la carpeta de las LTS a la de siempre era una forma de no
    # separarlas: hay una sola carpeta, y tiene que quedarse con todo. Si no se
    # mirase, el dedup se llevaría la segunda entrada y las LTS se quedarían
    # sin ninguna carpeta que las reciba.
    separate = (bool(lts) and bool(data.get("separate_lts"))
                and channels.normalize_path(lts)
                != channels.normalize_path(destination))
    resto = [build_type for build_type in channels.BUILD_TYPES
             if not (separate and build_type == channels.TYPE_LTS)]
    entries.append(Folder(path=destination or str(default_destination()),
                          types=resto, writable=True))
    if lts:
        entries.append(Folder(
            path=lts,
            types=[channels.TYPE_LTS] if separate else [],
            writable=True))
    extra = str(data.get("extra_folder") or "").strip()
    if extra and data.get("use_extra_folder"):
        entries.append(Folder(path=extra, types=[], writable=False))
    return clean_folders([asdict(entry) for entry in entries])


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
    # Esquema del fichero. Lo escribe ``save()`` y lo lee ``load()`` para saber
    # si hay que convertir un settings.json de una versión anterior.
    settings_version: int = SETTINGS_VERSION
    # La biblioteca de carpetas. Cada una dice qué tipos de compilación recibe
    # y si se puede escribir en ella (ver ``Folder``). Sustituye a los antiguos
    # ``dest_folder`` / ``lts_folder`` + ``separate_lts`` / ``extra_folder`` +
    # ``use_extra_folder``, que solo sabían expresar "las LTS aparte"; el caso
    # que lo motivó —tener las LTS en un SSD rápido y el resto en un disco
    # lento— sigue siendo una carpeta con el tipo "lts" marcado.
    folders: list[Folder] = field(default_factory=list)
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
    # Si ya se enseñó el aviso de que las carpetas ahora son una lista. Solo lo
    # ven quienes vienen del esquema viejo: en una instalación nueva no hay
    # nada que explicar, porque la pantalla se ve igual que siempre.
    folders_hint_shown: bool = True

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
            folders_hint_shown=bool(data.get("folders_hint_shown", True)),
        )
        # La biblioteca de carpetas: o se lee, o se convierte la del esquema
        # viejo. El número de versión es lo que distingue "vengo de una app
        # anterior" de "me he quedado sin carpetas": sin él, alguien que las
        # borrara todas se las vería reaparecer en el siguiente arranque.
        if data and int(data.get("settings_version") or 1) < SETTINGS_VERSION:
            settings.folders = folders_from_legacy(data)
            # Viene de una versión anterior: se le explica una vez. Una
            # instalación nueva (``data`` vacío) no ve nada.
            settings.folders_hint_shown = bool(data.get("folders_hint_shown"))
        else:
            settings.folders = clean_folders(data.get("folders"))
        if not settings.folders:
            # Primer arranque (o fichero irrecuperable): una sola carpeta que
            # se queda con todo, que es como se comportaba la app de siempre.
            settings.folders = [Folder(path=str(default_destination()),
                                       types=list(channels.BUILD_TYPES),
                                       writable=True)]
        if settings.channel not in CHANNELS:
            # Ajustes editados a mano (o de una versión con otros filtros).
            settings.channel = "all"
        if settings.update_interval_min not in UPDATE_INTERVALS:
            # Un valor raro (editado a mano) no puede dejar el temporizador con
            # un intervalo absurdo o negativo.
            settings.update_interval_min = DEFAULT_UPDATE_INTERVAL
        return settings

    def destination_for(self, build) -> str:
        """Carpeta donde se instala esa compilación, o ``""`` si no hay ninguna.

        La decisión vive aquí, y no en la interfaz, para poder probarla sin Qt.
        Devolver ``""`` no es un error que tragarse: significa que el usuario no
        ha marcado ninguna carpeta para ese tipo, y quien llame tiene que
        decírselo en vez de inventarse un destino (ver ``channels``).
        """
        return channels.resolve_destination(self.folders,
                                            channels.type_of_build(build))

    def destination_for_type(self, build_type: str) -> str:
        """Como ``destination_for`` pero partiendo del tipo ya calculado."""
        return channels.resolve_destination(self.folders, build_type)

    def install_folders(self) -> list[Folder]:
        """Carpetas donde la aplicación instala algo (las que reciben tipos).

        Es la lista que hay que recorrer para limpiar descargas a medias: un
        ``.part`` solo puede aparecer donde se descarga.
        """
        return [folder for folder in self.folders if folder.types]

    def folder_for(self, path) -> "Folder | None":
        """La carpeta de la biblioteca que contiene esa ruta, o ``None``.

        Sirve para saber si una versión instalada vive en una carpeta con el
        candado cerrado (y entonces no se puede borrar ni renombrar).
        """
        key = channels.normalize_path(path)
        if not key:
            return None
        for folder in self.folders:
            if channels.normalize_path(folder.path) == key:
                return folder
        return None

    def scan_roots(self) -> list[str]:
        """Todas las carpetas donde puede haber versiones instaladas.

        Se escanean **todas**, reciban descargas o no: una carpeta sin tipos
        marcados (o con el candado cerrado) está en la lista precisamente para
        que sus versiones se vean. Cuando dos rutas coinciden se escanea una
        sola vez.
        """
        roots = []
        seen = set()
        for folder in self.folders:
            path = (folder.path or "").strip()
            key = channels.normalize_path(path)
            if not key or key in seen:
                continue
            seen.add(key)
            roots.append(path)
        return roots

    def _legacy_mirror(self) -> dict:
        """Los campos del esquema viejo, calculados a partir de la biblioteca.

        No se leen nunca (salvo al migrar), pero se siguen escribiendo: si el
        usuario vuelve a una versión anterior de la aplicación, sin esto se
        encontraría todas las descargas yendo a ``~/Descargas/Blenders`` y sus
        carpetas olvidadas. Es una copia de cortesía, no una segunda fuente de
        verdad, y se podrá borrar cuando ya nadie pueda volver a la 1.x.

        Lo único que no sobrevive a un viaje de ida y vuelta son las carpetas
        sin tipos a partir de la segunda: el esquema viejo solo tenía hueco
        para una.
        """
        lts = channels.owner_of(self.folders, channels.TYPE_LTS)
        stable = channels.owner_of(self.folders, channels.TYPE_STABLE)
        main = stable or next((f for f in self.folders if f.types), None)
        extra = next((f for f in self.folders if not f.types), None)
        separate = lts is not None and lts is not main
        return {
            "dest_folder": main.path if main else "",
            "lts_folder": lts.path if separate else "",
            "separate_lts": separate,
            "extra_folder": extra.path if extra else "",
            "use_extra_folder": extra is not None,
        }

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

        Se añaden los campos del esquema viejo (``_legacy_mirror``) porque
        ``asdict`` reescribe el fichero entero: sin ellos, instalar una versión
        anterior de la aplicación dejaría al usuario con la configuración de
        fábrica.
        """
        payload = asdict(self)
        payload.update(self._legacy_mirror())
        return write_json_atomic(config_dir() / "settings.json", payload, indent=2)
