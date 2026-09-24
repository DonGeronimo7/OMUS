# SPDX-License-Identifier: AGPL-3.0-or-later
from types import SimpleNamespace

import pytest

from mouse_control.dependency_inference import DependencyKind
from mouse_control.discovery_lab import (
    DiscoveryLabCancelled,
    FieldSignal,
    LabExperiment,
    LabInterval,
    LabIntervalRecord,
    ProtocolObservation,
    analyze_differential_experiment,
    run_read_only_differential_lab,
)
from mouse_control.event_correlation import PhysicalAction, TimedReport
from mouse_control.learning_session import LearningSample
from mouse_control.logical_record import (
    LogicalRecord,
    RecordCompleteness,
    RecordIntegrity,
)
from mouse_control.temporal_dialogue import (
    DialogueKind,
    DialogueObservation,
    DialogueRecord,
    Direction,
)
from mouse_control.trace.models import (
    CaptureSource,
    UrbEventType,
    UsbDirection,
    UsbObservation,
    UsbTransferType,
)


def _checksum(payload):
    return bytes((*payload, sum(payload) & 0xFF))


def _observation(interval, repeat, timestamp, sequence, payload, *, stream="control"):
    return ProtocolObservation(
        source_id="stable-source",
        stream_id=stream,
        timestamp_ns=timestamp,
        sequence=sequence,
        payload=payload,
        interval=interval,
        repeat=repeat,
        report_id=payload[0],
    )


def _experiment(observations, *, dialogues=()):
    intervals = tuple(
        LabIntervalRecord(interval, 0, 0, 1, 0)
        for interval in LabInterval
    )
    return LabExperiment(
        experiment_id="lab-fixture",
        physical_device_context={
            "vendor_id": 0x1234,
            "product_id": 0x5678,
            "model_fingerprint": "model",
            "path": "/dev/hidraw9",
        },
        connection_generation=0,
        purpose="deterministic fixture",
        human_action="press labelled control",
        intervals=intervals,
        observations=tuple(observations),
        dialogues=tuple(dialogues),
    )


def test_analyzer_ranks_action_counter_length_integrity_padding_timing_and_echo():
    observations = []
    sequence = 0
    plans = (
        (LabInterval.BASELINE, 0, 0, (1, 2, 3), 100),
        (LabInterval.ACTION, 1, 1_000, (4, 5, 6), 10),
        (LabInterval.POST_ACTION, 0, 2_000, (7, 8, 9), 100),
        (LabInterval.NEGATIVE_CONTROL, 0, 3_000, (10, 11, 12), 100),
    )
    for interval, repeat, start, counters, gap in plans:
        status = 2 if interval in {LabInterval.ACTION, LabInterval.POST_ACTION} else 1
        for index, counter in enumerate(counters):
            observations.append(_observation(
                interval, repeat, start + index * gap, sequence,
                _checksum((0xA0, status, counter, 5)),
            ))
            observations.append(_observation(
                interval, repeat, start + index * gap, sequence,
                bytes((0xB0, status, 0, 0)), stream="padded",
            ))
            sequence += 1

    request = DialogueObservation(
        "capture", "physical", "channel", "usb-hid", Direction.OUT,
        "fixture", 1, 0, 1, 1, b"\x01\x02",
    )
    response = DialogueObservation(
        "capture", "physical", "channel", "usb-hid", Direction.IN,
        "fixture", 1, 0, 2, 2, b"\x01\x02",
    )
    dialogue = DialogueRecord(DialogueKind.ECHO, response, request=request)
    analyzed = analyze_differential_experiment(_experiment(observations, dialogues=(dialogue,)))

    assert analyzed.write_authorized is False
    assert analyzed.analysis is not None
    control = {item.offset: item for item in analyzed.analysis.ranked_fields if item.stream_id == "control"}
    assert FieldSignal.ACTION_CORRELATED in control[1].signals
    assert FieldSignal.COUNTER_CANDIDATE in control[2].signals
    assert FieldSignal.LENGTH_CANDIDATE in control[3].signals
    assert FieldSignal.INTEGRITY_CANDIDATE in control[4].signals
    padded = {item.offset: item for item in analyzed.analysis.ranked_fields if item.stream_id == "padded"}
    assert FieldSignal.STALE_OR_PADDING in padded[3].signals
    timing = {item.stream_id: item for item in analyzed.analysis.timing}
    assert timing["control"].changed is True
    assert timing["control"].action_ratio == 10.0
    assert analyzed.analysis.echoes[0].exact is True
    assert analyzed.analysis.transaction_differences[0].changed_offsets == ()
    assert any(
        hypothesis.label == "correlates-with:press labelled control"
        for hypothesis in analyzed.analysis.semantic_hypotheses
    )
    assert analyzed.analysis.next_recommended_experiment is not None
    assert analyzed.analysis.next_recommended_experiment.requires_hardware_write is False


def test_analyzer_reuses_dependency_inference_for_labelled_action_values():
    observations = [
        _observation(LabInterval.ACTION, index, index, index, bytes((0x01, raw)))
        for index, raw in enumerate((10, 20, 30), 1)
    ]
    analyzed = analyze_differential_experiment(
        _experiment(observations), semantic_values=(100, 200, 300),
    )
    assert analyzed.analysis is not None
    assert any(
        item.kind is DependencyKind.SCALED and item.offset == 1
        for item in analyzed.analysis.dependencies.candidates
    )


def test_negative_control_contradiction_lowers_action_claim():
    observations = [
        _observation(LabInterval.BASELINE, 0, 0, 0, b"\x01\x10"),
        _observation(LabInterval.ACTION, 1, 1, 1, b"\x01\x20"),
        _observation(LabInterval.NEGATIVE_CONTROL, 0, 2, 2, b"\x01\x20"),
    ]
    analyzed = analyze_differential_experiment(_experiment(observations))
    field = next(item for item in analyzed.analysis.ranked_fields if item.offset == 1)
    assert FieldSignal.ACTION_CORRELATED not in field.signals
    assert field.contradictions == ("negative control reproduced an action value",)
    assert analyzed.analysis.contradictions


def test_experiment_rejects_cross_generation_evidence():
    item = _observation(LabInterval.BASELINE, 0, 0, 0, b"\x01")
    with pytest.raises(ValueError, match="cannot cross"):
        LabExperiment(
            "id", {"model_fingerprint": "model"}, 1, "purpose", None, (), (item,),
        )


def test_analyzer_projects_existing_usb_and_logical_record_evidence_by_interval():
    intervals = (
        LabIntervalRecord(LabInterval.BASELINE, 0, 0, 99, 1),
        LabIntervalRecord(LabInterval.ACTION, 1, 100, 199, 1),
        LabIntervalRecord(LabInterval.NEGATIVE_CONTROL, 0, 200, 299, 1),
    )

    def usb(sequence, timestamp, value):
        payload = bytes((0x01, value))
        return UsbObservation(
            capture_id="capture", sequence=sequence, timestamp_ns=timestamp,
            source=CaptureSource.SYNTHETIC_TEST, bus_id=1, device_address=2,
            interface_number=3, endpoint=0x81, direction=UsbDirection.IN,
            transfer_type=UsbTransferType.INTERRUPT,
            event_type=UrbEventType.COMPLETE, urb_id=sequence, status=0,
            setup=None, declared_length=len(payload), captured_length=len(payload),
            payload=payload, physical_device_fingerprint="model",
        )

    logical = LogicalRecord(
        grammar="fixture", completeness=RecordCompleteness.INVALID,
        integrity=RecordIntegrity.INVALID, integrity_protected=True,
        data=b"\x09\x20", source_frames=(), start_timestamp_ns=150,
        end_timestamp_ns=151, generation=0, channel_id="feature",
        report_namespace="feature", report_id=9, declared_length=2,
        captured_logical_length=2, record_type=None, record_sequence=None,
    )
    experiment = LabExperiment(
        "existing-evidence", {"model_fingerprint": "model"}, 0,
        "project existing evidence", "press control", intervals, (),
        usb_observations=(usb(1, 50, 0x10), usb(2, 150, 0x20), usb(3, 250, 0x10)),
        logical_records=(logical,),
    )
    analyzed = analyze_differential_experiment(experiment)
    assert analyzed.analysis is not None
    assert any(item.stream_id.startswith("usb:") for item in analyzed.analysis.ranked_fields)
    assert any(item.stream_id.startswith("logical:") for item in analyzed.analysis.ranked_fields)
    assert any("invalid" in item for item in analyzed.analysis.contradictions)


def test_replay_fixture_is_deterministic_and_redacts_volatile_paths():
    experiment = _experiment([
        _observation(LabInterval.ACTION, 1, 5, 2, b"\xaa\xbb"),
        _observation(LabInterval.BASELINE, 0, 1, 1, b"\xaa\x00"),
    ])
    first = experiment.replay_fixture()
    second = experiment.replay_fixture()
    assert first == second
    assert "path" not in first["physical_device_context"]
    serialized = repr(first)
    assert "/dev/hidraw" not in serialized
    assert "evdev_events" not in serialized


class _FakeSession:
    calls = 0

    def __init__(self, physical, descriptors):
        self.physical = physical
        self.descriptors = descriptors

    def observe_action(self, *, seconds):
        type(self).calls += 1
        index = type(self).calls
        return LearningSample(PhysicalAction(
            start_ns=index * 100,
            end_ns=index * 100 + 50,
            hid_reports=[TimedReport(index * 100 + 1, ("stable", 1), bytes((1, index)))],
        ))


def test_read_only_runner_chooses_intervals_repeats_and_retains_no_evdev_history():
    _FakeSession.calls = 0
    physical = SimpleNamespace(
        ambiguous=False, bus=3, vendor_id=1, product_id=2,
        model_fingerprint="model", instance_fingerprint="instance",
    )
    steps = []
    experiment = run_read_only_differential_lab(
        physical, {}, prompt=lambda step: steps.append(step) or True,
        repeat_count=3, seconds=0.01, session_factory=_FakeSession,
    )
    assert _FakeSession.calls == 6
    assert len(steps) == 6
    assert [item.interval for item in experiment.intervals] == [
        LabInterval.BASELINE,
        LabInterval.ACTION, LabInterval.ACTION, LabInterval.ACTION,
        LabInterval.POST_ACTION,
        LabInterval.NEGATIVE_CONTROL,
    ]
    assert experiment.write_authorized is False
    assert "evdev" not in repr(experiment.replay_fixture()).lower()


def test_read_only_runner_cancel_stops_before_capture():
    _FakeSession.calls = 0
    physical = SimpleNamespace(
        ambiguous=False, bus=3, vendor_id=1, product_id=2,
        model_fingerprint="model", instance_fingerprint="instance",
    )
    with pytest.raises(DiscoveryLabCancelled):
        run_read_only_differential_lab(
            physical, {}, prompt=lambda _step: False,
            session_factory=_FakeSession,
        )
    assert _FakeSession.calls == 0
