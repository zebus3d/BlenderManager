import configparser

# Nuestra libreria para leer/escribir en settings.ini
sf = "settings.ini"

class ReaderWritterSettigns():
    # constructor:
    def __init__(self):
        self._Config = configparser.ConfigParser()
        self._sections = self._Config.sections()

    # por ahora no necesitaremos acceder a Config ni sections 
    # desde fuera por eso comento los getters y setters.
    
    # getters y setters:
    # @property
    # def config(self):
    #     return self._Config

    # @config.setter
    # def set_config(self, config):
    #     self._Config = config
    
    # @property
    # def sections(self):
    #     return self._sections

    # @sections.setter
    # def set_sections(self, sections):
    #     self._sections = sections


    # metodos:
    def reader(self, section, option):
        self._Config.read(sf)
        print(self._Config.get(section, option))