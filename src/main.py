from kivy.app import App
from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition, NoTransition, SlideTransition
from kivy.core.window import Window


Builder.load_file('views/gui.kv')

# Declare both screens para que las reconozca el gui.kv
class Screen01(Screen):
    pass

class Screen02(Screen):
    pass

# Create the screen manager
sm = ScreenManager()
# sm = ScreenManager(transition=NoTransition())
# sm = ScreenManager(transition=FadeTransition())
sm = ScreenManager(transition=SlideTransition())

# agregamos al screen manager los screens:
sm.add_widget(Screen01(name='home'))
sm.add_widget(Screen02(name='screen2'))

class TestApp(App):
    def build(self):
        return sm

if __name__ == '__main__':
    app = TestApp()
    Window.size = (600, 400)
    app.run()