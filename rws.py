import configparser

# settings file:
sf = "settings.ini"

class ReaderWritterSettigns():
    def __init__(self, **kwargs):
        super(ReaderWritterSettigns, self).__init__(**kwargs)

    def reader(self):
        Config = configparser.ConfigParser()
        Config.read(sf)
        # print(Config.sections())
        BuilderS = 'BuilderServer'
        print(Config.get('defaults', BuilderS))