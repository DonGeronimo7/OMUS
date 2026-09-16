"""Ordered factories with Automatic Discovery as the universal safe fallback."""
import logging
from collections.abc import Callable, Iterable
from .base import HardwareBackend, HardwareError
from .discovery_backend import DiscoveryBackend
from .openrazer import OpenRazerBackend
from .native_hid import NativeHidBackend
from ..discovery import MouseDevice

BACKEND_FACTORIES = (NativeHidBackend, OpenRazerBackend)


def get_backend(device: MouseDevice, factories: Iterable[Callable[[], HardwareBackend]] | None = None,
                *, log_failures: bool = True) -> HardwareBackend:
    """Return the strongest proven backend, then fall back to Discovery.

    Native/proven protocol implementations keep priority because they may own
    validated read/write transactions.  Anything not claimed by them enters the
    Automatic Discovery path instead of the old inert GenericBackend.  Discovery
    may reuse physically calibrated read-side evidence, but it never guesses or
    promotes unknown HID writes.
    """
    for factory in BACKEND_FACTORIES if factories is None else factories:
        backend = None
        try:
            backend = factory()
            if backend.supports_device(device):
                return backend
        except (HardwareError, OSError) as exc:
            if log_failures:
                logging.getLogger(__name__).warning("Hardware discovery failed: %s", exc)
        if backend is not None:
            close = getattr(backend, "close", None)
            if close:
                close()

    backend = DiscoveryBackend()
    # DiscoveryBackend is intentionally fail-soft: passive discovery can lose
    # hardware evidence without ever disabling normal evdev/uinput remapping.
    backend.supports_device(device)
    return backend
