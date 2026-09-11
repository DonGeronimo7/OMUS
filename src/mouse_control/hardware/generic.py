"""Fallback with no hardware writes. evdev/uinput remains independent."""
from .base import HardwareBackend
from ..discovery import MouseDevice


class GenericBackend(HardwareBackend):
    name = "Generic"

    def supports_device(self, device: MouseDevice) -> bool:
        return True
