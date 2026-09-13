import unittest

from model.build import Build, InstalledBuild, human_size, minor_of, version_tuple


class ModelTests(unittest.TestCase):
    def test_version_tuple(self):
        self.assertEqual(version_tuple("5.2.1"), (5, 2, 1))
        self.assertEqual(version_tuple("4.5"), (4, 5))
        self.assertEqual(version_tuple(""), (0,))

    def test_minor_of(self):
        self.assertEqual(minor_of("5.2.1"), "5.2")
        self.assertEqual(minor_of("4.5"), "4.5")
        self.assertEqual(minor_of("2"), "2")

    def test_human_size(self):
        self.assertEqual(human_size(0), "0 B")
        self.assertEqual(human_size(1024), "1.0 KB")
        self.assertEqual(human_size(1024 * 1024 * 350), "350.0 MB")

    def test_is_lts(self):
        stable = Build("4.5.13", "v45", "stable", "linux", "x86_64", "u", "f.tar.xz")
        self.assertTrue(stable.is_lts)
        non_lts = Build("4.4.3", "v44", "stable", "linux", "x86_64", "u", "f.tar.xz")
        self.assertFalse(non_lts.is_lts)
        alpha = Build("5.3.0", "main", "alpha", "linux", "x86_64", "u", "f.tar.xz")
        self.assertFalse(alpha.is_lts)

    def test_installed_build(self):
        entry = InstalledBuild("blender-4.5.13-linux-x64", "/tmp/x", "4.5.13", "/tmp/x/blender")
        self.assertTrue(entry.is_lts)
        self.assertTrue(entry.can_launch)


if __name__ == "__main__":
    unittest.main()
