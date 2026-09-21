"""Tests del lanzador (``services/launcher``).

No se arranca ningún proceso: se comprueba qué comando se construiría y con
qué opciones, que es donde está la lógica de "lanzar con consola".
"""

import unittest
from unittest import mock

from services import launcher


def _which(available):
    return lambda name: f"/usr/bin/{name}" if name in available else None


class ConsoleCommandTest(unittest.TestCase):
    def test_linux_usa_un_terminal_del_path(self):
        with mock.patch.object(launcher.sys, "platform", "linux"), \
                mock.patch.object(launcher.shutil, "which",
                                  side_effect=_which({"konsole"})):
            command = launcher.console_command(["blender", "file.blend"])
        self.assertEqual(command,
                         ["/usr/bin/konsole", "-e", "blender", "file.blend"])

    def test_sin_terminal_devuelve_none(self):
        with mock.patch.object(launcher.sys, "platform", "linux"), \
                mock.patch.object(launcher.shutil, "which",
                                  return_value=None):
            self.assertIsNone(launcher.console_command(["blender"]))
            self.assertFalse(launcher.terminal_available())

    def test_windows_no_necesita_comando_aparte(self):
        with mock.patch.object(launcher.sys, "platform", "win32"):
            self.assertIsNone(launcher.console_command(["blender"]))
            self.assertTrue(launcher.terminal_available())


class LaunchTest(unittest.TestCase):
    def test_consola_envuelve_blender_en_el_terminal(self):
        with mock.patch.object(launcher.sys, "platform", "linux"), \
                mock.patch.object(launcher.shutil, "which",
                                  side_effect=_which({"xterm"})), \
                mock.patch.object(launcher.subprocess, "Popen") as popen:
            launcher.Launcher().launch("/tmp/blender", args=["a.blend"],
                                       console=True)
        command = popen.call_args[0][0]
        self.assertEqual(command[0], "/usr/bin/xterm")
        self.assertIn("/tmp/blender", command)
        self.assertTrue(popen.call_args[1]["start_new_session"])

    def test_sin_consola_lanza_blender_directo(self):
        with mock.patch.object(launcher.subprocess, "Popen") as popen:
            launcher.Launcher().launch("/tmp/blender")
        self.assertEqual(popen.call_args[0][0], ["/tmp/blender"])


if __name__ == "__main__":
    unittest.main()
