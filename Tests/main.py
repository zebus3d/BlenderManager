from kivy.app import App
from kivy.core.window import Window

from kivy.uix.dropdown import DropDown
from kivy.uix.button import Button

from kivy.lang import Builder

Builder.load_file('test_ui.kv')

# test

class CustomDropDown(DropDown):
    pass

class MainApp(App):
    def build(self):
        
        # self.dropdown = CustomDropDown()
        # mainbutton = Button(text='Hello', size_hint=(None, None))
        # mainbutton.bind(on_release=self.dropdown.open)
        # self.dropdown.bind(on_select=lambda instance, x: setattr(mainbutton, 'text', x))
        
        self.dropdown = DropDown()

        for index in range(10):
            btn = Button(text='Value %d' % index, size_hint_y=None, height=30)
            btn.bind(on_release=lambda btn: self.dropdown.select(btn.text))
            self.dropdown.add_widget(btn)

        # create a big main button
        mainbutton = Button(text='Hello', size_hint=('1dp', None), pos=(0, 30), height=30)
        mainbutton.bind(on_release=self.dropdown.open)
        self.dropdown.bind(on_select=lambda instance, x: setattr(mainbutton, 'text', x))

        return mainbutton

if __name__=='__main__':
    app = MainApp()
    Window.size = (200, 500)
    app.run()
