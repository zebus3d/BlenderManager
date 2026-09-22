"""Un ``bpy`` de mentira para ejecutar los guiones de ``blender_prefs``.

Los guiones que corren dentro de Blender (``_DUMP_SCRIPT`` y ``_APPLY_SCRIPT``)
son Python normal salvo por ``bpy`` y ``addon_utils``. Con esta imitación del
RNA (propiedades con ``identifier``/``type``/``name``/``description``...) se
pueden ejecutar de verdad en los tests, en vez de comprobar que el texto del
guion contiene tal o cual palabra. Es lo que permite probar la recursión por
POINTER, los arrays, los enum de varios valores o un puntero a ``None``.
"""

import sys
import types


class FakeProp:
    """Una propiedad RNA: lo justo que miran los guiones."""

    def __init__(self, identifier, kind, default=None, *, name="",
                 description="", subtype="NONE", readonly=False,
                 is_array=False, enum_flag=False):
        self.identifier = identifier
        self.type = kind
        self.name = name
        self.description = description
        self.subtype = subtype
        self.is_readonly = readonly
        self.is_array = is_array
        self.is_enum_flag = enum_flag
        if enum_flag:
            self.default_flag = set(default or ())
        elif is_array:
            self.default_array = tuple(default or ())
        else:
            self.default = default


class PropCollection(list):
    """``bl_rna.properties``: se itera y se consulta por identificador."""

    def get(self, identifier):
        for prop in self:
            if prop.identifier == identifier:
                return prop
        return None


class FakeRNA:
    def __init__(self, props):
        self.properties = PropCollection(props)


class FakeObj:
    """Un objeto RNA: ``bl_rna`` + un atributo por propiedad."""

    def __init__(self, props, **values):
        self.bl_rna = FakeRNA(props)
        for key, value in values.items():
            setattr(self, key, value)


class Raising:
    """Descriptor que revienta al leerse: simula una propiedad rota."""

    def __get__(self, instance, owner):
        raise RuntimeError("cannot read")


class FakeAddon:
    def __init__(self, module, preferences):
        self.module = module
        self.preferences = preferences


class FakeAddons:
    """La colección ``preferences.addons`` (iterable, ``keys``, ``get``)."""

    def __init__(self, addons):
        self._addons = {addon.module: addon for addon in addons}

    def __iter__(self):
        return iter(self._addons.values())

    def keys(self):
        return list(self._addons)

    def get(self, module):
        return self._addons.get(module)

    def add(self, addon):
        self._addons[addon.module] = addon


def pointer(identifier, target, **kw):
    return FakeProp(identifier, "POINTER", **kw), target


def build_preferences():
    """Un árbol de preferencias con un caso de cada tipo que importa.

    Devuelve ``(preferences, view)`` para que los tests puedan mirar los
    atributos escritos.
    """
    view = FakeObj(
        [
            FakeProp("ui_scale", "FLOAT", 1.0, name="Resolution Scale",
                     description="Size multiplier for the UI"),
            FakeProp("show_developer_ui", "BOOLEAN", False,
                     name="Developer Extras"),
            FakeProp("color_thing", "FLOAT", (0.1, 0.2, 0.3), name="Color",
                     subtype="COLOR", is_array=True),
            FakeProp("text_hint", "STRING", "", name="Hint",
                     description="Where files go"),
            FakeProp("rna_type", "POINTER"),
        ],
        ui_scale=1.25, show_developer_ui=False, color_thing=(0.1, 0.2, 0.3),
        text_hint="", rna_type=None,
    )
    edit = FakeObj(
        [FakeProp("key_insert_channels", "ENUM", {"LOCATION", "ROTATION"},
                  name="Default Key Channels", enum_flag=True),
         FakeProp("undo_steps", "INT", 32, name="Undo Steps")],
        key_insert_channels={"ROTATION", "LOCATION", "SCALE"}, undo_steps=64,
    )
    system = FakeObj(
        [FakeProp("memory_cache_limit", "INT", 4096, name="Memory Cache Limit"),
         FakeProp("readonly_thing", "INT", 1, readonly=True),
         FakeProp("broken", "POINTER"),
         FakeProp("explodes", "INT", 0)],
        memory_cache_limit=8192, readonly_thing=1, broken=None,
    )
    # ``explodes`` revienta al leerse: se anota en ``skipped`` y se sigue.
    type(system).explodes = Raising()
    preferences = FakeObj(
        [FakeProp("view", "POINTER"), FakeProp("edit", "POINTER"),
         FakeProp("system", "POINTER"), FakeProp("themes", "COLLECTION"),
         FakeProp("version", "INT", (5, 2, 0), is_array=True)],
        view=view, edit=edit, system=system, themes=["default"],
        version=(5, 2, 0),
    )
    cycles_prefs = FakeObj(
        [FakeProp("compute_device_type", "ENUM", "NONE",
                  name="Cycles Render Device"),
         FakeProp("peer_memory", "BOOLEAN", False)],
        compute_device_type="OPTIX", peer_memory=False,
    )
    preferences.addons = FakeAddons([FakeAddon("cycles", cycles_prefs)])
    return preferences, view


class FakeBpy:
    """Módulo ``bpy`` con lo que usan los guiones: contexto, utils y ops."""

    def __init__(self, preferences, config_dir):
        self.context = types.SimpleNamespace(preferences=preferences)
        self.utils = types.SimpleNamespace(
            user_resource=lambda kind: str(config_dir))
        self.saved = 0

        def save_userpref():
            self.saved += 1

        self.ops = types.SimpleNamespace(
            wm=types.SimpleNamespace(save_userpref=save_userpref))


class FakeAddonUtils:
    """``addon_utils`` con ``modules()`` y ``enable()`` que se pueden observar."""

    def __init__(self, available, on_enable=None):
        self._available = [types.SimpleNamespace(__name__=name)
                           for name in available]
        self._on_enable = on_enable
        self.enabled = []

    def modules(self):
        return list(self._available)

    def enable(self, module, default_set=False):
        self.enabled.append(module)
        if self._on_enable is not None:
            self._on_enable(module)


def install(bpy, addon_utils=None):
    """Mete los módulos falsos en ``sys.modules`` y devuelve cómo quitarlos."""
    previous = {name: sys.modules.get(name) for name in ("bpy", "addon_utils")}
    sys.modules["bpy"] = bpy
    if addon_utils is not None:
        sys.modules["addon_utils"] = addon_utils

    def restore():
        for name, module in previous.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    return restore
