import json
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

import services.settings as settings_module
from model.build import Build
from services import api, detector, installed
from services.extractor import extract


def make_build(version, risk, branch, filename, platform="linux", arch="x86_64", mtime=0):
    return Build(version, branch, risk, platform, arch, "https://example/" + filename, filename, mtime=mtime)


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
            "release_cycle": "stable",
        }
        build = api._to_build(entry)
        self.assertEqual(build.version, "5.2.1")
        self.assertEqual(build.checksum, "ABC")
        self.assertTrue(build.is_lts)


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
        )
        settings.save()
        loaded = settings_module.Settings.load()
        self.assertEqual(loaded.dest_folder, "/tmp/blenders")
        self.assertEqual(loaded.language, "es")
        self.assertFalse(loaded.delete_archive)
        self.assertEqual(loaded.layout_mode, "list")
        self.assertAlmostEqual(loaded.zoom, 1.4)

    def test_defaults_fill_destination(self):
        loaded = settings_module.Settings.load()
        self.assertTrue(loaded.dest_folder)
        self.assertEqual(loaded.layout_mode, "grid")


class DetectorTests(unittest.TestCase):
    def test_detect_returns_known_arch(self):
        info = detector.detect()
        self.assertIn(info.arch, ("x86_64", "amd64", "arm64", "x86", ""))


if __name__ == "__main__":
    unittest.main()
