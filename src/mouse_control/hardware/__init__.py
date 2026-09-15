"""Hardware capability API; importing it does not import OpenRazer."""
from .base import HardwareBackend, HardwareError
from .capabilities import (BatteryCapabilities, BatteryState, DpiCapabilities,
                           DpiRange, DpiState, HardwareCapabilities, ReportRateCapabilities)
from .registry import get_backend
from .supervisor import DesiredHardwareState, HardwareSupervisor

__all__ = ["BatteryCapabilities", "BatteryState", "DpiCapabilities", "DpiRange", "DpiState", "HardwareBackend",
           "HardwareCapabilities", "HardwareError", "ReportRateCapabilities",
           "DesiredHardwareState", "HardwareSupervisor", "get_backend"]
