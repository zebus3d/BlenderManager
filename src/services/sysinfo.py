class SystemInfo():

    def __init__(self, os=None, arch=None):
        self._os = os
        self._arch = arch

    @property
    def os(self):
        return self._os

    @os.setter
    def os(self, os):
        if not isinstance(os, str):
            raise ValueError('os {} is not type str'.format(os))
        self._os = os

    @property
    def arch(self):
        return self._arch

    @arch.setter
    def arch(self, arch):
        if not isinstance(arch, str):
            raise ValueError('arch {} is not type str'.format(arch))
        self._arch = arch
