import platform


class OsDetect():
    def __init__(self, os=None, arch=None):
        self._os = os
        self._arch = arch

    @property
    def os(self):
        return self._os

    @os.setter
    def set_os(self, os):
        if not isinstance(os, str):
            raise ValueError( 'os {} is not type str'.format(os) )
        self._os = os

    @property
    def arch(self):
        return self._arch

    @arch.setter
    def set_arch(self, arch):
        if not isinstance(arch, str):
            raise ValueError( 'arch {} is not type str'.format(arch) )
        self._arch = arch

    def detect(self):
        os_name = platform.system()
        os_arch = platform.architecture()

        if os_name == "Linux":
            self._os = "GNU/Linux"
        elif os_name == "Windows":
            self._os = "Windows"
        elif os_name == "Darwin":
            self._os = "Mac"
        else:
            print("unsupported system!")
            self._os = None

        if os_arch[0] == "64bit":
            self._arch = '64'
        elif os_arch[0] == "32bit":
            self._arch = '32'
        else:
            print("unknown architecture!")
            self._arch = None
