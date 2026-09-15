"""Tests de la interfaz PySide6 (sin pantalla).

Se ejecutan con el plugin *offscreen* de Qt, así que no hace falta servidor
gráfico. Cubren lo que puede romperse sin abrir ventana: el filtrado del
controlador, el cálculo de columnas de la rejilla y los diálogos.
"""

import os
import unittest
from pathlib import Path

# El plugin offscreen tiene que estar fijado ANTES de crear QApplication.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication

    HAVE_QT = True
except ImportError:  # sin PySide6 (p. ej. el job de tests sin deps)
    HAVE_QT = False

from model.build import Build


def _build(version, branch, risk, lts=False):
    return Build(version=version, branch=branch, risk=risk, platform="linux",
                 arch="x86_64", url="http://x", filename=f"{version}.tar.xz",
                 size=1000, mtime=1)


class SettingsIsolated:
    """Mixin: la config va a un directorio temporal, no al del usuario.

    ``MainWindow`` guarda en disco (zoom, modo de vista...) y algunos tests
    mueven el zoom a proposito, asi que sin aislar la config la suite escribia
    en el ``settings.json`` real: ya paso, el zoom se quedo en 1.4.
    """

    def setUp(self):
        import tempfile
        from unittest import mock

        from services import settings as settings_service

        self._config_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._config_dir.cleanup)
        patch = mock.patch.object(settings_service, "config_dir",
                                  return_value=Path(self._config_dir.name))
        patch.start()
        self.addCleanup(patch.stop)


@unittest.skipUnless(HAVE_QT, "PySide6 no instalado")
class MainWindowTests(SettingsIsolated, unittest.TestCase):
    app = None

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from ui import fonts, qss

        fonts.load()
        cls.app.setStyleSheet(qss.build_qss())

    def _window(self):
        from ui.widgets.main_window import MainWindow

        window = MainWindow()
        # Inyectamos builds a mano: así el test no depende de la red.
        window.builds = [
            _build("5.2.1", "v52", "stable", lts=True),
            _build("5.1.2", "v51", "stable"),
            _build("5.3.0", "main", "alpha"),
        ]
        return window

    def test_filter_all(self):
        window = self._window()
        window.channel = "all"
        self.assertEqual(len(window._filtered()), 3)

    def test_filter_lts(self):
        window = self._window()
        window.channel = "lts"
        result = window._filtered()
        self.assertEqual([b.version for b in result], ["5.2.1"])

    def test_filter_stable_excluye_lts(self):
        window = self._window()
        window.channel = "stable"
        result = window._filtered()
        self.assertEqual([b.version for b in result], ["5.1.2"])

    def test_filter_daily(self):
        window = self._window()
        window.channel = "daily"
        result = window._filtered()
        self.assertEqual([b.version for b in result], ["5.3.0"])

    def test_installed_filtra_por_canal(self):
        """La pestaña de instaladas tambien filtra por canal, no solo busqueda.

        Bug real del port: reimplemente filter_installed y solo miraba la
        busqueda, asi que pulsar LTS/Stable/Daily no cambiaba nada en esa
        pestana (que es la que se abre por defecto si hay versiones).
        """
        class _Entry:
            def __init__(self, name, version, branch, lts):
                self.name = name
                self.version = version
                self.branch = branch
                self.path = "/tmp/" + name
                self.is_lts = lts
                self.can_launch = True

        window = self._window()
        window.installed = [
            _Entry("blender-5.2.1", "5.2.1", "v52", lts=True),
            _Entry("blender-5.1.2", "5.1.2", "v51", lts=False),
            _Entry("blender-5.3.0-alpha", "5.3.0", "main", lts=False),
        ]
        window.channel = "lts"
        self.assertEqual([e.name for e in window._filtered_installed()],
                         ["blender-5.2.1"])
        # OJO: en instaladas, "estable" es "no LTS", así que incluye la diaria
        # (a diferencia de la tienda, donde además exige risk == "stable").
        window.channel = "stable"
        self.assertEqual(len(window._filtered_installed()), 2)
        window.channel = "daily"
        self.assertEqual([e.name for e in window._filtered_installed()],
                         ["blender-5.3.0-alpha"])
        window.channel = "all"
        self.assertEqual(len(window._filtered_installed()), 3)

    def test_search_filtra_por_version(self):
        window = self._window()
        window.channel = "all"
        window.search = "5.2"
        self.assertEqual([b.version for b in window._filtered()], ["5.2.1"])

    def test_arch_no_se_traduce_en_linux(self):
        # En Linux la API usa x86_64; solo Windows la llama amd64.
        window = self._window()
        window.platform_label = "GNU/Linux"
        window.arch_label = "x86_64"
        self.assertEqual(window.arch, "x86_64")
        window.platform_label = "Windows"
        self.assertEqual(window.arch, "amd64")


@unittest.skipUnless(HAVE_QT, "PySide6 no instalado")
class LayoutTests(SettingsIsolated, unittest.TestCase):
    app = None

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_zoom_limits(self):
        from ui.widgets.main_window import MAX_ZOOM, MIN_ZOOM, MainWindow

        window = MainWindow()
        window.set_zoom(99)
        self.assertEqual(window.zoom, MAX_ZOOM)
        window.set_zoom(0.01)
        self.assertEqual(window.zoom, MIN_ZOOM)

    def test_zoom_por_defecto_es_80(self):
        from services.settings import Settings

        self.assertEqual(Settings().zoom, 0.8)

    def test_zoom_amortiguado(self):
        from PySide6.QtTest import QTest

        from ui.widgets.main_window import MainWindow

        window = MainWindow()
        window.builds = [_build("5.1.2", "v51", "stable")]
        window.resize(900, 600)
        window.layout_mode = "grid"
        window.zoom = 0.8
        window._rebuild_store()
        before = window.store_grid.itemAt(0).widget().minimumHeight()
        window.set_zoom(1.4)
        # El valor va al instante, pero la rejilla NO se reconstruye todavía:
        # hacerlo en cada tick del slider es lo que la hacía parpadear.
        self.assertEqual(window.zoom, 1.4)
        self.assertTrue(window._zoom_timer.isActive())
        self.assertEqual(window.store_grid.itemAt(0).widget().minimumHeight(),
                         before)
        QTest.qWait(300)
        self.assertFalse(window._zoom_timer.isActive())
        self.assertNotEqual(window.store_grid.itemAt(0).widget().minimumHeight(),
                            before)

    def test_atajos_registrados(self):
        from PySide6.QtGui import QShortcut

        from ui.widgets.main_window import MainWindow

        window = MainWindow()
        keys = {s.key().toString() for s in window.findChildren(QShortcut)}
        self.assertIn("Ctrl++", keys)
        self.assertIn("Ctrl+=", keys)
        self.assertIn("Ctrl+-", keys)
        self.assertIn("Ctrl+0", keys)

    def test_atajos_de_zoom(self):
        from services.settings import DEFAULT_ZOOM
        from ui.widgets.main_window import MAX_ZOOM, MIN_ZOOM, ZOOM_STEP, MainWindow

        window = MainWindow()
        window.resize(900, 600)
        window.layout_mode = "grid"
        window._set_zoom_value(DEFAULT_ZOOM)

        window.zoom_in()
        self.assertAlmostEqual(window.zoom, DEFAULT_ZOOM + ZOOM_STEP)
        # El slider va con el valor: si no, la UI mentiría.
        self.assertEqual(window.zoom_slider.value(),
                         round((DEFAULT_ZOOM + ZOOM_STEP) * 100))

        window.zoom_out()
        window.zoom_out()
        self.assertAlmostEqual(window.zoom, DEFAULT_ZOOM - ZOOM_STEP)

        for _ in range(50):
            window.zoom_in()
        self.assertAlmostEqual(window.zoom, MAX_ZOOM)
        for _ in range(50):
            window.zoom_out()
        self.assertAlmostEqual(window.zoom, MIN_ZOOM)

        window.reset_zoom()
        self.assertAlmostEqual(window.zoom, DEFAULT_ZOOM)
        self.assertEqual(window.zoom_slider.value(), round(DEFAULT_ZOOM * 100))

    def test_zoom_no_aplica_en_modo_lista(self):
        from services.settings import DEFAULT_ZOOM
        from ui.widgets.main_window import MainWindow

        window = MainWindow()
        window.layout_mode = "list"
        window._set_zoom_value(DEFAULT_ZOOM)
        window.zoom_in()
        self.assertAlmostEqual(window.zoom, DEFAULT_ZOOM)

    def test_ctrl_clic_en_el_slider_resetea(self):
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent

        from services.settings import DEFAULT_ZOOM
        from ui.widgets.main_window import MainWindow

        window = MainWindow()
        window.resize(900, 600)
        window.layout_mode = "grid"
        window._set_zoom_value(1.4)
        pos = QPointF(10, 5)
        event = QMouseEvent(QEvent.MouseButtonPress, pos, pos,
                            Qt.LeftButton, Qt.LeftButton, Qt.ControlModifier)
        window.zoom_slider.mousePressEvent(event)
        self.assertAlmostEqual(window.zoom, DEFAULT_ZOOM)

    def test_zebra_solo_en_modo_lista(self):
        from ui.widgets.main_window import MainWindow

        window = MainWindow()
        window.builds = [_build("5.2.1", "v52", "stable"),
                         _build("5.1.2", "v51", "stable")]
        window.channel = "all"
        window.resize(900, 600)

        def zebras():
            return [window.store_grid.itemAt(i).widget().property("zebra")
                    for i in range(window.store_grid.count())]

        window.layout_mode = "grid"
        window._rebuild_store()
        self.assertEqual(zebras(), ["false", "false"])

        window.layout_mode = "list"
        window._rebuild_store()
        self.assertEqual(zebras(), ["false", "true"])

    def test_columnas_grid_crecen_con_el_ancho(self):
        from ui.widgets.main_window import MainWindow

        window = MainWindow()
        window.resize(900, 600)
        window.layout_mode = "grid"
        narrow = window._columns_for(window.store_scroll, 300)
        window.resize(1600, 600)
        wide = window._columns_for(window.store_scroll, 300)
        self.assertGreaterEqual(wide, narrow)
        self.assertGreaterEqual(narrow, 1)


@unittest.skipUnless(HAVE_QT, "PySide6 no instalado")
class SourceUpdateUiTests(SettingsIsolated, unittest.TestCase):
    """Modo fuente: la actualización es ``git pull``, no un binario."""

    app = None

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from ui import fonts, qss

        fonts.load()
        cls.app.setStyleSheet(qss.build_qss())

    def test_no_avisa_al_arrancar_en_modo_fuente(self):
        from ui.widgets.main_window import MainWindow

        window = MainWindow()
        window._update_checking = False
        # En tests no hay binario (sys.frozen es False): modo fuente.
        window.check_updates(manual=False)
        # Ni hilo ni comprobación: en un checkout no se avisa al arrancar.
        self.assertFalse(window._update_checking)

    def test_modo_fuente_no_descarga_binario(self):
        from unittest import mock

        from ui.widgets import main_window
        from ui.widgets.main_window import MainWindow

        window = MainWindow()
        with mock.patch.object(main_window.updater, "source_root",
                               return_value=Path("/tmp/repo")), \
                mock.patch.object(window, "_show_update_available") as binario, \
                mock.patch.object(window, "_show_source_update") as fuente:
            window._on_update_result("v9.9.9", [], True)
        fuente.assert_called_once()
        binario.assert_not_called()

    def test_fuente_sin_git_abre_la_release(self):
        from unittest import mock

        from ui.widgets import main_window
        from ui.widgets.main_window import MainWindow

        window = MainWindow()
        with mock.patch.object(main_window.updater, "source_root",
                               return_value=None), \
                mock.patch.object(main_window.updater, "open_releases") as abrir, \
                mock.patch.object(window, "_show_update_available") as binario, \
                mock.patch.object(window, "_show_message"):
            window._on_update_result("v9.9.9", [], True)
        # Sin git no hay nada que aplicar: nada de descargar un binario.
        abrir.assert_called_once()
        binario.assert_not_called()

    def test_dialogo_fuente_rehabilita_al_fallar(self):
        from i18n import tr
        from ui.widgets.dialogs import AppDialog
        from ui.widgets.main_window import MainWindow

        window = MainWindow()
        dialog = AppDialog(window, tr("Update available"), tr("Updating..."))
        update_btn = dialog.add_button(tr("Update"), variant="accent")
        later_btn = dialog.add_button(tr("Later"))
        window._source_dialog = dialog
        window._on_source_update_done(False, "dirty")
        # Tras un pull fallido el diálogo explica el motivo y deja reintentar.
        self.assertEqual(
            dialog.body_label.text(),
            tr("You have local changes. Commit or stash them and try again."))
        self.assertTrue(update_btn.isEnabled())
        self.assertTrue(later_btn.isEnabled())


@unittest.skipUnless(HAVE_QT, "PySide6 no instalado")
class DialogTests(unittest.TestCase):
    app = None

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from ui import qss

        cls.app.setStyleSheet(qss.build_qss())

    def test_confirm_rechazado(self):
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QDialog

        from ui.widgets import dialogs

        def close():
            for widget in self.app.topLevelWidgets():
                if isinstance(widget, QDialog):
                    widget.reject()

        QTimer.singleShot(200, close)
        self.assertFalse(dialogs.confirm(None, "Uninstall", "¿Borrar?", danger=True))

    def test_confirm_aceptado(self):
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QDialog

        from ui.widgets import dialogs

        def close():
            for widget in self.app.topLevelWidgets():
                if isinstance(widget, QDialog):
                    widget.accept()

        QTimer.singleShot(200, close)
        self.assertTrue(dialogs.confirm(None, "Uninstall", "¿Borrar?"))


if __name__ == "__main__":
    unittest.main()
