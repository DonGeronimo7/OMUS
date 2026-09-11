"""Hardware capability API; importing it does not import OpenRazer."""
from .base import HardwareBackend, HardwareError
from .registry import get_backend

__all__ = ["HardwareBackend", "HardwareError", "get_backend"]
