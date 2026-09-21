"""Ajustes y addons de Blender: dónde viven y qué se puede migrar.

Cada versión de Blender guarda su configuración en su propia carpeta, así que
al subir de versión el usuario se queda sin sus preferencias y sin sus addons.
Blender trae su propio "Import Preferences From Previous Version", pero es todo
o nada y solo mira la versión inmediatamente anterior. Este módulo es la base
de la migración selectiva del gestor: **no interpreta** ``userpref.blend`` (es
un ``.blend`` binario; para eso está el propio Blender, ver
``services/blender_runner.py``), solo:

* localiza la carpeta de cada versión (incluidas las variables
  ``BLENDER_USER_*``),
* enumera los addons legacy (``scripts/addons``) y las extensiones
  (``extensions/<repo>``), leyendo su versión mínima del ``bl_info`` o del
  ``blender_manifest.toml``,
* decide si cada uno es compatible con la versión destino, y
* copia los elegidos con una copia de seguridad de lo que pisa.

Es un módulo de ``services/``, así que **no importa Qt** y se puede probar sin
interfaz. Las funciones de decisión (compatibilidad, plan, copia) son puras o
solo tocan el disco, a propósito.
"""

import ast
import json
import os
import re
import shutil
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from model.build import minor_of, version_tuple

# Variables de entorno con las que Blender permite reubicar sus carpetas. Son
# la forma estándar de decirle a Blender "usa esta config" y hay que respetarlas
# o la migración acabaría escribiendo donde no toca.
RESOURCES_ENV = "BLENDER_USER_RESOURCES"
CONFIG_ENV = "BLENDER_USER_CONFIG"
SCRIPTS_ENV = "BLENDER_USER_SCRIPTS"
EXTENSIONS_ENV = "BLENDER_USER_EXTENSIONS"

# Subcarpetas dentro de la carpeta de una versión.
CONFIG_SUBDIR = "config"
SCRIPTS_SUBDIR = "scripts"
EXTENSIONS_SUBDIR = "extensions"
LEGACY_ADDONS_SUBDIR = "addons"
# Repositorio local por defecto: ahí van las extensiones instaladas a mano
# ("Install from Disk"). Las que vienen de extensions.blender.org caen en
# ``blender_org``, así que se escanean todos los repositorios.
LOCAL_REPO = "user_default"
MANIFEST_NAME = "blender_manifest.toml"

# Archivos/carpetas del árbol de extensiones que no son repositorios.
_SKIP_EXTENSION_ENTRIES = {".cache", ".local", ".blender_ext", "__pycache__"}

# Marcador donde anotamos qué copiamos, para poder deshacer más adelante.
MIGRATION_MARKER = ".blendermanager-migration.json"

# Estados de compatibilidad de un addon. El texto lo pone la interfaz.
OK = "ok"            # compatible
WARN = "warn"        # se puede copiar, pero conviene avisar
BLOCKED = "blocked"  # no se debe copiar: no es compatible

# Motivos (claves de i18n). ``""`` cuando todo está bien.
REASON_REQUIRES_NEWER = "requires_newer"   # el addon pide un Blender más nuevo
REASON_TOO_NEW = "too_new"                 # el addon no soporta esta versión aún
REASON_PLATFORM = "platform"               # no está publicado para este sistema
REASON_WHEEL_ABI = "wheel_abi"             # sus wheels no son para este Python
REASON_UNKNOWN_VERSION = "unknown_version"  # el addon no declara versión mínima

# Wheels con extensión compilada: el nombre lleva la etiqueta de Python
# (``cp311``/``pp311``); compararla evita copiar un addon cuyas dependencias no
# van a cargar. Es heurística: la comprobación fina la hace Blender al arrancar.
_WHEEL_TAG_RE = re.compile(r"(?:cp|pp)(\d+)", re.IGNORECASE)

_OS_TOKENS = {"linux": "linux", "windows": "windows", "darwin": "macos"}
_ARCH_TOKENS = {
    "x86_64": ("x64",),
    "amd64": ("x64",),
    "arm64": ("arm64", "aarch64"),
}

# Versión de Python que embebe cada serie de Blender. Solo se usa para avisar
# de wheels incompatibles; si la serie no está en la tabla, no se avisa (mejor
# no dar un falso positivo que inventar). Está comprobada arrancando las builds
# con ``--python-expr`` (ver ``services.blender_runner.python_version``, que es
# la fuente de verdad cuando la build está instalada): 4.5/5.0 dan 3.11 y
# 5.1/5.2 dan 3.13.
_PYTHON_BY_SERIES = {
    (3, 6): "3.10",
    (4, 0): "3.11",
    (4, 2): "3.11",
    (4, 5): "3.11",
    (5, 0): "3.11",
    (5, 1): "3.13",
    (5, 2): "3.13",
    (5, 3): "3.13",
}


def python_for_version(version: str) -> str:
    """Versión de Python probable de una build, o "" si no la conocemos.

    Se busca la última serie conocida que no supere la versión pedida.
    """
    target = version_tuple(version)
    if not target:
        return ""
    best = None
    for series, python in _PYTHON_BY_SERIES.items():
        if series <= target and (best is None or series > best[0]):
            best = (series, python)
    return best[1] if best else ""


# --------------------------------------------------------------- ubicaciones

def config_base(platform: str, env: dict | None = None) -> Path:
    """Carpeta que contiene una subcarpeta por versión de Blender.

    * **Linux**: ``~/.config/blender`` (o ``$XDG_CONFIG_HOME``).
    * **Windows**: ``%APPDATA%\\Blender Foundation\\Blender``.
    * **macOS**: ``~/Library/Application Support/Blender``.
    """
    env = os.environ if env is None else env
    if platform == "windows":
        base = env.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "Blender Foundation" / "Blender"
    if platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Blender"
    base = env.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "blender"


@dataclass
class BlenderConfig:
    """Carpetas de configuración de una versión concreta de Blender.

    Se guardan las tres rutas ya resueltas (y no solo ``root``) porque las
    variables ``BLENDER_USER_CONFIG/_SCRIPTS/_EXTENSIONS`` pueden descolgarlas
    a sitios distintos.
    """

    version: str
    root: Path
    platform: str
    config_dir: Path
    scripts_dir: Path
    extensions_dir: Path

    @property
    def addons_dir(self) -> Path:
        """Carpeta de los addons legacy (``scripts/addons``)."""
        return self.scripts_dir / LEGACY_ADDONS_SUBDIR

    @property
    def userpref(self) -> Path:
        """Fichero de preferencias de esa versión."""
        return self.config_dir / "userpref.blend"

    def exists(self) -> bool:
        """True si la carpeta de esa versión ya existe."""
        return self.root.is_dir()


def config_for(version: str, platform: str, env: dict | None = None) -> BlenderConfig:
    """Ubica la carpeta de una versión, respetando los ``BLENDER_USER_*``.

    Blender usa ``mayor.menor`` como nombre de carpeta (``4.5`` para 4.5.13),
    así que se normaliza la versión antes de construir la ruta. Cuando el
    usuario fija una carpeta con una variable de entorno, esa ruta sustituye a
    la subcarpeta correspondiente (no se le añade la versión).

    ``BLENDER_USER_RESOURCES`` reemplaza la carpeta de la versión entera; si
    está definida, ``config``/``scripts``/``extensions`` cuelgan de ella.
    """
    env = os.environ if env is None else env
    minor = minor_of(version) or version
    resources = (env.get(RESOURCES_ENV) or "").strip()
    root = Path(resources).expanduser() if resources else \
        config_base(platform, env) / minor

    def _override(name: str, fallback: Path) -> Path:
        value = (env.get(name) or "").strip()
        return Path(value).expanduser() if value else fallback

    return BlenderConfig(
        version=minor,
        root=root,
        platform=platform,
        config_dir=_override(CONFIG_ENV, root / CONFIG_SUBDIR),
        scripts_dir=_override(SCRIPTS_ENV, root / SCRIPTS_SUBDIR),
        extensions_dir=_override(EXTENSIONS_ENV, root / EXTENSIONS_SUBDIR),
    )


def configs_for_installed(installed, platform: str,
                          env: dict | None = None) -> list[BlenderConfig]:
    """Carpeta de configuración de cada versión instalada, de nueva a vieja.

    Se deduplica por serie: dos builds de la misma serie (por ejemplo dos
    diarias de ``main``) comparten carpeta, no hay que ofrecerlas dos veces.
    """
    seen = set()
    configs = []
    for entry in installed:
        minor = minor_of(getattr(entry, "version", "") or "")
        if not minor or minor in seen:
            continue
        seen.add(minor)
        configs.append(config_for(entry.version, platform, env))
    return configs


# -------------------------------------------------------------------- addons

@dataclass
class Addon:
    """Un addon instalado en una versión de Blender.

    ``kind`` distingue una extensión (``blender_manifest.toml``, Blender 4.2+)
    de un addon legacy (``bl_info``). ``module`` es el nombre con el que Blender
    lo habilita: el nombre de la carpeta para los legacy y
    ``bl_ext.<repo>.<id>`` para las extensiones.
    """

    kind: str
    module: str
    name: str
    version: str
    min_version: str
    max_version: str
    path: Path
    repo: str = ""
    platforms: tuple = ()
    wheels: tuple = ()
    has_meta: bool = True   # False si no se pudo leer ni versión ni nombre


def _read_manifest(folder: Path) -> dict:
    """Lee ``blender_manifest.toml``; si falta o está roto, ``{}``."""
    path = Path(folder) / MANIFEST_NAME
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def read_bl_info(init_py: Path) -> dict:
    """Extrae el ``bl_info`` de un addon legacy sin ejecutarlo.

    El diccionario es una asignación literal en la mayoría de addons, así que
    se lee con ``ast.literal_eval`` (no se importa el módulo: importarlo
    ejecutaría código del addon, que es justo lo que queremos evitar). Si no se
    puede evaluar (se construye dinámicamente), cae a una búsqueda por regex.
    """
    try:
        source = init_py.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "bl_info" not in names:
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, SyntaxError):
            break
        return value if isinstance(value, dict) else {}
    # Plan B: un addon que arma el bl_info por partes. Se busca un "blender":
    # con una tupla de números.
    match = re.search(r'"blender"\s*:\s*\(([^)]*)\)', source)
    if match:
        numbers = re.findall(r"\d+", match.group(1))
        if numbers:
            return {"blender": [int(n) for n in numbers]}
    return {}


def _tuple_text(value) -> str:
    """Convierte ``(4, 5, 0)`` o ``"4.5.0"`` en el texto ``"4.5.0"``."""
    if value in (None, ""):
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        return ".".join(str(part) for part in value)
    return str(value)


def addons_in(config: BlenderConfig) -> list[Addon]:
    """Todos los addons y extensiones instalados en una versión.

    No toca red ni ejecuta nada del addon: solo lee ficheros de metadatos.
    """
    addons = _legacy_addons(config) + _extensions(config)
    addons.sort(key=lambda item: (item.kind, item.name.lower(), item.module))
    return addons


def _legacy_addons(config: BlenderConfig) -> list[Addon]:
    """Addons legacy: ``scripts/addons/<mod>/__init__.py`` (o ``<mod>.py``)."""
    folder = config.addons_dir
    if not folder.is_dir():
        return []
    result = []
    for entry in sorted(folder.iterdir()):
        if entry.name.startswith((".", "_")):
            continue
        if entry.is_dir():
            init = entry / "__init__.py"
            if not init.is_file():
                continue
            module = entry.name
        elif entry.suffix == ".py":
            init = entry
            module = entry.stem
        else:
            continue
        info = read_bl_info(init)
        result.append(Addon(
            kind="legacy",
            module=module,
            name=str(info.get("name") or module),
            version=_tuple_text(info.get("version")),
            min_version=_tuple_text(info.get("blender")),
            max_version="",
            path=entry,
            has_meta=bool(info),
        ))
    return result


def _extension_repos(config: BlenderConfig) -> dict:
    """Repositorios de extensiones: ``extensions/<repo>/`` -> carpeta.

    El repositorio local de las extensiones instaladas a mano es
    ``user_default``; las bajadas de extensions.blender.org van a
    ``blender_org``. Se aceptan todos los que tengan pinta de repositorio.
    """
    root = config.extensions_dir
    repos = {}
    if not root.is_dir():
        return repos
    for entry in sorted(root.iterdir()):
        if entry.is_dir() and entry.name not in _SKIP_EXTENSION_ENTRIES:
            repos[entry.name] = entry
    return repos


def _extensions(config: BlenderConfig) -> list[Addon]:
    """Extensiones con ``blender_manifest.toml`` en cada repositorio."""
    result = []
    for repo, folder in _extension_repos(config).items():
        for entry in sorted(folder.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            manifest = _read_manifest(entry)
            if not manifest:
                continue
            addon_id = str(manifest.get("id") or entry.name)
            result.append(Addon(
                kind="extension",
                module=f"bl_ext.{repo}.{addon_id}",
                name=str(manifest.get("name") or addon_id),
                version=str(manifest.get("version") or ""),
                min_version=str(manifest.get("blender_version_min") or ""),
                max_version=str(manifest.get("blender_version_max") or ""),
                path=entry,
                repo=repo,
                platforms=tuple(manifest.get("platforms") or ()),
                wheels=tuple(_wheels_of(entry, manifest)),
            ))
    return result


def _wheels_of(folder: Path, manifest: dict) -> list[str]:
    """Nombres de los wheels de una extensión (los declara o están en disco)."""
    names = [str(item) for item in (manifest.get("wheels") or [])]
    if names:
        return names
    wheels_dir = Path(folder) / "wheels"
    if wheels_dir.is_dir():
        names = [item.name for item in sorted(wheels_dir.glob("*.whl"))]
    return names


# ----------------------------------------------------------- compatibilidad

def _platform_ok(platforms, target_platform: str, target_arch: str) -> bool:
    """True si el addon declara soporte para este sistema.

    En el manifest las plataformas son ``<os>-<arch>`` (``linux-x64``,
    ``macos-arm64``...); se admite ``aarch64`` como sinónimo de ``arm64``.
    """
    if not platforms:
        return True
    os_token = _OS_TOKENS.get(target_platform, target_platform)
    arch_tokens = _ARCH_TOKENS.get(target_arch, (target_arch,) if target_arch else ())
    for entry in platforms:
        text = str(entry or "").lower()
        if "-" not in text:
            continue
        os_part, _, arch_part = text.partition("-")
        if os_part != os_token:
            continue
        if not arch_tokens or arch_part in arch_tokens:
            return True
    return False


def _python_tag(raw: str) -> str:
    """Normaliza ``"3.13"`` o ``"311"`` a ``"313"`` (mayor + menor a 2 dígitos)."""
    digits = re.sub(r"[^\d]", "", raw or "")
    if len(digits) < 2:
        return ""
    # ``cp311`` -> mayor 3, menor 11; ``cp39`` -> mayor 3, menor 9.
    major, minor = digits[0], digits[1:]
    return f"{major}{int(minor):02d}"


def _wheel_python_tag(wheel_name: str) -> str:
    """Etiqueta de Python de un wheel, o "" si es de Python puro.

    Un wheel se llama ``nombre-version-[build-]pytag-abitag-plattag.whl``. Se
    respeta la ABI cuando la hay: ``abi3`` (ABI estable) vale para cualquier
    Python 3, y ``cp3XX`` manda sobre la etiqueta de Python. Si la ABI no dice
    nada (``none``), vale la etiqueta de Python.
    """
    parts = str(wheel_name).split("-")
    if len(parts) < 3:
        return ""
    python_tag, abi_tag = parts[-3], parts[-2]
    if abi_tag.lower().startswith("abi"):
        # ABI estable (``abi3``): vale para cualquier Python 3, no hay conflicto.
        return ""
    for candidate in (abi_tag, python_tag):
        match = _WHEEL_TAG_RE.fullmatch(candidate or "")
        if match:
            return _python_tag(match.group(1))
    return ""


def _wheel_package(wheel_name: str) -> str:
    """Nombre del paquete de un wheel: lo que va antes del primer guion.

    Un wheel se llama ``paquete-version-pytag-abitag-plattag.whl`` y en el
    manifiesto viene con su ruta (``./wheels/pillow-11.1.0-...``), así que
    primero nos quedamos con el nombre del fichero.
    """
    base = str(wheel_name).replace("\\", "/").split("/")[-1]
    return base.split("-")[0].lower()


def wheel_problem(wheels, target_python: str) -> str:
    """Paquete cuyas dependencias no sirven para ``target_python``, o "".

    **Se mira paquete a paquete, no wheel a wheel**, y este es el motivo: una
    extensión bien empaquetada trae *un wheel por plataforma y por versión de
    Python*, y Blender instala el que le toca al arrancar. MatPlus, por
    ejemplo, declara Pillow en ``cp311`` (para Blender 4.2/5.0) y en ``cp313``
    (para 5.1+). Avisar en cuanto **uno** no encajaba marcaba esas extensiones
    como dudosas siempre, dijeras la versión de destino que dijeras: el aviso
    saltaba igual apuntando a 5.2 que a 5.3, que usan el mismo Python 3.13, y
    por eso parecía que comparaba los dos Blender entre sí. Solo hay problema
    de verdad cuando un paquete trae wheels compilados y **ninguno** vale.

    Los de Python puro (``py3-none-any``) y los de ABI estable (``abi3``) se
    ignoran: valen para cualquier Python 3. La plataforma la valida Blender al
    arrancar; aquí solo se mira la etiqueta de Python/ABI del nombre.
    """
    want = _python_tag(target_python)
    if not want:
        return ""
    # Por paquete: las etiquetas de sus wheels compilados (los puros no cuentan).
    tags_by_package = {}
    for name in wheels:
        tag = _wheel_python_tag(name)
        if not tag:
            continue
        tags_by_package.setdefault(_wheel_package(name), set()).add(tag)
    for package, tags in tags_by_package.items():
        if want not in tags:
            return package
    return ""


def wheel_conflict(wheels, target_python: str) -> bool:
    """True si algún paquete de los wheels no sirve para ese Python.

    Envoltorio de ``wheel_problem`` para cuando solo interesa el sí/no.
    """
    return bool(wheel_problem(wheels, target_python))


def compat_report(addon: Addon, target_version: str, target_platform: str = "",
                  target_arch: str = "", target_python: str = "") -> tuple:
    """Estado de un addon frente a la versión destino.

    Devuelve ``(status, reason)`` con ``status`` en ``OK``/``WARN``/``BLOCKED``
    y ``reason`` una de las claves ``REASON_*`` (o ``""``). Es pura: no toca el
    disco, para poder probarla con addons de mentira.
    """
    target = version_tuple(target_version)
    minimum = version_tuple(addon.min_version)
    if addon.min_version and minimum and target and target < minimum:
        return BLOCKED, REASON_REQUIRES_NEWER
    maximum = version_tuple(addon.max_version)
    if addon.max_version and maximum and target and target >= maximum:
        return BLOCKED, REASON_TOO_NEW
    if addon.platforms and not _platform_ok(
            addon.platforms, target_platform, target_arch):
        return BLOCKED, REASON_PLATFORM
    if addon.wheels and target_python and wheel_conflict(
            addon.wheels, target_python):
        return WARN, REASON_WHEEL_ABI
    if not addon.min_version:
        # Sin versión mínima no hay forma de saberlo: se copia, pero se avisa.
        return WARN, REASON_UNKNOWN_VERSION
    return OK, ""


# ------------------------------------------------------------- plan y copia

@dataclass
class AddonPlan:
    """Qué haríamos con un addon en la migración."""

    addon: Addon
    status: str
    reason: str
    destination: Path
    selected: bool = True
    # True si en la versión origen estaba **activado**. Se copia con el mismo
    # estado que tenía (no se activa por el simple hecho de migrar): si allí
    # estaba apagado, se queda apagado, que es lo que el usuario espera.
    was_enabled: bool = False
    # Dato suelto que acompaña al motivo, para que la interfaz pueda ser
    # concreta en vez de genérica. Hoy solo lo usa ``REASON_WHEEL_ABI``, donde
    # lleva el **nombre del paquete** que no encaja: decir "numpy no trae una
    # compilación para Python 3.13" se puede accionar; "sus dependencias son de
    # otro Python" no.
    detail: str = ""
    # Python que embebe la versión de destino ("3.13"), para poder nombrarlo en
    # el aviso. Vacío si no se conoce esa serie (ver ``python_for_version``).
    target_python: str = ""

    @property
    def blocked(self) -> bool:
        """True si no se debe copiar (incompatible)."""
        return self.status == BLOCKED

    @property
    def enable_module(self) -> str:
        """Módulo que Blender destino tiene que habilitar."""
        addon_id = self.addon.module.rsplit(".", 1)[-1]
        if self.addon.kind == "extension":
            return f"bl_ext.{LOCAL_REPO}.{addon_id}"
        return self.addon.module

    @property
    def is_extension(self) -> bool:
        """True si es una extensión (manifest) y no un addon legacy."""
        return self.addon.kind == "extension"


def addon_id_of(module: str) -> str:
    """Id de un addon, sin repositorio ni prefijo.

    ``bl_ext.user_default.MatPlus`` -> ``MatPlus``; ``mi_addon`` -> ``mi_addon``.
    Es la clave para comparar el estado activado entre versiones, porque el
    módulo cambia (el repositorio de origen puede no ser el de destino).
    """
    return (module or "").rsplit(".", 1)[-1]


def destination_for(addon: Addon, target: BlenderConfig) -> Path:
    """Dónde quedaría el addon copiado en la versión destino.

    Las extensiones se instalan en el repositorio local (``user_default``),
    aunque en origen vinieran de otro; así no hay que dar de alta repositorios
    remotos solo para copiar una carpeta.
    """
    if addon.kind == "extension":
        addon_id = addon.module.rsplit(".", 1)[-1]
        return target.extensions_dir / LOCAL_REPO / addon_id
    return target.addons_dir / addon.path.name


def plan_migration(source: BlenderConfig, target: BlenderConfig,
                   target_platform: str = "", target_arch: str = "",
                   target_python: str = "", enabled_ids=()) -> list[AddonPlan]:
    """Lista de addons de ``source`` y qué pasaría al llevarlos a ``target``.

    ``enabled_ids`` son los ids (``addon_id_of``) que estaban **activados** en
    origen; con eso se marca ``was_enabled`` y la interfaz sabe cuáles hay que
    activar en destino (solo esos). Si se deja vacío, se asume que ninguno lo
    estaba, que es lo prudente.
    """
    enabled = set(enabled_ids or ())
    plans = []
    for addon in addons_in(source):
        status, reason = compat_report(addon, target.version, target_platform,
                                       target_arch, target_python)
        # El paquete concreto solo se calcula cuando el motivo es el de los
        # wheels; para el resto no hay nada que detallar.
        detail = (wheel_problem(addon.wheels, target_python)
                  if reason == REASON_WHEEL_ABI else "")
        plans.append(AddonPlan(
            addon=addon,
            status=status,
            reason=reason,
            detail=detail,
            target_python=target_python,
            destination=destination_for(addon, target),
            # Los incompatibles llegan sin marcar: nunca se copian sin querer.
            selected=status != BLOCKED,
            was_enabled=addon_id_of(addon.module) in enabled,
        ))
    return plans


@dataclass
class MigrationResult:
    """Resumen de una migración aplicada (o simulada)."""

    copied: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    backed_up: list = field(default_factory=list)
    failed: list = field(default_factory=list)   # (plan, mensaje)
    dry_run: bool = False
    marker: Path | None = None
    modules: list = field(default_factory=list)


# Sufijo de las copias de seguridad. **Solo se conserva una por destino** (ver
# ``_park_existing``), no un histórico con fecha.
BACKUP_SUFFIX = ".blendermanager-bak"


def _delete_path(path: Path) -> None:
    """Borra un fichero o una carpeta entera, sin fallar si no está."""
    path = Path(path)
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        elif path.exists() or path.is_symlink():
            path.unlink()
    except OSError:
        pass


def _park_existing(destination: Path, backed_up: list, actions: list) -> None:
    """Aparta lo que ya hay en ``destination`` a su copia de seguridad.

    **Una sola copia por destino, reutilizable**: los usuarios migran más de una
    vez (y a veces en la dirección contraria), y con un sufijo por fecha se
    acumulaba un ``.bak`` por intento sin que nadie los viera. Se reutiliza el
    mismo nombre y se pisa: lo que interesa conservar es el estado
    *inmediatamente anterior* al último cambio, no un histórico.

    No hace nada si ``destination`` no existe.
    """
    if not destination.exists():
        return
    # Quita un sufijo .bak ya existente, para no respaldar el respaldo.
    base = destination.name.split(BACKUP_SUFFIX, 1)[0]
    # Limpia restos de intentos anteriores (y de versiones viejas de la app,
    # que sí ponían fecha) antes de reutilizar el nombre.
    for old in destination.parent.glob(f"{base}{BACKUP_SUFFIX}*"):
        if old != destination:
            _delete_path(old)
    backup = destination.with_name(f"{base}{BACKUP_SUFFIX}")
    destination.rename(backup)
    backed_up.append(backup)
    actions.append({"path": str(destination), "backup": str(backup)})


def _write_marker(target: BlenderConfig, actions: list, key: str = "actions") -> Path:
    """Anota en la carpeta destino qué se copió (para poder deshacer).

    ``key`` separa lo que copió la migración de addons (``actions``) de lo que
    copió la de preferencias (``preferences``): el deshacer lee las dos listas.
    """
    path = target.root / MIGRATION_MARKER
    payload = {
        "version": target.version,
        "date": datetime.now().isoformat(timespec="seconds"),
        key: actions,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        pass
    return path


def apply_migration(plans, target: BlenderConfig,
                    dry_run: bool = False) -> MigrationResult:
    """Copia los addons marcados y devuelve el resumen.

    Es conservador a propósito: lo que ya exista en destino **no se borra**,
    se aparta como ``.blendermanager-bak`` (por si el usuario tenía su propia
    versión de ese addon). Con ``dry_run`` no toca el disco.
    """
    result = MigrationResult(dry_run=dry_run)
    actions = []
    for plan in plans:
        if not plan.selected or plan.blocked:
            result.skipped.append(plan)
            continue
        if dry_run:
            result.copied.append(plan)
            continue
        try:
            destination = Path(plan.destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            _park_existing(destination, result.backed_up, actions)
            # ``symlinks=True`` como el propio ``preferences.copy_prev`` de
            # Blender: los addons enlazados (muy típicos en desarrollo) tienen
            # que seguir apuntando a su sitio, no duplicarse.
            shutil.copytree(plan.addon.path, destination, symlinks=True)
            result.copied.append(plan)
            result.modules.append(plan.enable_module)
            actions.append({"path": str(destination)})
        except OSError as error:
            result.failed.append((plan, str(error)))
    if not dry_run and actions:
        result.marker = _write_marker(target, actions)
    return result


# --------------------------------------------------------- fábrica / reset

# Carpeta, junto a la config de una versión, donde se guardan las instantáneas
# de ``config`` antes de resetear. El nombre lleva fecha y hora para que se
# puedan tener varias (resetear a fábrica y volver a intentarlo es normal).
SNAPSHOT_DIR = ".blendermanager-snapshots"
SNAPSHOT_PREFIX = "config"


def snapshot_config(target: BlenderConfig, label: str = "") -> Path | None:
    """Aparta la carpeta ``config`` de una versión y devuelve dónde quedó.

    Es lo que hace a mano quien quiere probar una versión "de fábrica": renombrar
    ``config`` y dejar que Blender la recree. Aquí se guarda además en una
    carpeta de instantáneas para poder **volver a ponerla** después. No borra
    nada: si no hay ``config``, devuelve ``None``.
    """
    source = target.config_dir
    if not source.exists():
        return None
    snapshots = target.root / SNAPSHOT_DIR
    snapshots.mkdir(parents=True, exist_ok=True)
    name = f"{SNAPSHOT_PREFIX}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    if label:
        clean = re.sub(r"[^A-Za-z0-9._-]+", "-", label).strip("-")
        if clean:
            name += f"-{clean}"
    destination = snapshots / name
    counter = 1
    while destination.exists():
        destination = snapshots / f"{name}-{counter}"
        counter += 1
    shutil.move(str(source), str(destination))
    return destination


def snapshot_dirs(target: BlenderConfig) -> list:
    """Todas las instantáneas de ``config`` de esa versión, vacías incluidas.

    Es la lista cruda (para borrar o para saber si hay algo), de la más nueva a
    la más vieja. Lo que se ofrece restaurar es ``snapshots_for``.
    """
    folder = target.root / SNAPSHOT_DIR
    if not folder.is_dir():
        return []
    return sorted((item for item in folder.iterdir()
                   if item.is_dir() and item.name.startswith(SNAPSHOT_PREFIX)),
                  key=lambda item: item.name, reverse=True)


def _has_settings(snapshot: Path) -> bool:
    """True si guarda preferencias de verdad (``userpref`` o ``startup``).

    No basta con que la carpeta tenga algo: una instantánea con solo
    ``platform_support.txt`` o los recientes no tiene ajustes que restaurar y no
    debe contar como "lo más reciente" (el botón de restaurar no recuperaría
    nada).
    """
    snapshot = Path(snapshot)
    return any((snapshot / name).is_file()
               for name in ("userpref.blend", "startup.blend"))


def snapshots_for(target: BlenderConfig) -> list:
    """Instantáneas con ajustes de verdad, de la más nueva a la más vieja.

    Las vacías se descartan: al restaurar se aparta la config que hubiera, y si
    no había nada queda una carpeta sin ficheros. Si esa contase como "lo más
    reciente", el botón de restaurar no recuperaría los ajustes de verdad (le
    pasó al usuario: su config real quedaba tapada por una vacía).
    """
    return [item for item in snapshot_dirs(target) if _has_settings(item)]


def snapshot_date(snapshot) -> str:
    """Fecha legible de una instantánea (``2026-09-18 14:21``), o ``""``.

    El nombre es ``config-AAAAMMDD-HHMMSS[-etiqueta]``. La interfaz enseña la
    fecha, no el nombre de la carpeta: «config-20260918-152704-factory» no dice
    nada a quien lo lee.
    """
    match = re.match(r"config-(\d{8})-(\d{6})", Path(snapshot).name)
    if not match:
        return ""
    try:
        moment = datetime.strptime(match.group(1) + match.group(2),
                                   "%Y%m%d%H%M%S")
    except ValueError:
        return ""
    return moment.strftime("%Y-%m-%d %H:%M")


def snapshot_label(snapshot) -> str:
    """Etiqueta con la que se guardó (``v5.2.0``, ``factory`` o ``""``).

    Es lo que distingue un guardado del usuario (los ajustes que se apartaron al
    restablecer) de una config limpia que se aparcó al restaurar.
    """
    match = re.match(r"config-\d{8}-\d{6}(?:-(.*))?$", Path(snapshot).name)
    return (match.group(1) or "") if match else ""


def snapshot_details(snapshot) -> dict:
    """Resumen barato de una instantánea (sin arrancar Blender).

    Cuenta los ficheros y sus tamaños, y las líneas de los que son texto
    (marcadores y recientes). ``has_userpref`` es lo que de verdad importa:
    sin él no hay preferencias que restaurar.
    """
    snapshot = Path(snapshot)
    files = {}
    if snapshot.is_dir():
        for child in snapshot.iterdir():
            try:
                if child.is_file():
                    files[child.name] = child.stat().st_size
            except OSError:
                continue

    def lines(name: str) -> int:
        try:
            text = (snapshot / name).read_text(encoding="utf-8",
                                               errors="ignore")
        except OSError:
            return 0
        return sum(1 for line in text.splitlines() if line.strip())

    return {
        "files": files,
        "total": sum(files.values()),
        "has_userpref": "userpref.blend" in files,
        "has_startup": "startup.blend" in files,
        "bookmarks": lines("bookmarks.txt"),
        "recent": lines("recent-files.txt"),
    }


def restore_snapshot(target: BlenderConfig, snapshot) -> Path | None:
    """Copia una instantánea a su sitio (``config``), sin consumirla.

    Antes se **movía** (el guardado desaparecía). Eso dejaba al usuario sin
    segunda oportunidad: si algo pisaba la config después (un Blender de la
    misma serie abierto, por ejemplo), los ajustes se perdían para siempre. Se
    copia y el guardado se queda hasta que el usuario lo borre a mano.

    La config que había se aparta como ``factory`` para poder deshacer, pero
    solo si tenía algo: aparcar una carpeta vacía solo añade ruido. Devuelve ese
    aparte (o ``None``).
    """
    snapshot = Path(snapshot)
    if not snapshot.is_dir():
        return None
    aside = None
    if _has_settings(target.config_dir):
        aside = snapshot_config(target, label="factory")
    target.config_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(snapshot, target.config_dir, dirs_exist_ok=True,
                    symlinks=True)
    return aside


def delete_snapshot(snapshot) -> bool:
    """Borra una instantánea (el usuario decidió que no la quiere)."""
    snapshot = Path(snapshot)
    if not snapshot.is_dir():
        return False
    try:
        shutil.rmtree(snapshot)
    except OSError:
        return False
    return True


@dataclass
class UndoResult:
    """Resumen de deshacer la última migración sobre un destino."""

    restored: list = field(default_factory=list)   # (destino, backup)
    removed: list = field(default_factory=list)    # rutas borradas
    failed: list = field(default_factory=list)     # (ruta, mensaje)
    marker_found: bool = False
    dry_run: bool = False


def read_migration_marker(target: BlenderConfig) -> dict:
    """Lee el marcador de la última migración de esa versión, o ``{}``."""
    path = target.root / MIGRATION_MARKER
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def undo_migration(target: BlenderConfig, dry_run: bool = False) -> UndoResult:
    """Deshace la última migración: revierte lo que se guardase como backup.

    Es deliberadamente conservador: solo toca lo que el marcador dice que hemos
    copiado nosotros. Lo que no tenía backup (porque el addon no existía antes)
    se **borra**, que es la única forma de que el estado vuelva atrás; si el
    usuario hubiera puesto ahí algo después, se perdería, así que la interfaz
    avisa antes de llamar a esto.

    Al terminar se elimina el marcador, de modo que un segundo "deshacer" no
    restaura nada (evita el clásico doble-clic que deshace de más).
    """
    result = UndoResult(dry_run=dry_run)
    payload = read_migration_marker(target)
    actions = (payload.get("actions") or []) + (payload.get("preferences") or [])
    if not actions:
        return result
    result.marker_found = True
    if dry_run:
        return result
    # En orden inverso: lo último copiado, lo primero en deshacerse.
    for action in reversed(actions):
        destination = Path(action.get("path") or "")
        backup = action.get("backup")
        if not destination:
            continue
        try:
            if backup and Path(backup).exists():
                _delete_path(destination)
                Path(backup).rename(destination)
                result.restored.append((destination, Path(backup)))
            elif destination.exists():
                _delete_path(destination)
                result.removed.append(destination)
        except OSError as error:
            result.failed.append((destination, str(error)))
    if not result.failed:
        try:
            (target.root / MIGRATION_MARKER).unlink()
        except OSError:
            pass
    return result


def summary_counts(plans) -> dict:
    """Cuenta addons por estado, para el resumen de la interfaz."""
    counts = {OK: 0, WARN: 0, BLOCKED: 0}
    for plan in plans:
        counts[plan.status] = counts.get(plan.status, 0) + 1
    return counts


# ------------------------------------------------------------ preferencias

# Ficheros de la carpeta ``config`` que forman las preferencias del usuario.
# ``userpref.blend`` es lo que Blender llama "preferences" (keymap, temas,
# addons habilitados...); ``startup.blend`` es la escena/UI por defecto, que es
# un ``.blend`` completo y por eso merece un aviso aparte.
USERPREF_FILE = "userpref.blend"
STARTUP_FILE = "startup.blend"

# Opciones de la migración de preferencias: (clave, fichero, aviso).
PREFERENCE_FILES = (
    ("userpref", USERPREF_FILE,
     "Preferences: keymap, theme, add-ons enabled, settings."),
    ("startup", STARTUP_FILE,
     "Startup file with the default scene and UI layout."),
)


@dataclass
class PreferenceItem:
    """Un fichero de preferencias y qué pasaría al migrarlo."""

    key: str
    filename: str
    source: Path
    destination: Path
    exists: bool          # en origen
    overwrites: bool      # ya hay uno en destino
    selected: bool = True

    @property
    def safe(self) -> bool:
        """True si se puede copiar (está en origen)."""
        return self.exists


def preference_plan(source: BlenderConfig, target: BlenderConfig) -> list:
    """Qué ficheros de preferencias se podrían copiar y con qué riesgo.

    No toca el disco más allá de comprobar existencia: la decisión de copiar
    (y el aviso de que pisa lo que ya hubiera) es del usuario.
    """
    items = []
    for key, filename, _ in PREFERENCE_FILES:
        origin = source.config_dir / filename
        destination = target.config_dir / filename
        items.append(PreferenceItem(
            key=key,
            filename=filename,
            source=origin,
            destination=destination,
            exists=origin.is_file(),
            overwrites=destination.exists(),
            # ``startup.blend`` no llega marcado: es un ``.blend`` entero y
            # sobrescribir la escena por defecto es más agresivo que el resto.
            selected=origin.is_file() and key != "startup",
        ))
    return items


@dataclass
class PreferenceResult:
    """Resumen de una migración de preferencias (aplicada o simulada)."""

    copied: list = field(default_factory=list)
    backed_up: list = field(default_factory=list)
    failed: list = field(default_factory=list)   # (item, mensaje)
    dry_run: bool = False
    marker: Path | None = None


def apply_preferences(items, target: BlenderConfig,
                      dry_run: bool = False) -> PreferenceResult:
    """Copia los ficheros de preferencias marcados, con copia de seguridad.

    ``shutil.copy2`` (no ``copy``): conserva los tiempos del fichero, que es lo
    que Blender usa para decidir si las preferencias están al día. Lo que ya
    exista **no se borra**: se aparta como ``.blendermanager-bak``.
    """
    result = PreferenceResult(dry_run=dry_run)
    actions = []
    for item in items:
        if not item.selected or not item.safe:
            continue
        if dry_run:
            result.copied.append(item)
            continue
        try:
            destination = Path(item.destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            _park_existing(destination, result.backed_up, actions)
            shutil.copy2(item.source, destination)
            result.copied.append(item)
            actions.append({"path": str(destination)})
        except OSError as error:
            result.failed.append((item, str(error)))
    if not dry_run and actions:
        result.marker = _write_marker(target, actions, key="preferences")
    return result
