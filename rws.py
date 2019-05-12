import configparser

# Nuestra libreria para leer/escribir las opciones
sf = "options.cfg"

class ReaderWritterSettigns():
    # constructor:
    def __init__(self):
        self._config = configparser.ConfigParser()
        self._sections = self._config.sections()
        self._config.read(sf)

    # metodos:
    def reader(self, section, option):
        print(self._config.get(section, option))

    def add_section(self, new_section):
        self._config.add_section(new_section)

    def add_option(self, section, option, value):
        self._config.set(section, option, value)
    
    def write_options(self):
        with open(sf, 'w') as configfile:
            self._config.write(configfile)