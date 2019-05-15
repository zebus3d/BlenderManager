# Config.set Debe utilizarse antes de importar cualquier otro módulo Kivy
from kivy.config import Config
Config.set('graphics', 'width', '600')
Config.set('graphics', 'height', '400')

from kivy.app import App
from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition, NoTransition, SlideTransition
# from kivy.core.window import Window

Builder.load_file('views/gui.kv')

# Declare both screens
class Screen01(Screen):
    pass

class Screen02(Screen):
    pass

# Create the screen manager
# NoTransition - switches screens instantly with no animation
# SlideTransition - slide the screen in/out, from any direction
# CardTransition - new screen slides on the previous or the old one slides off the new one depending on the mode
# SwapTransition - implementation of the iOS swap transition
# FadeTransition - shader to fade the screen in/out
# WipeTransition - shader to wipe the screens from right to left
# FallOutTransition - shader where the old screen ‘falls’ and becomes transparent, revealing the new one behind it.
# RiseInTransition - shader where the new screen rises from the screen centre while fading from transparent to opaque.
sm = ScreenManager()
# sm = ScreenManager(transition=NoTransition())
# sm = ScreenManager(transition=FadeTransition())
sm = ScreenManager(transition=SlideTransition())

sm.add_widget(Screen01(name='home'))
sm.add_widget(Screen02(name='screen2'))

class TestApp(App):
    def build(self):
        return sm

if __name__ == '__main__':
    app = TestApp()
    # Window.size = (1080/4, 1920/4)
    app.run()