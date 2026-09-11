"""Compatibility imports; implementation lives in hardware.ratbag."""
from .hardware.ratbag import RatbagClient, RatbagDevice, RatbagError, RatbagResolution

__all__ = ["RatbagClient", "RatbagDevice", "RatbagError", "RatbagResolution"]
