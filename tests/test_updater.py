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


if __name__ == "__main__":
    unittest.main()
