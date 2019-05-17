from kivy.app import App
from kivy.uix.dropdown import DropDown
from kivy.uix.boxlayout import BoxLayout
from kivy.lang import Builder

Builder.load_file('test_ui.kv')

class CustomDropDown(BoxLayout):
    pass

class MainApp(App):
    def build(self):
        return CustomDropDown()

if __name__=='__main__':
    MainApp().run()