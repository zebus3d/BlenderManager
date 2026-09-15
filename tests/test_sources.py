"""Fuentes de descarga: el CDN de Blender y el release oficial.

Lo que se comprueba aquí es la **elección** (qué URL y qué checksum), no la
velocidad: la red se simula. Las medidas reales que motivaron todo esto están en
el docstring de ``services/sources.py``.
"""

import unittest
from unittest import mock

from model.build import Build
from services import sources


def make_build(version="4.4.3", platform="linux", arch="x86_64", risk="stable"):
    return Build(version=version, branch="v" + version[:2].replace(".", ""),
                 risk=risk, platform=platform, arch=arch, url="https://cdn/x.tar.xz",
                 filename="x.tar.xz", size=1, checksum="aaa")


class ReleaseUrlTests(unittest.TestCase):
    def test_mapea_plataforma_y_arquitectura(self):
        casos = {
            ("linux", "x86_64"): "linux-x64.tar.xz",
            ("linux", "arm64"): "linux-arm64.tar.xz",
            ("windows", "x86_64"): "windows-x64.zip",
            ("windows", "arm64"): "windows-arm64.zip",
            ("darwin", "x86_64"): "macos-x64.dmg",
            ("darwin", "arm64"): "macos-arm64.dmg",
        }
        for (platform, arch), esperado in casos.items():
            url = sources.release_url(make_build(platform=platform, arch=arch))
            self.assertTrue(url.endswith("blender-4.4.3-" + esperado), url)
            # La carpeta es por rama menor: Blender4.4.
            self.assertIn("/Blender4.4/", url)

    def test_no_hay_release_para_diarias_o_alfas(self):
        # Se compilan al vuelo: no están en download.blender.org (verificado,
        # 404 en todos los espejos). Sin esto la sonda gastaría una petición.
        for riesgo in ("alpha", "beta", "daily"):
            self.assertIsNone(sources.release_url(make_build(risk=riesgo)))

    def test_combinacion_desconocida_no_tiene_release(self):
        self.assertIsNone(sources.release_url(make_build(arch="riscv64")))


class ReleaseChecksumTests(unittest.TestCase):
    def _respuesta(self, texto):
        respuesta = mock.MagicMock()
        respuesta.read.return_value = texto.encode("utf-8")
        respuesta.__enter__ = lambda self: respuesta
        respuesta.__exit__ = lambda *args: None
        return respuesta

    def test_lee_el_hash_del_fichero_que_toca(self):
        texto = ("1111  blender-4.4.3-windows-x64.zip\n"
                 "8d3be07d2bc412b502c6bfe3cfe3e22195a4164076867da987ce148d73c27946"
                 "  blender-4.4.3-linux-x64.tar.xz\n")
        with mock.patch.object(sources.urllib.request, "urlopen",
                               return_value=self._respuesta(texto)):
            self.assertEqual(
                sources.release_checksum(make_build()),
                "8d3be07d2bc412b502c6bfe3cfe3e22195a4164076867da987ce148d73c27946")

    def test_si_no_esta_el_fichero_devuelve_none(self):
        with mock.patch.object(sources.urllib.request, "urlopen",
                               return_value=self._respuesta("1111  otro.zip\n")):
            self.assertIsNone(sources.release_checksum(make_build()))

    def test_si_falla_la_descarga_devuelve_none(self):
        with mock.patch.object(sources.urllib.request, "urlopen",
                               side_effect=OSError("sin red")):
            self.assertIsNone(sources.release_checksum(make_build()))


class ChooseTests(unittest.TestCase):
    """La sonda decide; ante cualquier duda, el CDN de siempre."""

    def test_elige_la_mas_rapida(self):
        def velocidad(url, timeout=0):
            return 20e6 if "download.blender.org" in url else 3e6

        with mock.patch.object(sources, "_speed", side_effect=velocidad), \
                mock.patch.object(sources, "release_checksum",
                                  return_value="hash-del-release"):
            elegida = sources.choose(make_build())
        self.assertIn("download.blender.org", elegida.url)
        self.assertEqual(elegida.checksum, "hash-del-release")

    def test_gana_el_cdn_si_es_mas_rapido(self):
        with mock.patch.object(sources, "_speed", return_value=20e6), \
                mock.patch.object(sources, "release_checksum") as checksum:
            elegida = sources.choose(make_build())
        self.assertEqual(elegida.url, "https://cdn/x.tar.xz")
        self.assertEqual(elegida.checksum, "aaa")
        self.assertFalse(checksum.called)

    def test_sin_mediciones_gana_el_cdn(self):
        with mock.patch.object(sources, "_speed", return_value=None):
            elegida = sources.choose(make_build())
        self.assertEqual(elegida.url, "https://cdn/x.tar.xz")

    def test_sin_checksum_del_release_gana_el_cdn(self):
        # No se descarga nada sin poder verificar el SHA-256.
        with mock.patch.object(sources, "_speed",
                               side_effect=[3e6, 20e6]), \
                mock.patch.object(sources, "release_checksum", return_value=None):
            elegida = sources.choose(make_build())
        self.assertEqual(elegida.url, "https://cdn/x.tar.xz")

    def test_una_alfa_no_gasta_sonda(self):
        # Solo hay una candidata: el CDN. No se mide nada.
        with mock.patch.object(sources, "_speed") as sonda:
            elegida = sources.choose(make_build(risk="alpha"))
        self.assertEqual(elegida.url, "https://cdn/x.tar.xz")
        self.assertFalse(sonda.called)


if __name__ == "__main__":
    unittest.main()
