"""Libratbag adapter for hardware DPI and polling configuration."""

from __future__ import annotations

import re
import shutil
import subprocess
import threading
from dataclasses import dataclass
from typing import Callable

from ..discovery import MouseDevice
from ..hidpp import (ADJUSTABLE_DPI_FEATURE_ID, HidppDevice,
                     dpi_decoder_profile, load_cached_hidpp_device,
                     watch_dpi_events)
from .base import HardwareBackend, HardwareError
import logging


class RatbagError(HardwareError):
    """Raised when Libratbag cannot service a request."""


@dataclass(frozen=True)
class RatbagDevice:
    alias: str
    name: str
    model: str = ""


@dataclass(frozen=True)
class RatbagResolution:
    index: int
    dpi: int | None
    disabled: bool
    active: bool
    default: bool


class RatbagClient:
    """Use ratbagctl so the rest of the application stays independent of HID++ details."""

    def __init__(self, binary: str = "ratbagctl") -> None:
        self.binary = shutil.which(binary)

    @property
    def available(self) -> bool:
        return self.binary is not None

    def _run(self, *args: str) -> str:
        if not self.binary:
            raise RatbagError(
                "ratbagctl is unavailable. Install libratbag-ratbagd and ensure ratbagd is running."
            )
        try:
            result = subprocess.run(
                [self.binary, *args],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RatbagError(f"Could not execute ratbagctl: {exc}") from exc
        if result.returncode != 0:
            error = result.stderr.strip() or result.stdout.strip() or "unknown ratbagctl error"
            raise RatbagError(error)
        return result.stdout.strip()

    def list_devices(self) -> list[RatbagDevice]:
        output = self._run("list")
        devices: list[RatbagDevice] = []
        for line in output.splitlines():
            # ratbagctl list normally prints: alias:   Human-readable name
            # Some versions/builds have used a hyphen separator, so accept both.
            match = re.match(r"^\s*([^\s:]+)\s*:\s+(.+)$", line)
            if not match:
                match = re.match(r"^\s*([^\s]+)\s+-\s+(.+)$", line)
            if match:
                devices.append(RatbagDevice(match.group(1), match.group(2).strip()))
        return devices

    def info(self, device: RatbagDevice | str) -> str:
        alias = device.alias if isinstance(device, RatbagDevice) else device
        return self._run(alias, "info")

    def _model_for(self, device: RatbagDevice) -> str:
        info = self.info(device)
        for line in info.splitlines():
            if line.strip().startswith("Model:"):
                return line.split(":", 1)[1].strip()
        return ""

    def find_for_mouse(self, mouse: MouseDevice) -> RatbagDevice | None:
        """Return the Libratbag device with the same USB vendor/product identity.

        Device names are deliberately *not* used as a fallback. Linux input device
        names can be generic or misleading, while the Libratbag Model field contains
        the USB identity (for example ``usb:046d:4074:0`` for a Logitech G305).
        Matching only on VID/PID prevents accidentally applying settings to the wrong
        mouse when several Logitech devices are present.
        """
        if mouse.vendor is None or mouse.product is None:
            return None

        expected_prefix = f"usb:{mouse.vendor:04x}:{mouse.product:04x}:".lower()
        matches = []
        for device in self.list_devices():
            model = self._model_for(device)
            if model.lower().startswith(expected_prefix):
                matches.append(RatbagDevice(device.alias, device.name, model))
        if len(matches) > 1:
            raise RatbagError("Ambiguous Libratbag USB VID/PID; refusing hardware writes")
        return matches[0] if matches else None

    @staticmethod
    def _numbers(text: str) -> list[int]:
        values: list[int] = []
        for token in re.findall(r"\b\d+(?:\.\d+)?\b", text):
            value = int(float(token))
            if value > 0 and value not in values:
                values.append(value)
        return values

    def get_dpi_values(self, device: RatbagDevice) -> list[int]:
        return self._numbers(self._run(device.alias, "dpi", "get-all"))

    def get_dpi(self, device: RatbagDevice) -> int | None:
        values = self._numbers(self._run(device.alias, "dpi", "get"))
        return values[0] if values else None

    def set_dpi(self, device: RatbagDevice, dpi: int) -> None:
        if dpi <= 0:
            raise ValueError("DPI must be greater than zero")
        self._run(device.alias, "dpi", "set", str(dpi))

    def get_resolutions(self, device: RatbagDevice) -> list[RatbagResolution]:
        """Parse the resolution slots shown by ratbagctl info."""
        info = self.info(device)
        resolutions: list[RatbagResolution] = []
        in_resolutions = False
        for line in info.splitlines():
            if "Resolutions:" in line:
                in_resolutions = True
                continue
            if in_resolutions and line.strip().startswith("Button:"):
                break
            if not in_resolutions:
                continue
            match = re.match(
                r"^\s*(\d+):\s*(\d+)dpi(?:\s+(.*))?$",
                line,
                flags=re.IGNORECASE,
            )
            if not match:
                continue
            flags = (match.group(3) or "").lower()
            resolutions.append(
                RatbagResolution(
                    index=int(match.group(1)),
                    dpi=int(match.group(2)),
                    disabled="disabled" in flags,
                    active="active" in flags,
                    default="default" in flags,
                )
            )
        return resolutions

    def set_resolution_dpi(self, device: RatbagDevice, index: int, dpi: int) -> None:
        if index < 0 or dpi <= 0:
            raise ValueError("Resolution index and DPI must be positive")
        self._run(device.alias, "resolution", str(index), "dpi", "set", str(dpi))

    def set_active_resolution(self, device: RatbagDevice, index: int) -> None:
        if index < 0:
            raise ValueError("Resolution index must not be negative")
        self._run(device.alias, "resolution", "active", "set", str(index))

    def set_default_resolution(self, device: RatbagDevice, index: int) -> None:
        if index < 0:
            raise ValueError("Resolution index must not be negative")
        self._run(device.alias, "resolution", "default", "set", str(index))

    def apply_dpi_stages(self, device: RatbagDevice, stages: list[int], active_dpi: int) -> int | None:
        """Write desired DPI stages into available resolution slots and select the active stage.

        Only existing, non-disabled slots are changed. Individual slots that reject a value
        are skipped so one unsupported preferred DPI does not prevent the remaining stages or
        polling-rate configuration from being applied. The return value is the selected
        resolution index, or None if the requested active DPI could not be placed.
        """
        if not stages:
            return None
        if any(dpi <= 0 for dpi in stages):
            raise ValueError("All DPI stages must be greater than zero")

        resolutions = [r for r in self.get_resolutions(device) if not r.disabled]
        resolutions.sort(key=lambda r: r.index)
        if not resolutions:
            return None

        active_index: int | None = None
        for resolution, dpi in zip(resolutions, stages, strict=False):
            try:
                self.set_resolution_dpi(device, resolution.index, dpi)
            except RatbagError as exc:
                logging.getLogger(__name__).warning("Libratbag resolution %s rejected %s DPI: %s", resolution.index, dpi, exc)
                continue
            if dpi == active_dpi and active_index is None:
                active_index = resolution.index

        if active_index is None:
            return None
        self.set_active_resolution(device, active_index)
        self.set_default_resolution(device, active_index)
        return active_index

    def get_report_rates(self, device: RatbagDevice) -> list[int]:
        """Return polling/report rates, normalized to Hz."""
        # ratbagctl currently describes rates as Hz in user-facing output.
        return self._numbers(self._run(device.alias, "rate", "get-all"))

    def get_report_rate(self, device: RatbagDevice) -> int | None:
        values = self._numbers(self._run(device.alias, "rate", "get"))
        return values[0] if values else None

    def set_report_rate(self, device: RatbagDevice, rate_hz: int) -> None:
        if rate_hz <= 0:
            raise ValueError("Report rate must be greater than zero")
        self._run(device.alias, "rate", "set", str(rate_hz))


class RatbagBackend(HardwareBackend):
    """Keep the existing ratbagctl stage semantics behind the capability contract."""
    name = "Libratbag"

    def __init__(self, client: RatbagClient | None = None,
                 hidpp_loader: Callable[..., HidppDevice | None] = load_cached_hidpp_device) -> None:
        self.client = client if client is not None else RatbagClient()
        self._devices: dict[MouseDevice, RatbagDevice] = {}
        self._hidpp_devices: dict[MouseDevice, HidppDevice | None] = {}
        self._hidpp_loader = hidpp_loader

    def supports_device(self, device: MouseDevice) -> bool:
        if device in self._devices:
            return True
        if not self.client.available:
            return False
        match = self.client.find_for_mouse(device)
        if match is None:
            return False
        self._devices[device] = match
        if device not in self._hidpp_devices and device.vendor is not None and device.product is not None:
            # Normal startup is cache-only: ratbagd owns active HID++ traffic.
            self._hidpp_devices[device] = self._hidpp_loader(
                device.vendor, device.product, device.phys
            )
        return True

    def _device(self, device: MouseDevice) -> RatbagDevice:
        if not self.supports_device(device):
            raise RatbagError("No matching Libratbag device")
        return self._devices[device]

    def get_device_name(self, device: MouseDevice) -> str | None:
        ratbag = self._device(device)
        hidpp = self._hidpp_devices.get(device)
        if hidpp is not None and hidpp.name:
            return hidpp.name
        return ratbag.name or device.name

    def supports_dpi(self, device: MouseDevice) -> bool:
        return self.get_dpi(device) is not None

    def get_dpi(self, device: MouseDevice) -> int | None:
        return self.client.get_dpi(self._device(device))

    def supports_dpi_monitoring(self, device: MouseDevice) -> bool:
        # Firmware-owned active-resolution changes are not reliably observable
        # through ratbagctl (notably on the G305), so do not spawn a poller.
        return False

    def supports_dpi_events(self, device: MouseDevice) -> bool:
        if not self.supports_device(device):
            return False
        hidpp = self._hidpp_devices.get(device)
        supported = hidpp is not None and dpi_decoder_profile(hidpp) is not None
        if hidpp is None and device.vendor == 0x046D:
            logging.getLogger(__name__).info(
                "Logitech HID++ capabilities have not been discovered for this device. "
                "Run mouse-control debug-dpi to enable supported passive monitoring."
            )
        if (hidpp is not None and
                hidpp.feature(ADJUSTABLE_DPI_FEATURE_ID) is not None and not supported):
            logging.getLogger(__name__).info(
                "Adjustable DPI is present, but its event format is not validated; notifications disabled"
            )
        return supported

    def watch_dpi_events(self, device: MouseDevice, callback: Callable[[int], None],
                         shutdown_event: threading.Event) -> None:
        self._device(device)
        hidpp = self._hidpp_devices.get(device)
        profile = dpi_decoder_profile(hidpp) if hidpp is not None else None
        if hidpp is None or profile is None:
            raise RatbagError("Passive HID++ DPI events are not validated for this device")
        watch_dpi_events(hidpp, profile, callback, shutdown_event)

    def get_dpi_values(self, device: MouseDevice) -> list[int]:
        return self.client.get_dpi_values(self._device(device))

    def set_dpi(self, device: MouseDevice, dpi: int) -> None:
        if dpi <= 0:
            raise RatbagError("DPI must be greater than zero")
        self.client.set_dpi(self._device(device), dpi)

    def supports_dpi_stages(self, device: MouseDevice) -> bool:
        return any(not r.disabled for r in self.client.get_resolutions(self._device(device)))

    def apply_dpi_stages(self, device: MouseDevice, stages: list[int], active_dpi: int) -> int | None:
        if any(dpi <= 0 for dpi in stages):
            raise RatbagError("All DPI stages must be greater than zero")
        return self.client.apply_dpi_stages(self._device(device), stages, active_dpi)

    def supports_polling_rate(self, device: MouseDevice) -> bool:
        return self.get_polling_rate(device) is not None

    def get_polling_rate(self, device: MouseDevice) -> int | None:
        return self.client.get_report_rate(self._device(device))

    def get_polling_rates(self, device: MouseDevice) -> list[int]:
        return self.client.get_report_rates(self._device(device))

    def set_polling_rate(self, device: MouseDevice, hz: int) -> None:
        if hz <= 0:
            raise RatbagError("Polling rate must be greater than zero")
        self.client.set_report_rate(self._device(device), hz)
