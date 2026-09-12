"""Hardware capability API; importing it does not import OpenRazer."""
from .base import HardwareBackend, HardwareError
from .capabilities import (DpiCapabilities, DpiRange, DpiState,
                           HardwareCapabilities, ReportRateCapabilities)
from .registry import get_backend

__all__ = ["DpiCapabilities", "DpiRange", "DpiState", "HardwareBackend",
           "HardwareCapabilities", "HardwareError", "ReportRateCapabilities",
           "get_backend"]
