"""Revisitable, backend-neutral setup choices.

Discovery facts live here only as a snapshot for presentation/validation. Hardware
backends remain the authority for reads/writes; temporary writes are verified and
rolled back by the setup UI.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import DEFAULT_DPI, DEFAULT_DPI_STAGES
from .hardware import HardwareError
from .hardware.capabilities import DpiRange, HardwareCapabilities


@dataclass
class SetupChoices:
    stages: list[int] = field(default_factory=lambda: list(DEFAULT_DPI_STAGES))
    active_dpi: int = DEFAULT_DPI
    polling_rate: int | None = None
    mappings: dict[str, str] = field(default_factory=dict)
    macros: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    enable_service: bool = True

    # Device-specific discovery state. reset_device_state() MUST be called when
    # the selected physical mouse changes.
    original_dpi: int | None = None
    current_dpi: int | None = None
    dpi_values: list[int] = field(default_factory=list)
    dpi_ranges: list[DpiRange] = field(default_factory=list)
    polling_rates: list[int] = field(default_factory=list)
    dpi_readable: bool = False
    dpi_writable: bool = False
    dpi_increment: int | None = None
    polling_readable: bool = False
    polling_writable: bool = False
    current_polling_rate: int | None = None
    measured_polling_rate: int | None = None
    measured_polling_confidence: str | None = None

    # User edits are persistent-choice state, not capability state.
    dpi_changed: bool = False
    polling_changed: bool = False
    verified_dpi_values: set[int] = field(default_factory=set)

    def reset_device_state(self) -> None:
        """Invalidate every fact that belongs to one physical mouse."""
        self.original_dpi = None
        self.current_dpi = None
        self.dpi_values.clear()
        self.dpi_ranges.clear()
        self.polling_rates.clear()
        self.dpi_readable = False
        self.dpi_writable = False
        self.dpi_increment = None
        self.polling_readable = False
        self.polling_writable = False
        self.current_polling_rate = None
        self.measured_polling_rate = None
        self.measured_polling_confidence = None
        self.verified_dpi_values.clear()

    def accepts_dpi(self, value: int) -> bool:
        value = int(value)
        if value in self.dpi_values:
            return True
        return any(item.contains(value) for item in self.dpi_ranges)

    @property
    def dpi_minimum(self) -> int | None:
        candidates = list(self.dpi_values)
        candidates.extend(item.minimum for item in self.dpi_ranges)
        return min(candidates) if candidates else None

    @property
    def dpi_maximum(self) -> int | None:
        candidates = list(self.dpi_values)
        candidates.extend(item.maximum for item in self.dpi_ranges)
        return max(candidates) if candidates else None


def _dpi_number(value):
    if value is None:
        return None
    if hasattr(value, "display_value"):
        return int(value.display_value)
    if isinstance(value, tuple):
        return int(value[0])
    return int(value)


def _fixed_increment(values: list[int]) -> int | None:
    if len(values) < 2:
        return None
    increments = {b - a for a, b in zip(values, values[1:])}
    return increments.pop() if len(increments) == 1 else None


def _hardware_capabilities(backend, device) -> HardwareCapabilities | None:
    try:
        capability_getter = getattr(backend, "get_capabilities", None)
        if capability_getter is None:
            return None
        capabilities = capability_getter(device)
    except (HardwareError, OSError, AttributeError, TypeError, ValueError):
        return None
    return capabilities if isinstance(capabilities, HardwareCapabilities) else None


def discover_choices(backend, device, choices):
    """Refresh device-specific capability state without replacing user preferences.

    Capability failures are independent: a DPI failure never erases working polling
    facts and vice versa. Range-based DPI sensors are preserved as ranges instead of
    being flattened into an artificial enumerated list.
    """
    choices.reset_device_state()
    capabilities = _hardware_capabilities(backend, device)

    # DPI
    try:
        dpi_caps = capabilities.dpi if capabilities is not None else None
        if dpi_caps is not None:
            choices.dpi_readable = bool(dpi_caps.readable)
            choices.dpi_writable = bool(dpi_caps.writable)
            choices.dpi_values = sorted({int(value) for value in (dpi_caps.values or ())})
            choices.dpi_ranges = list(dpi_caps.ranges or ())
            if len(choices.dpi_ranges) == 1:
                choices.dpi_increment = choices.dpi_ranges[0].step
            elif choices.dpi_values:
                choices.dpi_increment = _fixed_increment(choices.dpi_values)

        # Preserve compatibility with validated/legacy backends that do not yet
        # populate HardwareCapabilities but do implement the established methods.
        method_writable = bool(backend.supports_dpi(device))
        # The backend execution-policy method is authoritative for write access.
        # A protocol capability may describe a writable primitive while the
        # backend still correctly refuses it for this identity/transport/mode.
        choices.dpi_writable = method_writable
        choices.dpi_readable = choices.dpi_readable or method_writable
        if method_writable and not choices.dpi_values and not choices.dpi_ranges:
            choices.dpi_values = sorted({int(value) for value in backend.get_dpi_values(device)})
            choices.dpi_increment = _fixed_increment(choices.dpi_values)

        if choices.dpi_readable or choices.dpi_writable:
            choices.original_dpi = _dpi_number(backend.get_dpi(device))
            choices.current_dpi = choices.original_dpi

        unsupported = [stage for stage in choices.stages if not choices.accepts_dpi(stage)]
        if unsupported and (choices.dpi_values or choices.dpi_ranges):
            print(
                "Some configured DPI stages are outside the discovered capability; "
                "they will be preserved unless you edit them."
            )
    except (HardwareError, OSError, TypeError, ValueError) as exc:
        print(f"DPI capability query incomplete: {exc}")
        # Do not touch polling capability state here.

    # Polling/report rate
    try:
        report_caps = capabilities.report_rate if capabilities is not None else None
        if report_caps is not None:
            choices.polling_readable = bool(report_caps.readable)
            choices.polling_writable = bool(report_caps.writable)
            choices.polling_rates = sorted(
                {int(value) for value in (report_caps.values or ())}, reverse=True
            )

        method_readable = bool(backend.supports_polling_rate(device))
        method_writable = bool(backend.supports_polling_rate_writes(device))
        choices.polling_readable = choices.polling_readable or method_readable
        # Never promote a report-rate write merely because the protocol-level
        # capability advertises one. Exact identity, transport, and control-mode
        # policy lives in supports_polling_rate_writes().
        choices.polling_writable = method_writable
        if method_readable and not choices.polling_rates:
            choices.polling_rates = sorted(
                {int(value) for value in backend.get_polling_rates(device)}, reverse=True
            )
        if choices.polling_readable:
            choices.current_polling_rate = backend.get_polling_rate(device)
        if choices.polling_writable and choices.polling_rates and choices.polling_rate is None:
            # First setup defaults to the maximum proven supported rate. Existing
            # configured preferences are never replaced by discovery.
            choices.polling_rate = choices.polling_rates[0]
    except (HardwareError, OSError, TypeError, ValueError) as exc:
        print(f"Polling capability query incomplete: {exc}")
        choices.polling_writable = False


def restore_dpi(backend, device, value):
    if value is None:
        return
    try:
        backend.set_dpi(device, value)
    except (HardwareError, OSError) as exc:
        print(f"Could not restore DPI: {exc}")
