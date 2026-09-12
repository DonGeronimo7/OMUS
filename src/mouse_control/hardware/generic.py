"""Safe fallback: generic HID identity plus evdev/uinput remapping.

The HID mouse specification does not define DPI or polling-rate controls, so
this backend never guesses vendor reports.  Native protocol backends are
selected before this fallback as they are added.
"""
from .base import HardwareBackend
from ..discovery import MouseDevice


class GenericBackend(HardwareBackend):
    name = "Generic HID / evdev"

    def supports_device(self, device: MouseDevice) -> bool:
        return True
