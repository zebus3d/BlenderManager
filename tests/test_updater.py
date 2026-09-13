import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services import updater


class VersionCompareTests(unittest.TestCase):
    def test_is_newer(self):
        self.assertTrue(updater.is_newer("1.0.0", "1.0.1"))
        self.assertTrue(updater.is_newer("1.0", "v2.0"))
        self.assertTrue(updater.is_newer("1.0.0", "1.10.0"))
        self.assertFalse(updater.is_newer("1.2.0", "1.1.9"))
        self.assertFalse(updater.is_newer("1.0.0", "1.0.0"))
        self.assertFalse(updater.is_newer("1.0.0", ""))

    def test_asset_for(self):
        self.assertEqual(updater.asset_for("linux"), "BlenderManager-x86_64.AppImage")
        self.assertEqual(updater.asset_for("windows"), "BlenderManager-windows-x86_64.zip")
        self.assertEqual(updater.asset_for("darwin"), "BlenderManager-macos.zip")
        self.assertIsNone(updater.asset_for("plan9"))


class ParseReleaseTests(unittest.TestCase):
    def test_parse(self):
        payload = {
            "tag_name": "v1.2.0",
            "assets": [
                {"name": "a", "browser_download_url": "http://a"},
                {"name": "b", "browser_download_url": "http://b"},
            ],
        }
        tag, assets = updater._parse_release(payload)
        self.assertEqual(tag, "v1.2.0")
        self.assertEqual([asset["name"] for asset in assets], ["a", "b"])
        self.assertEqual(assets[0]["url"], "http://a")

    def test_parse_empty(self):
        tag, assets = updater._parse_release({})
        self.assertEqual(tag, "")
        self.assertEqual(assets, [])


class _FakeResponse:
    def __init__(self, body=b"", headers=None):
        self._body = body
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._body


class ChecksumTests(unittest.TestCase):
    def test_checksum_for(self):
        body = (
            b"abc123  BlenderManager-x86_64.AppImage\n"
            b"def456  ./BlenderManager-linux/BlenderManager-x86_64.AppImage\n"
        )
        assets = [{"name": "checksums.txt", "url": "http://checksums"}]
        with mock.patch("urllib.request.urlopen", return_value=_FakeResponse(body)):
            value = updater.checksum_for(assets, "BlenderManager-x86_64.AppImage")
        self.assertEqual(value, "abc123")

    def test_checksum_missing_asset(self):
        self.assertIsNone(updater.checksum_for([], "whatever"))


class LatestReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._original = updater.cache_dir
        updater.cache_dir = lambda: Path(self.tmp.name)

    def tearDown(self):
        updater.cache_dir = self._original
        self.tmp.cleanup()

    def test_latest_release(self):
        payload = json.dumps({
            "tag_name": "v2.0.0",
            "assets": [{"name": "x", "browser_download_url": "http://x"}],
        }).encode("utf-8")
        response = _FakeResponse(payload, headers={"ETag": '"etag1"'})
        with mock.patch("urllib.request.urlopen", return_value=response):
            tag, assets = updater.latest_release()
        self.assertEqual(tag, "v2.0.0")
        self.assertEqual(assets[0]["name"], "x")
        self.assertTrue((Path(self.tmp.name) / "updates" / "release.json").is_file())

    def test_latest_release_network_error(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("boom")):
            self.assertIsNone(updater.latest_release())


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._original = updater.cache_dir
        updater.cache_dir = lambda: Path(self.tmp.name)

    def tearDown(self):
        updater.cache_dir = self._original
        self.tmp.cleanup()

    def test_cleanup_removes_downloads_but_keeps_cache(self):
        base = updater.updates_dir()
        (base / "staging-1").mkdir(parents=True)
        (base / "BlenderManager-x86_64.AppImage").write_text("binario grande")
        (base / "release.json").write_text("{}")
        (base / "release.etag").write_text("etag")
        updater.cleanup_staging()
        self.assertFalse((base / "staging-1").exists())
        self.assertFalse((base / "BlenderManager-x86_64.AppImage").exists())
        self.assertTrue((base / "release.json").is_file())
        self.assertTrue((base / "release.etag").is_file())

    def test_cleanup_partials(self):
        folder = Path(self.tmp.name) / "blenders"
        folder.mkdir()
        (folder / "blender.tar.xz.part").write_text("a medias")
        (folder / "blender.tar.xz").write_text("completo")
        updater.cleanup_partials(folder)
        self.assertFalse((folder / "blender.tar.xz.part").exists())
        self.assertTrue((folder / "blender.tar.xz").is_file())

    def test_cleanup_missing_folder(self):
        updater.cleanup_partials("/nonexistent/path/xyz")


class SourceUpdateTests(unittest.TestCase):
    """Actualizar un checkout en modo fuente (git pull) sin red ni repo real."""

    def test_no_git_checkout(self):
        with mock.patch.object(updater, "source_root", return_value=None):
            self.assertEqual(updater.source_update(), (False, "no-git"))
            self.assertFalse(updater.relaunch_source())

    def test_refuses_when_dirty(self):
        with mock.patch.object(updater, "source_root", return_value=Path("/tmp/repo")), \
                mock.patch.object(updater.subprocess, "check_output",
                                  return_value=b" M src/main.py\n"):
            self.assertEqual(updater.source_update(), (False, "dirty"))

    def test_pulls_when_clean(self):
        result = mock.Mock(returncode=0, stderr="")
        with mock.patch.object(updater, "source_root", return_value=Path("/tmp/repo")), \
                mock.patch.object(updater.subprocess, "check_output", return_value=b""), \
                mock.patch.object(updater.subprocess, "run", return_value=result) as run:
            self.assertEqual(updater.source_update(), (True, "ok"))
            self.assertIn("pull", run.call_args.args[0])
            self.assertIn("--ff-only", run.call_args.args[0])

    def test_reports_failed_pull(self):
        result = mock.Mock(returncode=1, stderr="boom")
        with mock.patch.object(updater, "source_root", return_value=Path("/tmp/repo")), \
                mock.patch.object(updater.subprocess, "check_output", return_value=b""), \
                mock.patch.object(updater.subprocess, "run", return_value=result):
            self.assertEqual(updater.source_update(), (False, "failed"))


if __name__ == "__main__":
    unittest.main()
