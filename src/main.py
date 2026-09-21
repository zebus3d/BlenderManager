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
import os
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import i18n
from services import api, detector, updater


def smoke() -> int:
    """Comprobación rápida sin interfaz: descarga el listado y lo imprime.

    Devuelve 0 si ha podido descargar y 1 si no, para que el CI (o quien lo
    ejecute) note que el binario no tiene red. Antes usaba ``get_builds``, que
    cae al caché de disco cuando falla: imprimía las compilaciones guardadas y
    salía con 0, así que un binario incapaz de hacer HTTPS *parecía* funcionar
    (nos pasó en Arch y lo tapó durante días).
    """
    info = detector.detect()
    try:
        # ``fetch_builds`` devuelve ``(builds, etags)``; aquí solo importan las
        # builds.
        builds, _ = api.fetch_builds()
    except Exception as error:
        print(f"ERROR: no se pudo descargar el listado: {error}", file=sys.stderr)
        return 1
    if not builds:
        print("ERROR: el listado vino vacío", file=sys.stderr)
        return 1
    print("system:", info)
    print("total builds:", len(builds))
    # El filtro usa el nombre normalizado (Windows es "amd64" en la API): si no,
    # en Windows este listado saldría vacío aunque hubiera compilaciones.
    for build in api.available_for(builds, info.os_name,
                                   api.normalize_arch(info.arch))[:12]:
        tag = "LTS" if build.is_lts else build.risk
        print(f"  {build.version:<8} {tag:<7} {build.branch:<5} "
              f"{build.human_size:>10}  {build.filename}")
    return 0


def _clean_previous_session(settings) -> None:
    """Borra los restos de la sesión anterior.

    Dos cosas: el binario que se descargó para actualizar (una AppImage son
    ~73 MB) y las descargas de Blender que se quedaron a medias (``.part``).

    OJO: estas dos llamadas vivían en ``root.py`` en la versión Kivy y se
    perdieron al portar la interfaz, así que el binario de cada actualización se
    quedaba en el caché para siempre. Hay un test que comprueba que se llaman.
    """
    updater.cleanup_staging()
    # Solo en las carpetas donde se descarga: un ``.part`` no puede aparecer en
    # una carpeta que solo se escanea, y en una con el candado cerrado no
    # tenemos permiso para borrar nada (ni queremos).
    for folder in settings.install_folders():
        updater.cleanup_partials(folder.path)


def _install_exception_hook() -> None:
    """Deja constancia (y avisa) cuando un fallo no controlado revienta la UI.

    PySide6 se traga las excepciones que saltan **dentro de un slot**: las
    imprime por stderr y sigue, así que desde el menú el usuario solo ve que "no
    pasa nada". Nos pasó con la papelera: reventaba al construir el mensaje del
    diálogo (concatenar un ``Path`` a un ``str``) y no se borraba nada ni se
    decía nada. El ``sys.excepthook`` de Python **sí** se llama en ese caso, así
    que desde aquí lo mandamos al log de la aplicación y lo enseñamos.
    """
    import traceback

    from i18n import tr
    from services.downloader import log
    from ui.widgets.dialogs import show_error

    def hook(tipo, valor, tb):
        if issubclass(tipo, KeyboardInterrupt):
            sys.__excepthook__(tipo, valor, tb)
            return
        detalle = "".join(traceback.format_exception(tipo, valor, tb))
        log(f"unhandled error:\n{detalle}")
        # Un diálogo como mucho: si algo falla en bucle, el log ya lo tiene todo
        # y no queremos llenar la pantalla de ventanas.
        if getattr(hook, "avisando", False):
            return
        hook.avisando = True
        try:
            show_error(None, tr("Unexpected error"),
                       f"{tipo.__name__}: {valor}")
        except Exception:
            pass
        finally:
            hook.avisando = False

    sys.excepthook = hook


def _prefer_xwayland_for_tray(settings) -> None:
    """Fuerza el backend X11 de Qt cuando "minimizar a la bandeja" lo exige.

    En Wayland no existe el estado "ventana minimizada" en ``xdg-shell``: si el
    botón de minimizar lo dibuja el compositor (KWin, decoraciones del servidor)
    la aplicación no recibe ningún aviso, así que la ventana se queda en la
    barra de tareas. La única forma de interceptarlo es correr bajo XWayland.
    Como el backend de Qt se elige **antes** de crear ``QApplication``, esto se
    decide aquí, al arrancar, y solo si el usuario activó esa opción (el resto
    sigue en Wayland nativo). Es el equivalente a ``--ozone-platform=x11`` que
    usan las apps Electron.
    """
    if detector.should_use_xwayland(settings.minimize_to_tray):
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")


def _start_window(window, start_minimized: bool) -> None:
    """Enseña la ventana, o la deja en la bandeja si se pidió arrancar oculto.

    Arrancar oculto (``start_minimized``) es lo que hace útil el autoarranque:
    la aplicación queda a mano sin aparecer al iniciar la sesión. Si no hay
    bandeja se enseña igual, porque esconderla sin un icono al que volver la
    dejaría inaccesible.
    """
    from PySide6.QtCore import QTimer

    from ui.widgets.tray import TrayIcon

    if start_minimized and TrayIcon.available():
        window.center_on_screen()
        QTimer.singleShot(0, window._hide_to_tray)
    else:
        window.show()
        window.center_on_screen()


def run_ui(screenshot: str | None = None, debug: bool = False) -> int:
    """Arranca la aplicación Qt."""
    from services import settings as settings_service

    # Los ajustes se leen (y el backend se decide) ANTES de importar la
    # interfaz: Wayland o X11 tiene que quedar fijado antes de QApplication.
    settings = settings_service.Settings.load()
    i18n.set_language(settings.language)
    _prefer_xwayland_for_tray(settings)

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from ui import fonts, qss
    from ui.widgets.main_window import (
        DEFAULT_WINDOW_HEIGHT,
        DEFAULT_WINDOW_WIDTH,
        MIN_WINDOW_HEIGHT,
        MIN_WINDOW_WIDTH,
        MainWindow,
    )

    _install_exception_hook()

    app = QApplication(sys.argv)
    app.setApplicationName("BlenderManager")
    app.setApplicationVersion(updater.app_version())
    # En Wayland/KDE el compositor empareja la ventana con el .desktop por este
    # nombre; sin el, la barra de tareas no encuentra el icono.
    app.setDesktopFileName("blendermanager")

    # Icono de la ventana y de la barra de tareas. Sin esto, el marco y el dock
    # ensenan el icono generico de Qt.
    from paths import ASSETS_DIR
    from PySide6.QtGui import QIcon

    icon = QIcon(str(ASSETS_DIR / "images" / "app_icon.png"))
    if not icon.isNull():
        app.setWindowIcon(icon)

    fonts.load()
    app.setStyleSheet(qss.build_qss())

    window = MainWindow()
    window.resize(max(MIN_WINDOW_WIDTH, settings.window_width or DEFAULT_WINDOW_WIDTH),
                  max(MIN_WINDOW_HEIGHT, settings.window_height or DEFAULT_WINDOW_HEIGHT))
    _start_window(window, settings.start_minimized)

    # Restos de la sesión anterior, con retardo para no retrasar el arranque.
    QTimer.singleShot(600, lambda: _clean_previous_session(settings))

    if screenshot:
        def grab():
            window.grab().save(screenshot)
            app.quit()

        QTimer.singleShot(6000, grab)
    return app.exec()


def main() -> None:
    """Punto de entrada: lee los argumentos y hace lo que toque."""
    parser = argparse.ArgumentParser(description="Blender Manager")
    parser.add_argument("--smoke", action="store_true",
                        help="List builds without opening the UI")
    parser.add_argument("--debug", action="store_true", help="Enable verbose logging")
    parser.add_argument("--screenshot", metavar="PATH",
                        help="Save a screenshot after startup and quit")
    parser.add_argument("--apply-update", nargs=2, metavar=("APP_DIR", "PID"),
                        help="Uso interno: aplica una actualizacion ya descargada")
    parser.add_argument("--grant-access", metavar="FOLDER",
                        help="Uso interno: crea la carpeta y da permiso de "
                             "escritura (Windows, con UAC)")
    args = parser.parse_args()

    if args.grant_access:
        # Segundo proceso, ya elevado: concede permiso y termina sin abrir la
        # interfaz (lo lanza services.elevate desde la app normal).
        from services import elevate

        sys.exit(0 if elevate.grant_write(args.grant_access) else 1)

    if args.apply_update:
        from services import updater as updater_service

        updater_service.apply_update(args.apply_update[0], args.apply_update[1])
        return

    if args.smoke:
        sys.exit(smoke())

    sys.exit(run_ui(screenshot=args.screenshot, debug=args.debug))


if __name__ == "__main__":
    main()
