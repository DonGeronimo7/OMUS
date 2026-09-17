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


def _confirmed_dpi_write(backend, device, requested: int) -> int | None:
    """Perform a temporary DPI write and require canonical confirmation."""
    result = backend.set_dpi(device, requested)
    result_value = _dpi_number(result)
    result_confirmed = bool(getattr(result, "confirmed", False))

    # DpiState(confirmed=True) is already canonical backend readback. Legacy
    # scalar setters must be followed by an explicit read.
    if result_confirmed and result_value == requested:
        return result_value

    readback = _dpi_number(backend.get_dpi(device))
    return readback if readback == requested else None


def tune_stage(backend, device, choices, index):
    """Return accepted/back/cancel; only a confirmed write updates wizard state."""
    accepted = choices.stages[index]
    current = accepted
    if not (choices.dpi_values or choices.dpi_ranges) or not choices.accepts_dpi(accepted):
        print("This stage cannot be live-tuned because it is outside the discovered DPI capability.")
        return "back"
    tested = False
    while True:
        print(f"\nDPI stage {index + 1}/{len(choices.stages)}")
        print(f"Current accepted value: {accepted} DPI")
        if choices.dpi_minimum is not None and choices.dpi_maximum is not None:
            print(f"Supported range: {choices.dpi_minimum}–{choices.dpi_maximum} DPI")
        if choices.dpi_values and not choices.dpi_ranges:
            print("Hardware-reported values: " + ", ".join(map(str, choices.dpi_values)))
        print(
            f"Native increment: {choices.dpi_increment} DPI"
            if choices.dpi_increment
            else "Native increment: varies or was not reported"
        )
        print("[B] Back (discard test)  [Q] Cancel setup")
        prompt = (
            f"Enter another DPI to keep testing, or press Enter to accept {current}: "
            if tested
            else f"Enter a DPI to test, or press Enter to keep {current}: "
        )
        raw = input(prompt).strip().lower()
        if raw == "":
            choices.stages[index] = current
            if index == 0:
                choices.active_dpi = current
            if tested:
                choices.verified_dpi_values.add(current)
            choices.dpi_changed = True
            return "accept"
        if raw in ("b", "esc"):
            restore_dpi(backend, device, accepted)
            return "back"
        if raw == "q":
            restore_dpi(backend, device, accepted)
            return "cancel"
        try:
            requested = int(raw)
        except ValueError:
            print("Enter a supported DPI value, B, or Q.")
            continue
        if not choices.accepts_dpi(requested):
            minimum, maximum = choices.dpi_minimum, choices.dpi_maximum
            if minimum is not None and maximum is not None:
                print(f"{requested} DPI is unsupported. Capability: {minimum}–{maximum} DPI.")
            else:
                print(f"{requested} DPI is not one of the hardware-reported values.")
            continue
        try:
            confirmed = _confirmed_dpi_write(backend, device, requested)
            if confirmed != requested:
                print(f"DPI readback did not confirm {requested}; the staged value was not changed.")
                continue
            current = confirmed
            choices.current_dpi = confirmed
            choices.verified_dpi_values.add(confirmed)
            tested = True
            print(f"Testing {current} DPI. Move the mouse to check the feel.")
        except (HardwareError, OSError, TypeError, ValueError) as exc:
            print(f"Could not test DPI: {exc}")


def dpi_screen(backend, device, choices):
    while True:
        print("\nDPI configuration")
        if choices.current_dpi is not None:
            print(f"Current hardware DPI: {choices.current_dpi}")
        mode = "writable" if choices.dpi_writable else "read-only" if choices.dpi_readable else "unknown"
        print(f"Hardware capability: {mode}")
        if choices.dpi_minimum is not None and choices.dpi_maximum is not None:
            suffix = f", step {choices.dpi_increment}" if choices.dpi_increment else ""
            print(f"Discovered range: {choices.dpi_minimum}–{choices.dpi_maximum}{suffix}")
        for i, value in enumerate(choices.stages, 1):
            verified = " [verified]" if value in choices.verified_dpi_values else ""
            print(f"  {i}. {value} DPI{verified}")
        print("[number] Test/change stage  [Enter] Continue  [B] Back  [Q] Cancel setup")
        raw = input("> ").strip().lower()
        if raw == "":
            return "continue"
        if raw in ("b", "q"):
            return raw
        if raw.isdigit() and 1 <= int(raw) <= len(choices.stages):
            if not choices.dpi_writable:
                print("Live DPI tuning is unavailable for this mouse.")
                continue
            result = tune_stage(backend, device, choices, int(raw) - 1)
            if result == "cancel":
                return "q"
            continue
        print("Choose a stage number, Enter, B, or Q.")


def polling_screen(choices):
    while True:
        print("\nPolling rate")
        if choices.polling_rates:
            print(
                "Protocol-reported supported rates: "
                + ", ".join(f"{hz} Hz" for hz in choices.polling_rates)
            )
        else:
            print("Protocol-supported rates were not reported.")
        if choices.current_polling_rate is not None:
            print(f"Current hardware rate: {choices.current_polling_rate} Hz (protocol-reported)")
        if choices.measured_polling_rate is not None:
            print(
                f"Measured current rate: {choices.measured_polling_rate} Hz "
                f"({choices.measured_polling_confidence or 'unknown'} confidence)"
            )
        if choices.polling_rate is not None:
            print(f"Configured rate: {choices.polling_rate} Hz")
        print(
            "Capability: "
            + ("read/write" if choices.polling_writable else "read-only" if choices.polling_readable else "not yet discovered")
        )
        if choices.polling_writable and choices.polling_rates:
            for i, hz in enumerate(choices.polling_rates, 1):
                print(f"  {i}. {hz} Hz" + (" [selected]" if hz == choices.polling_rate else ""))
            print(
                f"[Enter] Continue with configured {choices.polling_rate} Hz  [number] Select  "
                "[B] Back  [Q] Cancel setup"
            )
        else:
            print("Report-rate changes are unavailable; the current hardware rate will be kept.")
            print("No unverified polling write will be attempted.")
            print("[Enter] Continue  [B] Back  [Q] Cancel setup")
        raw = input("> ").strip().lower()
        if raw == "":
            return "continue"
        if raw in ("b", "q"):
            return raw
        if (
            choices.polling_writable
            and raw.isdigit()
            and 1 <= int(raw) <= len(choices.polling_rates)
        ):
            choices.polling_rate = choices.polling_rates[int(raw) - 1]
            choices.polling_changed = True
            continue
        print(
            "Choose a listed rate, Enter, B, or Q."
            if choices.polling_writable
            else "Choose Enter, B, or Q."
        )


def review_screen(device, choices):
    print("\nMouse configuration")
    print(f"Device: {device.name}")
    print("Configured software stages: " + " → ".join(map(str, choices.stages)))
    if choices.measured_polling_rate is not None:
        print(
            f"Measured polling: ~{choices.measured_polling_rate} Hz "
            f"({choices.measured_polling_confidence or 'unknown'} confidence)"
        )
    else:
        print("Measured polling: unavailable")
    print(
        f"Configured polling preference: {choices.polling_rate} Hz"
        if choices.polling_rate
        else (
            "Configured polling preference: unchanged "
            f"({choices.current_polling_rate} Hz protocol-reported)"
        )
        if choices.current_polling_rate is not None
        else "Configured polling preference: unchanged"
    )
    print(
        "DPI write control: "
        + ("available (proven)" if choices.dpi_writable else "unavailable / unproven")
    )
    print(
        "Polling write control: "
        + ("available (proven)" if choices.polling_writable else "unavailable / unproven")
    )
    print(f"Buttons: {len(choices.mappings)} mappings")
    print("[1] Edit DPI  [2] Edit polling  [3] Edit buttons")
    print("[Enter] Finish  [B] Back  [Q] Cancel setup")
    while True:
        raw = input("> ").strip().lower()
        if raw in ("", "b", "q", "1", "2", "3"):
            return raw
        print("Choose Enter, B, Q, 1, 2, or 3.")
