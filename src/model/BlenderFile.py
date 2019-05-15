class BlenderFile:

    def __init__(self, name):

        self.name = name
        self.version = ""
        self.builds = ["stable"]

    def addBuild(self, build):

        self.builds.append(build)