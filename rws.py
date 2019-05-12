import configparser

# Nuestra libreria para leer/escribir en settings.ini
sf = "settings.ini"

class ReaderWritterSettigns():
    # constructor:
    def __init__(self):
        self._Config = configparser.ConfigParser()
        self._sections = self._Config.sections()
        self._Config.read(sf)


    # metodos:
    def reader(self, section, option):
        print(self._Config.get(section, option))