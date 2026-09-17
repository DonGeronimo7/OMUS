"""Backend-neutral reversible write-possibility probes for Automatic Discovery.

These probes are research, not runtime authority. They execute only exact-model
DEMONSTRATED grammars, only demonstrated semantic values, and require a known
rollback value plus independent physical verification. Successful probes leave
persisted operation state unchanged; promotion to PROVEN remains a separate,
stricter evidence boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .learned_hid_session import LearnedHidSession
from .learned_hid_transport import (
    LearnedHidAdapter,
    LearnedHidTransportError,
    execute_learned_dpi,
    learned_dpi_read_spec,
)
from .learned_operations import (
    LearnedOperationState,
    LearnedOperationStore,
    matching_interface_node,
)
from .learned_polling import (
    LearnedPollingOperationStore,
    PollingControlState,
)
from .polling_observation import measure_current_polling
from .sensor_calibration import (
    capture_evdev_motion,
    measure_sensor_state_auto,
)
from .transaction_engine import (
    TransactionAuthorization,
    TransactionContext,
    TransactionEngine,
)


class ResearchProbeError(RuntimeError):
    """A bounded reversible research probe could not be completed safely."""


PromptCallback = Callable[[str, tuple[str, ...]], bool]
ProgressCallback = Callable[[str], None]


@dataclass(frozen=True)
class CapabilityProbeResult:
    semantic: str
    attempted: bool
    possible: bool
    original_value: int | None = None
    target_value: int | None = None
    restored: bool = False
    detail: str = ""


@dataclass(frozen=True)
class ReversibleResearchProbeOutcome:
    dpi: CapabilityProbeResult | None = None
    polling: CapabilityProbeResult | None = None

    @property
    def any_possible(self) -> bool:
        return bool(
            (self.dpi is not None and self.dpi.possible)
            or (self.polling is not None and self.polling.possible)
        )


def _choose_other(values, current: int) -> int | None:
    candidates = sorted({int(value) for value in values if int(value) != int(current)})
    if not candidates:
        return None
    return min(candidates, key=lambda value: (abs(value - int(current)), value))


def _measure_dpi(
    event_path: str,
    *,
    expected: int,
    prompt: PromptCallback,
    progress: ProgressCallback,
    label: str,
    distance_mm: float,
    seconds: float,
) -> float:
    if not prompt(
        f"Physical DPI verification — {label}",
        (
            f"Move the mouse exactly {distance_mm:g} mm in one straight direction after starting.",
            f"Expected state: {expected} DPI.",
            "This is read-only physical verification through evdev.",
        ),
    ):
        raise ResearchProbeError("DPI physical verification cancelled")
    events = capture_evdev_motion(event_path, seconds=seconds, exclusive=True)
    measurement = measure_sensor_state_auto(events, distance_mm=distance_mm)
    deviation = (measurement.estimated_dpi - expected) / expected
    progress(
        f"{label}: measured ~{measurement.estimated_dpi:.1f} CPI "
        f"({deviation * 100:+.1f}%, straightness {measurement.straightness * 100:.1f}%)"
    )
    if abs(deviation) > 0.15:
        raise ResearchProbeError(
            f"{label} physical CPI did not agree with raw state {expected} DPI"
        )
    return float(measurement.estimated_dpi)


def probe_demonstrated_dpi(
    selected,
    physical,
    *,
    prompt: PromptCallback,
    progress: ProgressCallback | None = None,
    operation_store: LearnedOperationStore | None = None,
    distance_mm: float = 254.0,
    seconds: float = 8.0,
) -> CapabilityProbeResult:
    """Test one DEMONSTRATED DPI grammar and restore using generic raw HID only."""
    report = progress or (lambda _message: None)
    store = operation_store or LearnedOperationStore()
    found = store.find_for_physical(physical, proven_only=False)
    if found is None:
        return CapabilityProbeResult("dpi", False, False, detail="no demonstrated DPI grammar")
    _path, operation = found
    if operation.state is not LearnedOperationState.DEMONSTRATED:
        return CapabilityProbeResult("dpi", False, False, detail="DPI operation is not in DEMONSTRATED research state")

    node = matching_interface_node(operation, physical)
    session = LearnedHidSession(Path(node.path))
    adapter = LearnedHidAdapter(node.path, operation, session=session)
    original: int | None = None
    target: int | None = None
    changed = False
    restored = False
    try:
        context = TransactionContext()
        TransactionEngine().run(
            learned_dpi_read_spec(),
            adapter,
            authorization=TransactionAuthorization(
                active_queries=True,
                reason="exact-model DEMONSTRATED research baseline query",
            ),
            context=context,
        )
        original = int(context.values["raw_readback"])
        if not operation.accepts(original):
            raise ResearchProbeError(
                f"current DPI {original} is outside the demonstrated reversible set; refusing probe"
            )
        target = _choose_other(operation.demonstrated_values, original)
        if target is None:
            raise ResearchProbeError("DPI grammar has no alternate demonstrated value for a reversible probe")

        _measure_dpi(
            selected.path,
            expected=original,
            prompt=prompt,
            progress=report,
            label="baseline",
            distance_mm=distance_mm,
            seconds=seconds,
        )
        if not prompt(
            "Reversible DPI write-possibility probe",
            (
                f"Mouse Control will test {original} → {target} DPI using the learned generic HID grammar.",
                "Only a previously demonstrated value will be sent.",
                f"The same generic session will restore {original} DPI before the probe completes.",
                "This validates possibility only; it does not grant runtime write authority.",
            ),
        ):
            return CapabilityProbeResult("dpi", False, False, original, target, detail="probe declined")

        result = execute_learned_dpi(
            operation,
            node.path,
            target,
            promotion=True,
            authorization=TransactionAuthorization(
                reversible_writes=True,
                reason="explicit bounded setup write-possibility probe",
            ),
            session=session,
        )
        if int(result.values["raw_readback"]) != target:
            raise ResearchProbeError("generic DPI write returned inconsistent readback")
        changed = True
        report(f"✓ Generic raw DPI readback changed {original} → {target}")
        _measure_dpi(
            selected.path,
            expected=target,
            prompt=prompt,
            progress=report,
            label="candidate target",
            distance_mm=distance_mm,
            seconds=seconds,
        )

        rollback = execute_learned_dpi(
            operation,
            node.path,
            original,
            promotion=True,
            authorization=TransactionAuthorization(
                reversible_writes=True,
                reason="mandatory generic rollback after setup research probe",
            ),
            session=session,
        )
        if int(rollback.values["raw_readback"]) != original:
            raise ResearchProbeError("generic DPI rollback readback did not restore the baseline")
        restored = True
        changed = False
        _measure_dpi(
            selected.path,
            expected=original,
            prompt=prompt,
            progress=report,
            label="restored baseline",
            distance_mm=distance_mm,
            seconds=seconds,
        )
        report("✓ DPI write possibility validated with generic readback, physical change, and generic rollback")
        return CapabilityProbeResult(
            "dpi", True, True, original, target, True,
            "generic raw-HID write/readback/physical verification/rollback succeeded",
        )
    except (OSError, LearnedHidTransportError) as exc:
        raise ResearchProbeError(str(exc)) from exc
    finally:
        if changed and original is not None:
            try:
                execute_learned_dpi(
                    operation,
                    node.path,
                    original,
                    promotion=True,
                    authorization=TransactionAuthorization(
                        reversible_writes=True,
                        reason="emergency generic rollback after interrupted research probe",
                    ),
                    session=session,
                )
                restored = True
            except Exception as exc:
                report(f"WARNING: generic DPI emergency rollback failed: {exc}")
        adapter.close()
        session.close()


def _resolved_pattern(pattern) -> bytes:
    if any(value is None for value in pattern.bytes_):
        raise ResearchProbeError("research request contains unresolved wildcard bytes")
    return bytes(int(value) for value in pattern.bytes_)


def _query_polling_state(operation, session: LearnedHidSession) -> PollingControlState:
    request = _resolved_pattern(operation.control_query_request)
    reply = session.exchange(request, operation.control_query_response)
    raw = int(reply[operation.control_state_offset])
    if raw == operation.onboard_state_raw:
        return PollingControlState.ONBOARD
    if raw == operation.host_state_raw:
        return PollingControlState.HOST
    raise ResearchProbeError(f"polling control query returned unknown state 0x{raw:02x}")


def _execute_polling_branch(operation, session: LearnedHidSession, state: PollingControlState, target: int) -> int:
    grammar = operation.replay_grammar(state)
    readback = None
    for step in grammar.steps:
        values = list(step.request.bytes_)
        if step.request_semantic_offset is not None:
            values[step.request_semantic_offset] = operation.raw_for_rate(int(target))
        if any(value is None for value in values):
            raise ResearchProbeError("polling research request contains unresolved wildcard bytes")
        reply = session.exchange(bytes(int(value) for value in values), step.response)
        if step.response_semantic_offset is not None:
            raw = int(reply[step.response_semantic_offset])
            try:
                readback = int(operation.raw_to_hz[raw])
            except KeyError as exc:
                raise ResearchProbeError(
                    f"polling readback raw value 0x{raw:02x} was not demonstrated"
                ) from exc
    if readback != int(target):
        raise ResearchProbeError(
            f"polling research requested {target} Hz, generic readback was {readback}"
        )
    return int(readback)


def _measure_polling(
    selected,
    *,
    prompt: PromptCallback,
    progress: ProgressCallback,
    label: str,
    seconds: float,
) -> int:
    if not prompt(
        f"Physical polling verification — {label}",
        (
            f"Move the mouse rapidly and continuously for about {seconds:g} seconds.",
            "Mouse Control will infer the report-rate fundamental from kernel event timing.",
        ),
    ):
        raise ResearchProbeError("polling physical verification cancelled")
    measurement = measure_current_polling(selected.path, seconds=seconds, exclusive=True)
    rate = getattr(measurement, "standard_hz", None)
    confidence = str(getattr(measurement, "confidence", "unknown"))
    if rate is None or confidence not in {"high", "medium"}:
        raise ResearchProbeError(
            f"polling measurement was not reliable enough for a reversible probe ({confidence})"
        )
    progress(f"{label}: measured approximately {int(rate)} Hz ({confidence} confidence)")
    return int(rate)


def probe_demonstrated_polling(
    selected,
    physical,
    *,
    prompt: PromptCallback,
    progress: ProgressCallback | None = None,
    operation_store: LearnedPollingOperationStore | None = None,
    seconds: float = 4.0,
) -> CapabilityProbeResult:
    """Test a DEMONSTRATED polling state machine with physical baseline/rollback proof."""
    report = progress or (lambda _message: None)
    store = operation_store or LearnedPollingOperationStore()
    found = store.find_for_physical(physical, proven_only=False)
    if found is None:
        return CapabilityProbeResult("report_rate", False, False, detail="no demonstrated polling grammar")
    _path, operation = found
    state_value = getattr(getattr(operation, "state", None), "value", getattr(operation, "state", None))
    if state_value != "demonstrated":
        return CapabilityProbeResult("report_rate", False, False, detail="polling operation is not DEMONSTRATED")

    original = _measure_polling(
        selected,
        prompt=prompt,
        progress=report,
        label="baseline",
        seconds=seconds,
    )
    if not operation.accepts(original):
        raise ResearchProbeError(
            f"measured baseline {original} Hz is outside the demonstrated reversible set"
        )
    target = _choose_other(operation.demonstrated_rates, original)
    if target is None:
        raise ResearchProbeError("polling grammar has no alternate demonstrated rate")
    if not prompt(
        "Reversible polling write-possibility probe",
        (
            f"Mouse Control will test {original} → {target} Hz through the learned generic state machine.",
            "The starting report rate was established physically before any write.",
            f"The generic Host branch will restore {original} Hz before completion.",
            "This validates possibility only; it does not grant runtime write authority.",
        ),
    ):
        return CapabilityProbeResult("report_rate", False, False, original, target, detail="probe declined")

    node = matching_interface_node(operation, physical)
    session = LearnedHidSession(Path(node.path))
    changed = False
    try:
        start_state = _query_polling_state(operation, session)
        _execute_polling_branch(operation, session, start_state, target)
        changed = True
        report(f"✓ Generic polling readback changed {original} → {target} Hz")
        measured_target = _measure_polling(
            selected,
            prompt=prompt,
            progress=report,
            label="candidate target",
            seconds=seconds,
        )
        if measured_target != target:
            raise ResearchProbeError(
                f"physical polling result was {measured_target} Hz, expected {target} Hz"
            )

        current_state = _query_polling_state(operation, session)
        _execute_polling_branch(operation, session, current_state, original)
        changed = False
        restored = _measure_polling(
            selected,
            prompt=prompt,
            progress=report,
            label="restored baseline",
            seconds=seconds,
        )
        if restored != original:
            raise ResearchProbeError(
                f"physical polling rollback measured {restored} Hz, expected {original} Hz"
            )
        report("✓ Polling write possibility validated with state-machine readback, physical timing, and rollback")
        return CapabilityProbeResult(
            "report_rate", True, True, original, target, True,
            "generic state-machine write/readback/physical verification/rollback succeeded",
        )
    finally:
        if changed:
            try:
                state = _query_polling_state(operation, session)
                _execute_polling_branch(operation, session, state, original)
                report(f"Emergency generic polling rollback requested {original} Hz")
            except Exception as exc:
                report(f"WARNING: generic polling emergency rollback failed: {exc}")
        session.close()


def run_reversible_research_probes(
    selected,
    physical,
    research_plan,
    *,
    prompt: PromptCallback,
    progress: ProgressCallback | None = None,
) -> ReversibleResearchProbeOutcome:
    """Execute only the DEMONSTRATED probes that the Discovery research plan exposed."""
    report = progress or (lambda _message: None)
    dpi = None
    polling = None
    if getattr(getattr(research_plan, "dpi", None), "probe_ready", False):
        dpi = probe_demonstrated_dpi(
            selected,
            physical,
            prompt=prompt,
            progress=report,
        )
    if getattr(getattr(research_plan, "polling", None), "probe_ready", False):
        polling = probe_demonstrated_polling(
            selected,
            physical,
            prompt=prompt,
            progress=report,
        )
    return ReversibleResearchProbeOutcome(dpi=dpi, polling=polling)
