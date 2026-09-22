"""La pantalla de migración, repartida por pestañas.

``MigrateView`` (en ``view.py``) es la cáscara: las pestañas, la tarjeta común
de origen → destino y el aviso de "Blender abierto". Cada pestaña es un mixin
en su propio módulo, porque apenas comparten nada más:

* ``addons_tab.py`` — copiar add-ons y extensiones de una versión a otra.
* ``prefs_tab.py`` — copiar ajustes (uno a uno, presets o el fichero entero).
* ``factory_tab.py`` — dejar una versión como recién instalada, sin perder nada.
* ``common.py`` — lo que usan las tres (textos de estado, el asa, las listas).

Se importa como siempre: ``from ui.widgets.migrate import MigrateView``.
"""

from ui.widgets.migrate.view import MigrateView

__all__ = ["MigrateView"]
