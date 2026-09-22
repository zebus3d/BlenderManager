"""Tests del tema/keymap como presets (``services/blender_style``).

Nunca se arranca Blender: se mockea ``blender_runner._run`` y se comprueba que
se interpretan bien sus salidas y qué entorno se le pasa.
"""

import json
import unittest
from unittest import mock

from services import blender_style as bs


def _completed(payload, code=0):
    line = "BLENDERMANAGER_RESULT=" + json.dumps(payload) + "\n"
    return code, line, ""


class ExportStyleTest(unittest.TestCase):
    def test_exporta_y_parsea(self):
        payload = {"theme": "/t.xml", "keymap": "/k.py", "errors": []}
        with mock.patch.object(bs.blender_runner, "_run",
                               return_value=_completed(payload)):
            result = bs.export_style("/bin/blender", "/tmp/style")
        self.assertEqual(result["theme"], "/t.xml")
        self.assertEqual(result["keymap"], "/k.py")
        self.assertEqual(result["errors"], [])

    def test_sin_ejecutable_no_arranca(self):
        with mock.patch.object(bs.blender_runner, "_run") as run:
            result = bs.export_style("", "/tmp/style")
            run.assert_not_called()
        self.assertTrue(result["errors"])

    def test_salida_rara(self):
        with mock.patch.object(bs.blender_runner, "_run",
                               return_value=(0, "ruido\n", "")):
            result = bs.export_style("/bin/blender", "/tmp/style")
        self.assertEqual(result["theme"], "")
        self.assertTrue(result["errors"])


class ImportStyleTest(unittest.TestCase):
    def test_instala_y_parsea(self):
        payload = {"applied": ["theme", "keymap"], "errors": []}
        with mock.patch.object(bs.blender_runner, "_run",
                               return_value=_completed(payload)):
            result = bs.import_style("/bin/blender", "BlenderManager 5.2",
                                     "/t.xml", "/k.py")
        self.assertEqual(result["applied"], ["theme", "keymap"])

    def test_pasa_el_nombre_y_las_rutas_por_entorno(self):
        with mock.patch.object(bs.blender_runner, "_run",
                               return_value=_completed({"applied": [],
                                                        "errors": []})) as run:
            bs.import_style("/bin/blender", "BM 5.2", "/t.xml", "/k.py")
        env = run.call_args[1]["extra_env"]
        self.assertEqual(env["BLENDERMANAGER_STYLE_NAME"], "BM 5.2")
        self.assertEqual(env["BLENDERMANAGER_STYLE_THEME"], "/t.xml")
        self.assertEqual(env["BLENDERMANAGER_STYLE_KEYMAP"], "/k.py")


class CopyStyleTest(unittest.TestCase):
    def test_exporta_del_origen_e_instala_en_el_destino(self):
        export = _completed({"theme": "/t.xml", "keymap": "/k.py",
                             "errors": []})
        install = _completed({"applied": ["theme", "keymap"], "errors": []})
        with mock.patch.object(bs.blender_runner, "_run",
                               side_effect=[export, install]) as run:
            result = bs.copy_style("/bin/src", "/bin/dst", "BM 5.2")
        self.assertEqual(run.call_count, 2)
        self.assertEqual(result["applied"], ["theme", "keymap"])
        self.assertEqual(result["errors"], [])

    def test_los_errores_del_export_no_se_pierden(self):
        export = _completed({"theme": "", "keymap": "/k.py",
                             "errors": ["theme: fallo"]})
        install = _completed({"applied": ["keymap"], "errors": []})
        with mock.patch.object(bs.blender_runner, "_run",
                               side_effect=[export, install]):
            result = bs.copy_style("/bin/src", "/bin/dst", "BM 5.2")
        self.assertIn("theme: fallo", result["errors"])
        self.assertEqual(result["applied"], ["keymap"])


if __name__ == "__main__":
    unittest.main()
