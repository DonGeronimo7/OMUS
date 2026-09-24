from __future__ import annotations

import json

import pytest

from mouse_control.evidence_graph import EvidenceGraph
from mouse_control.hid_bpf_observation import (
    HidBpfAdmission, HidBpfHook, HidBpfObservation, HidBpfObservationError, HidBpfStage,
    emit_hid_bpf_evidence, require_hid_bpf_admission,
)


def observation(**changes) -> HidBpfObservation:
    values = dict(
        timestamp_ns=10,
        generation=2,
        bus=3,
        vendor_id=0x046D,
        product_id=0x4074,
        interface_number=2,
        descriptor_sha256="a" * 64,
        hook=HidBpfHook.HW_REQUEST,
        stage=HidBpfStage.BEFORE,
        source_id=0,
        report_type=3,
        report_id=0x11,
        payload=b"\x11\x01",
        request_type=0x09,
    )
    values.update(changes)
    return HidBpfObservation(**values)


def test_admission_requires_every_safety_and_provenance_capability() -> None:
    admitted = HidBpfAdmission(True, True, True, True, True)
    assert admitted.admitted and admitted.blockers == ()
    require_hid_bpf_admission(admitted)

    blocked = HidBpfAdmission(True, True, True, False, True)
    assert blocked.blockers == ("synthetic-self-test-failed",)
    with pytest.raises(HidBpfObservationError, match="self-test"):
        require_hid_bpf_admission(blocked)


def test_source_zero_is_kernel_and_nonzero_is_userspace_hidraw_provenance() -> None:
    assert observation(source_id=0).source_kind == "kernel"
    assert observation(source_id=42).source_kind == "userspace_hidraw"


def test_binding_key_includes_generation_and_descriptor_not_live_path() -> None:
    first = observation(generation=1)
    second = observation(generation=2)
    assert first.binding_key != second.binding_key
    assert "/dev/" not in repr(first.binding_key)


def test_evidence_emission_preserves_source_stage_and_never_creates_capability() -> None:
    graph = EvidenceGraph()
    interface_id, event_id = emit_hid_bpf_evidence(graph, observation(source_id=37))
    rows = graph.explain(event_id)
    assert [row["kind"] for row in rows] == ["interface", "transaction"]
    assert all(row["kind"] != "capability" for row in rows)
    claim = json.loads(rows[-1]["claim"])
    assert claim["stage"] == "before"
    assert claim["source_kind"] == "userspace_hidraw"
    graph.invalidate(interface_id, "descriptor changed on reconnect")
    assert event_id not in graph.valid_ids


def test_input_report_becomes_frame_evidence() -> None:
    graph = EvidenceGraph()
    _, event_id = emit_hid_bpf_evidence(
        graph,
        observation(hook=HidBpfHook.INPUT_REPORT, source_id=0, request_type=None),
    )
    assert graph.explain(event_id)[-1]["kind"] == "frame"


def test_invalid_descriptor_or_oversized_payload_is_rejected() -> None:
    with pytest.raises(HidBpfObservationError):
        observation(descriptor_sha256="bad")
    with pytest.raises(HidBpfObservationError):
        observation(payload=bytes(4097))
