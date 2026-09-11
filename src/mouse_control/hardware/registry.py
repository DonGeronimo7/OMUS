"""Ordered factories; register future backends here without changing callers."""
import logging
from collections.abc import Callable, Iterable
from .base import HardwareBackend, HardwareError
from .generic import GenericBackend
from .ratbag import RatbagBackend
from .openrazer import OpenRazerBackend
from ..discovery import MouseDevice

BACKEND_FACTORIES = (RatbagBackend, OpenRazerBackend)


def get_backend(device: MouseDevice, factories: Iterable[Callable[[], HardwareBackend]] | None = None) -> HardwareBackend:
    for factory in BACKEND_FACTORIES if factories is None else factories:
        try:
            backend = factory()
            if backend.supports_device(device):
                return backend
        except HardwareError as exc:
            logging.getLogger(__name__).warning("Hardware discovery failed: %s", exc)
    return GenericBackend()
