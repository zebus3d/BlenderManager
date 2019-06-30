class BlenderFile:

    def __init__(self, name):
        self.name = name
        self.version = ""
        self.builds = ["stable"]

    def add_build(self, build):
        self.builds.append(build)
