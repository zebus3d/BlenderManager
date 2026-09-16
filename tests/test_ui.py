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
    """Mixin: config y carpeta de descargas en un directorio temporal.

    ``MainWindow`` guarda en disco (zoom, modo de vista...), asi que sin aislar
    la config la suite escribia en el ``settings.json`` real: ya paso, el zoom se
    quedo en 1.4. Y la carpeta de descargas apunta a un temporal vacio porque si
    no los tests leen las versiones de Blender del usuario (y un test de descarga
    que se creia "ya instalada" llego a lanzarle dos Blenders de verdad).
    """

    def setUp(self):
        import json
        import tempfile
        from unittest import mock

        from services import settings as settings_service

        self._config_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._config_dir.cleanup)
        config = Path(self._config_dir.name)
        destino = config / "Blenders"
        destino.mkdir()
        (config / "settings.json").write_text(
            json.dumps({"dest_folder": str(destino)}), encoding="utf-8")
        patch = mock.patch.object(settings_service, "config_dir",
                                  return_value=config)
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

    def test_el_icono_de_info_usa_la_url_de_la_api(self):
        """El port la había sustituido por una URL a mano que no existe.

        ``open_release_notes`` tiene que delegar en ``api.release_notes_url``,
        que recorta a la serie ("5.2.1" -> .../release_notes/5.2/). Antes se
        componía "blender.org/download/releases/5.2.1/", que es 404.
        """
        from unittest import mock

        from PySide6.QtTest import QTest

        from services import api
        from ui.widgets import main_window
        from ui.widgets.main_window import MainWindow

        window = MainWindow()
        abiertas = []
        with mock.patch.object(main_window.webbrowser, "open",
                               side_effect=lambda url: abiertas.append(url) or True):
            window.open_release_notes("5.2.1")
            QTest.qWait(200)

        self.assertEqual(abiertas, [api.release_notes_url("5.2.1")])
        self.assertTrue(abiertas[0].endswith("/release_notes/5.2/"))

    def test_si_el_navegador_no_abre_lo_dice(self):
        from unittest import mock

        from i18n import tr
        from PySide6.QtTest import QTest

        from ui.widgets import main_window
        from ui.widgets.main_window import MainWindow

        # Se deja pasar el refresco de arranque (a los 100 ms pone "Cargando...")
        # para que no pise el mensaje que estamos comprobando.
        with mock.patch.object(main_window.api, "get_builds", return_value=[]):
            window = MainWindow()
            QTest.qWait(300)
            with mock.patch.object(main_window.webbrowser, "open",
                                   return_value=False):
                window.open_release_notes("5.2.1")
                QTest.qWait(200)

        self.assertEqual(window.status_label.text(),
                         tr("Could not open the browser"))


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

    def test_clic_en_la_ranura_lleva_el_tirador_al_punto(self):
        """Un clic en la ranura mueve el tirador ahí, no un ``pageStep``.

        Antes, pulsar a 12 px del tirador daba un salto del 10 % de zoom.
        """
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtWidgets import QStyle

        from ui.widgets.main_window import MainWindow

        window = MainWindow()
        window.resize(900, 600)
        window.layout_mode = "grid"
        slider = window.zoom_slider

        def mouse(kind, x, button=Qt.LeftButton, buttons=Qt.LeftButton):
            pos = QPointF(x, 12)
            return QMouseEvent(kind, pos, pos, button, buttons, Qt.NoModifier)

        slider.setValue(120)
        center = slider._sub_rect(QStyle.SC_SliderHandle).center().x()
        for offset in (-30, 20, 40):
            x = center + offset
            slider.mousePressEvent(mouse(QEvent.MouseButtonPress, x))
            slider.mouseReleaseEvent(
                mouse(QEvent.MouseButtonRelease, x, Qt.NoButton, Qt.NoButton))
            landed = slider._sub_rect(QStyle.SC_SliderHandle).center().x()
            self.assertLessEqual(abs(landed - x), 2,
                                 f"clic en {x} dejó el tirador en {landed}")

        # Y tras el salto se sigue pudiendo arrastrar.
        slider.setValue(120)
        center = slider._sub_rect(QStyle.SC_SliderHandle).center().x()
        slider.mousePressEvent(mouse(QEvent.MouseButtonPress, center))
        slider.mouseMoveEvent(mouse(QEvent.MouseMove, center + 30, Qt.NoButton))
        self.assertGreater(slider.value(), 120)
        slider.mouseReleaseEvent(
            mouse(QEvent.MouseButtonRelease, center + 30, Qt.NoButton, Qt.NoButton))

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

    def test_las_tarjetas_de_la_tienda_miden_igual(self):
        """Instaladas y descargables del mismo canal no pueden bailar de alto.

        La tarjeta instalada llevaba una insignia "Instalada" que las
        descargables no tenían, así que en la rejilla estas salían 22 px más
        bajas y las filas quedaban desniveladas. En el Kivy original esa fila
        siempre existía (vacía si no estaba instalada).
        """
        from pathlib import Path

        from model.build import InstalledBuild
        from ui.widgets.main_window import MainWindow

        window = MainWindow()
        window.builds = [_build("5.2.1", "v52", "stable"),
                         _build("5.1.2", "v51", "stable")]
        window.installed = [InstalledBuild(
            name="blender-5.2.1", path=Path("/tmp/blender-5.2.1"),
            version="5.2.1", branch="v52")]
        window.channel = "all"
        window.resize(900, 600)
        window.layout_mode = "grid"
        window.zoom = 0.8
        window._rebuild_store()

        alturas = {window.store_grid.itemAt(i).widget().height()
                   for i in range(window.store_grid.count())}
        self.assertEqual(len(alturas), 1, alturas)

    def test_todas_las_tarjetas_llevan_sombra(self):
        from PySide6.QtWidgets import QGraphicsDropShadowEffect

        from model.build import InstalledBuild
        from ui.widgets.cards import (BuildCard, GridBuildCard,
                                      GridInstalledCard, InstalledCard)

        build = _build("5.2.1", "v52", "stable")
        entry = InstalledBuild(name="blender-5.2.1",
                               path=Path("/tmp/blender-5.2.1"),
                               version="5.2.1", branch="v52")
        tarjetas = [BuildCard(build, False, False),
                    GridBuildCard(build, False, False, 1.0),
                    InstalledCard(entry, False),
                    GridInstalledCard(entry, False, 1.0)]
        for card in tarjetas:
            efecto = card.graphicsEffect()
            self.assertIsInstance(efecto, QGraphicsDropShadowEffect, type(card))
            # Desplazada abajo a la derecha y con poco contraste.
            self.assertGreater(efecto.offset().x(), 0, type(card))
            self.assertGreater(efecto.offset().y(), 0, type(card))
            self.assertLessEqual(efecto.color().alpha(), 130, type(card))

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

    def test_recuerda_el_filtro_al_volver_a_abrir(self):
        from ui.widgets.main_window import MainWindow

        # Primera sesión: el usuario deja el filtro en Favoritos.
        primera = MainWindow()
        primera.set_channel("favorites")
        self.assertEqual(primera.settings.channel, "favorites")

        # Al volver a abrir, sigue en Favoritos y con su pastilla marcada.
        segunda = MainWindow()
        self.assertEqual(segunda.channel, "favorites")
        self.assertTrue(segunda._channel_buttons["favorites"].isChecked())
        self.assertFalse(segunda._channel_buttons["all"].isChecked())

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
class DownloadSourceTests(SettingsIsolated, unittest.TestCase):
    """La descarga usa la fuente que elige la sonda (CDN o release oficial)."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_descarga_desde_la_fuente_elegida(self):
        from unittest import mock

        from PySide6.QtTest import QTest

        from services.sources import Source
        from ui.widgets import main_window
        from ui.widgets.main_window import MainWindow

        window = MainWindow()
        window.builds = [_build("9.9.9", "v99", "stable")]
        window.installed = []
        elegida = Source("Blender release (Cloudflare)",
                         "https://download.blender.org/release/Blender5.1/f.tar.xz",
                         "hash-del-release")
        with mock.patch.object(main_window.sources, "choose",
                               return_value=elegida), \
                mock.patch.object(window.downloader, "start") as arranque:
            window.install_build(window.builds[0])
            # La eleccion va en un hilo y vuelve por senal: hay que dejar correr
            # el bucle de eventos para que llegue.
            QTest.qWait(300)

        self.assertTrue(arranque.called)
        url, _destino, _nombre, checksum = arranque.call_args.args
        self.assertEqual(url, elegida.url)
        self.assertEqual(checksum, "hash-del-release")


@unittest.skipUnless(HAVE_QT, "PySide6 no instalado")
class ElideTests(SettingsIsolated, unittest.TestCase):
    """Los nombres largos no deben ensanchar su columna ni salirse de la ventana."""

    LARGO = "blender-5.3.0-alpha+main.1fd06ddba680-linux.x86_64-release"

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from ui import fonts, qss

        fonts.load()
        cls.app.setStyleSheet(qss.build_qss())

    def _entrada(self, nombre):
        from pathlib import Path

        from services.installed import InstalledBuild

        return InstalledBuild(name=nombre,
                              path=Path("/home/u/Descargas/Blenders") / nombre,
                              version="5.3.0", branch="v53")

    def test_rejilla_con_nombre_largo_deja_las_columnas_iguales(self):
        from PySide6.QtWidgets import QGridLayout, QWidget

        from ui.widgets.cards import GridInstalledCard

        panel = QWidget()
        panel.resize(1060, 300)
        grid = QGridLayout(panel)
        grid.setContentsMargins(14, 14, 14, 14)
        grid.setSpacing(14)
        for columna in range(3):
            grid.setColumnStretch(columna, 1)
        nombres = [self.LARGO, "blender-5.2.0", "blender-5.1.2-linux-x64"]
        for indice, nombre in enumerate(nombres):
            grid.addWidget(GridInstalledCard(self._entrada(nombre), False, 1.0),
                           0, indice)
        panel.show()
        self.app.processEvents()

        # El minimo ya no depende del texto (antes la larga pedia 507 px).
        minimos = {grid.itemAtPosition(0, i).widget().minimumSizeHint().width()
                   for i in range(3)}
        self.assertEqual(len(minimos), 1)
        # Y en pantalla las tres ocupan lo mismo (1 px arriba o abajo, que es el
        # redondeo de repartir el ancho entre tres).
        anchos = [grid.itemAtPosition(0, i).widget().width() for i in range(3)]
        self.assertLessEqual(max(anchos) - min(anchos), 1)

    def test_lista_con_ruta_larga_cabe_en_la_ventana(self):
        from PySide6.QtWidgets import QHBoxLayout, QWidget

        from ui.widgets.cards import InstalledCard

        panel = QWidget()
        panel.resize(900, 200)
        lay = QHBoxLayout(panel)
        tarjeta = InstalledCard(self._entrada(self.LARGO), False)
        lay.addWidget(tarjeta)
        panel.show()
        self.app.processEvents()
        # Antes necesitaba 974 px (el nombre 483 + el meta con la ruta 666).
        self.assertLess(tarjeta.minimumSizeHint().width(), 500)

    def test_la_etiqueta_recorta_y_solo_avisa_si_no_cabe(self):
        from PySide6.QtCore import Qt

        from ui.widgets.labels import ElidedLabel

        etiqueta = ElidedLabel(self.LARGO, Qt.ElideMiddle)
        etiqueta.setFixedWidth(300)
        etiqueta.show()
        self.app.processEvents()
        self.assertTrue(etiqueta.is_elided())
        self.assertIn("…", etiqueta.displayed_text())
        # El texto completo sigue en text() y en el tooltip...
        self.assertEqual(etiqueta.text(), self.LARGO)
        self.assertEqual(etiqueta.toolTip(), self.LARGO)

        etiqueta.setFixedWidth(900)
        self.app.processEvents()
        # ...pero si cabe entero, el tooltip desaparece (no repite lo que ya se ve).
        self.assertFalse(etiqueta.is_elided())
        self.assertEqual(etiqueta.displayed_text(), self.LARGO)
        self.assertEqual(etiqueta.toolTip(), "")


@unittest.skipUnless(HAVE_QT, "PySide6 no instalado")
class UninstallTests(SettingsIsolated, unittest.TestCase):
    """Borrar una version instalada: el boton de la papelera."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from ui import fonts, qss

        fonts.load()
        cls.app.setStyleSheet(qss.build_qss())

    def _entrada(self, carpeta):
        from pathlib import Path

        from services.installed import InstalledBuild

        return InstalledBuild(name=carpeta.name, path=carpeta, version="3.5.0",
                              branch="v35")

    def test_el_mensaje_no_revienta_con_la_ruta(self):
        # entry.path es un Path y se concatenaba a un str: TypeError al
        # construir el mensaje, ANTES de crear el dialogo. Por eso la papelera
        # no hacia nada y no decia nada (PySide se come la excepcion del slot).
        import tempfile
        from unittest import mock

        from ui.widgets import main_window
        from ui.widgets.main_window import MainWindow
        from i18n import tr

        window = MainWindow()
        with tempfile.TemporaryDirectory() as temp:
            entrada = self._entrada(Path(temp) / "blender-3.5.0-linux-x64")
            with mock.patch.object(main_window, "confirm", return_value=False) as conf:
                window.delete_installed(entrada)
            # La ruta tiene que llegar como texto.
            _, _, mensaje = conf.call_args.args
            self.assertIn(str(entrada.path), mensaje)
            self.assertIn(tr("Delete {name}?", name=entrada.name), mensaje)

    def test_borra_de_verdad_la_carpeta(self):
        import tempfile
        from pathlib import Path
        from unittest import mock

        from ui.widgets import main_window
        from ui.widgets.main_window import MainWindow
        from i18n import tr

        window = MainWindow()
        with tempfile.TemporaryDirectory() as temp:
            carpeta = Path(temp) / "blender-3.5.0-linux-x64"
            carpeta.mkdir()
            (carpeta / "blender").write_text("binario", encoding="utf-8")
            with mock.patch.object(main_window, "confirm", return_value=True), \
                    mock.patch.object(window, "refresh_installed"), \
                    mock.patch.object(window, "_show_message") as aviso:
                window.delete_installed(self._entrada(carpeta))
            self.assertFalse(carpeta.exists())
            self.assertEqual(aviso.call_args.args[0],
                             tr("Deleted {name}", name=carpeta.name))

    def test_si_falla_lo_dice_y_lo_registra(self):
        # Antes era rmtree(..., ignore_errors=True): un fallo no dejaba rastro
        # ni en pantalla ni en el log.
        import tempfile
        from pathlib import Path
        from unittest import mock

        from ui.widgets import main_window
        from ui.widgets.main_window import MainWindow

        window = MainWindow()
        with tempfile.TemporaryDirectory() as temp:
            carpeta = Path(temp) / "blender-3.5.0-linux-x64"
            with mock.patch.object(main_window, "confirm", return_value=True), \
                    mock.patch.object(main_window.shutil, "rmtree",
                                      side_effect=OSError("read-only")), \
                    mock.patch.object(window, "refresh_installed") as refresco, \
                    mock.patch.object(main_window, "download_log") as registro, \
                    mock.patch.object(main_window, "show_error") as error:
                window.delete_installed(self._entrada(carpeta))
            self.assertTrue(error.called)
            self.assertIn("read-only", error.call_args.args[2])
            self.assertTrue(registro.called)
            self.assertFalse(refresco.called)


@unittest.skipUnless(HAVE_QT, "PySide6 no instalado")
class ExceptionHookTests(SettingsIsolated, unittest.TestCase):
    """Un slot que revienta ya no se pierde en silencio."""

    def test_registra_y_avisa(self):
        import sys
        from unittest import mock

        import main
        from services import downloader
        from ui.widgets import dialogs

        original = sys.excepthook
        self.addCleanup(setattr, sys, "excepthook", original)
        with mock.patch.object(downloader, "log") as registro, \
                mock.patch.object(dialogs, "show_error") as aviso:
            main._install_exception_hook()
            try:
                raise TypeError("como el de la papelera")
            except TypeError:
                sys.excepthook(*sys.exc_info())
        # El traceback completo al log, y un aviso en pantalla.
        self.assertTrue(registro.called)
        self.assertIn("unhandled error", registro.call_args.args[0])
        self.assertIn("TypeError", registro.call_args.args[0])
        self.assertTrue(aviso.called)


@unittest.skipUnless(HAVE_QT, "PySide6 no instalado")
class DialogTests(unittest.TestCase):
    app = None

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from ui import qss

        cls.app.setStyleSheet(qss.build_qss())

    def test_un_mensaje_largo_no_se_corta(self):
        """El texto del diálogo tiene que caber entero (verticalmente).

        Con el nombre largo de una instalada, el aviso de desinstalar se cortaba:
        Qt mide el `QLabel` con `wordWrap` antes de que el estilo aplique la
        fuente y con un ancho que después cambia, así que se quedaba con el alto
        viejo (90 px cuando necesitaba 108).
        """
        from i18n import tr
        from ui.widgets.dialogs import AppDialog

        nombre = "blender-5.3.0-alpha+main.1fd06ddba680-linux.x86_64-release"
        mensaje = (tr("Delete {name}?", name=nombre) + "\n\n"
                   + tr("This will remove the folder permanently.") + "\n\n"
                   + "/home/alguien/Descargas/Blenders/" + nombre)
        dialog = AppDialog(None, tr("Uninstall"), mensaje)
        dialog.add_button(tr("Cancel"), on_click=dialog.reject)
        dialog.show()
        for _ in range(3):
            self.app.processEvents()
        etiqueta = dialog.body_label
        self.assertGreaterEqual(etiqueta.height(),
                                etiqueta.heightForWidth(etiqueta.width()))
        # Y un nombre enorme no puede sacar la ventana de la pantalla.
        self.assertLessEqual(dialog.width(), dialog.MAX_WIDTH)

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
