"""Tests de la interfaz PySide6 (sin pantalla).

Se ejecutan con el plugin *offscreen* de Qt, así que no hace falta servidor
gráfico. Cubren lo que puede romperse sin abrir ventana: el filtrado del
controlador, el cálculo de columnas de la rejilla y los diálogos.
"""

import os
import sys
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

    def test_zoom_en_vivo_con_tope(self):
        from PySide6.QtTest import QTest

        from ui.widgets.main_window import MainWindow

        window = MainWindow()
        window.builds = [_build("5.1.2", "v51", "stable")]
        window.resize(900, 600)
        window.layout_mode = "grid"
        window.zoom = 0.8
        window._rebuild_store()
        card = lambda: window.store_grid.itemAt(0).widget()
        before = card().minimumHeight()

        window.set_zoom(1.4)
        # El valor va al instante, pero la rejilla no se toca en el mismo tick
        # (eso era el parpadeo), aunque tampoco espera a que sueltes: el timer
        # de refresco queda armado.
        self.assertEqual(window.zoom, 1.4)
        self.assertTrue(window._zoom_tick.isActive())
        self.assertEqual(card().minimumHeight(), before)

        # Mientras se arrastra, se refresca sola (esto es lo que faltaba).
        QTest.qWait(200)
        self.assertNotEqual(card().minimumHeight(), before)

        # Y al parar el slider, para y guarda una sola vez.
        QTest.qWait(300)
        self.assertFalse(window._zoom_tick.isActive())
        self.assertFalse(window._zoom_settle.isActive())
        self.assertEqual(window.settings.zoom, 1.4)

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

    def test_la_papelera_no_se_queda_sin_icono(self):
        from types import SimpleNamespace

        from ui.widgets.buttons import CardButton
        from ui.widgets.cards import GridInstalledCard
        from ui.widgets.main_window import MIN_ZOOM

        entry = SimpleNamespace(name="blender-5.2.0", version="5.2.0",
                                path="/tmp/blender-5.2.0")
        card = GridInstalledCard(entry, False, MIN_ZOOM)
        card.show()
        delete = next(b for b in card.findChildren(CardButton)
                      if b.property("iconOnly") == "true")
        # El ancho fijo tiene que dar cabida al glifo (si no, a zoom bajo el
        # boton sale como un recuadro rojo vacio).
        self.assertGreaterEqual(delete.minimumWidth(),
                                delete.sizeHint().width())
        # Y el QSS le quita el padding lateral de 14 px, o no habria forma.
        self.assertLess(delete.sizeHint().width(), 30)

    def test_el_logo_no_instalado_va_atenuado(self):
        from ui.widgets.cards import _logo_label

        claro = _logo_label(40, dim=False).pixmap().toImage()
        tenue = _logo_label(40, dim=True).pixmap().toImage()
        self.assertEqual(claro.size(), tenue.size())
        # El atenuado tiene que pintarse de verdad: en Qt el `opacity` del QSS
        # NO se aplica sobre un QLabel con pixmap, y eso se perdio en el port
        # (en la version Kivy las builds que no tienes se veian mas apagadas).
        self.assertLess(self._alpha_medio(tenue), self._alpha_medio(claro))

    @staticmethod
    def _alpha_medio(image):
        total = count = 0
        for y in range(image.height()):
            for x in range(image.width()):
                alpha = image.pixelColor(x, y).alpha()
                if alpha:
                    total += alpha
                    count += 1
        return total / count if count else 0

    def test_iconos_de_lanzar_y_de_descargar(self):
        from ui.widgets.buttons import CardButton
        from ui.widgets.cards import BuildCard, GridBuildCard

        def action_button(card):
            for button in card.findChildren(CardButton):
                if button.property("variant") in ("dark", "accent"):
                    return button
            return None

        build = _build("5.2.1", "v52", "stable")
        lanzar, descargar = [], []
        for card in (BuildCard(build, True, False),
                     GridBuildCard(build, True, False, 1.0)):
            lanzar.append(action_button(card))
        for card in (BuildCard(build, False, False),
                     GridBuildCard(build, False, False, 1.0)):
            descargar.append(action_button(card))

        # Lanzar va oscuro (como el boton de pestana de Blender) con la flecha
        # verde, en las cuatro tarjetas: en Kivy se pintaba dentro del texto y
        # al portar a Qt se perdio en las dos de la tienda.
        for button in lanzar:
            self.assertEqual(button.property("variant"), "dark")
            self.assertFalse(button.icon().isNull(), type(button))
        # Descargar va azul y con su flecha blanca hacia abajo.
        for button in descargar:
            self.assertEqual(button.property("variant"), "accent")
            self.assertFalse(button.icon().isNull(), type(button))
        # Y no es el mismo icono.
        self.assertNotEqual(lanzar[0].icon().cacheKey(),
                            descargar[0].icon().cacheKey())

    def test_ajustes_funciona_como_interruptor(self):
        from ui.widgets.main_window import MainWindow

        window = MainWindow()
        # La segunda pulsacion del boton de ajustes vuelve a donde estabas
        # (en el port se guardaba _previous_view pero no se usaba nunca).
        window.set_view("installed")
        window.set_view("settings")
        self.assertEqual(window.view, "settings")
        window.set_view("settings")
        self.assertEqual(window.view, "installed")

        window.set_view("store")
        window.set_view("settings")
        window.set_view("settings")
        self.assertEqual(window.view, "store")

    def test_el_buscador_va_pegado_al_boton_de_refrescar(self):
        from ui.widgets.buttons import IconFlatButton
        from ui.widgets.main_window import MainWindow

        window = MainWindow()
        window.resize(1500, 620)
        window.show()
        refresh = window.header_tools.findChild(IconFlatButton)
        hueco = window.search_input.x() - (refresh.x() + refresh.width())
        # Antes el bloque se estiraba y repartia el hueco que sobraba: a 1500 px
        # llegaba a 97 px entre el icono y el campo.
        self.assertLessEqual(hueco, 14)
        # Y el bloque queda pegado al borde derecho (margen de la cabecera).
        self.assertLessEqual(
            window.width() - (window.header_tools.x() + window.header_tools.width()),
            18)

    def test_hay_pastilla_de_favoritos(self):
        from ui.widgets.main_window import MainWindow

        window = MainWindow()
        self.assertIn("favorites", window._channel_buttons)

    def test_la_estrella_marca_y_desmarca(self):
        from ui.widgets.buttons import StarButton
        from ui.widgets.main_window import MainWindow

        window = MainWindow()
        window.resize(900, 600)
        window.layout_mode = "list"
        window.channel = "all"
        window.builds = [_build("5.1.2", "v51", "stable")]
        window._rebuild_store()

        card = window.store_grid.itemAt(0).widget()
        star = next(b for b in card.findChildren(StarButton))
        self.assertFalse(star.isChecked())

        star.setChecked(True)          # como si el usuario pulsara la estrella
        self.assertEqual(window.settings.favorites, ["v51|5.1.2"])
        self.assertTrue(star.isChecked())

        star.setChecked(False)
        self.assertEqual(window.settings.favorites, [])

    def test_la_estrella_sale_marcada_si_ya_era_favorita(self):
        from ui.widgets.buttons import StarButton
        from ui.widgets.main_window import MainWindow

        window = MainWindow()
        window.resize(900, 600)
        window.layout_mode = "list"
        window.channel = "all"
        window.builds = [_build("5.1.2", "v51", "stable")]
        window.settings.favorites = ["v51|5.1.2"]
        window._rebuild_store()

        card = window.store_grid.itemAt(0).widget()
        star = next(b for b in card.findChildren(StarButton))
        self.assertTrue(star.isChecked())

    def test_canal_favoritos_filtra_y_se_actualiza(self):
        from ui.widgets.buttons import StarButton
        from ui.widgets.main_window import MainWindow

        window = MainWindow()
        window.resize(900, 600)
        window.layout_mode = "list"
        window.builds = [_build("5.1.2", "v51", "stable"),
                         _build("5.2.1", "v52", "stable")]
        window.settings.favorites = ["v52|5.2.1"]
        window.set_channel("favorites")

        self.assertEqual([b.version for b in window._filtered()], ["5.2.1"])
        self.assertEqual(window.store_grid.count(), 1)

        # Quitar la estrella estando en ese canal deja la lista vacia al momento
        # (y sale el mensaje propio, no el generico).
        card = window.store_grid.itemAt(0).widget()
        star = next(b for b in card.findChildren(StarButton))
        star.setChecked(False)
        self.assertEqual(window._filtered(), [])
        self.assertEqual(window.store_grid.count(), 1)   # el placeholder

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

    def test_si_falla_la_comprobacion_lo_dice(self):
        from unittest import mock

        from i18n import tr
        from services import updater
        from ui.widgets.main_window import MainWindow

        window = MainWindow()
        window.current_version = "1.3.0"
        mensajes = []

        def falso_mensaje(text, timeout=4):
            mensajes.append(text)

        with mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(window, "_show_message", falso_mensaje), \
                mock.patch.object(window, "_show_update_available") as disponible:
            # Sin tag: la comprobacion no llego a hacerse (red, TLS, cuota...).
            # Antes esto decia "ya tienes la ultima version", que es mentira y
            # fue lo que hizo pensar que no habia actualizacion cuando si la
            # habia (paso en Arch: el OpenSSL del binario no encontraba las CAs).
            window._on_update_result("", [], True)
            self.assertEqual(mensajes, [tr("Update check failed")])
            disponible.assert_not_called()

            # Con tag y asset, si ofrece la actualizacion.
            mensajes.clear()
            asset = {"name": updater.asset_for(window.system), "url": "http://x"}
            window._on_update_result("v1.4.0", [asset], True)
            disponible.assert_called_once()

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
