import json
import tarfile
import tempfile
import unittest
import zipfile
from unittest import mock
from pathlib import Path

import services.settings as settings_module
from model.build import Build, favorite_key
from services import api, detector, installed, tls
from services.extractor import extract, is_archive


def make_build(version, risk, branch, filename, platform="linux", arch="x86_64", mtime=0,
               build_hash="", experimental=False):
    return Build(version, branch, risk, platform, arch, "https://example/" + filename, filename,
                 mtime=mtime, build_hash=build_hash, experimental=experimental)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.builds = [
            make_build("5.2.1", "stable", "v52", "b-5.2.1-linux.x86_64.tar.xz", mtime=100),
            make_build("5.3.0", "alpha", "main", "b-5.3.0-alpha-linux.x86_64.tar.xz", mtime=200),
            make_build("4.5.5", "stable", "v45", "b-4.5.5-linux.x86_64.tar.xz", mtime=50),
            make_build("5.2.0", "stable", "v52", "b-5.2.0-windows.amd64.zip", platform="windows", arch="amd64"),
        ]

    def test_available_filters_platform_and_arch(self):
        result = api.available_for(self.builds, "linux", "x86_64")
        self.assertEqual(len(result), 3)
        self.assertTrue(all(build.platform == "linux" for build in result))

    def test_available_sorted_desc(self):
        result = api.available_for(self.builds, "linux", "x86_64")
        self.assertEqual(result[0].version, "5.3.0")
        self.assertEqual(result[-1].version, "4.5.5")

    def test_available_prefers_extension(self):
        builds = [
            make_build("5.2.1", "stable", "v52", "b-linux.x86_64.tar.xz", mtime=1),
            make_build("5.2.1", "stable", "v52", "b-linux.x86_64.zip", mtime=2),
        ]
        result = api.available_for(builds, "linux", "x86_64")
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].filename.endswith(".tar.xz"))

    def test_to_build(self):
        entry = {
            "version": "5.2.1",
            "branch": "v52",
            "risk_id": "stable",
            "platform": "linux",
            "architecture": "x86_64",
            "url": "https://example/f.tar.xz",
            "file_name": "f.tar.xz",
            "file_size": 123,
            "checksum": "ABC",
            "file_mtime": 10,
            "hash": "b787619620d1",
        }
        build = api._to_build(entry)
        self.assertEqual(build.version, "5.2.1")
        self.assertEqual(build.checksum, "ABC")
        self.assertEqual(build.build_hash, "b787619620d1")
        self.assertTrue(build.is_lts)

    def test_to_build_experimental_flag(self):
        entry = {
            "version": "4.5.0", "branch": "geometry-nodes", "risk_id": "alpha",
            "platform": "linux", "architecture": "x86_64", "url": "u",
            "file_name": "f.tar.xz",
        }
        self.assertTrue(api._to_build(entry, experimental=True).experimental)
        self.assertFalse(api._to_build(entry).experimental)

    def test_available_prefers_dmg_on_darwin(self):
        # En macOS la API solo publica .dmg; que quede claro en los tests,
        # porque de ahí viene que no se pueda extraer.
        builds = [
            make_build("5.2.1", "stable", "v52", "b-darwin.arm64.dmg",
                       platform="darwin", arch="arm64"),
        ]
        result = api.available_for(builds, "darwin", "arm64")
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].filename.endswith(".dmg"))

    def test_load_cache_ignores_unknown_fields(self):
        # Un caché escrito por una versión anterior de la app no debe dejar la
        # tienda vacía por traer un campo que ya no existe.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "builds.json"
            payload = {
                "saved_at": 10 ** 12,
                "builds": [{
                    "version": "5.2.1", "branch": "v52", "risk": "stable",
                    "platform": "linux", "arch": "x86_64", "url": "u",
                    "filename": "f.tar.xz", "campo_que_ya_no_existe": "x",
                }],
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            original = api.cache_path
            api.cache_path = lambda: path
            try:
                builds = api.load_cache()
            finally:
                api.cache_path = original
            self.assertEqual(len(builds), 1)
            self.assertEqual(builds[0].version, "5.2.1")


class ChannelFilterTests(unittest.TestCase):
    """Filtro de canal de la tienda (incluidas las ramas experimentales)."""

    def _builds(self):
        return [
            make_build("5.2.1", "stable", "v52", "b.tar.xz", mtime=1),
            make_build("5.3.0", "alpha", "main", "b.tar.xz", mtime=2),
            make_build("4.5.13", "stable", "v45", "b.tar.xz", mtime=3),
            make_build("4.5.0", "alpha", "geometry-nodes", "b.tar.xz", mtime=4,
                       experimental=True),
        ]

    def test_experimental_only_in_its_own_channel(self):
        builds = self._builds()
        experimental = api.filter_builds(builds, "experimental")
        self.assertEqual([build.branch for build in experimental], ["geometry-nodes"])
        for channel in ("all", "lts", "stable", "lts_stable", "daily"):
            selected = api.filter_builds(builds, channel)
            self.assertNotIn("geometry-nodes", [build.branch for build in selected])

    def test_channels_keep_their_meaning(self):
        builds = self._builds()
        self.assertEqual(len(api.filter_builds(builds, "lts")), 2)
        self.assertEqual(len(api.filter_builds(builds, "stable")), 0)
        self.assertEqual(len(api.filter_builds(builds, "lts_stable")), 2)
        self.assertEqual(len(api.filter_builds(builds, "daily")), 1)
        self.assertEqual(len(api.filter_builds(builds, "all")), 3)

    def test_search(self):
        builds = self._builds()
        result = api.filter_builds(builds, "all", "5.3")
        self.assertEqual([build.version for build in result], ["5.3.0"])


class FavoriteFilterTests(unittest.TestCase):
    """El canal "Favoritos" es transversal: no es un canal de Blender."""

    def _builds(self):
        return [
            make_build("4.5.13", "stable", "v45", "a.tar.xz"),
            make_build("5.3.0", "alpha", "main", "b.tar.xz"),
            make_build("4.5.0", "alpha", "geometry-nodes", "c.tar.xz",
                       experimental=True),
        ]

    def test_solo_las_marcadas(self):
        builds = self._builds()
        marked = [favorite_key("v45", "4.5.13")]
        selected = api.filter_builds(builds, "favorites", "", marked)
        self.assertEqual([b.version for b in selected], ["4.5.13"])

    def test_incluye_experimentales_si_estan_marcadas(self):
        # A diferencia del resto de canales, aqui no se excluyen: si la has
        # marcado, la quieres ver.
        builds = self._builds()
        marked = [favorite_key("geometry-nodes", "4.5.0")]
        selected = api.filter_builds(builds, "favorites", "", marked)
        self.assertEqual([b.version for b in selected], ["4.5.0"])

    def test_la_busqueda_sigue_aplicando(self):
        builds = self._builds()
        marked = [b.favorite_key for b in builds]
        selected = api.filter_builds(builds, "favorites", "5.3", marked)
        self.assertEqual([b.version for b in selected], ["5.3.0"])

    def test_sin_marcadas_sale_vacio(self):
        self.assertEqual(api.filter_builds(self._builds(), "favorites"), [])


class InstalledTests(unittest.TestCase):
    def test_scan_finds_versions_and_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "blender-4.5.13-linux-x64"
            folder.mkdir()
            (folder / "blender").write_text("#!/bin/sh\n")
            (root / "not-a-build").mkdir()
            results = installed.scan(root, "linux")
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].version, "4.5.13")
            self.assertTrue(results[0].can_launch)

    def test_scan_missing_folder(self):
        self.assertEqual(installed.scan("/nonexistent/path/xyz", "linux"), [])

    def test_is_version_installed(self):
        entry = installed.InstalledBuild("b", Path("/tmp/b"), "5.2.0")
        self.assertTrue(installed.is_version_installed([entry], "5.2.0"))
        self.assertFalse(installed.is_version_installed([entry], "5.2.1"))

    def test_executable_search_is_depth_limited(self):
        # El ejecutable enterrado a tres niveles no cuenta: si no ponemos
        # tope, un escaneo recorre el árbol entero de Blender.
        with tempfile.TemporaryDirectory() as tmp:
            deep = Path(tmp) / "blender-5.2.0" / "a" / "b" / "c"
            deep.mkdir(parents=True)
            (deep / "blender").write_text("bin")
            results = installed.scan(Path(tmp), "linux")
            self.assertEqual(len(results), 1)
            self.assertFalse(results[0].can_launch)


class InstalledFilterTests(unittest.TestCase):
    """Filtro de canal de la pestaña de instaladas."""

    def _entries(self):
        return [
            installed.InstalledBuild("blender-4.5.13-linux-x64", Path("/tmp/a"), "4.5.13",
                                     branch="v45"),
            installed.InstalledBuild("blender-5.3.0-alpha-linux-x64", Path("/tmp/b"), "5.3.0",
                                     branch="main"),
            installed.InstalledBuild("blender-4.5.0-geometry-nodes-linux-x64", Path("/tmp/c"),
                                     "4.5.0", branch="geometry-nodes"),
        ]

    def test_experimental_only_in_its_own_channel(self):
        entries = self._entries()
        experimental = installed.filter_installed(entries, "experimental")
        self.assertEqual([entry.branch for entry in experimental], ["geometry-nodes"])
        for channel in ("all", "lts", "stable", "daily"):
            selected = installed.filter_installed(entries, channel)
            self.assertNotIn("geometry-nodes", [entry.branch for entry in selected])

    def test_daily_and_lts(self):
        entries = self._entries()
        self.assertEqual(len(installed.filter_installed(entries, "lts")), 1)
        self.assertEqual(len(installed.filter_installed(entries, "daily")), 1)

    def test_favoritos_comparten_clave_con_la_tienda(self):
        # La clave no lleva plataforma ni arquitectura a proposito: asi marcar
        # una version en la tienda marca tambien la que tienes instalada.
        build = make_build("4.5.13", "stable", "v45", "b.tar.xz")
        entry = installed.InstalledBuild("blender-4.5.13-linux-x64", Path("/tmp/a"),
                                         "4.5.13", branch="v45")
        self.assertEqual(build.favorite_key, entry.favorite_key)
        self.assertEqual(build.favorite_key, favorite_key("v45", "4.5.13"))
        # Dos builds del mismo dia (mismo numero, hash distinto) comparten
        # favorito: si no, el de una diaria se perderia al dia siguiente.
        otra = make_build("4.5.13", "daily", "v45", "c.tar.xz", build_hash="ffff")
        self.assertEqual(build.favorite_key, otra.favorite_key)

    def test_filtro_de_favoritos(self):
        entries = self._entries()
        marked = [entries[1].favorite_key]
        selected = installed.filter_installed(entries, "favorites", "", marked)
        self.assertEqual([entry.branch for entry in selected], ["main"])
        # Sin marcar nada el canal sale vacio (y no revienta).
        self.assertEqual(installed.filter_installed(entries, "favorites"), [])


class FindInstalledTests(unittest.TestCase):
    """Las diarias comparten número de versión, así que se comparan por hash."""

    def _entry(self, build_hash=""):
        return installed.InstalledBuild(
            "blender-5.3.0-linux-x64", Path("/tmp/x"), "5.3.0", build_hash=build_hash)

    def test_stable_matches_by_version(self):
        entry = installed.InstalledBuild("b", Path("/tmp/b"), "5.2.1")
        build = make_build("5.2.1", "stable", "v52", "f.tar.xz", build_hash="otro")
        self.assertIsNotNone(installed.find_installed([entry], build))

    def test_daily_with_other_hash_is_not_installed(self):
        entry = self._entry(build_hash="aaaaaaaaaaaa")
        build = make_build("5.3.0", "alpha", "main", "f.tar.xz", build_hash="bbbbbbbbbbbb")
        self.assertIsNone(installed.find_installed([entry], build))

    def test_daily_with_same_hash_is_installed(self):
        entry = self._entry(build_hash="aaaaaaaaaaaa")
        build = make_build("5.3.0", "alpha", "main", "f.tar.xz", build_hash="aaaaaaaaaaaa")
        self.assertIsNotNone(installed.find_installed([entry], build))

    def test_daily_without_marker_falls_back_to_version(self):
        # Carpetas instaladas antes de que existiera el marcador: se comportan
        # como siempre en vez de aparecer de golpe como no instaladas.
        entry = self._entry()
        build = make_build("5.3.0", "alpha", "main", "f.tar.xz", build_hash="bbbbbbbbbbbb")
        self.assertIsNotNone(installed.find_installed([entry], build))

    def test_marker_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "blender-5.3.0-linux-x64"
            folder.mkdir()
            (folder / "blender").write_text("bin")
            build = make_build("5.3.0", "alpha", "main", "f.tar.xz", build_hash="abc123abc123")
            installed.write_marker(folder, build)
            scanned = installed.scan(Path(tmp), "linux")
            self.assertEqual(scanned[0].build_hash, "abc123abc123")
            self.assertIsNone(installed.find_installed(
                scanned, make_build("5.3.0", "alpha", "main", "f.tar.xz", build_hash="otro")))


class ExtractorTests(unittest.TestCase):
    def _make_tar(self, path, member_name):
        source = Path(path).parent / "payload"
        source.mkdir()
        (source / "blender").write_text("bin")
        with tarfile.open(path, "w:xz") as archive:
            archive.add(source / "blender", arcname=f"{member_name}/blender")

    def test_extract_tar_xz(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "build.tar.xz"
            self._make_tar(archive_path, "blender-9.9.9-linux-x64")
            dest = Path(tmp) / "out"
            target = extract(archive_path, dest)
            self.assertEqual(target.name, "blender-9.9.9-linux-x64")
            self.assertTrue((target / "blender").is_file())

    def test_extract_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "build.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("blender-8.8.8-windows.zip/blender.exe", "bin")
            target = extract(archive_path, Path(tmp) / "out")
            self.assertTrue((target / "blender.exe").is_file())

    def test_dmg_is_not_an_archive(self):
        # macOS: la API sirve .dmg y no sabemos abrirlo. Que no acabe en la
        # rama de tarfile es justo lo que evita el falso "Download failed".
        self.assertFalse(is_archive("blender-5.2.1-macos.dmg"))
        self.assertTrue(is_archive("blender-5.2.1-linux.tar.xz"))
        self.assertTrue(is_archive("blender-5.2.1-windows.zip"))

    def test_extract_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "evil.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../evil.txt", "nope")
            with self.assertRaises(ValueError):
                extract(archive_path, Path(tmp) / "out")


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._original = settings_module.config_dir
        settings_module.config_dir = lambda: Path(self.tmp.name)

    def tearDown(self):
        settings_module.config_dir = self._original
        self.tmp.cleanup()

    def test_roundtrip(self):
        settings = settings_module.Settings(
            dest_folder="/tmp/blenders",
            language="es",
            delete_archive=False,
            launch_args="--background",
            layout_mode="list",
            zoom=1.4,
            auto_update=False,
            window_width=1200,
            window_height=700,
            platform="Windows",
            arch="arm64",
        )
        settings.save()
        loaded = settings_module.Settings.load()
        self.assertEqual(loaded.dest_folder, "/tmp/blenders")
        self.assertEqual(loaded.language, "es")
        self.assertFalse(loaded.delete_archive)
        self.assertEqual(loaded.layout_mode, "list")
        self.assertAlmostEqual(loaded.zoom, 1.4)
        self.assertFalse(loaded.auto_update)
        self.assertEqual(loaded.window_width, 1200)
        self.assertEqual(loaded.window_height, 700)
        self.assertEqual(loaded.platform, "Windows")
        self.assertEqual(loaded.arch, "arm64")

    def test_save_is_atomic(self):
        # Tras guardar no debe quedar ningún .tmp suelto y el JSON debe ser
        # legible (la escritura va a un temporal y luego se mueve encima).
        settings_module.Settings(dest_folder="/tmp/x").save()
        directory = Path(self.tmp.name)
        self.assertEqual(list(directory.glob("*.tmp")), [])
        json.loads((directory / "settings.json").read_text(encoding="utf-8"))

    def test_defaults_fill_destination(self):
        loaded = settings_module.Settings.load()
        self.assertTrue(loaded.dest_folder)
        self.assertEqual(loaded.layout_mode, "grid")
        self.assertTrue(loaded.auto_update)
        self.assertEqual(loaded.favorites, [])

    def test_favoritos_se_marcan_y_se_guardan(self):
        settings = settings_module.Settings()
        self.assertTrue(settings.set_favorite("v45|4.5.13", True))
        # Repetirlo no cambia nada (y no ensucia el JSON con duplicados).
        self.assertFalse(settings.set_favorite("v45|4.5.13", True))
        self.assertTrue(settings.set_favorite("main|5.3.0", True))
        settings.save()
        self.assertEqual(settings_module.Settings.load().favorites,
                         ["v45|4.5.13", "main|5.3.0"])
        # Y se pueden quitar.
        self.assertTrue(settings.set_favorite("v45|4.5.13", False))
        self.assertFalse(settings.set_favorite("v45|4.5.13", False))
        self.assertEqual(settings.favorites, ["main|5.3.0"])
        # Una clave vacia se ignora.
        self.assertFalse(settings.set_favorite("", True))

    def test_recuerda_el_filtro_de_canal(self):
        settings = settings_module.Settings()
        self.assertEqual(settings.channel, "all")
        settings.channel = "favorites"
        settings.save()
        self.assertEqual(settings_module.Settings.load().channel, "favorites")

    def test_filtro_desconocido_cae_a_todas(self):
        # Un settings.json editado a mano (o de una version con otros filtros)
        # no puede dejar la barra sin ninguna pastilla marcada.
        (Path(self.tmp.name) / "settings.json").write_text(
            json.dumps({"channel": "inventado"}), encoding="utf-8")
        self.assertEqual(settings_module.Settings.load().channel, "all")

    def test_favoritos_con_basura_en_el_json(self):
        (Path(self.tmp.name) / "settings.json").write_text(
            json.dumps({"favorites": ["v45|4.5.13", 7, None, "", "v45|4.5.13"]}),
            encoding="utf-8")
        loaded = settings_module.Settings.load()
        self.assertEqual(loaded.favorites, ["v45|4.5.13"])


class SmokeTests(unittest.TestCase):
    """`--smoke` tiene que decir la verdad: si no hay red, fallar."""

    def _smoke(self, efecto):
        """Ejecuta smoke() con la descarga simulada, sin ensuciar la salida."""
        import contextlib
        import io

        import main

        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()), \
                mock.patch.object(main.api, "fetch_builds", **efecto):
            return main.smoke()

    def test_con_red_devuelve_cero(self):
        builds = [make_build("5.2.1", "stable", "v52", "b.tar.xz")]
        self.assertEqual(self._smoke({"return_value": builds}), 0)

    def test_sin_red_falla(self):
        # Antes caia al cache de disco y salia con 0: un binario sin HTTPS
        # "parecia" funcionar. Se descubrio en Arch, con el auto-update roto.
        self.assertEqual(
            self._smoke({"side_effect": OSError("sin red")}), 1)

    def test_listado_vacio_falla(self):
        self.assertEqual(self._smoke({"return_value": []}), 1)


class TlsTests(unittest.TestCase):
    """El binario empaquetado no encontraba las CAs fuera de Debian/Ubuntu."""

    def setUp(self):
        self._original = tls._ca_file
        tls._ca_file = None

    def tearDown(self):
        tls._ca_file = self._original

    def test_usa_el_primer_candidato_que_existe(self):
        # En esta maquina (como en la mayoria) hay al menos uno.
        self.assertTrue(tls.ca_file())
        self.assertTrue(any(tls.ca_file() == c for c in tls.CA_CANDIDATES))

    def test_el_contexto_trae_autoridades_de_verdad(self):
        # Lo que fallaba era justo esto: un contexto sin CAs, que rechaza
        # cualquier certificado con "unable to get local issuer certificate".
        contexto = tls.ssl_context()
        self.assertGreater(contexto.cert_store_stats()["x509_ca"], 0)

    def test_sin_candidatos_cae_al_contexto_por_defecto(self):
        # Si no hay ningun fichero conocido, no se inventa nada: contexto
        # normal, y como mucho fallara la peticion (no se degrada la seguridad).
        with mock.patch.object(tls, "CA_CANDIDATES", ("/no/existe/ca.crt",)):
            tls._ca_file = None
            self.assertIsNone(tls.ca_file())
            self.assertIsNotNone(tls.ssl_context())


class DetectorTests(unittest.TestCase):
    def test_detect_returns_known_arch(self):
        info = detector.detect()
        self.assertIn(info.arch, ("x86_64", "amd64", "arm64", "x86", ""))


if __name__ == "__main__":
    unittest.main()


class ReleaseNotesUrlTests(unittest.TestCase):
    """La "i" de cada tarjeta abre las notas de esa serie de Blender."""

    def test_series_page(self):
        self.assertEqual(
            api.release_notes_url("4.2.1"),
            "https://developer.blender.org/docs/release_notes/4.2/")
        self.assertEqual(
            api.release_notes_url("5.2.0-alpha"),
            "https://developer.blender.org/docs/release_notes/5.2/")
        self.assertEqual(
            api.release_notes_url("2.93.18"),
            "https://developer.blender.org/docs/release_notes/2.93/")

    def test_falls_back_to_the_index(self):
        # Sin versión entendible o antes de que hubiera notas publicadas.
        for version in ("", None, "sin numero", "2.78c", "1.0"):
            self.assertEqual(
                api.release_notes_url(version),
                "https://developer.blender.org/docs/release_notes/")
