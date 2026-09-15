"""Protocol-neutral native HID backend."""

from __future__ import annotations

from collections.abc import Callable
import logging

from ..discovery import MouseDevice
from ..generic_hid import discover_hid_devices
from ..hid_session import HidSession
from ..hidpp import HidppError, LOGITECH_VENDOR_ID
from ..hidpp_driver import (HOST_MODE, ONBOARD_MODE, Hidpp20Driver,
                            connect_hidpp20)
from .base import HardwareBackend, HardwareError
from .capabilities import BatteryState, DpiState, HardwareCapabilities

LOG = logging.getLogger(__name__)

# Host-mode takeover changes who owns hardware behavior (notably DPI cycling).
# Keep knowledge of validated identities separate from ordinary capability
# reporting so setup can preserve native/onboard behavior by default.
HOST_MODE_TRANSITION_ALLOWLIST = frozenset({(3, 0x046D, 0x4074)})


class NativeHidBackend(HardwareBackend):
    name = "Native HID"

    def __init__(self, *, discovery=discover_hid_devices,
                 session_factory=HidSession,
                 connectors: tuple[Callable[[HidSession], Hidpp20Driver], ...] =
                 (connect_hidpp20,)) -> None:
        self._discovery = discovery
        self._session_factory = session_factory
        self._connectors = connectors
        self._bound: dict[MouseDevice, tuple[HidSession, Hidpp20Driver]] = {}

    def supports_device(self, device: MouseDevice) -> bool:
        if device in self._bound:
            return True
        if device.vendor != LOGITECH_VENDOR_ID or device.product is None:
            return False
        candidates: list[tuple[HidSession, Hidpp20Driver]] = []
        for interface in self._discovery(device):
            try:
                session = self._session_factory(interface.path)
            except OSError:
                continue
            try:
                for connector in self._connectors:
                    try:
                        candidates.append((session, connector(session)))
                        break
                    except HidppError:
                        continue
                else:
                    session.close()
            except Exception:
                session.close()
                raise
        if len(candidates) > 1:
            for session, _driver in candidates:
                session.close()
            raise HardwareError("Native HID: multiple interfaces claimed the protocol; refusing ambiguous writes")
        if not candidates:
            return False
        self._bound[device] = candidates[0]
        return True

    def _driver(self, device: MouseDevice) -> Hidpp20Driver:
        bound = self._bound.get(device)
        if bound is not None and getattr(bound[0], "closed", False):
            bound[0].close()
            del self._bound[device]
        if not self.supports_device(device):
            raise HardwareError("Native HID: no validated protocol driver")
        return self._bound[device][1]

    def get_capabilities(self, device: MouseDevice) -> HardwareCapabilities:
        return self._driver(device).capabilities

    def get_device_name(self, device: MouseDevice) -> str | None:
        return self._driver(device).name or device.name

    def supports_dpi(self, device: MouseDevice) -> bool:
        caps = self.get_capabilities(device).dpi
        return caps.readable and caps.writable

    def supports_battery(self, device: MouseDevice) -> bool:
        return self.get_capabilities(device).battery.readable

    def get_battery_state(self, device: MouseDevice) -> BatteryState | None:
        try:
            return self._driver(device).get_battery_state()
        except HidppError as exc:
            raise HardwareError(f"Native HID: {exc}") from exc

    def supports_dpi_monitoring(self, device: MouseDevice) -> bool:
        return self.get_capabilities(device).dpi.readable

    def supports_dpi_events(self, device: MouseDevice) -> bool:
        return self.get_capabilities(device).dpi.events

    def get_dpi_state(self, device: MouseDevice) -> DpiState | None:
        try:
            return self._driver(device).get_dpi_state()
        except HidppError as exc:
            raise HardwareError(f"Native HID: {exc}") from exc

    def get_dpi(self, device: MouseDevice) -> int | tuple[int, int] | None:
        state = self.get_dpi_state(device)
        return state.display_value if state else None

    def get_dpi_values(self, device: MouseDevice) -> list[int]:
        caps = self.get_capabilities(device).dpi
        values = list(caps.values or ())
        for item in caps.ranges or ():
            values.extend(range(item.minimum, item.maximum + 1, item.step))
        return sorted(set(values))

    def set_dpi(self, device: MouseDevice, dpi: int) -> DpiState:
        try:
            return self._driver(device).set_dpi(dpi)
        except HidppError as exc:
            raise HardwareError(f"Native HID: {exc}") from exc

    def supports_polling_rate(self, device: MouseDevice) -> bool:
        return self.get_capabilities(device).report_rate.readable

    def supports_polling_rate_writes(self, device: MouseDevice) -> bool:
        """Report whether a rate write is safe *without changing control mode*.

        An Onboard -> Host transition changes ownership of physical behavior,
        including the G305's native DPI-cycle handling.  Setup therefore must
        not advertise a write merely because mouse-control knows a validated
        way to take over Host mode.  Explicit takeover can be offered separately
        when the user intentionally remaps/replaces native behavior.
        """

        driver = self._driver(device)
        if not driver.capabilities.report_rate.writable:
            return False
        try:
            return driver.get_control_mode() == HOST_MODE
        except HidppError:
            return False

    @staticmethod
    def _may_enter_host_mode(device: MouseDevice) -> bool:
        """Whether an explicit future takeover is hardware-validated."""
        return (device.bustype, device.vendor, device.product) in HOST_MODE_TRANSITION_ALLOWLIST

    def get_polling_rates(self, device: MouseDevice) -> list[int]:
        return list(self.get_capabilities(device).report_rate.values or ())

    def get_polling_rate(self, device: MouseDevice) -> int | None:
        try:
            return self._driver(device).get_report_rate()
        except HidppError as exc:
            raise HardwareError(f"Native HID: {exc}") from exc

    def set_polling_rate(self, device: MouseDevice, hz: int) -> None:
        """Set report rate only when the device is already in Host mode.

        This method deliberately never performs an implicit Onboard -> Host
        transition.  Taking over Host mode changes native button/DPI behavior
        and therefore requires a separate explicit user action.
        """

        driver = self._driver(device)
        caps = driver.capabilities.report_rate
        if not caps.readable or not caps.writable or not caps.values or hz not in caps.values:
            raise HardwareError(f"Native HID: unsupported polling rate {hz} Hz")
        try:
            mode = driver.get_control_mode()
            if mode == ONBOARD_MODE:
                raise HardwareError(
                    "Native HID: polling-rate write requires explicit Host-mode takeover; "
                    "native onboard DPI behavior was preserved"
                )
            if mode != HOST_MODE:
                raise HardwareError(
                    f"Native HID: unsupported control mode 0x{mode:02x}"
                )
            driver.set_report_rate(hz)
        except HidppError as exc:
            raise HardwareError(f"Native HID: {exc}") from exc

    def watch_dpi_events(self, device: MouseDevice, callback,
                         shutdown_event, ready_callback=None) -> None:
        # The supervisor owns retries. A failed subscription must discard this
        # session and trigger fresh backend discovery instead of becoming sticky.
        self._driver(device).watch_dpi(callback, shutdown_event, ready_callback)

    def close(self) -> None:
        for session, _driver in self._bound.values():
            session.close()
        self._bound.clear()
