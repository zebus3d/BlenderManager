from kivy.app import App
from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition, NoTransition, SlideTransition
from kivy.core.window import Window
from kivy.uix.dropdown import DropDown
from kivy.uix.button import Button

Builder.load_file('views/gui.kv')


# Declare both screens para que las reconozca el gui.kv
class Screen01(Screen):
    pass


class Screen02(Screen):
    pass


class CustomDropDown(DropDown):
    pass


# Create the screen manager
sm = ScreenManager()
sm = ScreenManager(transition=NoTransition())
# sm = ScreenManager(transition=FadeTransition())
# sm = ScreenManager(transition=SlideTransition())

# agregamos al screen manager los screens:


s01 = Screen01(name='home')

cdd = CustomDropDown()
mainbutton = Button(text='SO', size_hint_y=None, size_hint_x=None, pos=(0, 0), height=30, width=200)
mainbutton.bind(on_release=cdd.open)
cdd.bind(on_select=lambda instance, x: setattr(mainbutton, 'text', x))

s01.add_widget(mainbutton)

sm.add_widget(s01)
sm.add_widget(Screen02(name='screen2'))


class TestApp(App):
    def build(self):
        return sm


if __name__ == '__main__':
    app = TestApp()
    Window.size = (600, 400)
    app.run()
