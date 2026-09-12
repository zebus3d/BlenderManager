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


class DevReloader:
    """Recarga en caliente el .kv y el tema cuando se guardan los archivos.

    Es una ayuda de desarrollo: los cambios de estilo (gui.kv, theme.py,
    icons.py, i18n.py) se aplican sin reiniciar. Los cambios de lógica en
    Python siguen necesitando reiniciar la aplicación.
    """

    def __init__(self, app, kv_path, files):
        from kivy.clock import Clock

        self.app = app
        self.kv_path = kv_path
        self.files = files
        self.mtimes = {}
        for path in files:
            try:
                self.mtimes[path] = os.path.getmtime(path)
            except OSError:
                pass
        Clock.schedule_interval(self._check, 1.0)

    def _check(self, dt):
        changed = False
        for path in self.files:
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if mtime != self.mtimes.get(path):
                self.mtimes[path] = mtime
                changed = True
        if changed:
            self._reload()

    def _reload(self):
        import importlib

        import i18n
        from kivy.lang import Builder
        from kivy.logger import Logger
        from ui import icons, theme

        try:
            importlib.reload(i18n)
            importlib.reload(theme)
            importlib.reload(icons)
            theme.init()
            Builder.unload_file(str(self.kv_path))
            Builder.load_file(str(self.kv_path))
            self.app.root._reload_ui()
            Logger.info("Watch: interfaz recargada")
        except Exception:
            import traceback

            traceback.print_exc()


def run_ui(debug: bool = False, screenshot: str = None, watch: bool = False) -> None:
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
        GridInstalledCard,
        HoverButton,
        HoverSpinner,
        InstalledCard,
        Pill,
        RootWidget,
        SideButton,
        SwitchPill,
        ZoomSlider,
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
        GridInstalledCard,
        InstalledCard,
        RootWidget,
        SwitchPill,
        ZoomSlider,
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

        def on_start(self):
            if watch:
                DevReloader(self, VIEWS_DIR / "gui.kv", [
                    VIEWS_DIR / "gui.kv",
                    SRC_DIR / "ui" / "theme.py",
                    SRC_DIR / "ui" / "icons.py",
                    SRC_DIR / "i18n.py",
                ])

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
    parser.add_argument("--watch", action="store_true", help="Recargar .kv/tema al guardar (desarrollo)")
    args = parser.parse_args()

    if args.smoke:
        smoke()
        return

    run_ui(debug=args.debug, screenshot=args.screenshot, watch=args.watch)


if __name__ == "__main__":
    main()
