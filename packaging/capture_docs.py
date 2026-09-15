"""Genera las capturas de documentación (docs/img/*.png) desde la app Qt.

Uso:  QT_QPA_PLATFORM=offscreen .venv/bin/python packaging/capture_docs.py

Las capturas del README son 1280x624, en español y con la barra de filtros
visible. Se hacen con el plugin offscreen de Qt, así que no hace falta
servidor gráfico (a diferencia del Kivy antiguo, que necesitaba ventana real).
"""

import sys
import tempfile
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "docs" / "img"
WIDTH, HEIGHT = 1280, 624

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main() -> None:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    import i18n
    from services import settings as settings_service
    from ui import fonts, qss
    from ui.widgets import MainWindow
    from ui.widgets.dialogs import AppDialog
    from i18n import tr

    # Los ajustes van a un directorio temporal, y ojo con esto: el script fija
    # el zoom en memoria para que las capturas salgan siempre iguales, y sin
    # aislar la config ese zoom acababa escrito en el settings.json del usuario.
    # Lo vuelca closeEvent al salir, que es lo correcto en la app (flush del
    # zoom pendiente) pero aquí no debe tocar nada del usuario.
    with tempfile.TemporaryDirectory() as temp:
        settings_service.config_dir = lambda: Path(temp)

        app = QApplication([])
        i18n.set_language("es")
        fonts.load()
        app.setStyleSheet(qss.build_qss())

        OUT.mkdir(parents=True, exist_ok=True)
        window = MainWindow()
        window.resize(WIDTH, HEIGHT)
        # El zoom se fija en memoria para que la captura sea siempre igual,
        # independientemente de lo que tenga guardado el usuario. Hay que
        # reflejarlo también en el slider y la etiqueta, o la captura sale con
        # las tarjetas a un tamaño y el "NN %" de otro.
        window.zoom = 1.0
        window.zoom_slider.blockSignals(True)
        window.zoom_slider.setValue(100)
        window.zoom_slider.blockSignals(False)
        window._update_zoom_label()
        window.show()

        def capture_store():
            window.set_layout_mode("grid")
            window.set_view("store")
            # Una marcada como favorita, para que la captura enseñe la estrella
            # en ámbar (se marca la primera que haya, así no depende de una
            # versión concreta).
            visible = window._filtered()
            if visible:
                window.settings.favorites = [visible[0].favorite_key]
                window._rebuild_store()
            QTimer.singleShot(600, save_store)

        def save_store():
            window.grab().save(str(OUT / "store_grid.png"))
            print("guardada store_grid.png")
            QTimer.singleShot(300, capture_installed)

        def capture_installed():
            window.set_layout_mode("list")
            window.set_view("installed")
            QTimer.singleShot(600, save_installed)

        def save_installed():
            window.grab().save(str(OUT / "installed_list.png"))
            print("guardada installed_list.png")
            QTimer.singleShot(300, capture_update)

        def capture_update():
            dialog = AppDialog(
                window, tr("Update available"),
                tr("A new version is available: {version}", version="v1.2.34")
                + "\n\n"
                + tr("It will be installed and the app will restart automatically."))
            dialog.add_button(tr("Later"), on_click=dialog.reject)
            dialog.add_button(tr("Update"), variant="accent",
                              on_click=dialog.reject)
            dialog.show()

            def save_dialog():
                dialog.grab().save(str(OUT / "update_dialog.png"))
                print("guardada update_dialog.png")
                app.quit()

            QTimer.singleShot(600, save_dialog)

        QTimer.singleShot(8000, capture_store)
        app.exec()


if __name__ == "__main__":
    main()
