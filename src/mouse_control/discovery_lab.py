"""Production orchestration for the Automatic Discovery laboratory.

This module deliberately does not reimplement any discovery science.  It exposes
one catalog around the existing physically validated command modules so setup
and future front-ends invoke the exact same calibration, demonstration and
promotion engines used during hardware acceptance.

Unknown hardware remains read-only until a separate promotion engine persists
PROVEN exact-model authority.  A front-end confirmation only authorizes running
an existing guarded experiment; it never bypasses that experiment's validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class DiscoveryTool(str, Enum):
    SENSOR_CALIBRATION = "sensor-calibration"
    DPI_WRITE_TRACE = "dpi-write-trace"
    DPI_WRITE_PROMOTION = "dpi-write-promotion"
    POLLING_ONBOARD_TRACE = "polling-onboard-trace"
    POLLING_HOST_TRACE = "polling-host-trace"
    POLLING_PROMOTION = "polling-promotion"


@dataclass(frozen=True)
class DiscoveryToolSpec:
    tool: DiscoveryTool
    label: str
    description: str
    writes_hardware: bool
    promotion: bool = False


_TOOL_SPECS = (
    DiscoveryToolSpec(
        DiscoveryTool.SENSOR_CALIBRATION,
        "Measure physical CPI + polling",
        "Vendor-neutral ruler calibration and repeated evdev timing measurement.",
        False,
    ),
    DiscoveryToolSpec(
        DiscoveryTool.DPI_WRITE_TRACE,
        "Learn DPI write grammar from proven teacher",
        "Capture opaque TX/RX demonstrations as DEMONSTRATED evidence only.",
        True,
    ),
    DiscoveryToolSpec(
        DiscoveryTool.DPI_WRITE_PROMOTION,
        "Prove learned DPI write",
        "Generic replay + readback + physical CPI verification + rollback before PROVEN.",
        True,
        True,
    ),
    DiscoveryToolSpec(
        DiscoveryTool.POLLING_ONBOARD_TRACE,
        "Learn polling Onboard → Host branch",
        "Capture complete teacher transactions and independent physical timing evidence.",
        True,
    ),
    DiscoveryToolSpec(
        DiscoveryTool.POLLING_HOST_TRACE,
        "Learn polling Host → Host branch",
        "Capture the steady-state branch needed for repeated polling changes.",
        True,
    ),
    DiscoveryToolSpec(
        DiscoveryTool.POLLING_PROMOTION,
        "Prove learned polling state machine",
        "Exercise both branches on one generic session, verify timing, rollback, then persist PROVEN.",
        True,
        True,
    ),
)


def discovery_tool_specs() -> tuple[DiscoveryToolSpec, ...]:
    return _TOOL_SPECS


def selected_device_number(devices: tuple[Any, ...] | list[Any], selected: Any) -> int:
    """Return the one-based device index expected by existing CLI laboratories."""
    for index, device in enumerate(devices, 1):
        if device == selected:
            return index
    raise ValueError("selected mouse is not part of the setup device list")


def _runner(tool: DiscoveryTool) -> tuple[Callable[[list[str] | None], int], list[str]]:
    """Resolve lazily so importing setup never imports every experimental module."""
    if tool is DiscoveryTool.SENSOR_CALIBRATION:
        from .sensor_calibration_cli import main
        return main, []
    if tool is DiscoveryTool.DPI_WRITE_TRACE:
        from .write_trace_cli import main
        return main, ["--i-understand-this-writes-hardware"]
    if tool is DiscoveryTool.DPI_WRITE_PROMOTION:
        from .write_promotion_cli import main
        return main, ["--authorize-reversible-replay"]
    if tool is DiscoveryTool.POLLING_ONBOARD_TRACE:
        from .polling_trace_cli import main
        return main, ["--i-understand-this-writes-hardware"]
    if tool is DiscoveryTool.POLLING_HOST_TRACE:
        from .polling_host_trace_cli import main
        return main, ["--i-understand-this-writes-hardware"]
    if tool is DiscoveryTool.POLLING_PROMOTION:
        from .polling_promotion_cli import main
        return main, ["--authorize-polling-promotion"]
    raise ValueError(f"unsupported discovery tool: {tool}")


def run_discovery_tool(
    tool: DiscoveryTool,
    *,
    devices: tuple[Any, ...] | list[Any],
    selected: Any,
) -> int:
    """Run one existing laboratory against the already-selected setup mouse.

    Guard flags are supplied only after the caller has performed an explicit UI
    confirmation for write-capable tools.  The underlying laboratory still
    performs every identity, evidence, readback, physical verification and
    rollback check and may refuse the run.
    """
    main, guard_args = _runner(tool)
    device_number = selected_device_number(devices, selected)
    return int(main(["--device", str(device_number), *guard_args]))
