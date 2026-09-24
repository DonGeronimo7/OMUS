# SPDX-License-Identifier: AGPL-3.0-or-later
"""Universal hardware entry point.

Callers always receive Automatic Discovery.  Proven vendor/protocol backends are
internal adapters owned by Discovery rather than competing top-level backends.
"""
from collections.abc import Callable, Iterable

from .base import HardwareBackend
from .discovery_backend import DiscoveryBackend
from .native_hid import NativeHidBackend
from .native_razer import NativeRazerBackend
from ..discovery import MouseDevice

PROTOCOL_ADAPTER_FACTORIES = (NativeHidBackend, NativeRazerBackend)


def get_backend(
    device: MouseDevice,
    factories: Iterable[Callable[[], HardwareBackend]] | None = None,
    *,
    log_failures: bool = True,
) -> HardwareBackend:
    """Return the universal Discovery backend for every mouse.

    ``factories`` now supplies proven protocol adapters *to* Discovery.  It no
    longer changes the backend type returned to callers.  Unknown hardware gets
    the same Discovery surface, with safe evdev/remapping behavior and any
    physically learned read-side capabilities that can be rebound.
    """
    backend = DiscoveryBackend(
        protocol_factories=PROTOCOL_ADAPTER_FACTORIES if factories is None else tuple(factories),
        log_protocol_failures=log_failures,
    )
    backend.supports_device(device)
    return backend
