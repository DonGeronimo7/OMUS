"""Production orchestration for the Automatic Discovery laboratory.

This catalog is intentionally a thin adapter over the exact experiment engines
used during hardware acceptance. The TUI is the user-facing surface; these
entries describe the science that must remain reachable without weakening any
identity, evidence, readback, physical-verification, or rollback rule.

Unknown hardware remains read-only until a promotion engine persists PROVEN
exact-model authority. A UI confirmation authorizes running a guarded
experiment; it never authorizes a write by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class DiscoveryTool(str, Enum):
    HYPOTHESIS_INSPECTION = "hypothesis-inspection"
    SENSOR_CALIBRATION = "sensor-calibration"
    CALIBRATED_DPI_DISCOVERY = "calibrated-dpi-discovery"
    POLLING_PHYSICAL_VERIFY = "polling-physical-verify"
    DPI_WRITE_TRACE = "dpi-write-trace"
    DPI_WRITE_PROMOTION = "dpi-write-promotion"
    DPI_GENERALIZATION = "dpi-generalization"
    LEARNED_ACTION_CAPTURE = "learned-action-capture"
    POLLING_ONBOARD_TRACE = "polling-onboard-trace"
    POLLING_HOST_TRACE = "polling-host-trace"
    POLLING_REPLAY = "polling-replay"
    POLLING_STATE_MACHINE = "polling-state-machine"
    POLLING_PROMOTION = "polling-promotion"


@dataclass(frozen=True)
class DiscoveryToolSpec:
    tool: DiscoveryTool
    label: str
    description: str
    writes_hardware: bool
    promotion: bool = False
    evidence_phase: str = "observe"


_TOOL_SPECS = (
    DiscoveryToolSpec(
        DiscoveryTool.HYPOTHESIS_INSPECTION,
        "Inspect topology + protocol hypotheses",
        "Read-only descriptor, feature-baseline, repertoire, and evidence-ladder inspection for the selected mouse.",
        False,
        evidence_phase="observe",
    ),
    DiscoveryToolSpec(
        DiscoveryTool.SENSOR_CALIBRATION,
        "Measure physical CPI + rough polling",
        "Vendor-neutral ruler calibration with repeated evdev motion measurement.",
        False,
        evidence_phase="calibrate",
    ),
    DiscoveryToolSpec(
        DiscoveryTool.CALIBRATED_DPI_DISCOVERY,
        "Correlate physical DPI states with raw HID",
        "Teacher-free CPI calibration plus simultaneous read-only HID observation and contrastive state inference.",
        False,
        evidence_phase="correlate",
    ),
    DiscoveryToolSpec(
        DiscoveryTool.POLLING_PHYSICAL_VERIFY,
        "Verify polling with fundamental timing analyzer",
        "Use the harmonic-resistant p50/mode/direct-support verifier built for promotion evidence.",
        True,
        evidence_phase="validate",
    ),
    DiscoveryToolSpec(
        DiscoveryTool.DPI_WRITE_TRACE,
        "Capture DPI transaction demonstrations",
        "Capture opaque TX/RX demonstrations as DEMONSTRATED evidence only when a proven teacher exists.",
        True,
        evidence_phase="infer",
    ),
    DiscoveryToolSpec(
        DiscoveryTool.DPI_WRITE_PROMOTION,
        "Prove learned DPI write",
        "Generic replay + readback + physical CPI verification + rollback before PROVEN.",
        True,
        True,
        evidence_phase="prove",
    ),
    DiscoveryToolSpec(
        DiscoveryTool.DPI_GENERALIZATION,
        "Test unseen DPI values inside proven envelope",
        "Generate bounded unseen values from an already-PROVEN numeric grammar and verify them physically without widening persisted authority.",
        True,
        evidence_phase="generalize",
    ),
    DiscoveryToolSpec(
        DiscoveryTool.LEARNED_ACTION_CAPTURE,
        "Learn physical DPI-cycle trigger",
        "Read-only exact-interface press/release learning for runtime DPI-cycle events after a DPI writer is proven.",
        False,
        evidence_phase="persist",
    ),
    DiscoveryToolSpec(
        DiscoveryTool.POLLING_ONBOARD_TRACE,
        "Capture polling cold-start branch",
        "Capture complete teacher transaction evidence and independent physical timing for the initial ownership/state transition.",
        True,
        evidence_phase="infer",
    ),
    DiscoveryToolSpec(
        DiscoveryTool.POLLING_HOST_TRACE,
        "Capture polling steady-state branch",
        "Capture the repeated-rate-change branch needed for persistent-session polling control.",
        True,
        evidence_phase="infer",
    ),
    DiscoveryToolSpec(
        DiscoveryTool.POLLING_REPLAY,
        "Replay one learned polling transaction",
        "Exercise the inferred generic polling grammar with readback and physical timing while preserving rollback requirements.",
        True,
        evidence_phase="validate",
    ),
    DiscoveryToolSpec(
        DiscoveryTool.POLLING_STATE_MACHINE,
        "Validate chained polling state machine",
        "Exercise two consecutive generic transitions on one persistent HID session and physically verify both rates.",
        True,
        evidence_phase="validate",
    ),
    DiscoveryToolSpec(
        DiscoveryTool.POLLING_PROMOTION,
        "Prove learned polling state machine",
        "Exercise all demonstrated branches/rates, verify timing and rollback, then persist exact-model PROVEN authority.",
        True,
        True,
        evidence_phase="prove",
    ),
)


def discovery_tool_specs() -> tuple[DiscoveryToolSpec, ...]:
    return _TOOL_SPECS


def selected_device_number(devices: tuple[Any, ...] | list[Any], selected: Any) -> int:
    """Return the one-based device index expected by existing laboratories."""
    for index, device in enumerate(devices, 1):
        if device == selected:
            return index
    raise ValueError("selected mouse is not part of the setup device list")


def _runner(tool: DiscoveryTool) -> tuple[Callable[[list[str] | None], int], list[str]]:
    """Resolve lazily so importing setup never imports every experiment module."""
    if tool is DiscoveryTool.HYPOTHESIS_INSPECTION:
        from .hypothesis_inspection_cli import main
        return main, []
    if tool is DiscoveryTool.SENSOR_CALIBRATION:
        from .sensor_calibration_cli import main
        return main, []
    if tool is DiscoveryTool.CALIBRATED_DPI_DISCOVERY:
        from .calibrated_discovery_cli import main
        return main, []
    if tool is DiscoveryTool.POLLING_PHYSICAL_VERIFY:
        from .polling_verify_cli import main
        return main, ["--i-understand-this-writes-hardware"]
    if tool is DiscoveryTool.DPI_WRITE_TRACE:
        from .write_trace_cli import main
        return main, ["--i-understand-this-writes-hardware"]
    if tool is DiscoveryTool.DPI_WRITE_PROMOTION:
        from .write_promotion_cli import main
        return main, ["--authorize-reversible-replay"]
    if tool is DiscoveryTool.DPI_GENERALIZATION:
        from .dpi_generalization_cli import main
        return main, ["--authorize-generalization-test"]
    if tool is DiscoveryTool.LEARNED_ACTION_CAPTURE:
        from .learned_action_capture_cli import main
        return main, ["--authorize-guided-capture"]
    if tool is DiscoveryTool.POLLING_ONBOARD_TRACE:
        from .polling_trace_cli import main
        return main, ["--i-understand-this-writes-hardware"]
    if tool is DiscoveryTool.POLLING_HOST_TRACE:
        from .polling_host_trace_cli import main
        return main, ["--i-understand-this-writes-hardware"]
    if tool is DiscoveryTool.POLLING_REPLAY:
        from .polling_replay_cli import main
        return main, ["--authorize-generic-replay"]
    if tool is DiscoveryTool.POLLING_STATE_MACHINE:
        from .polling_state_machine_cli import main
        return main, ["--authorize-generic-chain"]
    if tool is DiscoveryTool.POLLING_PROMOTION:
        from .polling_promotion_cli import main
        return main, ["--authorize-polling-promotion"]
    raise ValueError(f"unsupported discovery tool: {tool}")


def run_discovery_tool(
    tool: DiscoveryTool,
    *,
    devices: tuple[Any, ...] | list[Any],
    selected: Any,
    extra_args: list[str] | tuple[str, ...] = (),
) -> int:
    """Run one guarded experiment against the already-selected setup mouse.

    ``extra_args`` is supplied by the TUI for experiment-specific values while
    device identity and authorization flags remain controlled here. The
    underlying experiment still owns every safety check and may refuse to run.
    """
    main, guard_args = _runner(tool)
    device_number = selected_device_number(devices, selected)
    return int(main(["--device", str(device_number), *guard_args, *extra_args]))
