import sys
import platform
from typing import NamedTuple

class OSInfo(NamedTuple):
    os: str
    arch: str

def detect() -> OSInfo:
    """Returns the detected operating system and architecture."""
    if sys.platform.startswith('win32'):
        return OSInfo(os='Windows', arch=platform.architecture()[0])
    elif sys.platform.startswith('linux'):
        return OSInfo(os='Linux', arch=platform.architecture()[0])
    elif sys.platform.startswith('darwin'):
        return OSInfo(os='MacOS', arch=platform.architecture()[0])
    else:
        return OSInfo(os=None, arch=None)
