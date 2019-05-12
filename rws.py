import configparser

# settings file:
sf = "settings.ini"

class ReaderWritterSettigns():
    def __init__(self, **kwargs):
        super(ReaderWritterSettigns, self).__init__(**kwargs)

    def reader(self, section, option):
        Config = configparser.ConfigParser()
        Config.read(sf)
        sections = Config.sections() 
        print(Config.get(section, option))