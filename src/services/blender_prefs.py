"""Preferencias de Blender por clave, para migrarlas de forma selectiva.

``userpref.blend`` es un ``.blend`` binario: no se interpreta a mano. Lo que
hace este módulo es **preguntarle al propio Blender** (en ``--background``) por
sus preferencias y traerlas como un diccionario plano ``{"view.ui_scale": 1.25}``.
Así:

* volcar las preferencias del usuario y las de fábrica (``--factory-startup``),
* **diferenciarlas** para quedarse solo con lo que el usuario cambió de verdad
  (y no con las 280 claves, la mayoría por defecto),
* y aplicar solo las claves marcadas en la versión destino, avisando de las que
  ya no existen allí (Blender renombra/mueve cosas entre versiones).

La ruta de cada clave es una ruta RNA (``seccion.propiedad.subpropiedad``). No
es API estable entre versiones: esa es justo la razón de que aplicar vaya
**clave a clave** y se reporten las que fallan, en vez de copiar de golpe.

Es un módulo de ``services/``: no importa Qt. La parte que habla con Blender
está en ``blender_runner``; aquí solo vive el guion, el filtrado y los tipos.
"""

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from services import blender_runner

# Valores que no son una preferencia "del usuario" sino del entorno: el diff
# contra fábrica los detectaría como cambio, pero migrarlos no tiene sentido
# (o es directamente peligroso: mover `gpu_backend` de un equipo a otro puede
# dejar a la otra build sin arrancar).
ENVIRONMENT_KEYS = (
    "system.gpu_backend",
    "system.gpu_backend_os",
    "system.audio_device",
    "system.audio_channels",
    "system.audio_sample_rate",
    "system.audio_sample_rate_hz",
    "system.opengl_extension_enabled",
    "system.maximum_resolution_x",
    "system.maximum_resolution_y",
    "system.maximum_resolution_scale",
    "system.memory_cache_limit",
    "system.use_preferences_save",
    "filepaths.use_scripts_auto_execute",
    "filepaths.script_directory",
    "filepaths.font_directory",
    "filepaths.texture_directory",
    "filepaths.render_output_directory",
    "filepaths.render_cache_directory",
    "filepaths.temp_directory",
    "filepaths.asset_libraries",
    "extensions",
    "experimental",
    "apps",
    "active_section",   # la pestaña de preferencias que estaba abierta
    "is_dirty",
    "version",
)

# Propiedades que, aunque lleguen del volcado como un texto (los ``set`` de
# Blender se imprimen así: ``{'A', 'B'}``), no se pueden volver a escribir por
# esta vía: ``key_insert_channels`` espera un ``set`` y le llega una cadena.
# Se listan explícitamente para no ofrecer algo que va a fallar siempre.
_UNSETTABLE = (
    "edit.key_insert_channels",
)


def is_settable(path: str) -> bool:
    """True si esa clave se puede escribir de vuelta por ruta RNA."""
    return not any(path == blocked or path.startswith(blocked + ".")
                   for blocked in _UNSETTABLE)

# Secciones que se pueden ofrecer al usuario. La vista agrupa por prefijo; el
# orden es el de las pestañas de preferencias de Blender.
SECTIONS = (
    ("view", "Interface"),
    ("edit", "Editing"),
    ("inputs", "Input"),
    ("filepaths", "File Paths"),
    ("keymap", "Keymap"),
    ("system", "System"),
    # Preferencias de los addons activos (p. ej. el dispositivo de Cycles).
    ("addons", "Add-ons"),
)

# --- Guion que corre dentro de Blender ------------------------------------
#
# Recorre el árbol de preferencias por las propiedades RNA y vuelca las hojas.
# Se salta colecciones (addons, temas, asset libraries) porque no son escalares
# y se migran de otra forma (los addons tienen su propia vista), y las
# Read-only de hoja. Los POINTER se recorren aunque sean de solo lectura: por
# ahí se baja (``view``, ``edit``...), no se copian como valor.

_DUMP_SCRIPT = r'''
import bpy
import json

OUT = {}


def walk(obj, prefix, depth=0):
    if depth > 5:
        return
    for prop in obj.bl_rna.properties:
        if prop.identifier in ("rna_type", "bl_idname") or prop.type == "COLLECTION":
            continue
        try:
            value = getattr(obj, prop.identifier)
        except Exception:
            continue
        path = prefix + prop.identifier
        if prop.type == "POINTER":
            walk(value, path + ".", depth + 1)
            continue
        if prop.is_readonly:
            continue
        if prop.type == "ENUM":
            # Un enum de varios valores llega como ``set``, y ``str()`` sobre un
            # set NO tiene orden estable entre procesos (Python aleatoriza el
            # hash de las cadenas). Sin ordenarlo, la misma preferencia sin
            # tocar sale distinta en dos lecturas y el diff la da por cambiada.
            # Hoy la única así (``edit.key_insert_channels``) no es escribible y
            # el filtro la descarta, pero eso es suerte, no diseño.
            OUT[path] = str(sorted(value)) if isinstance(value, set) else str(value)
        elif isinstance(value, (bool, int, float, str)):
            OUT[path] = value


walk(bpy.context.preferences, "")

# Preferencias de los addons ACTIVOS. No son atributos de ``preferences`` (viven
# en la coleccion ``addons``), asi que el recorrido de arriba no las ve: de ahi
# salian sin detectar el dispositivo de Cycles (OPTIX/CUDA/HIP) o las opciones
# de glTF. Los modulos de extension llevan puntos en el nombre
# (``bl_ext.<repo>.<id>``); quien las aplica resuelve el modulo por el prefijo
# mas largo de ``addons``.
for addon in bpy.context.preferences.addons:
    try:
        addon_prefs = addon.preferences
    except Exception:
        continue
    if addon_prefs is None:
        continue
    walk(addon_prefs, "addons." + addon.module + ".", 0)

print("BLENDERMANAGER_DUMP=" + json.dumps(OUT))
'''

# --- Guion que aplica las claves elegidas ---------------------------------
#
# Recibe pares ``[ruta, valor]`` por variable de entorno. Aplica cada uno por
# su cuenta: si una clave ya no existe en esta versión (o cambió de tipo), se
# anota el error y se sigue con las demás. Solo guarda si algo se aplicó.

_APPLY_SCRIPT = r'''
import bpy
import json
import os

pairs = json.loads(os.environ.get("BLENDERMANAGER_PREFS", "[]"))
applied = []
errors = []
prefs = bpy.context.preferences

# Igual que al habilitar addons: `save_userpref` no crea la carpeta de config,
# y sin ella el guardado falla en silencio en `--background`.
try:
    config = bpy.utils.user_resource("CONFIG")
    if config:
        os.makedirs(config, exist_ok=True)
    prefs.use_preferences_save = True
except Exception:
    pass

def resolve(path):
    """Objeto RNA al que apunta la ruta, o None si no existe.

    ``addons.<modulo>.<clave>`` no es una cadena de atributos (``addons`` es una
    coleccion), asi que se entra por ella. El modulo puede llevar puntos
    (extensiones), y se elige el que sea prefijo mas largo de la ruta.
    """
    if path.startswith("addons."):
        rest = path[len("addons."):]
        modules = [m for m in prefs.addons.keys() if rest.startswith(m + ".")]
        if not modules:
            return None
        module = max(modules, key=len)
        addon = prefs.addons.get(module)
        obj = addon.preferences if addon is not None else None
        if obj is None:
            return None
        head = rest[len(module) + 1:].rpartition(".")[0]
    else:
        obj = prefs
        head = path.rpartition(".")[0]
    for part in head.split(".") if head else []:
        obj = getattr(obj, part)
    return obj


for path, value in pairs:
    try:
        leaf = path.rpartition(".")[2]
        obj = resolve(path)
        if obj is None:
            errors.append({"path": path, "error": "unknown add-on or property"})
            continue
        prop = obj.bl_rna.properties.get(leaf)
        if prop is None:
            errors.append({"path": path, "error": "unknown property"})
            continue
        if prop.type == "ENUM":
            setattr(obj, leaf, str(value))
        elif prop.type == "BOOLEAN":
            setattr(obj, leaf, bool(value))
        elif prop.type in ("INT", "FLOAT"):
            setattr(obj, leaf, float(value) if prop.type == "FLOAT" else int(value))
        else:
            setattr(obj, leaf, value)
        applied.append(path)
    except Exception as exc:
        errors.append({"path": path, "error": str(exc)})

if applied:
    try:
        bpy.ops.wm.save_userpref()
    except Exception as exc:
        errors.append({"path": "", "error": "save_userpref: " + str(exc)})

print("BLENDERMANAGER_RESULT=" + json.dumps({"applied": applied, "errors": errors}))
'''


@dataclass
class Preference:
    """Una preferencia escalar, ya filtrada (el usuario la cambió)."""

    path: str
    value: object
    selected: bool = True

    @property
    def section(self) -> str:
        """Sección de la ruta RNA (``view.ui_scale`` -> ``view``)."""
        return (self.path or "").split(".", 1)[0]

    @property
    def label(self) -> str:
        """Nombre legible de la clave (la última parte de la ruta)."""
        return self.path.rsplit(".", 1)[-1]


def is_environment(key: str) -> bool:
    """True si la clave depende del equipo y no conviene migrarla."""
    return any(key == blocked or key.startswith(blocked + ".")
               for blocked in ENVIRONMENT_KEYS)


def is_scalar(value) -> bool:
    """True si el valor se puede escribir como un número, texto o booleano."""
    return isinstance(value, (bool, int, float, str))


def changed(user: dict, factory: dict) -> list:
    """Todas las claves que el usuario cambió respecto a fábrica.

    ``diff`` aparta las que dependen del equipo; aquí se devuelven **todas**,
    porque para resumir "cuánto tiene este guardado" cuenta todo lo que el
    usuario tocó, esté donde esté. Es la misma base que usa ``diff``.
    """
    return _changed(user, factory)


def _changed(user: dict, factory: dict) -> list:
    """Todas las claves que el usuario cambió respecto a fábrica.

    Solo se miran las que están en las dos: una que falte en fábrica no es un
    "cambio del usuario", es una propiedad distinta (o una versión que no la
    tiene). Se descartan los valores no escalares y los que no se pueden volver
    a escribir por ruta RNA (ver ``is_settable``).
    """
    changed = []
    for path, value in user.items():
        if not is_scalar(value) or not is_settable(path):
            continue
        if path not in factory or factory[path] == value:
            continue
        changed.append(Preference(path=path, value=value))
    changed.sort(key=lambda item: item.path)
    return changed


def diff(user: dict, factory: dict) -> list:
    """Claves que el usuario cambió y que son suyas (no del equipo).

    Es lo que se ofrece migrar de verdad: los cambios que dependen del hardware
    o de rutas van aparte, en ``environment_preferences``.
    """
    return [item for item in _changed(user, factory)
            if not is_environment(item.path)]


def environment_preferences(user: dict, factory: dict) -> list:
    """Cambios que son del equipo (GPU, audio, rutas): se enseñan aparte.

    No se seleccionan por defecto, pero se listan para que el usuario sepa que
    existen y decida (sobre todo para migrar a la **misma** máquina).
    """
    items = [item for item in _changed(user, factory)
             if is_environment(item.path)]
    for item in items:
        item.selected = False
    return items


def group_by_section(preferences) -> dict:
    """Agrupa las preferencias por sección, conservando el orden de ``SECTIONS``."""
    order = {key: index for index, (key, _) in enumerate(SECTIONS)}
    groups = {}
    for item in preferences:
        groups.setdefault(item.section, []).append(item)
    grouped = []
    for section in sorted(groups, key=lambda key: (order.get(key, 99), key)):
        grouped.append((section, groups[section]))
    return grouped


def read_preferences(executable, factory: bool = False, timeout: int = 180,
                     config_dir=None) -> dict:
    """Pide a Blender su volcado de preferencias (de fábrica o del usuario).

    ``config_dir`` apunta a una carpeta de configuración concreta
    (``BLENDER_USER_CONFIG``): es lo que permite leer un guardado sin tocar la
    config viva. Devuelve ``{}`` si no se pudo (sin ejecutable, timeout, salida
    rara). El fallo no es fatal: la interfaz lo enseña como "no se pudo leer".
    """
    if not executable:
        return {}
    args = ["--background"]
    if factory:
        args.append("--factory-startup")
    args += ["--python-expr", _DUMP_SCRIPT]
    extra_env = None
    if config_dir:
        extra_env = {"BLENDER_USER_CONFIG": str(config_dir)}
    code, out, _ = blender_runner._run(executable, args, extra_env=extra_env,
                                       timeout=timeout)
    if code is None:
        return {}
    payload = blender_runner._parse_marker(out, "BLENDERMANAGER_DUMP=")
    return payload if isinstance(payload, dict) else {}


def snapshot_preferences(executable, snapshot, timeout: int = 180) -> dict:
    """Preferencias guardadas en una instantánea, sin tocarla.

    Se copia a un temporal y se arranca Blender con esa config: un guardado se
    abre **en una copia**, nunca en su sitio (Blender escribe cosas suyas al
    arrancar y no queremos que un guardado cambie por leerlo).
    """
    snapshot = Path(snapshot)
    if not executable or not snapshot.is_dir():
        return {}
    with tempfile.TemporaryDirectory(
            prefix="blendermanager-snapshot-") as tmp:
        config = Path(tmp) / "config"
        try:
            shutil.copytree(snapshot, config)
        except OSError:
            return {}
        return read_preferences(executable, config_dir=config, timeout=timeout)


def apply_preferences(executable, preferences, timeout: int = 180) -> dict:
    """Aplica esas claves (``Preference`` o pares ``(ruta, valor)``).

    Devuelve ``{"applied", "errors", "log"}``. Nunca lanza: si Blender no está
    o se cuelga, el motivo viaja en ``errors``.
    """
    pairs = []
    for item in preferences or []:
        if isinstance(item, Preference):
            pairs.append([item.path, item.value])
        else:
            pairs.append([item[0], item[1]])
    result = {"applied": [], "errors": [], "log": ""}
    if not pairs or not executable:
        result["errors"].append({"path": "", "error": "no Blender to run"})
        return result
    import json

    code, out, err = blender_runner._run(
        executable,
        ["--background", "--python-expr", _APPLY_SCRIPT],
        extra_env={"BLENDERMANAGER_PREFS": json.dumps(pairs)},
        timeout=timeout,
    )
    result["log"] = (err or "")[-4000:]
    if code is None:
        result["errors"].append({"path": "", "error": err})
        return result
    payload = blender_runner._parse_marker(out, "BLENDERMANAGER_RESULT=")
    if payload is None:
        result["errors"].append(
            {"path": "", "error": f"no result from Blender (exit {code})"})
        return result
    result["applied"] = list(payload.get("applied") or [])
    result["errors"] = list(payload.get("errors") or [])
    return result
