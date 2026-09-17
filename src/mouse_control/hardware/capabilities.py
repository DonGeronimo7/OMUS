"""Protocol-neutral hardware capabilities and state."""

from __future__ import annotations

from dataclasses import dataclass


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


@dataclass(frozen=True)
class HardwareCapabilities:
    dpi: DpiCapabilities = DpiCapabilities()
    report_rate: ReportRateCapabilities = ReportRateCapabilities()
    battery: BatteryCapabilities = BatteryCapabilities()


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
