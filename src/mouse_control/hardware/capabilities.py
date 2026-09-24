# SPDX-License-Identifier: AGPL-3.0-or-later
"""Protocol-neutral hardware capabilities and state."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class DpiRange:
    minimum: int
    maximum: int
    step: int

    def contains(self, value: int) -> bool:
        return (self.minimum <= value <= self.maximum and
                (value - self.minimum) % self.step == 0)


@dataclass(frozen=True)
class DpiCapabilities:
    readable: bool = False
    writable: bool = False
    values: tuple[int, ...] | None = None
    ranges: tuple[DpiRange, ...] | None = None
    independent_axes: bool = False
    stage_count: int | None = None
    stage_values_readable: bool = False
    stage_values_writable: bool = False
    active_stage_readable: bool = False
    active_stage_writable: bool = False
    persistent: bool = False
    events: bool = False

    def accepts(self, value: int) -> bool:
        if value <= 0:
            return False
        if self.values is not None and value in self.values:
            return True
        return bool(self.ranges and any(item.contains(value) for item in self.ranges))


@dataclass(frozen=True)
class ReportRateCapabilities:
    readable: bool = False
    writable: bool = False
    values: tuple[int, ...] | None = None


@dataclass(frozen=True)
class BatteryCapabilities:
    """A protocol-neutral, read-only battery contract."""
    readable: bool = False
    percentage: bool = False
    voltage: bool = False
    events: bool = False


class LightingMode(str, Enum):
    OFF = "off"
    STATIC = "static"
    BREATHING = "breathing"
    SPECTRUM = "spectrum"


class LightingPersistence(str, Enum):
    ONBOARD = "onboard"
    AUTOMATIC_SAVE = "automatic_save"
    MANUAL_SAVE = "manual_save"
    VOLATILE = "volatile"
    HOST_STREAMED = "host_streamed"
    UNKNOWN = "unknown"


class LightingWriteScope(str, Enum):
    LIGHTING_ONLY = "lighting_only"
    SHARED_DEVICE_CONFIG = "shared_device_config"


@dataclass(frozen=True)
class LightingZoneCapabilities:
    zone_id: str
    name: str
    modes: tuple[LightingMode, ...] = ()
    rgb24: bool = False
    brightness_range: tuple[int, int] | None = None
    speed_range: tuple[int, int] | None = None
    persistence: tuple[LightingPersistence, ...] = (LightingPersistence.UNKNOWN,)
    write_scope: LightingWriteScope = LightingWriteScope.LIGHTING_ONLY
    readable: bool = False
    writable: bool = False


@dataclass(frozen=True)
class LightingCapabilities:
    zones: tuple[LightingZoneCapabilities, ...] = ()

    @property
    def available(self) -> bool:
        return bool(self.zones)


@dataclass(frozen=True)
class LightingState:
    zone_id: str
    mode: LightingMode
    color: str | None = None
    brightness: int | None = None
    speed: int | None = None
    persistence: LightingPersistence = LightingPersistence.UNKNOWN
    confirmed: bool = False


@dataclass(frozen=True)
class HardwareCapabilities:
    dpi: DpiCapabilities = DpiCapabilities()
    report_rate: ReportRateCapabilities = ReportRateCapabilities()
    battery: BatteryCapabilities = BatteryCapabilities()
    lighting: LightingCapabilities = LightingCapabilities()


@dataclass(frozen=True)
class DpiState:
    x_dpi: int
    y_dpi: int | None = None
    active_stage: int | None = None
    active_profile: int | None = None
    confirmed: bool = False
    cycle_trigger: bool = False
    reconnect_resync: bool = False

    @property
    def display_value(self) -> int | tuple[int, int]:
        if self.y_dpi in (None, 0, self.x_dpi):
            return self.x_dpi
        return self.x_dpi, self.y_dpi


@dataclass(frozen=True)
class BatteryState:
    percentage: int | None = None
    voltage_mv: int | None = None
    status: str | None = None
