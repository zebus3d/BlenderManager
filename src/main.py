"""Punto de entrada de Blender Manager.

Modos de uso:

* ``python3 src/main.py``               -> abre la interfaz.
* ``python3 src/main.py --debug``       -> interfaz con registro detallado.
* ``python3 src/main.py --smoke``       -> lista compilaciones por consola (sin ventana).
* ``python3 src/main.py --screenshot RUTA.png`` -> arranca, captura y sale.
"""

import argparse
import os
import sys
from pathlib import Path

# Hay que fijarlo ANTES de importar Kivy, o Kivy intentará procesar
# nuestros argumentos de línea de comandos y se hará un lío.
os.environ.setdefault("KIVY_NO_ARGS", "1")

# Aseguramos que 'src' esté en el path para poder importar services/ui/model.
SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import i18n
from paths import ASSETS_DIR, VIEWS_DIR
from services import api, detector, settings as settings_service


def smoke():
    """Comprobación rápida sin interfaz: descarga el listado y lo imprime."""
    info = detector.detect()
    builds = api.get_builds(force=True)
    print("system:", info)
    print("total builds:", len(builds))
    for build in api.available_for(builds, info.os_name, info.arch)[:12]:
        tag = "LTS" if build.is_lts else build.risk
        print(f"  {build.version:<8} {tag:<7} {build.branch:<5} {build.human_size:>10}  {build.filename}")


def run_ui(debug: bool = False, screenshot: str = None) -> None:
    """Arranca la aplicación Kivy."""
    from kivy.app import App
    from kivy.clock import Clock
    from kivy.core.window import Window
    from kivy.factory import Factory
    from kivy.lang import Builder
    from kivy.logger import Logger, LOG_LEVELS
    from kivy.resources import resource_add_path

    from ui import theme
    from ui.widgets import (
        BuildCard,
        CardButton,
        GridBuildCard,
        HoverButton,
        HoverSpinner,
        InstalledCard,
        Pill,
        RootWidget,
        SideButton,
        SwitchPill,
    )

    if debug:
        Logger.setLevel(LOG_LEVELS["debug"])

    # Las clases propias que aparecen dentro del .kv deben estar registradas
    # en la Factory para que el parser de Kivy sepa construirlas.
    widgets = (
        Pill,
        SideButton,
        CardButton,
        HoverButton,
        HoverSpinner,
        BuildCard,
        GridBuildCard,
        InstalledCard,
        RootWidget,
        SwitchPill,
    )
    for widget in widgets:
        Factory.register(widget.__name__, cls=widget)

    # Registramos la fuente de iconos y cargamos la vista.
    theme.init()
    Builder.load_file(str(VIEWS_DIR / "gui.kv"))

    class MainApp(App):
        def build(self):
            app_settings = settings_service.Settings.load()
            i18n.set_language(app_settings.language)
            self.title = i18n.tr("Blender Downloads Manager")
            Window.clearcolor = theme.BG
            Window.size = (1060, 680)
            Window.minimum_width = 880
            Window.minimum_height = 540
            # Permite que el .kv encuentre "images/blender_logo.png".
            resource_add_path(str(ASSETS_DIR))
            return RootWidget()

    # Modo de captura automática (útil para generar imágenes de documentación).
    if screenshot:
        def capture(dt):
            Window.screenshot(name=str(screenshot))

        def stop(dt):
            App.get_running_app().stop()

        Clock.schedule_once(capture, 6)
        Clock.schedule_once(stop, 8)

    MainApp().run()


def main():
    parser = argparse.ArgumentParser(description="Blender Manager")
    parser.add_argument("--smoke", action="store_true", help="List builds without opening the UI")
    parser.add_argument("--debug", action="store_true", help="Enable verbose logging")
    parser.add_argument("--screenshot", metavar="PATH", help="Save a screenshot after startup and quit")
    args = parser.parse_args()

    if args.smoke:
        smoke()
        return

    run_ui(debug=args.debug, screenshot=args.screenshot)


if __name__ == "__main__":
    main()
