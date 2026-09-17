"""Reusable read-only guided learning used by setup and discovery CLI.

This module intentionally owns no write or promotion path. It orchestrates the
existing :class:`ReadOnlyLearningSession` controls/action samples and returns
what was observed. Writable hardware support remains the responsibility of the
existing exact-model PROVEN operation stores and transaction machinery.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Callable

from .contrastive_inference import refine_teacher_free
from .calibrated_discovery import (
    CalibratedDpiState,
    calibrated_cycle_hypothesis,
    capture_calibrated_motion,
    infer_calibrated_raw_mappings,
)
from .calibrated_profiles import (
    calibrated_profile_data,
    find_calibrated_profile,
    save_calibrated_profile,
)
from .sensor_calibration import measure_sensor_state_auto, summarize_calibrations
from .discovery_engine import DiscoveryEngine
from .learning_session import ReadOnlyLearningSession
from .protocol_grammar import SemanticBehavior
from .teacher_registry import read_teacher_labels
from .transition_sources import infer_calibrated_transition_sources


class GuidedDiscoveryCancelled(RuntimeError):
    """The user cancelled a guided read-only capture before it completed."""


@dataclass(frozen=True)
class GuidedStep:
    """One plain-English capture instruction presented by a caller."""

    index: int
    total: int
    title: str
    instructions: str


@dataclass(frozen=True)
class AutomaticDiscoveryOutcome:
    """One complete safe Automatic Discovery pass and its reusable engine."""

    result: Any
    engine: DiscoveryEngine
    research_plan: Any | None = None


@dataclass(frozen=True)
class GuidedDpiLearningOutcome:
    """Result of the five-sample DPI-button observation workflow."""

    learned: Any
    controls: tuple[Any, ...]
    samples: tuple[Any, ...]
    action_identified: bool
    teacher_used: bool


@dataclass(frozen=True)
class DeepDpiLearningOutcome:
    """Full teacher-free DPI-stage calibration suitable for runtime notifications."""

    result: Any
    profile_path: Any | None
    measured_cycle: tuple[CalibratedDpiState, ...]
    raw_mappings: tuple[Any, ...]
    wrap_confirmed: bool
    action_identified: bool
    transition_sources: tuple[Any, ...] = ()
    reused_profile: bool = False


@dataclass(frozen=True)
class GuidedDiscoveryOutcome:
    """Passive discovery plus optional read-only DPI-action learning."""

    result: Any
    learning: GuidedDpiLearningOutcome | None = None
    learning_available: bool = False
    learning_skipped_reason: str | None = None

    @property
    def dpi_writable(self) -> bool:
        capability = self.result.capabilities.get("dpi")
        return bool(capability and capability.writable)

    @property
    def polling_writable(self) -> bool:
        capability = self.result.capabilities.get("report_rate")
        return bool(capability and capability.writable)

    @property
    def dpi_action_identified(self) -> bool:
        return bool(self.learning and self.learning.action_identified)


PromptCallback = Callable[[GuidedStep], bool]
ProgressCallback = Callable[[str], None]


def _full_access_preflight(session: ReadOnlyLearningSession) -> tuple[str, ...]:
    readable, unreadable = session.hidraw_access_report()
    if unreadable:
        raise PermissionError(
            "full-access discovery requires every correlated hidraw sibling to be readable; "
            "still unavailable: " + ", ".join(unreadable)
        )
    return tuple(str(path) for path in readable)


def _check_sample_access(sample: Any, *, require_complete_access: bool) -> None:
    if require_complete_access and sample.unreadable_hidraw_paths:
        raise PermissionError(
            "a hidraw sibling became unavailable during full-access capture: "
            + ", ".join(sample.unreadable_hidraw_paths)
        )


def _sample_summary(sample: Any, *, prefix: str = "Captured") -> str:
    return (
        f"{prefix} {len(sample.action.hid_reports)} HID report(s), "
        f"{len(sample.action.evdev_events)} input event(s), and "
        f"{len(sample.action.feature_changes)} read-only feature change(s)."
    )


def _action_identified(learned: Any) -> bool:
    """Return whether repeated action-specific evidence supports the DPI action.

    This is deliberately an observation-only statement. It does not create or
    promote a learned operation and therefore cannot authorize a hardware write.
    """

    teacher_transitions = any(
        sample.teacher_before_state or sample.teacher_state
        for sample in learned.samples
    )
    if teacher_transitions:
        candidates = tuple(learned.discriminative_trigger_candidates)
        hypotheses = tuple(learned.hypotheses)
    else:
        refinement = refine_teacher_free(learned)
        candidates = tuple(item.candidate for item in refinement.candidates)
        hypotheses = tuple(refinement.hypotheses)
    return bool(candidates) or any(
        hypothesis.behavior is SemanticBehavior.DPI_CYCLE_TRIGGER
        for hypothesis in hypotheses
    )


def run_guided_dpi_learning(
    selected: Any,
    result: Any,
    engine: DiscoveryEngine,
    *,
    prompt: PromptCallback,
    progress: ProgressCallback | None = None,
    seconds: float = 1.5,
    teacher: bool = False,
    require_complete_access: bool = False,
    session_factory: Callable[..., ReadOnlyLearningSession] = ReadOnlyLearningSession,
    teacher_reader: Callable[[Any], dict[str, Any]] = read_teacher_labels,
) -> GuidedDpiLearningOutcome:
    """Capture the existing two controls and three DPI-button samples read-only."""

    if seconds <= 0:
        raise ValueError("capture window must be greater than zero")
    report = progress or (lambda _message: None)
    session = session_factory(result.device, engine.descriptors)

    if require_complete_access:
        readable = _full_access_preflight(session)
        report(
            f"Full-access preflight: {len(readable)}/{len(result.device.hidraw_nodes)} "
            "correlated HID interface(s) readable."
        )

    steps = (
        GuidedStep(
            1,
            5,
            "Quiet control",
            "Leave the mouse completely untouched. This teaches Mouse Control what idle traffic looks like.",
        ),
        GuidedStep(
            2,
            5,
            "Normal-use control",
            "Move the mouse normally and left-click once. Do not press the DPI/profile button.",
        ),
        GuidedStep(
            3,
            5,
            "DPI-button sample",
            "Keep the mouse still and press the DPI button exactly once during the sample.",
        ),
        GuidedStep(
            4,
            5,
            "DPI-button sample",
            "Keep the mouse still and press the DPI button exactly once during the sample.",
        ),
        GuidedStep(
            5,
            5,
            "DPI-button sample",
            "Keep the mouse still and press the DPI button exactly once during the sample.",
        ),
    )

    controls: list[Any] = []
    for step in steps[:2]:
        if not prompt(step):
            raise GuidedDiscoveryCancelled("guided DPI learning cancelled")
        sample = session.observe_action(seconds=seconds)
        _check_sample_access(sample, require_complete_access=require_complete_access)
        controls.append(sample)
        report(_sample_summary(sample))

    reader = (lambda: teacher_reader(selected)) if teacher else None
    samples: list[Any] = []
    for step in steps[2:]:
        # Preserve the existing isolation rule: teacher reads happen before the
        # prompt/capture window so teacher protocol traffic cannot leak into the
        # blind learner's raw acquisition window.
        teacher_before = dict(reader()) if reader is not None else {}
        if not prompt(step):
            raise GuidedDiscoveryCancelled("guided DPI learning cancelled")
        sample = session.observe_action(
            seconds=seconds,
            teacher_reader=reader,
            teacher_before_state=teacher_before,
        )
        _check_sample_access(sample, require_complete_access=require_complete_access)
        samples.append(sample)
        report(_sample_summary(sample))
        if sample.unreadable_hidraw_paths:
            report(
                "Skipped unreadable HID interface(s): "
                + ", ".join(sample.unreadable_hidraw_paths)
            )

    learned = session.analyze(
        samples,
        trigger_behavior=SemanticBehavior.DPI_CYCLE_TRIGGER,
        control_samples=controls,
    )
    return GuidedDpiLearningOutcome(
        learned=learned,
        controls=tuple(controls),
        samples=tuple(samples),
        action_identified=_action_identified(learned),
        teacher_used=reader is not None,
    )


def _rounded_stage_label(measured_cpi: float) -> int:
    # CPI calibration is physical evidence, not a claim about firmware labels.
    # A 50-CPI display quantum avoids false precision while preserving stage identity.
    return max(50, int(round(float(measured_cpi) / 50.0) * 50))


def _same_physical_stage(left: CalibratedDpiState, right: CalibratedDpiState) -> bool:
    high = max(float(left.measured_cpi), float(right.measured_cpi), 1.0)
    return abs(float(left.measured_cpi) - float(right.measured_cpi)) / high <= 0.12


def _distance_label(distance_mm: float) -> str:
    """Show the calibration distance in familiar imperial and precise metric units."""

    return f"{distance_mm / 25.4:g} inches ({distance_mm:g} mm)"


def _stable_node_identity(node: Any) -> dict[str, object]:
    """Return path-independent interface facts safe for calibrated profiles."""

    return {
        "bus": node.bus,
        "vendor_id": node.vendor_id,
        "product_id": node.product_id,
        "interface_number": node.interface_number,
        "descriptor_sha256": node.descriptor_sha256,
        "name": node.name or "",
        "uniq": node.uniq or "",
    }


def _feature_report_metadata(session: ReadOnlyLearningSession) -> dict[object, dict[str, object]]:
    metadata: dict[object, dict[str, object]] = {}
    for node, descriptor in session.descriptors.items():
        identity = _stable_node_identity(node)
        for definition in descriptor.feature_reports:
            length = definition.byte_length if definition.report_id else definition.byte_length + 1
            key = session._feature_key(node, definition.report_id)
            metadata[key] = {
                **identity,
                "report_id": int(definition.report_id),
                "report_length": max(1, int(length)),
            }
    return metadata


def _profile_measured_cycle(profile: Any) -> tuple[CalibratedDpiState, ...]:
    cycle = profile.get("dpi_cycle", {}) if isinstance(profile, dict) else {}
    states = cycle.get("states", ()) if isinstance(cycle, dict) else ()
    result: list[CalibratedDpiState] = []
    for state in states if isinstance(states, list) else ():
        if not isinstance(state, dict):
            continue
        try:
            result.append(
                CalibratedDpiState(
                    configured_dpi=int(state["configured_dpi"]),
                    measured_cpi=float(state["measured_cpi"]),
                    polling_hz=(
                        None if state.get("polling_hz") is None else int(state["polling_hz"])
                    ),
                    confidence=str(state["confidence"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            return ()
    return tuple(result)


def run_deep_dpi_stage_learning(
    selected: Any,
    result: Any,
    engine: DiscoveryEngine,
    *,
    prompt: PromptCallback,
    progress: ProgressCallback | None = None,
    distance_mm: float = 254.0,
    calibration_passes: int = 5,
    calibration_seconds: float = 8.0,
    transition_seconds: float = 1.5,
    max_stages: int = 8,
    session_factory: Callable[..., ReadOnlyLearningSession] = ReadOnlyLearningSession,
) -> DeepDpiLearningOutcome:
    """Learn a complete physical DPI cycle without a vendor teacher or writes.

    Physical stage calibration and runtime-source inference are independent.
    The expensive ruler/wrap experiment is an exact-device first-run operation:
    once a validated read-only profile exists, later setup runs reuse it.
    """
    if distance_mm <= 0 or calibration_passes <= 0 or calibration_seconds <= 0:
        raise ValueError("calibration distance, passes, and capture window must be positive")
    if transition_seconds <= 0 or max_stages < 2:
        raise ValueError("transition window must be positive and max_stages must be at least two")
    if result.device.ambiguous:
        raise PermissionError("physical identity is ambiguous; calibrated learning cannot be persisted safely")

    report = progress or (lambda _message: None)
    existing = find_calibrated_profile(result.device)
    if existing is not None:
        profile_path, profile = existing
        cycle = profile.get("dpi_cycle", {})
        transition_sources = tuple(profile.get("transition_sources", ()))
        if not transition_sources and profile.get("raw_mappings"):
            transition_sources = tuple(profile["raw_mappings"])
        report("✓ Reusing existing exact-device DPI calibration; ruler/wrap learning is not repeated")
        return DeepDpiLearningOutcome(
            result=result,
            profile_path=profile_path,
            measured_cycle=_profile_measured_cycle(profile),
            raw_mappings=(),
            wrap_confirmed=bool(cycle.get("wrap_confirmed")) if isinstance(cycle, dict) else True,
            action_identified=True,
            transition_sources=transition_sources,
            reused_profile=True,
        )

    if not result.device.hidraw_nodes or not engine.descriptors:
        raise PermissionError("no readable correlated HID descriptor path is available for stage learning")

    session = session_factory(result.device, engine.descriptors)
    motion_controls: list[Any] = []

    def calibrate(stage_number: int) -> CalibratedDpiState:
        measurements = []
        for pass_index in range(1, calibration_passes + 1):
            step = GuidedStep(
                pass_index,
                calibration_passes,
                f"Calibrate DPI stage {stage_number}",
                (
                    "Place the mouse at a ruler start mark. After starting the sample, move exactly "
                    f"{_distance_label(distance_mm)} in one straight direction. "
                    f"Pass {pass_index}/{calibration_passes}."
                ),
            )
            if not prompt(step):
                raise GuidedDiscoveryCancelled("calibrated DPI-stage learning cancelled")
            capture = capture_calibrated_motion(
                session,
                evdev_path=selected.path,
                seconds=calibration_seconds,
            )
            measurement = measure_sensor_state_auto(
                capture.calibration_events,
                distance_mm=distance_mm,
            )
            measurements.append(measurement)
            motion_controls.append(capture.sample)
            report(
                f"Stage {stage_number} pass {pass_index}: ~{measurement.rounded_dpi} CPI; "
                f"straightness {measurement.straightness * 100:.1f}%"
            )
        summary = summarize_calibrations(measurements)
        label = _rounded_stage_label(summary.estimated_dpi)
        report(
            f"Stage {stage_number}: measured ~{summary.estimated_dpi:.1f} CPI "
            f"({summary.confidence} confidence; display label ~{label})"
        )
        return CalibratedDpiState(
            configured_dpi=label,
            measured_cpi=summary.estimated_dpi,
            polling_hz=summary.standard_polling_hz,
            confidence=summary.confidence,
        )

    report("• First-time DPI calibration: learning the current physical stage…")
    initial = calibrate(1)
    measured_cycle: list[CalibratedDpiState] = [initial]
    transition_samples: list[Any] = []
    resulting_states: list[CalibratedDpiState] = []
    wrap_confirmed = False

    for transition_index in range(1, max_stages + 1):
        step = GuidedStep(
            transition_index,
            max_stages,
            "Advance physical DPI stage",
            (
                "Keep the mouse still. After starting the sample, press the physical DPI/profile "
                "button exactly once. Mouse Control will then calibrate the resulting stage."
            ),
        )
        if not prompt(step):
            raise GuidedDiscoveryCancelled("calibrated DPI-stage learning cancelled")
        transition = session.observe_action(seconds=transition_seconds)
        transition_samples.append(transition)
        report(_sample_summary(transition, prefix="Transition captured"))

        state = calibrate(len(measured_cycle) + 1)
        resulting_states.append(state)
        measured_cycle.append(state)
        if len(measured_cycle) >= 3 and _same_physical_stage(state, initial):
            wrap_confirmed = True
            report("✓ Physical DPI cycle learned and wraparound confirmed")
            report("✓ DPI stage behavior physically calibrated")
            break

    learned = session.analyze(
        transition_samples,
        trigger_behavior=SemanticBehavior.DPI_CYCLE_TRIGGER,
        control_samples=motion_controls,
    )
    refinement = refine_teacher_free(learned)
    action_specific_keys = frozenset(shape.report_key for shape in refinement.report_shapes)
    descriptor_roles = {
        (candidate.report_key, candidate.offset): session.descriptor_roles_for_candidate(candidate)
        for candidate in learned.report_candidates
    }
    mappings = (
        infer_calibrated_raw_mappings(
            transition_samples,
            resulting_states,
            allowed_report_keys=set(action_specific_keys),
            descriptor_roles=descriptor_roles,
        )
        if action_specific_keys else ()
    )
    cycle = calibrated_cycle_hypothesis(resulting_states) if wrap_confirmed else None
    action_identified = _action_identified(learned)
    profile_path = None
    transition_sources: tuple[Any, ...] = ()

    configured_cycle = (
        tuple(state.configured_dpi for state in measured_cycle[:-1])
        if wrap_confirmed
        else ()
    )
    if wrap_confirmed and configured_cycle:
        evdev_identities = {
            os.fspath(node.path): _stable_node_identity(node)
            for node in result.device.evdev_nodes
        }
        transition_sources = infer_calibrated_transition_sources(
            transition_samples,
            resulting_states,
            cycle_order=configured_cycle,
            raw_mappings=mappings,
            contrastive_candidates=refinement.candidates,
            guided_report_shapes=refinement.report_shapes,
            control_samples=motion_controls,
            evdev_source_identities=evdev_identities,
            feature_report_metadata=_feature_report_metadata(session),
        )

    if wrap_confirmed and cycle is not None and cycle.confidence == "validated":
        profile = calibrated_profile_data(
            device=result.device,
            configured_cycle=configured_cycle,
            measured_cycle=tuple(measured_cycle),
            mappings=mappings,
            action_report_keys=action_specific_keys,
            transition_sources=transition_sources,
        )
        profile_path = save_calibrated_profile(profile)
        report("✓ Physical DPI cycle learned")
        if transition_sources:
            report("✓ Runtime DPI source learned")
            report("✓ Saved exact-device calibrated read-only DPI event profile")
        else:
            report("• Physical calibration saved; runtime source still unresolved")
    elif not wrap_confirmed:
        report("? Full DPI-cycle wrap was not observed; no runtime profile was promoted")
    elif cycle is None or cycle.confidence != "validated":
        report("? DPI-cycle evidence did not reach validated confidence; no runtime profile was promoted")
    else:
        report("• No absolute HID stage register was found")
        report("? Physical DPI cycle is learned, but no stable runtime transition source has been identified yet")

    return DeepDpiLearningOutcome(
        result=result,
        profile_path=profile_path,
        measured_cycle=tuple(measured_cycle),
        raw_mappings=tuple(mappings),
        wrap_confirmed=wrap_confirmed,
        action_identified=action_identified,
        transition_sources=tuple(transition_sources),
    )


def run_automatic_discovery(
    selected: Any,
    *,
    progress: ProgressCallback | None = None,
    engine_factory: Callable[[], DiscoveryEngine] = DiscoveryEngine,
) -> AutomaticDiscoveryOutcome:
    """Run the shared comprehensive safe discovery engine with progress events."""
    report = progress or (lambda _message: None)
    engine = engine_factory()
    result = engine.discover(selected, progress=report)
    return AutomaticDiscoveryOutcome(result=result, engine=engine, research_plan=engine.research_plan(result))


def run_guided_discovery(
    selected: Any,
    *,
    prompt: PromptCallback,
    progress: ProgressCallback | None = None,
    seconds: float = 1.5,
    teacher: bool = False,
    engine_factory: Callable[[], DiscoveryEngine] = DiscoveryEngine,
    session_factory: Callable[..., ReadOnlyLearningSession] = ReadOnlyLearningSession,
) -> GuidedDiscoveryOutcome:
    """Run passive Automatic Discovery, then offer the safe DPI learner if useful.

    No generic polling writer exists here. Existing PROVEN exact-model polling
    evidence is surfaced by DiscoveryEngine; otherwise polling remains unchanged.
    """

    report = progress or (lambda _message: None)
    automatic = run_automatic_discovery(
        selected,
        progress=report,
        engine_factory=engine_factory,
    )
    engine = automatic.engine
    result = automatic.result

    dpi = result.capabilities.get("dpi")
    if dpi is not None and dpi.writable:
        return GuidedDiscoveryOutcome(
            result=result,
            learning_skipped_reason="DPI control is already safely proven for this mouse.",
        )
    if result.device.ambiguous:
        return GuidedDiscoveryOutcome(
            result=result,
            learning_skipped_reason=(
                "Mouse identity is ambiguous, so guided hardware learning was not bound to a writable identity."
            ),
        )
    if not result.device.hidraw_nodes or not engine.descriptors:
        return GuidedDiscoveryOutcome(
            result=result,
            learning_skipped_reason=(
                "No readable HID descriptor path is available for safe DPI-button learning."
            ),
        )

    learning = run_guided_dpi_learning(
        selected,
        result,
        engine,
        prompt=prompt,
        progress=report,
        seconds=seconds,
        teacher=teacher,
        session_factory=session_factory,
    )
    return GuidedDiscoveryOutcome(
        result=result,
        learning=learning,
        learning_available=True,
    )
