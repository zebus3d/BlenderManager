from kivy.uix.screenmanager import Screen
from services.osdetector import detect

class MainScreen(Screen):
    def set_platform_name(self) -> str:
        print("auto detect os: ", self.detect_os())
        return self.detect_os() or "current system not supported"

    def set_architecture(self) -> str:
        print("auto detect architecture: ", self.detect_arch())
        return self.detect_arch() or "err"

    def print_current(self, current_value):
        print(current_value)

    def detect_os(self) -> str:
        return detect().os
    
    def detect_arch(self) -> str:
        return detect().arch
