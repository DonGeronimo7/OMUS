"""Capability contract. Backends translate library failures to HardwareError.

Empty value lists mean enumeration is unavailable, not a guessed range.
Unsupported reads return None/[]; unsupported writes raise HardwareError.
Instances are scoped to one selection and must not guess ambiguous identities.
"""
from abc import ABC, abstractmethod
import threading
from typing import Callable
from ..discovery import MouseDevice


class HardwareError(RuntimeError):
    """Hardware operation failed; software remapping can continue."""


class HardwareBackend(ABC):
    name = "Hardware"

    @abstractmethod
    def supports_device(self, device: MouseDevice) -> bool:
        """Probe and bind a confidently matched physical device."""

    def get_device_name(self, device: MouseDevice) -> str | None:
        return device.name

    def supports_dpi(self, device: MouseDevice) -> bool:
        return False

    def get_dpi(self, device: MouseDevice) -> int | tuple[int, int] | None:
        return None

    def supports_dpi_monitoring(self, device: MouseDevice) -> bool:
        """Return whether repeated current-DPI reads are supported."""
        return False

    def supports_dpi_events(self, device: MouseDevice) -> bool:
        return False

    def watch_dpi_events(self, device: MouseDevice, callback: Callable[[int], None],
                         shutdown_event: threading.Event) -> None:
        raise HardwareError(f"{self.name}: DPI events are unsupported")

    def get_dpi_values(self, device: MouseDevice) -> list[int]:
        return []

    def set_dpi(self, device: MouseDevice, dpi: int) -> None:
        raise HardwareError(f"{self.name}: DPI is unsupported")

    def supports_dpi_stages(self, device: MouseDevice) -> bool:
        return False

    def apply_dpi_stages(self, device: MouseDevice, stages: list[int], active_dpi: int) -> int | None:
        """Return selected slot, or None if the active DPI could not be placed."""
        return None

    def supports_polling_rate(self, device: MouseDevice) -> bool:
        return False

    def get_polling_rate(self, device: MouseDevice) -> int | None:
        return None

    def get_polling_rates(self, device: MouseDevice) -> list[int]:
        return []

    def set_polling_rate(self, device: MouseDevice, hz: int) -> None:
        raise HardwareError(f"{self.name}: polling rate is unsupported")
