from kivy.app import App
from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition, NoTransition, SlideTransition
from kivy.uix.tabbedpanel import TabbedPanel
from kivy.core.window import Window
import platform

# Para el inspector:
from kivy.modules import inspector

Builder.load_file('views/gui.kv')


class MainScreen(Screen):
    def set_platform_name(self) -> str:
        os_name = platform.system()
        if os_name == "Linux":
            os_name = "GNU/Linux"
        elif os_name == "Windows":
            os_name = "Windows"
        elif os_name == "Darwin":
            os_name = "Mac"
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
# Effectos de transicion:
# sm = ScreenManager(transition=NoTransition())
# sm = ScreenManager(transition=FadeTransition())
sm = ScreenManager(transition=SlideTransition())

# Inspector:
# Para mostrar el inspector hay que pulsar ctrl + e
# Si seleccionas un item dale al boton grande (a la izquierda del boton x ) para expandir sus propiedades:
inspector.create_inspector(Window, sm)


s01 = MainScreen(name='home')
# s01.add_widget(TabbedPanelDemo())

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
    # posicion de la ventana ( no consigo centrarla correctamente y pongo valores a manopla):
    Window.top = 200
    Window.left = 350
    # pongo este color por si usas transiciones que queden bien:
    # el color de background donde no ocupa por completo un screen:
    Window.clearcolor = (66/255.0, 66/255.0, 66/255.0, 1)
    app.run()
