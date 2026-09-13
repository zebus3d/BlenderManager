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
from services import api, detector, settings as settings_service, updater


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
        AppModalView,
        AppPopup,
        AppDropDown,
        AppProgressBar,
        BuildCard,
        CardButton,
        DarkSpinnerOption,
        FolderRow,
        GridBuildCard,
        GridInstalledCard,
        HoverButton,
        HoverSpinner,
        IconLinkButton,
        InstalledCard,
        Pill,
        RootWidget,
        SettingsCard,
        SettingsHeader,
        SettingsInput,
        SideButton,
        SwitchPill,
        ZoomSlider,
    )

    if debug:
        Logger.setLevel(LOG_LEVELS["debug"])

    # Las clases propias que aparecen dentro del .kv deben estar registradas
    # en la Factory para que el parser de Kivy sepa construirlas.
    widgets = (
        AppDropDown,
        AppModalView,
        AppPopup,
        AppProgressBar,
        Pill,
        SideButton,
        CardButton,
        DarkSpinnerOption,
        FolderRow,
        HoverButton,
        HoverSpinner,
        IconLinkButton,
        BuildCard,
        GridBuildCard,
        GridInstalledCard,
        InstalledCard,
        RootWidget,
        SettingsCard,
        SettingsHeader,
        SettingsInput,
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
            # La versión también en el título. En modo fuente sale del último
            # tag del repo (updater.app_version), no del 0.0.0 de version.py.
            self.title = f"{i18n.tr('Blender Downloads Manager')} {updater.app_version()}"
            Window.clearcolor = theme.BG
            # Restauramos el tamaño que dejó el usuario en la sesión anterior.
            width = max(880, app_settings.window_width or 1060)
            height = max(540, app_settings.window_height or 680)
            Window.minimum_width = 880
            Window.minimum_height = 540
            # Nos suscribimos ANTES de fijar el tamaño para no perder eventos.
            self._resize_event = None
            Window.bind(on_resize=self._on_resize)
            Window.size = (width, height)
            # Permite que el .kv encuentre "images/blender_logo.png".
            resource_add_path(str(ASSETS_DIR))
            # Icono de la ventana / barra de tareas (en vez del de Kivy).
            try:
                Window.set_icon(str(ASSETS_DIR / "images" / "app_icon.png"))
            except Exception:
                pass
            return RootWidget()

        def on_start(self):
            # Traemos la ventana al frente y pedimos el foco: si el gestor de
            # ventanas no la enfoca al abrir, el primer clic se lo come él
            # (click-to-focus) y parece que los botones no responden.
            try:
                Window.raise_window()
                Window.focus = True
            except Exception:
                pass
            if watch:
                DevReloader(self, VIEWS_DIR / "gui.kv", [
                    VIEWS_DIR / "gui.kv",
                    SRC_DIR / "ui" / "theme.py",
                    SRC_DIR / "ui" / "icons.py",
                    SRC_DIR / "i18n.py",
                ])

        def _on_resize(self, window, width, height):
            # Guardamos con un pequeño retardo para no escribir en cada píxel.
            if self._resize_event is not None:
                self._resize_event.cancel()
            self._resize_event = Clock.schedule_once(
                lambda dt: self._save_window_size(width, height), 0.6
            )

        def _save_window_size(self, width, height):
            # Importante: reutilizamos el MISMO objeto Settings que tiene la
            # pantalla principal. Si cargásemos uno nuevo del disco, el de la
            # pantalla (con el tamaño viejo) lo sobrescribiría en cuanto el
            # usuario tocase el zoom o el modo de vista, y el tamaño se perdería.
            settings = getattr(self.root, "settings", None)
            if settings is None:
                settings = settings_service.Settings.load()
            try:
                settings.window_width = int(width)
                settings.window_height = int(height)
                settings.save()
            except OSError:
                pass

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
    parser.add_argument(
        "--apply-update",
        nargs=2,
        metavar=("APP_DIR", "PID"),
        help="Uso interno: aplica una actualizacion ya descargada y relanza la app",
    )
    args = parser.parse_args()

    if args.apply_update:
        # Modo ayudante del auto-update: espera a que salga la app antigua,
        # copia los ficheros nuevos y relanza. No abrimos ninguna ventana.
        from services import updater

        updater.apply_update(args.apply_update[0], args.apply_update[1])
        return

    if args.smoke:
        smoke()
        return

    run_ui(debug=args.debug, screenshot=args.screenshot, watch=args.watch)


if __name__ == "__main__":
    main()
