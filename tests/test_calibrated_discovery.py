# SPDX-License-Identifier: AGPL-3.0-or-later
from mouse_control.calibrated_discovery import (
    CalibratedDpiState,
    calibrated_cycle_hypothesis,
    infer_calibrated_raw_mappings,
)
from mouse_control.event_correlation import PhysicalAction, RawStreamIdentity, TimedReport
from mouse_control.learning_session import LearningSample
from mouse_control.protocol_grammar import SemanticBehavior


def _identity() -> RawStreamIdentity:
    return RawStreamIdentity(3, 0x1234, 0x5678, 2, "descriptor")


def _sample(index: int, raw_value: int) -> LearningSample:
    identity = _identity()
    action = PhysicalAction(
        start_ns=index * 100,
        end_ns=index * 100 + 20,
        hid_reports=[
            TimedReport(
                timestamp_ns=index * 100 + 1,
                source=identity,
                data=bytes((0x11, 0x00, 0x00, 0x00, raw_value)),
            )
        ],
    )
    return LearningSample(action=action)


def _state(configured: int, measured: float, confidence: str = "high") -> CalibratedDpiState:
    return CalibratedDpiState(
        configured_dpi=configured,
        measured_cpi=measured,
        polling_hz=1000,
        confidence=confidence,
    )


def test_calibrated_mapping_correlates_raw_state_with_configured_and_measured_cpi():
    samples = (_sample(1, 2), _sample(2, 3), _sample(3, 1))
    states = (
        _state(1500, 1529.0),
        _state(2000, 2054.0),
        _state(800, 819.0),
    )

    mappings = infer_calibrated_raw_mappings(samples, states)
    mapping = next(item for item in mappings if item.offset == 4)

    assert dict(mapping.configured_mapping) == {2: 1500, 3: 2000, 1: 800}
    assert dict(mapping.measured_cpi_mapping) == {2: 1529, 3: 2054, 1: 819}
    assert mapping.hypothesis.confidence == "correlated"
    assert mapping.hypothesis.behavior is SemanticBehavior.DPI_VALUE


def test_calibrated_mapping_can_be_restricted_to_action_specific_report_shapes():
    samples = (_sample(1, 2), _sample(2, 3), _sample(3, 1))
    states = (_state(1500, 1529), _state(2000, 2054), _state(800, 819))

    assert infer_calibrated_raw_mappings(
        samples,
        states,
        allowed_report_keys={"not-the-guided-report"},
    ) == ()


def test_conflicting_raw_state_labels_are_rejected():
    samples = (_sample(1, 1), _sample(2, 2), _sample(3, 1))
    states = (_state(800, 819), _state(1500, 1529), _state(2000, 2054))

    mappings = infer_calibrated_raw_mappings(samples, states)

    assert all(item.offset != 4 for item in mappings)


def test_calibrated_cycle_is_semantically_validated_without_claiming_a_raw_location():
    hypothesis = calibrated_cycle_hypothesis(
        (
            _state(800, 819),
            _state(1500, 1529),
            _state(2000, 2054),
        )
    )

    assert hypothesis is not None
    assert hypothesis.behavior is SemanticBehavior.DPI_CYCLE_TRIGGER
    assert hypothesis.confidence == "validated"
    assert hypothesis.report_key is None
    assert hypothesis.offset is None


def test_calibrated_cycle_downgrades_when_physical_evidence_is_not_high_confidence():
    hypothesis = calibrated_cycle_hypothesis(
        (
            _state(800, 819),
            _state(1500, 1529, confidence="low"),
        )
    )

    assert hypothesis is not None
    assert hypothesis.confidence == "correlated"
