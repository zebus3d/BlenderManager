# Config.set Debe utilizarse antes de importar cualquier otro módulo Kivy
from kivy.config import Config
Config.set('graphics', 'width', '600')
Config.set('graphics', 'height', '400')

from kivy.app import App
from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition, NoTransition
# from kivy.core.window import Window

Builder.load_file('gui.kv')

# Declare both screens
class Screen01(Screen):
    pass

class Screen02(Screen):
    pass

# Create the screen manager
# sm = ScreenManager()
# sm = ScreenManager(transition=NoTransition())
sm = ScreenManager(transition=FadeTransition())
sm.add_widget(Screen01(name='home'))
sm.add_widget(Screen02(name='screen2'))

class TestApp(App):
    def build(self):
        return sm

if __name__ == '__main__':
    app = TestApp()
    # Window.size = (1080/4, 1920/4)
    app.run()