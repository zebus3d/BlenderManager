"""Tests de las preferencias selectivas (``services/blender_prefs``).

El volcado y la aplicación reales se prueban contra Blender de verdad en el
momento de desarrollo; aquí se prueba la parte pura (filtrado, diff, agrupado),
que es la que decide **qué** se ofrece migrar.
"""

import unittest

from services import blender_prefs as bp


class FilterTest(unittest.TestCase):
    def test_entorno_no_es_preferencia_del_usuario(self):
        self.assertTrue(bp.is_environment("system.gpu_backend"))
        self.assertTrue(bp.is_environment("system.audio_device"))
        self.assertTrue(bp.is_environment("filepaths.temp_directory"))
        self.assertFalse(bp.is_environment("view.ui_scale"))
        self.assertFalse(bp.is_environment("inputs.use_zoom_to_mouse"))
        # El dispositivo de Cycles (OPTIX/CUDA/HIP) es una preferencia del
        # usuario: se migra lo que él tenga configurado, no se descarta.
        self.assertFalse(
            bp.is_environment("addons.cycles.compute_device_type"))

    def test_seccion_de_una_clave_de_addon(self):
        pref = bp.Preference("addons.cycles.compute_device_type", "OPTIX")
        self.assertEqual(pref.section, "addons")
        self.assertEqual(pref.label, "compute_device_type")
        self.assertIn(("addons", "Add-ons"), bp.SECTIONS)

    def test_sets_conocidos_no_son_escribibles(self):
        self.assertFalse(bp.is_settable("edit.key_insert_channels"))
        self.assertTrue(bp.is_settable("edit.undo_steps"))

    def test_seccion(self):
        self.assertEqual(bp.Preference("view.ui_scale", 1).section, "view")
        self.assertEqual(
            bp.Preference("inputs.use_zoom_to_mouse", True).section, "inputs")
        self.assertEqual(bp.Preference("", 0).section, "")


class DiffTest(unittest.TestCase):
    def setUp(self):
        self.factory = {
            "view.ui_scale": 1.0,
            "view.show_developer_ui": False,
            "inputs.use_zoom_to_mouse": False,
            "system.gpu_backend": "OPENGL",
            "system.audio_device": "PulseAudio",
            "edit.key_insert_channels": "{'A'}",
        }

    def test_solo_devuelve_lo_que_cambio(self):
        user = dict(self.factory)
        user["view.ui_scale"] = 1.25
        user["view.show_developer_ui"] = True
        prefs = {p.path: p for p in bp.diff(user, self.factory)}
        self.assertEqual(set(prefs), {"view.ui_scale", "view.show_developer_ui"})
        self.assertEqual(prefs["view.ui_scale"].value, 1.25)

    def test_filtra_claves_del_equipo(self):
        user = dict(self.factory)
        user["system.gpu_backend"] = "VULKAN"
        self.assertEqual(bp.diff(user, self.factory), [])

    def test_filtra_valores_no_escalares(self):
        user = dict(self.factory)
        user["edit.key_insert_channels"] = "{'A', 'B'}"
        self.assertEqual(bp.diff(user, self.factory), [])

    def test_no_inventa_claves_que_no_estan_en_factory(self):
        user = dict(self.factory)
        user["view.nueva_de_esta_version"] = 3
        self.assertEqual(bp.diff(user, self.factory), [])

    def test_incluye_prefs_de_addons_que_no_estan_en_fabrica(self):
        """Un addon activado solo en la config del usuario no sale en fábrica.

        Sus preferencias faltan del volcado de fábrica (el addon no está
        activado allí) y antes se descartaban; ahora se ofrecen.
        """
        user = dict(self.factory)
        user["addons.hurricane.cache_format"] = "USD"
        self.assertIn("addons.hurricane.cache_format",
                      [pref.path for pref in bp.diff(user, self.factory)])

    def test_environment_preferences_va_aparte_y_sin_marcar(self):
        user = dict(self.factory)
        user["system.gpu_backend"] = "VULKAN"
        items = bp.environment_preferences(user, self.factory)
        self.assertEqual([p.path for p in items], ["system.gpu_backend"])
        self.assertFalse(items[0].selected)


class GroupTest(unittest.TestCase):
    def test_agrupa_por_seccion_en_orden(self):
        prefs = [
            bp.Preference("inputs.use_zoom_to_mouse", True),
            bp.Preference("view.ui_scale", 1.25),
            bp.Preference("view.show_developer_ui", True),
        ]
        grouped = bp.group_by_section(prefs)
        self.assertEqual([section for section, _ in grouped], ["view", "inputs"])
        self.assertEqual(len(grouped[0][1]), 2)


if __name__ == "__main__":
    unittest.main()
