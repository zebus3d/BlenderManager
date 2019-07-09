import platform
from .sysinfo import SystemInfo


class OSDetector():

    def detect(self):
        sysi = SystemInfo()

        os_name = platform.system()
        os_arch = platform.architecture()

        if os_name == "Linux":
            sysi.os = "GNU/Linux"
        elif os_name == "Windows":
            sysi.os = "Windows"
        elif os_name == "Darwin":
            sysi.os = "Mac"
        else:
            print("unsupported system!")
            sysi.os = None

        if os_arch[0] == "64bit":
            sysi.arch = '64'
        elif os_arch[0] == "32bit":
            sysi.arch = '32'
        else:
            print("unknown architecture!")
            sysi.arch = None

        return sysi
