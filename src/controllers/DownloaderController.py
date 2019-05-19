from kivy.app import App
from kivy.core.window import Window

from kivy.uix.dropdown import DropDown
from kivy.uix.button import Button

import sys
sys.path.insert(0, 'src/model')
sys.path.insert(1, 'src/services')
sys.path.insert(2, 'src/views')

from BlenderFile import BlenderFile
from DownloaderService import DownloaderService

from kivy.lang import Builder

Builder.load_file('src/views/downloader_view.kv')


class DownloaderController(App):
    
    def build(self):

        self.versionDropDown = self.ids.versionDropDown
        self.downloaderService = DownloaderService()

        return

    def on_start(self):

        self.refreshDropDown()

    def refreshDropDown(self):

        self.versionDropDown.clear_widgets()

        blenderFiles = self.downloaderService.getAvaibleVersions()
        blenderFiles.sort(key=lambda x: x.version, reverse=True)

        for bFile in blenderFiles:
            btn = Button(text=bFile.name, size_hint_y=None, height=30)
            btn.bind(on_release=lambda btn: self.versionDropDown.select(btn.text))
            self.versionDropDown.add_widget(btn)

if __name__=='__main__':
    
    app = DownloaderController()
    Window.size = (600, 480)
    app.run()