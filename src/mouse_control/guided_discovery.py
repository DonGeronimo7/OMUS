"""Reusable read-only guided learning used by setup and discovery CLI.

This module intentionally owns no write or promotion path.  It orchestrates the
existing :class:`ReadOnlyLearningSession` controls/action samples and returns
what was observed.  Writable hardware support remains the responsibility of the
existing exact-model PROVEN operation stores and transaction machinery.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .contrastive_inference import refine_teacher_free
from .discovery_engine import DiscoveryEngine
from .learning_session import ReadOnlyLearningSession
from .protocol_grammar import SemanticBehavior
from .teacher_registry import read_teacher_labels


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
class GuidedDpiLearningOutcome:
    """Result of the five-sample DPI-button observation workflow."""

    learned: Any
    controls: tuple[Any, ...]
    samples: tuple[Any, ...]
    action_identified: bool
    teacher_used: bool


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

    This is deliberately an observation-only statement.  It does not create or
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

    No generic polling writer exists here.  Existing PROVEN exact-model polling
    evidence is surfaced by DiscoveryEngine; otherwise polling remains unchanged.
    """

    report = progress or (lambda _message: None)
    report("Inspecting mouse…")
    engine = engine_factory()
    result = engine.discover(selected)
    report("✓ Physical device identified")
    report(f"✓ {len(result.device.hidraw_nodes)} hardware interface(s) correlated")
    report(f"✓ {len(engine.descriptors)} hardware descriptor(s) read")
    report("✓ Existing protocol teachers and exact-model learned support checked")

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
