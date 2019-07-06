from kivy.app import App
from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition, NoTransition, SlideTransition
from kivy.uix.tabbedpanel import TabbedPanel
from kivy.core.window import Window
import platform
from kivy.modules import inspector

Builder.load_file('views/gui.kv')


class MainScreen(Screen):
    def set_platform_name(self) -> str:
        os_name = platform.system()
        if os_name == "Linux":
            os_name = "GNU/Linux"
        elif os_name == "Darwin":
            os_name = "Mac"
        elif os_name == "Windows":
            os_name = "Windows"
        else:
            print("unsupported system!")

        print("auto detect os: ", os_name)
        return os_name

    def print_current(self, current_value):
        print(current_value)


class PreferencesScreen(Screen):
    pass


class TabbedPanelDemo(TabbedPanel):
    pass


# Screen manager
sm = ScreenManager()
# sm = ScreenManager(transition=NoTransition())
# sm = ScreenManager(transition=FadeTransition())
sm = ScreenManager(transition=SlideTransition())

s01 = MainScreen(name='home')
# s01.add_widget(TabbedPanelDemo())

# el inspector aun no se bien donde ponerlo para que salga entero:
inspector.create_inspector(Window, s01)

s02 = PreferencesScreen(name='screen2')


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
    # posicion de la ventana:
    Window.top = 200
    Window.left = 350
    # pongo este color por si usas transiciones que quede bien:
    # color de background donde no hay screens:
    Window.clearcolor = (66/255.0, 66/255.0, 66/255.0, 1)
    app.run()
