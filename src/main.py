from kivy.app import App
from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition  # , FadeTransition, NoTransition
from kivy.uix.tabbedpanel import TabbedPanel
from kivy.core.window import Window
import os, sys
from services.detect_os import OsDetect

# Para el inspector:
from kivy.modules import inspector


# para que las builds de pyinstaller onefile encuentren los paths dentro del bundle:
if hasattr(sys, "_MEIPASS"):
    base_path = sys._MEIPASS
    os.chdir(base_path)

Builder.load_file('views/gui.kv')

detection = OsDetect()
detection.detect()


class MainScreen(Screen):
    def set_platform_name(self) -> str:
        print("auto detect os: ", detection.os)
        if detection.os:
            return detection.os
        else:
            return "current system not supported"

    def set_architecture(self) -> str:
        print("auto detect architecture: ", detection.arch)
        if detection.arch:
            return detection.arch
        else:
            return "err"

    def print_current(self, current_value):
        print(current_value)


class PreferencesScreen(Screen):
    pass


class TabbedPanel(TabbedPanel):
    pass


# Screen manager
sm = ScreenManager()
# Effectos de transicion:
# sm = ScreenManager(transition=NoTransition())
# sm = ScreenManager(transition=FadeTransition())
sm = ScreenManager(transition=SlideTransition())

# Inspector:
# Para mostrar el inspector hay que pulsar ctrl + e
# Si seleccionas un item dale al boton grande (a la izquierda del boton x ) para expandir sus propiedades:
inspector.create_inspector(Window, sm)


s01 = MainScreen(name='main_screen')
s02 = PreferencesScreen(name='settings')


sm.add_widget(s01)
sm.add_widget(s02)



class MainApp(App):
    def build(self):
        self.title = 'Blender Downloader'
        return sm


if __name__ == '__main__':
    app = MainApp()
    Window.size = (600, 400)
    Window.exit_on_scape = 1
    # centrando ventana:
    Window.top = Window.top+50
    Window.left = Window.left-600/3.6
    # pongo este color por si usas transiciones que queden bien:
    # el color de background donde no ocupa por completo un screen:
    Window.clearcolor = (66/255.0, 66/255.0, 66/255.0, 1)
    app.run()
