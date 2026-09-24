# SPDX-License-Identifier: AGPL-3.0-or-later
"""Regression tests for teacher-free transition/report-shape refinement."""

from mouse_control.contrastive_inference import refine_teacher_free
from mouse_control.discovery_models import PhysicalDevice
from mouse_control.event_correlation import PhysicalAction, TimedReport
from mouse_control.learning_session import LearningSample, ReadOnlyLearningSession
from mouse_control.protocol_grammar import SemanticBehavior


def _session() -> ReadOnlyLearningSession:
    physical = PhysicalDevice(
        "Unknown Mouse",
        0x1234,
        0x5678,
        3,
        None,
        model_fingerprint="model",
    )
    return ReadOnlyLearningSession(physical, {})


def _action(timestamp: int, values: tuple[int, ...]) -> PhysicalAction:
    reports = [
        TimedReport(timestamp + index, "stream", bytes((0x02, 0, 0, value)))
        for index, value in enumerate(values)
    ]
    return PhysicalAction(timestamp, timestamp + len(values), hid_reports=reports)


def _single_state_report(timestamp: int, value: int) -> PhysicalAction:
    data = bytearray(20)
    data[0] = 0x11
    data[4] = value
    return PhysicalAction(
        timestamp,
        timestamp + 1,
        hid_reports=[TimedReport(timestamp, "vendor-stream", bytes(data))],
    )


def test_same_location_can_be_discriminative_when_transition_motif_differs():
    session = _session()
    controls = [
        LearningSample(_action(1, (10, 11, 12))),
        LearningSample(_action(10, (20, 21, 22))),
    ]
    samples = [
        LearningSample(_action(20, (0, 1, 0))),
        LearningSample(_action(30, (0, 1, 0))),
        LearningSample(_action(40, (0, 1, 0))),
    ]

    learned = session.analyze(
        samples,
        trigger_behavior=SemanticBehavior.DPI_CYCLE_TRIGGER,
        control_samples=controls,
    )

    # The old broad location filter rejects this because the control and guided
    # traffic share byte 3 of the same report.
    assert learned.discriminative_trigger_candidates == ()

    refined = refine_teacher_free(learned)
    assert len(refined.candidates) == 1
    candidate = refined.candidates[0]
    assert candidate.candidate.offset == 3
    assert set(candidate.distinctive_transitions) == {(0, 1), (1, 0)}
    assert any(
        hypothesis.behavior is SemanticBehavior.DPI_CYCLE_TRIGGER
        and hypothesis.confidence == "validated"
        and hypothesis.report_key is None
        for hypothesis in refined.hypotheses
    )


def test_stage_guess_active_in_normal_controls_is_suppressed():
    session = _session()
    controls = [
        LearningSample(_action(1, (10, 11, 12))),
        LearningSample(_action(10, (20, 21, 22))),
    ]
    # Different final values create a small persistent-state hypothesis at the
    # same byte that is also visibly active during normal control traffic.
    samples = [
        LearningSample(_action(20, (0, 1))),
        LearningSample(_action(30, (0, 2))),
        LearningSample(_action(40, (0, 3))),
    ]

    learned = session.analyze(
        samples,
        trigger_behavior=SemanticBehavior.DPI_CYCLE_TRIGGER,
        control_samples=controls,
    )
    assert any(
        hypothesis.behavior is SemanticBehavior.DPI_STAGE_INDEX
        and hypothesis.offset == 3
        for hypothesis in learned.hypotheses
    )

    refined = refine_teacher_free(learned)
    assert not any(
        hypothesis.behavior is SemanticBehavior.DPI_STAGE_INDEX
        and hypothesis.offset == 3
        for hypothesis in refined.hypotheses
    )
    assert refined.suppressed_stage_locations


def test_single_report_per_press_can_validate_guided_behavior_without_teacher():
    """Match hardware that emits one state/event report per physical DPI press."""

    session = _session()
    controls = [
        LearningSample(PhysicalAction(1, 2)),
        # Ordinary mouse traffic uses a different report shape.
        LearningSample(_action(10, (10, 11, 12))),
    ]
    samples = [
        LearningSample(_single_state_report(20, 1)),
        LearningSample(_single_state_report(30, 2)),
        LearningSample(_single_state_report(40, 3)),
    ]

    learned = session.analyze(
        samples,
        trigger_behavior=SemanticBehavior.DPI_CYCLE_TRIGGER,
        control_samples=controls,
    )

    # One packet per action means there is deliberately no within-window trigger
    # transition. The cross-action state field is still visible.
    assert learned.trigger_candidates == ()
    assert any(
        hypothesis.behavior is SemanticBehavior.DPI_STAGE_INDEX
        and hypothesis.offset == 4
        for hypothesis in learned.hypotheses
    )

    refined = refine_teacher_free(learned)
    assert len(refined.report_shapes) == 1
    shape = refined.report_shapes[0]
    assert shape.guided_counts == (1, 1, 1)
    assert shape.control_counts == (0, 0)
    assert any(
        hypothesis.behavior is SemanticBehavior.DPI_CYCLE_TRIGGER
        and hypothesis.confidence == "correlated"
        and hypothesis.report_key == shape.report_key
        and hypothesis.offset is None
        for hypothesis in refined.hypotheses
    )
    assert any(
        hypothesis.behavior is SemanticBehavior.DPI_CYCLE_TRIGGER
        and hypothesis.confidence == "validated"
        and hypothesis.report_key is None
        for hypothesis in refined.hypotheses
    )
