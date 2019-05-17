from kivy.app import App
from kivy.uix.dropdown import DropDown
from kivy.uix.button import Button

from kivy.lang import Builder

Builder.load_file('test_ui.kv')


class CustomDropDown(DropDown):
    pass

class MainApp(App):
    def build(self):
        
        # dropdown = CustomDropDown()
        # mainbutton = Button(text='Hello', size_hint=(None, None))
        # mainbutton.bind(on_release=dropdown.open)
        # dropdown.bind(on_select=lambda instance, x: setattr(mainbutton, 'text', x))
        
        dropdown = DropDown()

        for index in range(10):
            btn = Button(text='Value %d' % index, size_hint_y=None, height=44)
            btn.bind(on_release=lambda btn: dropdown.select(btn.text))
            dropdown.add_widget(btn)

        # create a big main button
        mainbutton = Button(text='Hello', size_hint=('1dp', None))
        mainbutton.bind(on_release=dropdown.open)
        dropdown.bind(on_select=lambda instance, x: setattr(mainbutton, 'text', x))

        return mainbutton

if __name__=='__main__':
    MainApp().run()