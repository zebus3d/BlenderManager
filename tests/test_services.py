import json
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

import services.settings as settings_module
from model.build import Build
from services import api, detector, installed
from services.extractor import extract, is_archive


def make_build(version, risk, branch, filename, platform="linux", arch="x86_64", mtime=0,
               build_hash=""):
    return Build(version, branch, risk, platform, arch, "https://example/" + filename, filename,
                 mtime=mtime, build_hash=build_hash)


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
