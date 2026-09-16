"""Regression tests for teacher-free contrastive guided learning."""

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


def _reports(timestamp: int, values: tuple[tuple[int, int], ...]) -> PhysicalAction:
    """Build reports whose payload bytes 1 and 3 can vary independently."""

    return PhysicalAction(
        timestamp,
        timestamp + len(values),
        hid_reports=[
            TimedReport(
                timestamp + index,
                "stable-stream",
                bytes((0x02, motion, 0x00, trigger)),
            )
            for index, (motion, trigger) in enumerate(values)
        ],
    )


def _dpi_action(timestamp: int) -> PhysicalAction:
    return _reports(timestamp, ((0, 0), (0, 1), (0, 0)))


def test_teacher_free_controls_validate_semantic_action_not_raw_location():
    session = _session()
    samples = [
        LearningSample(_dpi_action(10)),
        LearningSample(_dpi_action(20)),
        LearningSample(_dpi_action(30)),
    ]
    controls = [
        LearningSample(_reports(100, ((0, 0), (0, 0)))),
        LearningSample(_reports(200, ((0, 0), (7, 0), (2, 0)))),
    ]

    learned = session.analyze(
        samples,
        trigger_behavior=SemanticBehavior.DPI_CYCLE_TRIGGER,
        control_samples=controls,
    )

    assert len(learned.control_samples) == 2
    assert any(candidate.offset == 1 for candidate in learned.control_trigger_candidates)
    assert any(candidate.offset == 3 for candidate in learned.discriminative_trigger_candidates)

    semantic = next(
        hypothesis
        for hypothesis in learned.hypotheses
        if hypothesis.behavior is SemanticBehavior.DPI_CYCLE_TRIGGER
        and hypothesis.confidence == "validated"
    )
    assert semantic.report_key is None
    assert semantic.offset is None
    assert "teacher-free contrastive learning" in semantic.reason

    raw = next(
        hypothesis
        for hypothesis in learned.hypotheses
        if hypothesis.behavior is SemanticBehavior.DPI_CYCLE_TRIGGER
        and hypothesis.offset == 3
    )
    assert raw.confidence == "correlated"


def test_control_transition_removes_false_action_candidate():
    session = _session()
    samples = [
        LearningSample(_dpi_action(10)),
        LearningSample(_dpi_action(20)),
        LearningSample(_dpi_action(30)),
    ]
    # The same byte-3 transition also happens during ordinary-use controls, so
    # it cannot be treated as action-specific evidence.
    controls = [
        LearningSample(_dpi_action(100)),
        LearningSample(_dpi_action(200)),
    ]

    learned = session.analyze(
        samples,
        trigger_behavior=SemanticBehavior.DPI_CYCLE_TRIGGER,
        control_samples=controls,
    )

    assert learned.discriminative_trigger_candidates == ()
    assert not any(
        hypothesis.behavior is SemanticBehavior.DPI_CYCLE_TRIGGER
        for hypothesis in learned.hypotheses
    )


def test_one_control_is_not_enough_for_teacher_free_validation():
    session = _session()
    samples = [
        LearningSample(_dpi_action(10)),
        LearningSample(_dpi_action(20)),
        LearningSample(_dpi_action(30)),
    ]
    controls = [LearningSample(_reports(100, ((0, 0), (0, 0))))]

    learned = session.analyze(
        samples,
        trigger_behavior=SemanticBehavior.DPI_CYCLE_TRIGGER,
        control_samples=controls,
    )

    assert any(candidate.offset == 3 for candidate in learned.discriminative_trigger_candidates)
    assert not any(
        hypothesis.behavior is SemanticBehavior.DPI_CYCLE_TRIGGER
        and hypothesis.confidence == "validated"
        for hypothesis in learned.hypotheses
    )
