"""Punto de entrada de Blender Manager (versión PySide6).

Modos de uso:

* ``python3 src/main.py``               -> abre la interfaz.
* ``python3 src/main.py --smoke``       -> lista compilaciones por consola (sin ventana).
* ``python3 src/main.py --screenshot RUTA.png`` -> arranca, captura y sale.
* ``python3 src/main.py --apply-update APP_DIR PID`` -> uso interno del auto-update.

La interfaz usa Qt Widgets (PySide6), que renderiza con el motor *raster* (CPU)
en vez de exigir OpenGL: eso es lo que permite que un mismo AppImage funcione
en todas las distros, sin depender del Mesa del sistema.
"""

import argparse
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import i18n
from services import api, detector, updater


def smoke() -> None:
    """Comprobación rápida sin interfaz: descarga el listado y lo imprime."""
    info = detector.detect()
    builds = api.get_builds(force=True)
    print("system:", info)
    print("total builds:", len(builds))
    for build in api.available_for(builds, info.os_name, info.arch)[:12]:
        tag = "LTS" if build.is_lts else build.risk
        print(f"  {build.version:<8} {tag:<7} {build.branch:<5} "
              f"{build.human_size:>10}  {build.filename}")


def run_ui(screenshot: str | None = None, debug: bool = False) -> int:
    """Arranca la aplicación Qt."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from services import settings as settings_service
    from ui import fonts, qss
    from ui.widgets.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("BlenderManager")
    app.setApplicationVersion(updater.app_version())

    settings = settings_service.Settings.load()
    i18n.set_language(settings.language)

    fonts.load()
    app.setStyleSheet(qss.build_qss())

    window = MainWindow()
    window.resize(max(880, settings.window_width or 1060),
                  max(540, settings.window_height or 680))
    window.show()

    if screenshot:
        def grab():
            window.grab().save(screenshot)
            app.quit()

        QTimer.singleShot(6000, grab)
    return app.exec()


def main() -> None:
    parser = argparse.ArgumentParser(description="Blender Manager")
    parser.add_argument("--smoke", action="store_true",
                        help="List builds without opening the UI")
    parser.add_argument("--debug", action="store_true", help="Enable verbose logging")
    parser.add_argument("--screenshot", metavar="PATH",
                        help="Save a screenshot after startup and quit")
    parser.add_argument("--apply-update", nargs=2, metavar=("APP_DIR", "PID"),
                        help="Uso interno: aplica una actualizacion ya descargada")
    args = parser.parse_args()

    if args.apply_update:
        from services import updater as updater_service

        updater_service.apply_update(args.apply_update[0], args.apply_update[1])
        return

    if args.smoke:
        smoke()
        return

    sys.exit(run_ui(screenshot=args.screenshot, debug=args.debug))


if __name__ == "__main__":
    main()
