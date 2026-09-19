"""Tests for the vendor-agnostic protocol repertoire and inference core."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from mouse_control.discovery_models import DeviceNode, HidReportDefinition, PhysicalDevice
from mouse_control.event_correlation import CorrelationCandidate
from mouse_control.hid_descriptor import ParsedHidDescriptor
from mouse_control.protocol_codec import (
    ProtocolCodecError,
    decode_value,
    encode_value,
    fit_linear_codec,
    infer_polling_codecs,
    infer_trailing_checksums,
)
from mouse_control.protocol_grammar import CodecKind, CodecSpec
from mouse_control.protocol_repertoire import (
    DEFAULT_REPERTOIRE, ProtocolKnowledgeError, SemanticExchange,
    decode_redragon_m724_dpi, decode_ryunix_telemetry,
    encode_redragon_m724_dpi, match_repertoire, recognize_family_semantics,
    recognize_open_set, RecognitionStatus,
)
from mouse_control.semantic_inference import infer_stage_hypotheses
from mouse_control.temporal_dialogue import (
    BurstDialogueSpec, DialogueAssembler, DialogueObservation, Direction,
    PushedStateSpec,
)


def node(
    path: str = "/dev/hidraw8", *, vendor: int = 0x1234,
    product: int = 0x5678, interface: int = 2,
):
    return DeviceNode(
        path=Path(path),
        sysfs_path=None,
        subsystem="hidraw",
        node_type="hidraw",
        bus=3,
        vendor_id=vendor,
        product_id=product,
        interface_number=interface,
        parent_key="parent:test",
    )


def physical(*, vendor: int = 0x1234, product: int = 0x5678, n: DeviceNode | None = None):
    n = n or node(vendor=vendor, product=product)
    return PhysicalDevice(
        name="Test Mouse",
        vendor_id=vendor,
        product_id=product,
        bus=3,
        parent_path=None,
        hidraw_nodes=[n],
        model_fingerprint="model",
    )


def descriptor(*reports: HidReportDefinition):
    return ParsedHidDescriptor(raw=b"", reports=tuple(reports))


def family(name: str):
    return next(item for item in DEFAULT_REPERTOIRE if item.name == name)


def test_codec_roundtrips_linear_reciprocal_and_enum():
    linear = CodecSpec(CodecKind.LINEAR, scale=50, offset=50)
    assert decode_value(31, linear) == 1600
    assert encode_value(1600, linear) == b"\x1f"

    reciprocal = CodecSpec(CodecKind.RECIPROCAL, base=1000)
    assert decode_value(2, reciprocal) == 500
    assert encode_value(500, reciprocal) == b"\x02"

    enum = CodecSpec(CodecKind.ENUM, values={4: 125, 3: 250, 2: 500, 1: 1000})
    assert decode_value(1, enum) == 1000
    assert encode_value(250, enum) == b"\x03"


def test_linear_dpi_codec_is_inferred_from_exact_observations():
    spec = fit_linear_codec(((0, 50), (1, 100), (31, 1600)))
    assert spec is not None
    assert spec.kind is CodecKind.LINEAR
    assert spec.scale == 50
    assert spec.offset == 50


def test_polling_inference_recognizes_period_divisor_family():
    hypotheses = infer_polling_codecs((8, 4, 2, 1))
    assert hypotheses
    assert any(
        dict(item.mapping) == {1: 1000, 2: 500, 4: 250, 8: 125}
        for item in hypotheses
    )


def test_sum8_frame_checksum_is_inferred():
    samples = []
    for command, payload in ((0x21, (1, 2, 3)), (0x22, (4, 5)), (0x23, (6,))):
        frame = bytearray(64)
        frame[0] = 0x05
        frame[1] = command
        frame[2] = 0
        frame[3] = len(payload)
        frame[4:4 + len(payload)] = bytes(payload)
        frame[63] = sum(frame[1:63]) & 0xFF
        samples.append(bytes(frame))
    inferred = infer_trailing_checksums(samples)
    assert any(item.algorithm == "sum8" and item.start == 1 for item in inferred)


def test_sinowealth_family_can_match_cross_brand_from_report_grammar():
    n = node(vendor=0x9999, product=0x1111)
    d = descriptor(
        HidReportDefinition(0x04, "feature", 520, (0xFF00,)),
        HidReportDefinition(0x05, "feature", 6, (0xFF00,)),
    )
    matches = match_repertoire(physical(vendor=0x9999, product=0x1111, n=n), {n: d})
    assert matches
    assert matches[0].family.name == "sinowealth-config-blob"
    assert matches[0].score >= matches[0].family.minimum_match_score
    assert not matches[0].write_authorized


def test_identity_hint_alone_cannot_match_hidpp_teacher():
    n = node(vendor=0x046D, product=0x4074)
    matches = match_repertoire(physical(vendor=0x046D, product=0x4074, n=n), {n: descriptor()})
    assert all(item.family.name != "hidpp2" for item in matches)


def test_attackshark_requires_structural_signature_not_just_vid_pid():
    n = node(vendor=0x1D57, product=0xFA60)
    missing = match_repertoire(
        physical(vendor=0x1D57, product=0xFA60, n=n),
        {n: descriptor(HidReportDefinition(0x04, "feature", 56, (0xFF00,)))},
    )
    assert all(item.family.name != "attackshark-x11-feature" for item in missing)

    complete = match_repertoire(
        physical(vendor=0x1D57, product=0xFA60, n=n),
        {
            n: descriptor(
                HidReportDefinition(0x04, "feature", 56, (0xFF00,)),
                HidReportDefinition(0x05, "feature", 15, (0xFF00,)),
                HidReportDefinition(0x06, "feature", 9, (0xFF00,)),
            )
        },
    )
    attack = next(item for item in complete if item.family.name == "attackshark-x11-feature")
    assert attack.exact_identity
    # The repertoire is strong enough to describe the known exact model, but
    # DiscoveryEngine still does not manufacture writable capabilities from a
    # repertoire match. Writes require a later execution/validation layer.
    assert attack.write_authorized


def test_stage_inference_labels_repeated_small_state_changes_only_as_hypothesis():
    candidate = CorrelationCandidate(
        report_key=5,
        offset=2,
        observations=3,
        values=(1, 2, 3),
        transitions=((1, 2), (2, 3), (3, 1)),
    )
    result = infer_stage_hypotheses((candidate,))
    assert len(result) == 1
    assert result[0].behavior.value == "dpi_stage_index"
    assert result[0].confidence == "correlated"


def _bitmouse_request(*, target: int, sequence: int, reply_length: int) -> bytes:
    frame = bytearray(64)
    frame[1:6] = bytes((0x72, target, sequence, 0x31, reply_length))
    frame[0] = sum(frame[1:6]) & 0xFF
    return bytes(frame)


def test_bitmouse_semantic_phase_recognizes_grammar_but_never_authorizes_write() -> None:
    n = node(vendor=0x9999, product=0x2222)
    matches = match_repertoire(
        physical(vendor=0x9999, product=0x2222, n=n),
        {n: descriptor(
            HidReportDefinition(0x72, "output", 64, (0xFF00,)),
            HidReportDefinition(0x72, "input", 64, (0xFF00,)),
        )},
    )
    structural = next(item for item in matches if item.family.name == "bitmouse-72")
    request = _bitmouse_request(target=4, sequence=9, reply_length=3)
    response = bytearray([0xEE] * 64)
    response[:8] = bytes((0x72, 4, 9, 0, 3, 0x10, 0x20, 0x30))
    semantic = recognize_family_semantics(
        structural, (SemanticExchange(request, bytes(response)),)
    )

    assert semantic.recognized
    assert semantic.semantic_records == (bytes(response[:8]),)
    assert b"\xee" not in semantic.semantic_records[0]
    assert semantic.write_authorized is False
    assert structural.write_authorized is False


def test_bitmouse_semantic_phase_refuses_sequence_collision() -> None:
    n = node()
    structural = next(item for item in match_repertoire(
        physical(n=n), {n: descriptor(
            HidReportDefinition(0x72, "output", 64, (0xFF00,)),
            HidReportDefinition(0x72, "input", 64, (0xFF00,)),
        )},
    ) if item.family.name == "bitmouse-72")
    request = _bitmouse_request(target=1, sequence=2, reply_length=1)
    response = bytearray(64)
    response[:6] = bytes((0x72, 1, 99, 0, 1, 7))
    semantic = recognize_family_semantics(structural, (SemanticExchange(request, bytes(response)),))
    assert not semantic.recognized
    assert "sequence-correlation" in semantic.missing


@pytest.mark.parametrize(
    ("mutation", "missing"),
    (
        (lambda request, response: request.__setitem__(0, request[0] ^ 0x01), "leading-request-checksum"),
        (lambda request, response: response.__setitem__(1, response[1] ^ 0x01), "target-correlation"),
        (lambda request, response: response.__setitem__(2, response[2] ^ 0x01), "sequence-correlation"),
        (lambda request, response: response.__setitem__(4, 0xFF), "declared-semantic-reply-length"),
    ),
)
def test_bitmouse_generic_recipe_turns_each_broken_relation_into_negative_evidence(
    mutation, missing: str,
) -> None:
    n = node()
    descriptor_map = {n: descriptor(
        HidReportDefinition(0x72, "output", 64, (0xFF00,)),
        HidReportDefinition(0x72, "input", 64, (0xFF00,)),
    )}
    request = bytearray(_bitmouse_request(target=4, sequence=9, reply_length=3))
    response = bytearray(64)
    response[:8] = bytes((0x72, 4, 9, 0, 3, 0x10, 0x20, 0x30))
    mutation(request, response)
    decision = recognize_open_set(
        physical(n=n), descriptor_map,
        exchanges={"bitmouse-72": (SemanticExchange(bytes(request), bytes(response)),)},
    )
    assert decision.status is RecognitionStatus.CANDIDATE
    assert decision.family == "bitmouse-72"
    assert missing in decision.ranked[0].missing
    assert decision.write_authorized is False


def test_open_set_recognizes_identity_blinded_bitmouse_grammar() -> None:
    n = node(vendor=0xDEAD, product=0xBEEF)
    descriptor_map = {n: descriptor(
        HidReportDefinition(0x72, "output", 64, (0xFF00,)),
        HidReportDefinition(0x72, "input", 64, (0xFF00,)),
    )}
    request = _bitmouse_request(target=7, sequence=22, reply_length=2)
    response = bytearray(64)
    response[:7] = bytes((0x72, 7, 22, 0, 2, 0xAA, 0x55))
    decision = recognize_open_set(
        physical(vendor=0xDEAD, product=0xBEEF, n=n), descriptor_map,
        exchanges={"bitmouse-72": (SemanticExchange(request, bytes(response)),)},
    )
    assert decision.status is RecognitionStatus.RECOGNIZED
    assert decision.family == "bitmouse-72"
    assert decision.ranked[0].write_authorized is False


def test_open_set_unknown_and_structural_collision_abstain() -> None:
    n = node()
    unknown = recognize_open_set(
        physical(n=n),
        {n: descriptor(HidReportDefinition(0x44, "input", 11, (0xFF33,)))},
    )
    assert unknown.status is RecognitionStatus.UNKNOWN
    assert unknown.family is None

    collision = recognize_open_set(
        physical(n=n),
        {n: descriptor(
            HidReportDefinition(0x04, "feature", 520, (0xFF00,)),
            HidReportDefinition(0x05, "feature", 6, (0xFF00,)),
            HidReportDefinition(0xB3, "output", 64, (0xFFC1,)),
            HidReportDefinition(0xB4, "input", 64, (0xFFC1,)),
            HidReportDefinition(0xB5, "output", 64, (0xFFC1,)),
            HidReportDefinition(0xB6, "input", 64, (0xFFC1,)),
        )},
    )
    assert collision.status is RecognitionStatus.AMBIGUOUS
    assert collision.family is None
    assert {item.candidate.family.name for item in collision.ranked} >= {
        "sinowealth-config-blob", "keychron-m6-paired-namespaces",
    }


def test_redragon_m724_requires_exact_identity_and_control_collection() -> None:
    n = node(vendor=0x04D9, product=0xFC7A)
    report = HidReportDefinition(
        0x02, "feature", 16, (0xFFA0,), ((0xFFA0, 0x01),),
    )
    matches = match_repertoire(
        physical(vendor=0x04D9, product=0xFC7A, n=n), {n: descriptor(report)}
    )
    redragon = next(item for item in matches if item.family.name == "redragon-m724-feature-session")
    assert redragon.exact_identity
    assert redragon.write_authorized is False

    wrong_usage = HidReportDefinition(0x02, "feature", 16, (0xFFA0,), ((0xFFA0, 0x02),))
    assert not any(item.family.name == redragon.family.name for item in match_repertoire(
        physical(vendor=0x04D9, product=0xFC7A, n=n), {n: descriptor(wrong_usage)}
    ))
    assert not any(item.family.name == redragon.family.name for item in match_repertoire(
        physical(vendor=0x04D9, product=0xFC7B, n=n), {n: descriptor(report)}
    ))
    assert not any(item.family.name == redragon.family.name for item in match_repertoire(
        physical(vendor=0x04D9, product=0xFC7A, n=n), {n: descriptor()}
    ))


def test_redragon_m724_dpi_polling_and_session_knowledge_are_descriptive_only() -> None:
    assert encode_redragon_m724_dpi(800).value == 0x12
    assert encode_redragon_m724_dpi(12400).value == 0x8C
    assert encode_redragon_m724_dpi(12400).range_flag == 1
    assert decode_redragon_m724_dpi(0x12, 0) == 800
    assert decode_redragon_m724_dpi(0x8C, 1) == 12444
    with pytest.raises(ProtocolKnowledgeError):
        encode_redragon_m724_dpi(0)

    redragon = family("redragon-m724-feature-session")
    polling = redragon.bindings[0].codec
    assert [decode_value(raw, polling) for raw in (1, 2, 4, 8)] == [1000, 500, 250, 125]
    with pytest.raises(ProtocolCodecError, match="observed codec domain"):
        encode_value(200, polling)
    session = redragon.sessions[0]
    assert session.open_frame[:3] == b"\x02\xf5\x00"
    assert session.close_frame[:3] == b"\x02\xf5\x01"
    assert session.cleanup_required
    assert session.commit_codes == (0x04, 0x01, 0x02, 0x08, 0x10)
    assert "individual commit-code meanings" in session.unresolved_semantics
    assert redragon.transactions == ()
    assert redragon.can_authorize_write(exact_model=True) is False


def test_ryunix_telemetry_is_exact_read_only_structure() -> None:
    n = node(vendor=0x04F3, product=0x026E)
    telemetry_report = HidReportDefinition(
        0x04, "input", 7, (0x0A,), ((0x0A, 0xC7),),
    )
    matches = match_repertoire(
        physical(vendor=0x04F3, product=0x026E, n=n), {n: descriptor(telemetry_report)}
    )
    ryunix = next(item for item in matches if item.family.name == "ryunix-kyu-pro-mx1-telemetry")
    assert ryunix.write_authorized is False
    assert ryunix.family.can_authorize_write(exact_model=True) is False
    decoded = decode_ryunix_telemetry(bytes((0x04, 1, 3, 2, 83, 1, 7)))
    assert (decoded.active, decoded.dpi_stage, decoded.polling_rate_hz) == (True, 3, 500)
    assert (decoded.battery_percent, decoded.charging, decoded.led_mode) == (83, True, 7)

    for malformed in (
        b"\x04\x01\x03\x02\x53\x01",
        bytes((0x04, 2, 3, 2, 83, 1, 7)),
        bytes((0x04, 1, 3, 3, 83, 1, 7)),
        bytes((0x04, 1, 3, 2, 101, 1, 7)),
        bytes((0x04, 1, 3, 2, 83, 2, 7)),
    ):
        with pytest.raises(ProtocolKnowledgeError):
            decode_ryunix_telemetry(malformed)

    assert not any(item.family.name == ryunix.family.name for item in match_repertoire(
        physical(vendor=0x04F3, product=0x9999, n=n), {n: descriptor(telemetry_report)}
    ))
    assert not any(item.family.name == ryunix.family.name for item in match_repertoire(
        physical(vendor=0x04F3, product=0x026E, n=n), {
            n: descriptor(HidReportDefinition(0x05, "feature", 7, (0x0A,), ((0x0A, 0xC7),)))
        }
    ))


def test_holtek_venus_requires_exact_identity_interface_and_both_feature_shapes() -> None:
    n = node(vendor=0x04D9, product=0xFC55, interface=2)
    reports = descriptor(
        HidReportDefinition(0x02, "feature", 16, (0xFFA0,)),
        HidReportDefinition(0x03, "feature", 64, (0xFFA0,)),
    )
    matches = match_repertoire(
        physical(vendor=0x04D9, product=0xFC55, n=n), {n: reports}
    )
    venus = next(item for item in matches if item.family.name == "holtek-venus-feature-flash")
    assert venus.exact_identity
    assert venus.write_authorized is False
    assert venus.family.transactions == ()

    wrong_interface = node(vendor=0x04D9, product=0xFC55, interface=1)
    assert not any(item.family.name == venus.family.name for item in match_repertoire(
        physical(vendor=0x04D9, product=0xFC55, n=wrong_interface),
        {wrong_interface: reports},
    ))
    assert not any(item.family.name == venus.family.name for item in match_repertoire(
        physical(vendor=0x04D9, product=0xFC55, n=n),
        {n: descriptor(HidReportDefinition(0x02, "feature", 16, (0xFFA0,)))},
    ))


def test_keychron_namespace_shape_is_candidate_not_confident_recognition() -> None:
    n = node(vendor=0x3434, product=0x0B30)
    reports = descriptor(
        HidReportDefinition(0xB3, "output", 64, (0xFFC1,)),
        HidReportDefinition(0xB4, "input", 64, (0xFFC1,)),
        HidReportDefinition(0xB5, "output", 64, (0xFFC1,)),
        HidReportDefinition(0xB6, "input", 64, (0xFFC1,)),
    )
    decision = recognize_open_set(
        physical(vendor=0x3434, product=0x0B30, n=n), {n: reports}
    )
    assert decision.status is RecognitionStatus.CANDIDATE
    assert decision.family == "keychron-m6-paired-namespaces"
    assert decision.write_authorized is False

    partial = recognize_open_set(
        physical(vendor=0x3434, product=0x0B30, n=n), {n: reports},
        exchanges={"keychron-m6-paired-namespaces": (
            SemanticExchange(b"query", b"status", 0xB3, 0xB4),
        )},
    )
    assert partial.status is RecognitionStatus.CANDIDATE
    assert "setting-ack-namespace-pair" in partial.ranked[0].missing

    paired = recognize_open_set(
        physical(vendor=0x3434, product=0x0B30, n=n), {n: reports},
        exchanges={"keychron-m6-paired-namespaces": (
            SemanticExchange(b"query", b"status", 0xB3, 0xB4),
            SemanticExchange(b"setting", b"ack", 0xB5, 0xB6),
        )},
    )
    assert paired.status is RecognitionStatus.RECOGNIZED
    assert paired.family == "keychron-m6-paired-namespaces"
    assert paired.write_authorized is False


def _finalmouse_observation(
    sequence: int, timestamp_ms: int, direction: Direction, payload: bytes,
    *, target: str = "mouse",
) -> DialogueObservation:
    namespace_role = "command" if direction is Direction.OUT else "telemetry"
    return DialogueObservation(
        source_id="finalmouse-fixture", physical_id="finalmouse-physical",
        channel_id=f"finalmouse-{target}", transport="hid",
        direction=direction,
        report_namespace=f"finalmouse.{target}.{namespace_role}",
        report_id=0x50 if direction is Direction.OUT else 0x51,
        generation=1, timestamp_ns=timestamp_ms * 1_000_000,
        sequence=sequence, payload=payload, transaction_tag=0x10,
        grammar="finalmouse-telemetry-burst",
    )


def _finalmouse_burst(*, request_target: str = "mouse", response_target: str = "mouse"):
    assembler = DialogueAssembler()
    request = _finalmouse_observation(
        1, 0, Direction.OUT, bytes((0, 0x10)), target=request_target,
    )
    assembler.begin_burst(request, BurstDialogueSpec(
        request_namespace=f"finalmouse.{request_target}.command",
        response_namespace=f"finalmouse.{request_target}.telemetry",
        request_report_id=0x50, response_report_id=0x51,
        response_channel_id=f"finalmouse-{request_target}",
        response_grammar="finalmouse-telemetry-burst",
        quiet_interval_ms=10, absolute_deadline_ms=50, max_responses=8,
    ))
    assembler.observe_burst(_finalmouse_observation(
        2, 5, Direction.IN, bytes((2, 0x10, 0x34, 0x12)),
        target=response_target,
    ))
    return assembler.advance_time(15_000_000)[0]


def test_finalmouse_recognition_consumes_generic_burst_and_remains_write_disabled() -> None:
    n = node(vendor=0x361D, product=0x0100)
    reports = descriptor(
        HidReportDefinition(0x50, "output", 64, (0xFF00,)),
        HidReportDefinition(0x51, "input", 64, (0xFF00,)),
    )
    burst = _finalmouse_burst()
    decision = recognize_open_set(
        physical(vendor=0x361D, product=0x0100, n=n), {n: reports},
        bursts={"finalmouse-ulx-bounded-telemetry": (burst,)},
    )
    assert decision.status is RecognitionStatus.RECOGNIZED
    assert decision.family == "finalmouse-ulx-bounded-telemetry"
    assert decision.write_authorized is False
    assert decision.ranked[0].semantic_records == (bytes((2, 0x10, 0x34, 0x12)),)


@pytest.mark.parametrize(
    ("request_target", "response_target"),
    (("mouse", "dongle"), ("dongle", "mouse")),
)
def test_finalmouse_mouse_and_dongle_namespaces_are_not_interchangeable(
    request_target: str, response_target: str,
) -> None:
    n = node(vendor=0x361D, product=0x0100)
    reports = descriptor(
        HidReportDefinition(0x50, "output", 64, (0xFF00,)),
        HidReportDefinition(0x51, "input", 64, (0xFF00,)),
    )
    burst = _finalmouse_burst(
        request_target=request_target, response_target=response_target,
    )
    assert burst.responses == ()
    decision = recognize_open_set(
        physical(vendor=0x361D, product=0x0100, n=n), {n: reports},
        bursts={"finalmouse-ulx-bounded-telemetry": (burst,)},
    )
    assert decision.status is RecognitionStatus.CANDIDATE
    assert decision.write_authorized is False


def test_unknown_multi_response_protocol_abstains_from_finalmouse() -> None:
    n = node(vendor=0x9999, product=0x9999)
    reports = descriptor(
        HidReportDefinition(0x60, "output", 32, (0xFF44,)),
        HidReportDefinition(0x61, "input", 32, (0xFF44,)),
    )
    assembler = DialogueAssembler()
    request = DialogueObservation(
        "unknown", "unknown-physical", "unknown-channel", "hid", Direction.OUT,
        "unknown.command", 0x60, 1, 0, 1, b"\x00\x99", grammar="unknown-burst",
    )
    assembler.begin_burst(request, BurstDialogueSpec(
        "unknown.command", "unknown.records", 10, 50, 8,
        request_report_id=0x60, response_report_id=0x61,
        response_grammar="unknown-burst",
    ))
    for sequence, timestamp in ((2, 2), (3, 4)):
        assembler.observe_burst(DialogueObservation(
            "unknown", "unknown-physical", "unknown-channel", "hid", Direction.IN,
            "unknown.records", 0x61, 1, timestamp * 1_000_000, sequence,
            b"\x01\x99\x01", grammar="unknown-burst",
        ))
    burst = assembler.advance_time(14_000_000)[0]
    decision = recognize_open_set(
        physical(vendor=0x9999, product=0x9999, n=n), {n: reports},
        bursts={"finalmouse-ulx-bounded-telemetry": (burst,)},
    )
    assert decision.status is RecognitionStatus.CANDIDATE
    assert decision.family == "finalmouse-ulx-bounded-telemetry"
    assert "declared-burst-namespace-pair" in decision.ranked[0].missing


def _mchose_spec(*, namespace="mchose.realtek.state"):
    return PushedStateSpec(
        namespace=namespace, report_id=0x13, grammar="async-state",
        channel_id="realtek-input", periodic_max_gap_ms=100,
        nudge_window_ms=50, nudge_namespace="feature-nudge",
        nudge_report_id=0x05, nudge_channel_id="realtek-feature",
    )


def _mchose_observation(sequence: int, timestamp_ms: int, encoded: int, *, generation=1):
    return DialogueObservation(
        "mchose-fixture", "mchose-physical", "realtek-input", "hid",
        Direction.IN, "mchose.realtek.state", 0x13, generation,
        timestamp_ms * 1_000_000, sequence, bytes((0x1D, encoded)),
        grammar="async-state",
    )


def _mchose_periodic_records(*, subtype=0x1D, wrong_transform=False):
    assembler = DialogueAssembler()
    records = []
    for sequence, timestamp, encoded in ((1, 0, 0xFE), (2, 40, 0xFD)):
        transformed = bytes((encoded ^ (0x00 if wrong_transform else 0xFF),))
        record = assembler.observe_pushed_state(
            _mchose_observation(sequence, timestamp, encoded), _mchose_spec(),
            semantic_state_id="opaque-device-state", decoded_state=transformed,
            subtype=subtype, transform="xor_ff", transform_source=bytes((encoded,)),
            transformed_payload=transformed,
        )
        assert record is not None
        records.append(record)
    return tuple(records)


def _mchose_descriptor():
    return descriptor(HidReportDefinition(0x13, "input", 16, (0xFF00,)))


def test_mchose_periodic_push_recognition_is_passive_and_write_disabled() -> None:
    n = node(vendor=0x3554, product=0xF58A)
    decision = recognize_open_set(
        physical(vendor=0x3554, product=0xF58A, n=n), {n: _mchose_descriptor()},
        pushed_states={"mchose-realtek-l7-pushed-state": _mchose_periodic_records()},
    )
    assert decision.status is RecognitionStatus.RECOGNIZED
    assert decision.family == "mchose-realtek-l7-pushed-state"
    assert decision.write_authorized is False
    assert decision.ranked[0].semantic_records == (b"\x01", b"\x02")


def test_mchose_nudge_association_recognizes_delayed_push_without_response_ownership() -> None:
    n = node(vendor=0x3554, product=0xF58A)
    assembler = DialogueAssembler()
    nudge = DialogueObservation(
        "mchose-fixture", "mchose-physical", "realtek-feature", "hid",
        Direction.OUT, "feature-nudge", 0x05, 1, 0, 1, b"read-side-nudge",
        grammar="nudge",
    )
    assembler.begin_state_nudge(nudge, _mchose_spec())
    record = assembler.observe_pushed_state(
        _mchose_observation(2, 20, 0xFE), _mchose_spec(),
        semantic_state_id="opaque-device-state", decoded_state=b"\x01",
        subtype=0x1D, transform="xor_ff", transform_source=b"\xfe",
        transformed_payload=b"\x01",
    )
    assert record is not None
    decision = recognize_open_set(
        physical(vendor=0x3554, product=0xF58A, n=n), {n: _mchose_descriptor()},
        pushed_states={"mchose-realtek-l7-pushed-state": (record,)},
    )
    assert decision.status is RecognitionStatus.RECOGNIZED
    assert decision.write_authorized is False


@pytest.mark.parametrize(
    "records",
    (
        pytest.param(_mchose_periodic_records(subtype=0x1C), id="wrong-subtype"),
        pytest.param(_mchose_periodic_records(wrong_transform=True), id="wrong-transform"),
    ),
)
def test_mchose_negative_discriminators_abstain(records) -> None:
    n = node(vendor=0x3554, product=0xF58A)
    decision = recognize_open_set(
        physical(vendor=0x3554, product=0xF58A, n=n), {n: _mchose_descriptor()},
        pushed_states={"mchose-realtek-l7-pushed-state": records},
    )
    assert decision.status is RecognitionStatus.CANDIDATE
    assert decision.write_authorized is False


def test_old_generation_and_unknown_async_state_abstain() -> None:
    n = node(vendor=0x3554, product=0xF58A)
    assembler = DialogueAssembler()
    assembler.advance_generation("mchose-physical", 2)
    stale = assembler.observe_pushed_state(
        _mchose_observation(1, 10, 0xFE, generation=1), _mchose_spec(),
        semantic_state_id="opaque-device-state", decoded_state=b"\x01",
        subtype=0x1D, transform="xor_ff", transform_source=b"\xfe",
        transformed_payload=b"\x01",
    )
    assert stale is not None
    stale_decision = recognize_open_set(
        physical(vendor=0x3554, product=0xF58A, n=n), {n: _mchose_descriptor()},
        pushed_states={"mchose-realtek-l7-pushed-state": (stale,)},
    )
    assert stale_decision.status is RecognitionStatus.CANDIDATE

    unknown_spec = _mchose_spec(namespace="unknown.async.state")
    unknown_observation = DialogueObservation(
        "unknown", "unknown-physical", "realtek-input", "hid", Direction.IN,
        "unknown.async.state", 0x13, 1, 0, 1, b"\x99\x44", grammar="async-state",
    )
    unknown = DialogueAssembler().observe_pushed_state(
        unknown_observation, unknown_spec, semantic_state_id="unknown-state",
        decoded_state=b"\xbb", subtype=0x99, transform="xor_ff",
        transform_source=b"\x44", transformed_payload=b"\xbb",
    )
    assert unknown is not None
    unknown_decision = recognize_open_set(
        physical(vendor=0x3554, product=0xF58A, n=n), {n: _mchose_descriptor()},
        pushed_states={"mchose-realtek-l7-pushed-state": (unknown,)},
    )
    assert unknown_decision.status is RecognitionStatus.CANDIDATE
    assert "pushed-state-namespace" in unknown_decision.ranked[0].missing


def test_mixed_pushed_state_streams_cannot_form_one_recognition() -> None:
    n = node(vendor=0x3554, product=0xF58A)
    records = list(_mchose_periodic_records())
    records[1] = replace(
        records[1],
        observation=replace(records[1].observation, source_id="different-source"),
    )
    decision = recognize_open_set(
        physical(vendor=0x3554, product=0xF58A, n=n), {n: _mchose_descriptor()},
        pushed_states={"mchose-realtek-l7-pushed-state": tuple(records)},
    )
    assert decision.status is RecognitionStatus.CANDIDATE
    assert "coherent-pushed-state-stream" in decision.ranked[0].missing
