import unittest

import i18n


class I18nTests(unittest.TestCase):
    def tearDown(self):
        i18n.set_language("en")

    def test_english_passthrough(self):
        i18n.set_language("en")
        self.assertEqual(i18n.tr("Download"), "Download")
        self.assertEqual(i18n.tr("Unknown key"), "Unknown key")

    def test_spanish_translation(self):
        i18n.set_language("es")
        self.assertEqual(i18n.tr("Download"), "Descargar")
        self.assertEqual(i18n.tr("Downloads"), "Descargas")

    def test_format_arguments(self):
        i18n.set_language("es")
        self.assertEqual(i18n.tr("Downloading {name}", name="x.tar.xz"), "Descargando x.tar.xz")

    def test_broken_placeholder_does_not_raise(self):
        i18n.set_language("es")
        # Una traducción con una llave suelta no puede tumbar la interfaz.
        i18n._TRANSLATIONS["es"]["__rota__"] = "Version {"
        try:
            self.assertEqual(i18n.tr("__rota__", version="1"), "Version {")
        finally:
            del i18n._TRANSLATIONS["es"]["__rota__"]

    def test_auto_falls_back(self):
        i18n.set_language("auto")
        self.assertIn(i18n.get_language(), ("en", "es"))


if __name__ == "__main__":
    unittest.main()


class CoberturaTests(unittest.TestCase):
    """Que no se cuele una cadena sin traducir al español.

    Se leen las llamadas a ``tr("...")`` con ``ast``, que junta solo las
    cadenas partidas en varias líneas: buscarlas con ``grep`` no vale, porque
    en el código van troceadas y la clave es el texto ya unido (justo el error
    que hace que una traducción no enganche y el usuario vea inglés suelto).
    """

    def test_todas_las_cadenas_tienen_traduccion(self):
        import ast
        from pathlib import Path

        spanish = i18n._TRANSLATIONS["es"]
        missing = []
        root = Path(__file__).resolve().parents[1] / "src"
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id == "tr" and node.args):
                    continue
                first = node.args[0]
                if not (isinstance(first, ast.Constant)
                        and isinstance(first.value, str) and first.value):
                    continue
                if first.value not in spanish:
                    missing.append(f"{path.name}:{node.lineno} {first.value!r}")
        self.assertEqual(missing, [], "\n".join(missing))
