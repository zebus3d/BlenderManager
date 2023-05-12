import os
import sys
import configparser
from kivy.app import App
from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition
from kivy.uix.tabbedpanel import TabbedPanel
from kivy.core.window import Window
from kivy.modules import inspector
from services.osdetector import detect
from mainscreen import MainScreen


# Para que las builds de pyinstaller onefile encuentren los paths dentro del bundle:
base_path = getattr(sys, "_MEIPASS", None)
if base_path is not None:
    os.chdir(base_path)


class PreferencesScreen(Screen):
    pass

class MyTabbedPanel(TabbedPanel):
    pass

# Carga el archivo KV
Builder.load_file('views/gui.kv')

# Detecta el sistema operativo y la arquitectura
sysi = detect()

# Define la pantalla principal
mainscreen = MainScreen(name='main_screen')

# Agrega las pantallas al manejador de pantallas (ScreenManager)
sm = ScreenManager(transition=NoTransition())
sm.add_widget(mainscreen)
sm.add_widget(PreferencesScreen(name='settings'))

# Crea un inspector para la ventana principal
inspector.create_inspector(Window, sm)

# Define la aplicación principal
class MainApp(App):
    def build(self):
        # Lee las configuraciones desde el archivo ini
        config = configparser.ConfigParser()
        config.read('src/config.ini')
        self.title = config['app']['title']
        Window.size = (int(config['app']['width']), int(config['app']['height']))

        r, g, b, a= config['app']['background_color'].split(',')
        red = float(r) / 255.0
        green = float(g)
        blue = float(b)
        alpha = float(a)
        Window.clearcolor = (red, green, blue, alpha)
        
        # Centra la ventana
        if self.root_window:
            Window.center = self.root_window.get_rect().center
        
        return sm

if __name__ == '__main__':
    app = MainApp()
    app.run()
