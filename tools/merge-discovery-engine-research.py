from pathlib import Path

ROOT = Path('.')


def replace(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text()
    if old not in text:
        raise SystemExit(f'expected block not found in {path}: {old[:80]!r}')
    target.write_text(text.replace(old, new, 1))


# ---------------------------------------------------------------------------
# 1. Formal research-plan model: Discovery Engine decides what evidence exists,
#    what can be probed reversibly, and when deeper read-side learning is useful.
# ---------------------------------------------------------------------------
(ROOT / 'src/mouse_control/discovery_research.py').write_text(r'''"""Research orchestration policy for Automatic Discovery.

This module deliberately separates three things that were historically mixed:

* runtime authority -- only PROVEN operations may write during normal use;
* reversible research probes -- DEMONSTRATED exact-model grammars may be tested
  under explicit setup/research authorization; and
* deeper read-side learning -- used when an unknown device has no executable
  write grammar yet, so Mouse Control can still learn stage events/notifications.

A structural repertoire match is evidence about *where to investigate*.  It is
never write authority by itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .learned_operations import LearnedOperationState
from .protocol_grammar import SemanticBehavior, WriteScope


class ResearchStatus(str, Enum):
    PROVEN = "proven"
    REVERSIBLE_PROBE_READY = "reversible-probe-ready"
    STRUCTURAL_CANDIDATE = "structural-candidate"
    KNOWN_READ_ONLY = "known-read-only"
    NO_EVIDENCE = "no-evidence"


@dataclass(frozen=True)
class CapabilityResearchPlan:
    semantic: str
    status: ResearchStatus
    candidate_transports: tuple[str, ...] = ()
    reason: str = ""

    @property
    def probe_ready(self) -> bool:
        return self.status is ResearchStatus.REVERSIBLE_PROBE_READY

    @property
    def writable(self) -> bool:
        return self.status is ResearchStatus.PROVEN


@dataclass(frozen=True)
class DiscoveryResearchPlan:
    dpi: CapabilityResearchPlan
    polling: CapabilityResearchPlan
    unknown_protocol: bool
    deeper_learning_recommended: bool
    reason: str

    @property
    def reversible_probe_available(self) -> bool:
        return self.dpi.probe_ready or self.polling.probe_ready


def _candidate_transports(repertoire_candidates: Iterable[object]) -> tuple[str, ...]:
    transports: set[str] = set()
    for candidate in repertoire_candidates:
        family = getattr(candidate, "family", None)
        if family is None or getattr(family, "write_scope", WriteScope.NEVER) is WriteScope.NEVER:
            continue
        for transport in getattr(family, "transports", ()):
            transports.add(getattr(transport, "value", str(transport)))
    return tuple(sorted(transports))


def build_discovery_research_plan(
    result,
    repertoire_candidates,
    *,
    learned_operation_store,
    learned_polling_store,
) -> DiscoveryResearchPlan:
    """Build the next safe research step from evidence already collected.

    This function never opens hardware and never grants authority.  Its output is
    an auditable orchestration decision consumed by setup.
    """
    protocol_known = result.protocol is not None
    transports = _candidate_transports(repertoire_candidates)

    def capability_proven(name: str) -> bool:
        capability = result.capabilities.get(name)
        return bool(capability and capability.writable)

    if protocol_known:
        dpi = CapabilityResearchPlan(
            "dpi",
            ResearchStatus.PROVEN if capability_proven("dpi") else ResearchStatus.KNOWN_READ_ONLY,
            reason=(
                "Known protocol exposes a proven writable DPI operation."
                if capability_proven("dpi")
                else "Known protocol was identified; its DPI policy remains authoritative."
            ),
        )
        polling = CapabilityResearchPlan(
            "report_rate",
            ResearchStatus.PROVEN if capability_proven("report_rate") else ResearchStatus.KNOWN_READ_ONLY,
            reason=(
                "Known protocol exposes a proven writable polling operation."
                if capability_proven("report_rate")
                else "Known protocol was identified; its polling policy remains authoritative."
            ),
        )
        return DiscoveryResearchPlan(
            dpi=dpi,
            polling=polling,
            unknown_protocol=False,
            deeper_learning_recommended=False,
            reason="A proven protocol implementation is already bound; do not substitute speculative generic learning.",
        )

    dpi_status = ResearchStatus.PROVEN if capability_proven("dpi") else ResearchStatus.NO_EVIDENCE
    dpi_reason = "PROVEN exact-model learned DPI operation is already available." if capability_proven("dpi") else ""
    if dpi_status is not ResearchStatus.PROVEN:
        found = learned_operation_store.find_for_physical(
            result.device,
            behavior=SemanticBehavior.DPI_VALUE,
            proven_only=False,
        )
        if found is not None:
            _path, operation = found
            if operation.state is LearnedOperationState.DEMONSTRATED:
                dpi_status = ResearchStatus.REVERSIBLE_PROBE_READY
                dpi_reason = (
                    "An exact-model DEMONSTRATED DPI grammar exists. Discovery may run a bounded reversible "
                    "generic probe, but normal runtime writes remain disabled until physical promotion."
                )

    polling_status = ResearchStatus.PROVEN if capability_proven("report_rate") else ResearchStatus.NO_EVIDENCE
    polling_reason = (
        "PROVEN exact-model learned polling state machine is already available."
        if capability_proven("report_rate") else ""
    )
    if polling_status is not ResearchStatus.PROVEN:
        found = learned_polling_store.find_for_physical(result.device, proven_only=False)
        if found is not None:
            _path, operation = found
            state = getattr(operation, "state", None)
            if getattr(state, "value", state) == "demonstrated":
                polling_status = ResearchStatus.REVERSIBLE_PROBE_READY
                polling_reason = (
                    "An exact-model DEMONSTRATED polling state machine exists. Discovery may run its bounded "
                    "generic replay/promotion methodology; runtime writes remain disabled until promotion."
                )

    if transports:
        if dpi_status is ResearchStatus.NO_EVIDENCE:
            dpi_status = ResearchStatus.STRUCTURAL_CANDIDATE
            dpi_reason = (
                "Descriptor/repertoire evidence exposes a plausible writable transport, but no executable DPI "
                "transaction grammar has been demonstrated yet."
            )
        if polling_status is ResearchStatus.NO_EVIDENCE:
            polling_status = ResearchStatus.STRUCTURAL_CANDIDATE
            polling_reason = (
                "Descriptor/repertoire evidence exposes a plausible writable transport, but no executable polling "
                "transaction grammar has been demonstrated yet."
            )

    if not dpi_reason:
        dpi_reason = "No evidence-backed DPI write transaction could be constructed during automatic discovery."
    if not polling_reason:
        polling_reason = "No evidence-backed polling write transaction could be constructed during automatic discovery."

    probe_ready = (
        dpi_status is ResearchStatus.REVERSIBLE_PROBE_READY
        or polling_status is ResearchStatus.REVERSIBLE_PROBE_READY
    )
    any_proven = (
        dpi_status is ResearchStatus.PROVEN
        or polling_status is ResearchStatus.PROVEN
    )
    # Deeper stage learning is the fallback only after an unknown device has no
    # immediately executable generic research probe.  Structural candidates are
    # still useful inputs to deeper learning; they do not block it.
    deeper = not any_proven and not probe_ready
    reason = (
        "A demonstrated reversible write grammar is ready for research verification before deeper learning."
        if probe_ready
        else (
            "Automatic Discovery found no executable generic write grammar. Offer deeper protocol learning so "
            "stage/event behavior can be calibrated and persisted without granting write authority."
            if deeper
            else "Writable authority is already proven for at least one hardware capability."
        )
    )
    return DiscoveryResearchPlan(
        dpi=CapabilityResearchPlan("dpi", dpi_status, transports, dpi_reason),
        polling=CapabilityResearchPlan("report_rate", polling_status, transports, polling_reason),
        unknown_protocol=True,
        deeper_learning_recommended=deeper,
        reason=reason,
    )
''')

# Add a research-plan method to DiscoveryEngine without contaminating DiscoveryResult/profile schema.
replace(
    'src/mouse_control/discovery_engine.py',
    '    def save_profile(self, result: DiscoveryResult) -> Path | None:\n',
    '''    def research_plan(self, result: DiscoveryResult):\n        """Return the next evidence-driven research step for this discovery result."""\n        from .discovery_research import build_discovery_research_plan\n\n        return build_discovery_research_plan(\n            result,\n            self._repertoire_candidates,\n            learned_operation_store=self._learned_operation_store,\n            learned_polling_store=self._learned_polling_store,\n        )\n\n    def save_profile(self, result: DiscoveryResult) -> Path | None:\n''',
)

# ---------------------------------------------------------------------------
# 2. Full calibrated stage-cycle learner. This promotes the existing research
#    CLI methodology into a reusable service used by setup.
# ---------------------------------------------------------------------------
replace(
    'src/mouse_control/guided_discovery.py',
    'from .contrastive_inference import refine_teacher_free\n',
    '''from .contrastive_inference import refine_teacher_free\nfrom .calibrated_discovery import (\n    CalibratedDpiState,\n    calibrated_cycle_hypothesis,\n    capture_calibrated_motion,\n    infer_calibrated_raw_mappings,\n)\nfrom .calibrated_profiles import calibrated_profile_data, save_calibrated_profile\nfrom .sensor_calibration import measure_sensor_state_auto, summarize_calibrations\n''',
)

replace(
    'src/mouse_control/guided_discovery.py',
    'class GuidedDiscoveryOutcome:\n',
    '''class DeepDpiLearningOutcome:\n    """Full teacher-free DPI-stage calibration suitable for runtime notifications."""\n\n    result: Any\n    profile_path: Any | None\n    measured_cycle: tuple[CalibratedDpiState, ...]\n    raw_mappings: tuple[Any, ...]\n    wrap_confirmed: bool\n    action_identified: bool\n\n\n@dataclass(frozen=True)\nclass GuidedDiscoveryOutcome:\n''',
)
# The replacement above consumed the original dataclass decorator; fix duplicated shape.
text = (ROOT / 'src/mouse_control/guided_discovery.py').read_text()
text = text.replace('@dataclass(frozen=True)\nclass DeepDpiLearningOutcome:', '@dataclass(frozen=True)\nclass DeepDpiLearningOutcome:', 1)
(ROOT / 'src/mouse_control/guided_discovery.py').write_text(text)

# Append calibrated learner before run_automatic_discovery.
replace(
    'src/mouse_control/guided_discovery.py',
    '\ndef run_automatic_discovery(\n',
    r'''
def _rounded_stage_label(measured_cpi: float) -> int:
    # CPI calibration is physical evidence, not a claim about firmware labels.
    # A 50-CPI display quantum avoids false precision while preserving stage identity.
    return max(50, int(round(float(measured_cpi) / 50.0) * 50))


def _same_physical_stage(left: CalibratedDpiState, right: CalibratedDpiState) -> bool:
    high = max(float(left.measured_cpi), float(right.measured_cpi), 1.0)
    return abs(float(left.measured_cpi) - float(right.measured_cpi)) / high <= 0.12


def run_deep_dpi_stage_learning(
    selected: Any,
    result: Any,
    engine: DiscoveryEngine,
    *,
    prompt: PromptCallback,
    progress: ProgressCallback | None = None,
    distance_mm: float = 254.0,
    calibration_passes: int = 3,
    calibration_seconds: float = 8.0,
    transition_seconds: float = 1.5,
    max_stages: int = 8,
    session_factory: Callable[..., ReadOnlyLearningSession] = ReadOnlyLearningSession,
) -> DeepDpiLearningOutcome:
    """Learn a complete physical DPI cycle without a vendor teacher or writes.

    Each state is physically calibrated from evdev motion while correlated hidraw
    streams are observed. DPI-button transitions are captured separately. The
    cycle ends only after at least two distinct states and a physical wrap back to
    the initial state. A calibrated read-only profile is saved only when a
    persistent action-specific raw state field is found and cycle semantics are
    validated.
    """
    if distance_mm <= 0 or calibration_passes <= 0 or calibration_seconds <= 0:
        raise ValueError("calibration distance, passes, and capture window must be positive")
    if transition_seconds <= 0 or max_stages < 2:
        raise ValueError("transition window must be positive and max_stages must be at least two")
    if result.device.ambiguous:
        raise PermissionError("physical identity is ambiguous; calibrated learning cannot be persisted safely")
    if not result.device.hidraw_nodes or not engine.descriptors:
        raise PermissionError("no readable correlated HID descriptor path is available for stage learning")

    report = progress or (lambda _message: None)
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
                    f"Place the mouse at a ruler start mark. After starting the sample, move exactly "
                    f"{distance_mm:g} mm in one straight direction. Pass {pass_index}/{calibration_passes}."
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

    report("• Calibrating the current physical DPI stage…")
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
            report("✓ Physical DPI cycle wrapped back to the initial stage")
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

    if (
        wrap_confirmed
        and mappings
        and cycle is not None
        and cycle.confidence == "validated"
    ):
        # configured_cycle excludes the final wrap-confirmation state.
        configured_cycle = tuple(state.configured_dpi for state in measured_cycle[:-1])
        profile = calibrated_profile_data(
            device=result.device,
            configured_cycle=configured_cycle,
            measured_cycle=tuple(measured_cycle),
            mappings=mappings,
            action_report_keys=action_specific_keys,
        )
        profile_path = save_calibrated_profile(profile)
        report("✓ Saved exact-device calibrated read-only DPI event profile")
    elif not wrap_confirmed:
        report("? Full DPI-cycle wrap was not observed; no runtime profile was promoted")
    elif not mappings:
        report("? DPI stages changed physically, but no unambiguous persistent raw state field was found")
    else:
        report("? DPI-cycle evidence did not reach validated confidence; no runtime profile was promoted")

    return DeepDpiLearningOutcome(
        result=result,
        profile_path=profile_path,
        measured_cycle=tuple(measured_cycle),
        raw_mappings=tuple(mappings),
        wrap_confirmed=wrap_confirmed,
        action_identified=action_identified,
    )


def run_automatic_discovery(
''',
)

# Automatic outcome carries research plan so setup can choose the correct next methodology.
replace(
    'src/mouse_control/guided_discovery.py',
    'class AutomaticDiscoveryOutcome:\n    """One complete safe Automatic Discovery pass and its reusable engine."""\n\n    result: Any\n    engine: DiscoveryEngine\n',
    'class AutomaticDiscoveryOutcome:\n    """One complete safe Automatic Discovery pass and its reusable engine."""\n\n    result: Any\n    engine: DiscoveryEngine\n    research_plan: Any | None = None\n',
)
replace(
    'src/mouse_control/guided_discovery.py',
    '    return AutomaticDiscoveryOutcome(result=result, engine=engine)\n',
    '    return AutomaticDiscoveryOutcome(result=result, engine=engine, research_plan=engine.research_plan(result))\n',
)

# ---------------------------------------------------------------------------
# 3. Setup controller consumes the plan and refreshes runtime after calibrated
#    profile creation. Deeper learning is no longer "all non-writable mice".
# ---------------------------------------------------------------------------
replace(
    'src/mouse_control/setup_tui.py',
    '        self.guided_outcome: GuidedDiscoveryOutcome | None = None\n',
    '        self.guided_outcome: GuidedDiscoveryOutcome | None = None\n        self.deep_learning_outcome: Any | None = None\n        self.research_plan: Any | None = None\n        self.discovery_engine: Any | None = None\n',
)
replace(
    'src/mouse_control/setup_tui.py',
    '        self.guided_outcome = None\n        self.polling_measurement = None\n',
    '        self.guided_outcome = None\n        self.deep_learning_outcome = None\n        self.research_plan = None\n        self.discovery_engine = None\n        self.polling_measurement = None\n',
)
replace(
    'src/mouse_control/setup_tui.py',
    '        self.discovery_result = outcome.result if hasattr(outcome, "result") else outcome\n        self.discovery_complete = True\n',
    '        self.discovery_result = outcome.result if hasattr(outcome, "result") else outcome\n        self.discovery_engine = getattr(outcome, "engine", None)\n        self.research_plan = getattr(outcome, "research_plan", None)\n        self.discovery_complete = True\n',
)
replace(
    'src/mouse_control/setup_tui.py',
    '    def guided_discovery_available(self) -> bool:\n        # The generic guided learner is intentionally DPI-observation only.\n        return not self.choices.dpi_writable and not self.discovery_skipped\n',
    '''    def guided_discovery_available(self) -> bool:\n        # Deeper learning is specifically the fallback for an unknown protocol\n        # when Automatic Discovery has no executable generic write probe.\n        return bool(\n            self.discovery_complete\n            and not self.discovery_skipped\n            and self.research_plan is not None\n            and getattr(self.research_plan, "deeper_learning_recommended", False)\n        )\n''',
)
replace(
    'src/mouse_control/setup_tui.py',
    '        if self.no_write_path:\n            lines.append("✓ Discovery complete: no verified host-accessible DPI/polling write path")\n            lines.append("✓ Button remapping remains available through evdev")\n',
    '''        if self.research_plan is not None:\n            lines.append(f"• DPI research state: {self.research_plan.dpi.status.value}")\n            lines.append(f"• Polling research state: {self.research_plan.polling.status.value}")\n            if self.research_plan.reversible_probe_available:\n                lines.append("! A bounded reversible learned write probe is available before deeper learning")\n            elif self.research_plan.deeper_learning_recommended:\n                lines.append("✓ Deeper protocol learning is available for physical DPI-stage/event adaptation")\n\n        if self.no_write_path:\n            lines.append("✓ Discovery complete: no verified host-accessible DPI/polling write path")\n            lines.append("✓ Button remapping remains available through evdev")\n''',
)
# Add deep outcome application before detail_rows.
replace(
    'src/mouse_control/setup_tui.py',
    '    def detail_rows(self) -> list[DisplayRow]:\n',
    '''    def apply_deep_learning_outcome(self, outcome: Any) -> None:\n        self.deep_learning_outcome = outcome\n        if getattr(outcome, "profile_path", None) is not None:\n            self.refresh_discovery_backend(\n                status="Calibrated DPI-stage behavior learned; runtime notifications are now available."\n            )\n        elif getattr(outcome, "wrap_confirmed", False):\n            self.status = (\n                "Physical DPI cycle was observed, but no unambiguous persistent HID stage field was promoted."\n            )\n        else:\n            self.status = "Deeper DPI-stage learning finished without a complete validated cycle."\n\n    def detail_rows(self) -> list[DisplayRow]:\n''',
)
replace(
    'src/mouse_control/setup_tui.py',
    '                rows.append(DisplayRow("Continue deeper guided DPI learning", 1))\n',
    '                rows.append(DisplayRow("Run deeper protocol / DPI-stage learning", 1))\n',
)

# ---------------------------------------------------------------------------
# 4. TUI runs the full calibrated learner and prompts immediately after
#    automatic discovery when that is the evidence-driven next step.
# ---------------------------------------------------------------------------
replace(
    'src/mouse_control/setup_tui_curses.py',
    '    GuidedDiscoveryCancelled, GuidedStep, run_automatic_discovery, run_guided_discovery,\n',
    '    GuidedDiscoveryCancelled, GuidedStep, run_automatic_discovery, run_deep_dpi_stage_learning,\n',
)
replace(
    'src/mouse_control/setup_tui_curses.py',
    '        self.controller.apply_automatic_discovery(outcome)\n\n    def _run_polling_measurement(self) -> None:\n',
    '''        self.controller.apply_automatic_discovery(outcome)\n        plan = getattr(outcome, "research_plan", None)\n        if plan is not None and getattr(plan, "reversible_probe_available", False):\n            self._confirm(\n                "Reversible write research available",\n                [\n                    "Mouse Control found an exact-model DEMONSTRATED transaction grammar.",\n                    "It is not runtime write authority yet; physical promotion is still required.",\n                    "Deeper read-side learning is deferred until this evidence-backed probe is resolved.",\n                ],\n                yes="Enter Continue",\n                no="Esc Continue",\n            )\n        elif plan is not None and getattr(plan, "deeper_learning_recommended", False):\n            if self._confirm(\n                "Continue to deeper protocol learning?",\n                [\n                    "Automatic Discovery could not construct an executable generic write grammar.",\n                    "Mouse Control can now learn the complete physical DPI-stage cycle read-only.",\n                    "This uses ruler-based CPI calibration plus simultaneous HID observation.",\n                    "No unknown DPI or polling configuration write will be sent.",\n                ],\n                yes="Enter Begin deeper learning",\n                no="b Not now",\n            ):\n                self._run_guided()\n\n    def _run_polling_measurement(self) -> None:\n''',
)
# Replace old _run_guided implementation with deep learner.
start = (ROOT / 'src/mouse_control/setup_tui_curses.py').read_text()
old_start = '    def _run_guided(self) -> None:\n'
old_end = '    def _suspend_curses(self, function: Callable[[], Any]) -> Any:\n'
left, remainder = start.split(old_start, 1)
old_body, right = remainder.split(old_end, 1)
new_body = r'''    def _run_guided(self) -> None:
        if self.controller.discovery_result is None or self.controller.discovery_engine is None:
            self.controller.status = "Run Automatic Discovery before deeper protocol learning."
            return
        try:
            outcome = run_deep_dpi_stage_learning(
                self.controller.selected,
                self.controller.discovery_result,
                self.controller.discovery_engine,
                prompt=self._guided_prompt,
                progress=self._guided_progress,
            )
        except GuidedDiscoveryCancelled:
            self.controller.status = "Deeper protocol learning cancelled; no hardware authority changed."
            return
        except (TopologyError, PermissionError, OSError, HardwareError, ValueError) as exc:
            self.controller.status = f"Deeper protocol learning unavailable: {exc}"
            return
        self.controller.apply_deep_learning_outcome(outcome)
        lines = []
        if outcome.wrap_confirmed:
            lines.append("✓ Complete physical DPI cycle and wraparound observed")
        else:
            lines.append("? Complete physical DPI cycle was not confirmed")
        if outcome.action_identified:
            lines.append("✓ DPI-button action isolated from ordinary motion")
        if outcome.raw_mappings:
            lines.append("✓ Persistent raw DPI-stage state correlated with physical CPI")
        if outcome.profile_path is not None:
            lines.append("✓ Exact-device read-only stage profile saved for runtime notifications")
        else:
            lines.append("? No runtime stage profile was promoted")
        lines.append("Write authority remains unchanged by deeper read-side learning.")
        self._confirm("Deeper discovery result", lines, yes="Enter Continue", no="Esc Continue")

'''
(ROOT / 'src/mouse_control/setup_tui_curses.py').write_text(left + new_body + old_end + right)

# ---------------------------------------------------------------------------
# 5. Final setup transaction: capability authority is absolute. Existing/default
#    preferences must never cause a write when discovery says non-writable.
# ---------------------------------------------------------------------------
replace(
    'src/mouse_control/setup_entry.py',
    '''        cli._apply_hardware(\n            backend,\n            selected,\n            choices.stages,\n            choices.active_dpi if apply_dpi else 0,\n            choices.polling_rate if apply_polling else None,\n            setup=True,\n        )\n''',
    '''        # Preferences are never write authority. A default/old config may be\n        # persisted for software behavior, but hardware application is strictly\n        # gated by the capability policy discovered for this exact device.\n        dpi_request = choices.active_dpi if (choices.dpi_writable and apply_dpi) else 0\n        polling_request = (\n            choices.polling_rate\n            if (choices.polling_writable and apply_polling)\n            else None\n        )\n        cli._apply_hardware(\n            backend,\n            selected,\n            choices.stages,\n            dpi_request,\n            polling_request,\n            setup=True,\n        )\n''',
)

# ---------------------------------------------------------------------------
# 6. Regression tests for the integration boundary.
# ---------------------------------------------------------------------------
(ROOT / 'tests/test_discovery_research_plan.py').write_text(r'''from types import SimpleNamespace
from unittest.mock import Mock

from mouse_control.discovery_models import DiscoveredCapability, DiscoveryEvidence, DiscoveryResult, EvidenceLevel
from mouse_control.discovery_research import ResearchStatus, build_discovery_research_plan
from mouse_control.learned_operations import LearnedOperationState
from mouse_control.protocol_grammar import SemanticBehavior, TransportKind, WriteScope


def _result(*, protocol=None, capabilities=None):
    device = SimpleNamespace(ambiguous=False)
    return DiscoveryResult(device=device, protocol=protocol, capabilities=capabilities or {})


def test_known_protocol_read_only_does_not_trigger_generic_deeper_learning():
    plan = build_discovery_research_plan(
        _result(protocol=SimpleNamespace(name="known")),
        (),
        learned_operation_store=Mock(),
        learned_polling_store=Mock(),
    )
    assert plan.dpi.status is ResearchStatus.KNOWN_READ_ONLY
    assert plan.polling.status is ResearchStatus.KNOWN_READ_ONLY
    assert plan.deeper_learning_recommended is False


def test_unknown_without_executable_probe_routes_to_deeper_learning():
    dpi_store = Mock()
    dpi_store.find_for_physical.return_value = None
    polling_store = Mock()
    polling_store.find_for_physical.return_value = None
    plan = build_discovery_research_plan(
        _result(), (),
        learned_operation_store=dpi_store,
        learned_polling_store=polling_store,
    )
    assert plan.dpi.status is ResearchStatus.NO_EVIDENCE
    assert plan.polling.status is ResearchStatus.NO_EVIDENCE
    assert plan.deeper_learning_recommended is True


def test_demonstrated_dpi_grammar_is_probe_ready_not_runtime_writable():
    op = SimpleNamespace(state=LearnedOperationState.DEMONSTRATED)
    dpi_store = Mock()
    dpi_store.find_for_physical.return_value = ("path", op)
    polling_store = Mock()
    polling_store.find_for_physical.return_value = None
    plan = build_discovery_research_plan(
        _result(), (),
        learned_operation_store=dpi_store,
        learned_polling_store=polling_store,
    )
    assert plan.dpi.status is ResearchStatus.REVERSIBLE_PROBE_READY
    assert plan.reversible_probe_available is True
    assert plan.deeper_learning_recommended is False


def test_structural_write_transport_is_candidate_not_authority():
    family = SimpleNamespace(
        write_scope=WriteScope.EXACT_MODEL,
        transports=(TransportKind.HID_FEATURE_SET,),
    )
    candidate = SimpleNamespace(family=family)
    dpi_store = Mock(); dpi_store.find_for_physical.return_value = None
    polling_store = Mock(); polling_store.find_for_physical.return_value = None
    plan = build_discovery_research_plan(
        _result(), (candidate,),
        learned_operation_store=dpi_store,
        learned_polling_store=polling_store,
    )
    assert plan.dpi.status is ResearchStatus.STRUCTURAL_CANDIDATE
    assert plan.polling.status is ResearchStatus.STRUCTURAL_CANDIDATE
    assert plan.deeper_learning_recommended is True
    assert plan.dpi.writable is False


def test_proven_capability_remains_runtime_authority():
    proof = DiscoveryEvidence(EvidenceLevel.PROVEN, "learned-operation-proven", "ok")
    cap = DiscoveredCapability("dpi", readable=True, writable=True, evidence=[proof]).normalized()
    dpi_store = Mock(); dpi_store.find_for_physical.return_value = None
    polling_store = Mock(); polling_store.find_for_physical.return_value = None
    plan = build_discovery_research_plan(
        _result(capabilities={"dpi": cap}), (),
        learned_operation_store=dpi_store,
        learned_polling_store=polling_store,
    )
    assert plan.dpi.status is ResearchStatus.PROVEN
    assert plan.deeper_learning_recommended is False
''')

(ROOT / 'tests/test_setup_write_authority.py').write_text(r'''from pathlib import Path


def test_tui_setup_final_apply_is_capability_gated():
    source = Path("src/mouse_control/setup_entry.py").read_text()
    assert "choices.dpi_writable and apply_dpi" in source
    assert "choices.polling_writable and apply_polling" in source
    assert "dpi_request" in source
    assert "polling_request" in source


def test_deeper_learning_is_research_plan_driven_not_generic_nonwritable():
    source = Path("src/mouse_control/setup_tui.py").read_text()
    section = source[source.index("def guided_discovery_available"):]
    section = section[:section.index("def _discovered_capability")]
    assert "deeper_learning_recommended" in section
    assert "not self.choices.dpi_writable" not in section
''')

(ROOT / 'tests/test_deep_stage_learning.py').write_text(r'''from pathlib import Path


def test_deep_stage_learning_uses_full_calibrated_methodology():
    source = Path("src/mouse_control/guided_discovery.py").read_text()
    required = (
        "capture_calibrated_motion",
        "measure_sensor_state_auto",
        "summarize_calibrations",
        "refine_teacher_free",
        "infer_calibrated_raw_mappings",
        "calibrated_cycle_hypothesis",
        "calibrated_profile_data",
        "save_calibrated_profile",
    )
    for name in required:
        assert name in source
    assert "wrap_confirmed" in source
    assert "Write authority" not in source  # service does not grant authority


def test_tui_prompts_for_deeper_learning_after_automatic_discovery():
    source = Path("src/mouse_control/setup_tui_curses.py").read_text()
    assert "Continue to deeper protocol learning?" in source
    assert "run_deep_dpi_stage_learning" in source
    assert "No unknown DPI or polling configuration write will be sent." in source
''')

print('Discovery Engine research integration staged')
