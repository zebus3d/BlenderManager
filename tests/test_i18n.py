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
