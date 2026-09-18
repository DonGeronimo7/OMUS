"""Generic fixed-frame to variable logical-record reconstruction tests."""

from dataclasses import replace
from pathlib import Path

from mouse_control.discovery_integration import integrate_logical_records
from mouse_control.discovery_models import DeviceNode, HidReportDefinition, PhysicalDevice
from mouse_control.hid_descriptor import ParsedHidDescriptor
from mouse_control.integrity_inference import IntegrityHypothesis
from mouse_control.logical_record import (
    IntegritySelector,
    LogicalRecordGrammar,
    LogicalRecordReassembler,
    RecordCompleteness,
    RecordFieldSpec,
    RecordIntegrity,
    TransportFrame,
)
from mouse_control.protocol_repertoire import RecognitionStatus, recognize_open_set
from mouse_control.temporal_dialogue import Direction


def grammar(*, namespace: str = "rawm.records") -> LogicalRecordGrammar:
    return LogicalRecordGrammar(
        name="rawm-style-state-v1",
        report_namespace=namespace,
        report_id=None,
        fixed_wire_length=64,
        start_markers=(b"\x5a", b"\xa5"),
        length_offset=1,
        type_offset=2,
        sequence_offset=3,
        minimum_record_length=12,
        maximum_record_length=192,
        known_fields=(
            RecordFieldSpec("model", 4, 2),
            RecordFieldSpec("sensor", 6, 2),
            RecordFieldSpec("dpi-stage-count", 8),
            RecordFieldSpec("polling", 9),
            RecordFieldSpec("power", 10),
            RecordFieldSpec("capabilities", 11),
        ),
        integrity_selectors=(
            IntegritySelector(0, 0xA5, IntegrityHypothesis("sum8", -1, 1)),
        ),
    )


def record(
    *, length: int = 16, marker: int = 0x5A, record_type: int = 0x20,
    sequence: int = 1, bad_integrity: bool = False,
) -> bytes:
    if length < 12:
        raise ValueError("fixture record is too short")
    data = bytearray(length)
    data[:12] = bytes((
        marker, length, record_type, sequence,
        0x52, 0x4D, 0x33, 0x39, 0x04, 0x02, 0x63, 0x0F,
    ))
    for offset in range(12, length):
        data[offset] = (offset * 7) & 0xFF
    if marker == 0xA5:
        data[-1] = sum(data[:-1]) & 0xFF
        if bad_integrity:
            data[-1] ^= 0xFF
    return bytes(data)


def frame(
    payload: bytes, *, sequence: int = 1, generation: int = 1,
    channel: str = "rawm-input", namespace: str = "rawm.records",
) -> TransportFrame:
    return TransportFrame(
        "rawm-fixture", "rawm-physical", channel, "hid", Direction.IN,
        namespace, None, 64, generation, sequence * 1_000_000, sequence,
        payload.ljust(64, b"\x00"),
    )


def descriptor_context(*, length: int = 64):
    node = DeviceNode(
        path=Path("/dev/hidraw-rawm"), sysfs_path=None, subsystem="hidraw",
        node_type="hidraw", bus=3, vendor_id=0x9999, product_id=0x1000,
        interface_number=2, parent_key="parent:rawm",
    )
    physical = PhysicalDevice(
        name="RAWM Fixture Mouse", vendor_id=node.vendor_id,
        product_id=node.product_id, bus=node.bus, parent_path=None,
        hidraw_nodes=[node], model_fingerprint="rawm-fixture-model",
    )
    parsed = ParsedHidDescriptor(
        raw=b"", reports=(HidReportDefinition(0x07, "input", length, (0xFF00,)),),
    )
    return node, physical, {node: parsed}


def test_one_record_in_one_frame_preserves_transport_and_opaque_bytes() -> None:
    raw = record()
    assembler = LogicalRecordReassembler(grammar())
    records = assembler.add(frame(raw + b"\xee\xdd"))

    assert len(records) == 1
    item = records[0]
    assert item.completeness is RecordCompleteness.COMPLETE
    assert item.integrity is RecordIntegrity.UNKNOWN
    assert item.declared_length == item.captured_logical_length == len(raw)
    assert item.transport_wire_lengths == (64,)
    assert item.data == raw
    assert item.opaque_regions == (type(item.opaque_regions[0])(12, raw[12:]),)
    assert b"\xee\xdd" not in item.data


def test_record_fragmented_across_frames() -> None:
    raw = record(length=80)
    assembler = LogicalRecordReassembler(grammar())
    assert assembler.add(frame(raw[:64], sequence=1)) == ()
    records = assembler.add(frame(raw[64:], sequence=2))
    assert len(records) == 1
    assert records[0].data == raw
    assert len(records[0].source_frames) == 2
    assert records[0].start_timestamp_ns == 1_000_000
    assert records[0].end_timestamp_ns == 2_000_000


def test_two_records_in_one_frame_are_distinct() -> None:
    first = record(length=16, sequence=1)
    second = record(length=18, sequence=2)
    records = LogicalRecordReassembler(grammar()).add(frame(first + second))
    assert tuple(item.data for item in records) == (first, second)


def test_stale_tail_is_not_searched_for_a_fabricated_record_start() -> None:
    raw = record()
    for stale in (
        b"\xee\xdd" + record(length=14, sequence=2),
        b"\x00\x00" + record(length=14, sequence=2),
    ):
        records = LogicalRecordReassembler(grammar()).add(frame(raw + stale))
        assert tuple(item.data for item in records) == (raw,)


def test_declared_length_outside_bound_is_invalid() -> None:
    invalid = bytes((0x5A, 250, 0x20, 1))
    records = LogicalRecordReassembler(grammar()).add(frame(invalid))
    assert len(records) == 1
    assert records[0].completeness is RecordCompleteness.INVALID
    assert records[0].declared_length == 250


def test_truncated_capture_is_retained_as_incomplete() -> None:
    raw = record(length=80)
    assembler = LogicalRecordReassembler(grammar())
    assert assembler.add(frame(raw[:64])) == ()
    records = assembler.finish()
    assert len(records) == 1
    assert records[0].completeness is RecordCompleteness.INCOMPLETE
    assert records[0].captured_logical_length == 64


def test_generation_change_invalidates_old_partial_without_crossing() -> None:
    raw = record(length=80)
    assembler = LogicalRecordReassembler(grammar())
    assembler.add(frame(raw[:64], generation=1))
    records = assembler.add(frame(raw[64:], generation=2, sequence=2))
    assert len(records) == 1
    assert records[0].completeness is RecordCompleteness.INCOMPLETE
    assert records[0].generation == 1
    assert "generation changed" in records[0].reason


def test_channel_isolation_never_joins_fragments() -> None:
    raw = record(length=80)
    assembler = LogicalRecordReassembler(grammar())
    assembler.add(frame(raw[:64], channel="channel-a"))
    assert assembler.add(frame(raw[64:], sequence=2, channel="channel-b")) == ()
    incomplete = assembler.finish()
    assert len(incomplete) == 1
    assert incomplete[0].channel_id == "channel-a"


def test_optional_integrity_wrapper_accepts_valid_and_rejects_bad() -> None:
    valid = LogicalRecordReassembler(grammar()).add(frame(record(marker=0xA5)))
    bad = LogicalRecordReassembler(grammar()).add(
        frame(record(marker=0xA5, bad_integrity=True))
    )
    assert valid[0].integrity is RecordIntegrity.VALID
    assert valid[0].integrity_protected
    assert valid[0].completeness is RecordCompleteness.COMPLETE
    assert bad[0].integrity is RecordIntegrity.INVALID
    assert bad[0].completeness is RecordCompleteness.INVALID


def test_unknown_protected_integrity_stays_unknown_and_cannot_recognize() -> None:
    unknown_integrity = replace(
        grammar(),
        integrity_selectors=(IntegritySelector(
            0, 0xA5, IntegrityHypothesis("unresolved-crc", -1, 1),
        ),),
    )
    records = LogicalRecordReassembler(unknown_integrity).add(
        frame(record(marker=0xA5))
    )
    _, physical, descriptors = descriptor_context()
    decision = recognize_open_set(
        physical, descriptors,
        logical_records={"rawm-variable-logical-records": records},
    )
    assert records[0].integrity is RecordIntegrity.UNKNOWN
    assert records[0].integrity_protected
    assert decision.status is RecognitionStatus.CANDIDATE


def test_rawm_recognition_and_integration_remain_read_only() -> None:
    records = LogicalRecordReassembler(grammar()).add(frame(record()))
    _, physical, descriptors = descriptor_context()
    decision = recognize_open_set(
        physical, descriptors,
        logical_records={"rawm-variable-logical-records": records},
    )
    integrated = integrate_logical_records(
        records, family_name="rawm-variable-logical-records",
        physical=physical, descriptors=descriptors,
    )
    assert decision.status is RecognitionStatus.RECOGNIZED
    assert decision.family == "rawm-variable-logical-records"
    assert not decision.write_authorized
    assert not integrated.write_authorized
    assert integrated.proof.operation == "read.logical_protocol_record"


def test_rawm_near_miss_and_bad_integrity_are_not_recognized() -> None:
    _, physical, descriptors = descriptor_context()
    cases = (
        (
            replace(
                grammar(),
                known_fields=grammar().known_fields[:-1],
            ),
            record(),
        ),
        (grammar(), record(marker=0xA5, bad_integrity=True)),
    )
    for record_grammar, raw in cases:
        records = LogicalRecordReassembler(record_grammar).add(frame(raw))
        decision = recognize_open_set(
            physical, descriptors,
            logical_records={"rawm-variable-logical-records": records},
        )
        assert decision.status is RecognitionStatus.CANDIDATE
        assert not decision.write_authorized


def test_unknown_variable_record_protocol_abstains() -> None:
    unknown_grammar = grammar(namespace="unknown.records")
    unknown = LogicalRecordReassembler(unknown_grammar).add(
        frame(record(), namespace="unknown.records")
    )
    _, physical, descriptors = descriptor_context(length=32)
    decision = recognize_open_set(
        physical, descriptors,
        logical_records={"rawm-variable-logical-records": unknown},
    )
    assert decision.status is RecognitionStatus.CANDIDATE
    assert not decision.write_authorized
