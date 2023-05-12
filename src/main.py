from kivy.app import App
from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition
from kivy.uix.tabbedpanel import TabbedPanel
from kivy.core.window import Window
from services.detector import OSDetector
import os
import sys
from kivy.modules import inspector

# Para que las builds de pyinstaller onefile encuentren los paths dentro del bundle:
base_path = getattr(sys, "_MEIPASS", None)
if base_path is not None:
    os.chdir(base_path)

Window.size = (600, 400)
Window.top = Window.top+50
Window.left = Window.left-600/3.6
Window.clearcolor = (66/255.0, 66/255.0, 66/255.0, 1)

Builder.load_file('views/gui.kv')

detector = OSDetector()
sysi = detector.detect()

class MainScreen(Screen):
    def set_platform_name(self) -> str:
        print("auto detect os: ", sysi.os)
        return sysi.os or "current system not supported"

    def set_architecture(self) -> str:
        print("auto detect architecture: ", sysi.arch)
        return sysi.arch or "err"

    def print_current(self, current_value):
        print(current_value)

class PreferencesScreen(Screen):
    pass

class MyTabbedPanel(TabbedPanel):
    pass

sm = ScreenManager(transition=NoTransition())
sm.add_widget(MainScreen(name='main_screen'))
sm.add_widget(PreferencesScreen(name='settings'))

inspector.create_inspector(Window, sm)

class MainApp(App):
    def build(self):
        self.title = 'Blender Downloader'
        return sm

if __name__ == '__main__':
    app = MainApp()
    app.run()