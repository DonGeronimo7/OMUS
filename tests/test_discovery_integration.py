# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path

from mouse_control.community_report import build_community_report, render_community_report
from mouse_control.discovery_integration import (
    integrate_bitmouse_observations, integrate_pushed_state_observations,
)
from mouse_control.discovery_models import (
    DeviceNode, DiscoveryResult, HidReportDefinition, PhysicalDevice,
)
from mouse_control.hid_descriptor import ParsedHidDescriptor
from mouse_control.temporal_dialogue import (
    DialogueAssembler, DialogueObservation, Direction, PushedStateSpec,
)
from mouse_control.trace.models import (
    CaptureQuality, CaptureSource, CompletenessStatus, UrbEventType,
    UsbDirection, UsbObservation, UsbTransferType,
)


def _request(target: int, sequence: int, reply_length: int) -> bytes:
    frame = bytearray(64)
    frame[1:6] = bytes((0x72, target, sequence, 0x31, reply_length))
    frame[0] = sum(frame[1:6]) & 0xFF
    return bytes(frame)


def _response(target: int, sequence: int, value: int) -> bytes:
    frame = bytearray([0xDD] * 64)
    frame[:7] = bytes((0x72, target, sequence, 0, 2, value & 0xFF, value >> 8))
    return bytes(frame)


def _observation(sequence: int, direction: UsbDirection, payload: bytes) -> UsbObservation:
    return UsbObservation(
        capture_id="fixture-session", sequence=sequence, timestamp_ns=sequence * 1_000,
        source=CaptureSource.SYNTHETIC_TEST, bus_id=1, device_address=2,
        interface_number=3, endpoint=1, direction=direction,
        transfer_type=UsbTransferType.INTERRUPT,
        event_type=UrbEventType.SUBMIT if direction is UsbDirection.OUT else UrbEventType.COMPLETE,
        urb_id=sequence, status=0, setup=None, declared_length=64,
        captured_length=64, payload=payload, physical_device_fingerprint="model:test",
        capture_quality=CaptureQuality(
            source_representation="independent-semantic-fixture",
            full_binary_header_available=False,
            completeness=CompletenessStatus.COMPLETE,
        ),
    )


def test_complete_discovery_chain_preserves_evidence_and_never_grants_write() -> None:
    node = DeviceNode(
        Path("/dev/hidraw7"), None, "hidraw", "hidraw", 3,
        0x9999, 0x2222, 3, descriptor_sha256="descriptor-safe",
    )
    physical = PhysicalDevice(
        "Fixture Mouse", 0x9999, 0x2222, 3, None,
        hidraw_nodes=[node], model_fingerprint="model:test",
    )
    descriptor = ParsedHidDescriptor(
        raw=b"synthetic-bitmouse-descriptor",
        reports=(
            HidReportDefinition(0x72, "output", 64, (0xFF00,)),
            HidReportDefinition(0x72, "input", 64, (0xFF00,)),
        ),
    )
    observations = []
    for index, value in enumerate((800, 1600, 3200), start=1):
        observations.extend((
            _observation(index * 2 - 1, UsbDirection.OUT, _request(4, index, 2)),
            _observation(index * 2, UsbDirection.IN, _response(4, index, value)),
        ))

    integrated = integrate_bitmouse_observations(
        observations, physical=physical, descriptors={node: descriptor},
        semantic_values=(800, 1600, 3200), generation=7,
    )
    report = build_community_report(
        DiscoveryResult(physical, None, {}), version="0.9.4",
        integrated_evidence=integrated.community_evidence(),
    )
    text = render_community_report(report)

    assert integrated.recognition.recognized
    assert len(integrated.dialogues) == 3
    assert any(item.offset == 5 and item.width == 2 for item in integrated.dependencies.candidates)
    assert integrated.recognition.semantic_records[0] == _response(4, 1, 800)[:7]
    assert integrated.proof.state.value == "recognized"
    assert integrated.write_authorized is False
    assert report["safety"]["active_writes_authorized"] is False
    assert report["integrated_evidence"]["connection_generation"] == 7
    assert report["integrated_evidence"]["next_safe_observation_recipe_id"]
    assert report["integrated_evidence"]["descriptor_structure"][0]["usage_pages"] == [0xFF00]
    assert "/dev/" not in text


def test_pushed_state_integration_recognizes_without_write_authority() -> None:
    node = DeviceNode(
        Path("/dev/hidraw8"), None, "hidraw", "hidraw", 3,
        0x3554, 0xF58A, 2, descriptor_sha256="descriptor-async",
    )
    physical = PhysicalDevice(
        "Async Fixture Mouse", 0x3554, 0xF58A, 3, None,
        hidraw_nodes=[node], model_fingerprint="model:async",
    )
    descriptor = ParsedHidDescriptor(
        raw=b"synthetic-async-descriptor",
        reports=(HidReportDefinition(0x13, "input", 16, (0xFF00,)),),
    )
    spec = PushedStateSpec(
        "mchose.realtek.state", 0x13, "async-state",
        channel_id="realtek-input", periodic_max_gap_ms=100,
    )
    assembler = DialogueAssembler()
    records = []
    for sequence, timestamp, encoded in ((1, 0, 0xFE), (2, 40, 0xFD)):
        observation = DialogueObservation(
            "async-session", "model:async", "realtek-input", "hid",
            Direction.IN, "mchose.realtek.state", 0x13, 1,
            timestamp * 1_000_000, sequence, bytes((0x1D, encoded)),
            grammar="async-state",
        )
        record = assembler.observe_pushed_state(
            observation, spec, semantic_state_id="opaque-device-state",
            decoded_state=encoded ^ 0xFF, subtype=0x1D, transform="xor_ff",
            transform_source=bytes((encoded,)),
            transformed_payload=bytes((encoded ^ 0xFF,)),
        )
        assert record is not None
        records.append(record)

    integrated = integrate_pushed_state_observations(
        records, family_name="mchose-realtek-l7-pushed-state",
        physical=physical, descriptors={node: descriptor},
    )
    assert integrated.recognition.status.value == "recognized"
    assert integrated.recognition.family == "mchose-realtek-l7-pushed-state"
    assert integrated.proof.state.value == "recognized"
    assert integrated.evidence_source_ids == ("async-session:1", "async-session:2")
    assert integrated.write_authorized is False
