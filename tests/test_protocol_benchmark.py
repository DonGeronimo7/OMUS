"""Project-owned open-set corpus and metric regression tests."""

from pathlib import Path

from mouse_control.discovery_models import DeviceNode, HidReportDefinition, PhysicalDevice
from mouse_control.hid_descriptor import ParsedHidDescriptor
from mouse_control.protocol_benchmark import BenchmarkObservation, score_benchmark
from mouse_control.protocol_repertoire import (
    RecognitionStatus, SemanticExchange, recognize_open_set,
)
from mouse_control.temporal_dialogue import (
    BurstDialogueSpec, BurstDialogueResult, DialogueAssembler,
    DialogueObservation, Direction,
)


def _node(*, vendor: int = 0x1234, product: int = 0x5678, interface: int = 2):
    return DeviceNode(
        path=Path("/dev/hidraw-test"), sysfs_path=None, subsystem="hidraw",
        node_type="hidraw", bus=3, vendor_id=vendor, product_id=product,
        interface_number=interface, parent_key="parent:benchmark",
    )


def _physical(node: DeviceNode) -> PhysicalDevice:
    return PhysicalDevice(
        name="Corpus Mouse", vendor_id=node.vendor_id, product_id=node.product_id,
        bus=node.bus, parent_path=None, hidraw_nodes=[node],
        model_fingerprint="benchmark-model",
    )


def _descriptor(*reports: HidReportDefinition) -> ParsedHidDescriptor:
    return ParsedHidDescriptor(raw=b"", reports=tuple(reports))


def _bitmouse_exchange(*, corrupt_sequence: bool = False) -> SemanticExchange:
    request = bytearray(64)
    request[1:6] = bytes((0x72, 4, 9, 0x31, 2))
    request[0] = sum(request[1:6]) & 0xFF
    response = bytearray(64)
    response[:7] = bytes((0x72, 4, 8 if corrupt_sequence else 9, 0, 2, 0xAA, 0x55))
    return SemanticExchange(bytes(request), bytes(response))


def _burst_observation(
    sequence: int, timestamp_ms: int, direction: Direction, payload: bytes,
    *, namespace: str, report_id: int, channel: str = "finalmouse-mouse",
    grammar: str = "finalmouse-burst",
) -> DialogueObservation:
    return DialogueObservation(
        "burst-fixture", "burst-physical", channel, "hid", direction,
        namespace, report_id, 1, timestamp_ms * 1_000_000, sequence, payload,
        transaction_tag=0x10, grammar=grammar,
    )


def _finalmouse_burst(mode: str) -> BurstDialogueResult:
    assembler = DialogueAssembler()
    request = _burst_observation(
        1, 0, Direction.OUT, b"\x00\x10",
        namespace="finalmouse.mouse.command", report_id=0x50,
    )
    quiet, deadline, maximum = (10, 25, 20) if mode == "deadline" else (10, 50, 2)
    assembler.begin_burst(request, BurstDialogueSpec(
        "finalmouse.mouse.command", "finalmouse.mouse.telemetry",
        quiet, deadline, maximum, request_report_id=0x50,
        response_report_id=0x51, response_grammar="finalmouse-burst",
    ))
    namespace = (
        "finalmouse.dongle.telemetry"
        if mode == "wrong-namespace" else "finalmouse.mouse.telemetry"
    )
    timings = ((2, 8), (3, 16), (4, 24)) if mode == "deadline" else ((2, 5),)
    if mode == "max-responses":
        timings = ((2, 2), (3, 4))
    for sequence, timestamp in timings:
        completed = assembler.observe_burst(_burst_observation(
            sequence, timestamp, Direction.IN, b"\x02\x10\x34\x12",
            namespace=namespace, report_id=0x51,
        ))
        if completed:
            return completed[0]
    final_time = 25_000_000 if mode == "deadline" else 15_000_000
    return assembler.advance_time(final_time)[0]


def _unknown_burst() -> BurstDialogueResult:
    assembler = DialogueAssembler()
    request = _burst_observation(
        1, 0, Direction.OUT, b"\x00\x99", namespace="unknown.command",
        report_id=0x60, channel="unknown-channel", grammar="unknown-burst",
    )
    assembler.begin_burst(request, BurstDialogueSpec(
        "unknown.command", "unknown.records", 10, 50, 8,
        request_report_id=0x60, response_report_id=0x61,
        response_channel_id="unknown-channel", response_grammar="unknown-burst",
    ))
    for sequence, timestamp in ((2, 2), (3, 4)):
        assembler.observe_burst(_burst_observation(
            sequence, timestamp, Direction.IN, b"\x01\x99\x01",
            namespace="unknown.records", report_id=0x61,
            channel="unknown-channel", grammar="unknown-burst",
        ))
    return assembler.advance_time(14_000_000)[0]


def test_research_ingestion_corpus_reports_open_set_metrics_without_writes() -> None:
    bitmouse = _node(vendor=0xDEAD, product=0xBEEF)
    bitmouse_descriptors = {bitmouse: _descriptor(
        HidReportDefinition(0x72, "output", 64, (0xFF00,)),
        HidReportDefinition(0x72, "input", 64, (0xFF00,)),
    )}
    valid = recognize_open_set(
        _physical(bitmouse), bitmouse_descriptors,
        exchanges={"bitmouse-72": (_bitmouse_exchange(),)},
    )
    near_miss = recognize_open_set(
        _physical(bitmouse), bitmouse_descriptors,
        exchanges={"bitmouse-72": (_bitmouse_exchange(corrupt_sequence=True),)},
    )

    unknown_node = _node()
    unknown = recognize_open_set(
        _physical(unknown_node),
        {unknown_node: _descriptor(HidReportDefinition(0x44, "input", 11, (0xFF33,)))},
    )

    keychron = _node(vendor=0x3434, product=0x0B30)
    keychron_reports = (
        HidReportDefinition(0xB3, "output", 64, (0xFFC1,)),
        HidReportDefinition(0xB4, "input", 64, (0xFFC1,)),
        HidReportDefinition(0xB5, "output", 64, (0xFFC1,)),
        HidReportDefinition(0xB6, "input", 64, (0xFFC1,)),
    )
    keychron_candidate = recognize_open_set(
        _physical(keychron), {keychron: _descriptor(*keychron_reports)},
        exchanges={"keychron-m6-paired-namespaces": (
            SemanticExchange(b"query", b"status", 0xB3, 0xB4),
            SemanticExchange(b"setting", b"ack", 0xB5, 0xB6),
        )},
    )

    collision = _node()
    collision_decision = recognize_open_set(
        _physical(collision), {collision: _descriptor(
            HidReportDefinition(0x04, "feature", 520, (0xFF00,)),
            HidReportDefinition(0x05, "feature", 6, (0xFF00,)),
            *keychron_reports,
        )},
    )

    venus = _node(vendor=0x04D9, product=0xFC55)
    venus_candidate = recognize_open_set(
        _physical(venus), {venus: _descriptor(
            HidReportDefinition(0x02, "feature", 16, (0xFFA0,)),
            HidReportDefinition(0x03, "feature", 64, (0xFFA0,)),
        )},
    )

    finalmouse = _node(vendor=0x361D, product=0x0100)
    finalmouse_descriptors = {finalmouse: _descriptor(
        HidReportDefinition(0x50, "output", 64, (0xFF00,)),
        HidReportDefinition(0x51, "input", 64, (0xFF00,)),
    )}
    finalmouse_decisions = {
        mode: recognize_open_set(
            _physical(finalmouse), finalmouse_descriptors,
            bursts={"finalmouse-ulx-bounded-telemetry": (_finalmouse_burst(mode),)},
        )
        for mode in ("max-responses", "quiet", "deadline", "wrong-namespace")
    }
    unknown_burst_node = _node(vendor=0x9999, product=0x9999)
    unknown_burst_decision = recognize_open_set(
        _physical(unknown_burst_node), {unknown_burst_node: _descriptor(
            HidReportDefinition(0x60, "output", 32, (0xFF44,)),
            HidReportDefinition(0x61, "input", 32, (0xFF44,)),
        )},
        bursts={"finalmouse-ulx-bounded-telemetry": (_unknown_burst(),)},
    )

    observations = (
        BenchmarkObservation(
            "bitmouse-valid-identity-blinded", RecognitionStatus.RECOGNIZED,
            valid, "bitmouse-72", identity_blinded=True,
        ),
        BenchmarkObservation("bitmouse-wrong-sequence", RecognitionStatus.CANDIDATE, near_miss),
        BenchmarkObservation("synthetic-unknown", RecognitionStatus.UNKNOWN, unknown),
        BenchmarkObservation(
            "keychron-paired-dialogues", RecognitionStatus.RECOGNIZED,
            keychron_candidate, "keychron-m6-paired-namespaces",
        ),
        BenchmarkObservation("structural-collision", RecognitionStatus.AMBIGUOUS, collision_decision),
        BenchmarkObservation("venus-structure-only", RecognitionStatus.CANDIDATE, venus_candidate),
        BenchmarkObservation(
            "finalmouse-valid-max-count", RecognitionStatus.RECOGNIZED,
            finalmouse_decisions["max-responses"], "finalmouse-ulx-bounded-telemetry",
        ),
        BenchmarkObservation(
            "finalmouse-quiet-completion", RecognitionStatus.RECOGNIZED,
            finalmouse_decisions["quiet"], "finalmouse-ulx-bounded-telemetry",
        ),
        BenchmarkObservation(
            "finalmouse-deadline-completion", RecognitionStatus.RECOGNIZED,
            finalmouse_decisions["deadline"], "finalmouse-ulx-bounded-telemetry",
        ),
        BenchmarkObservation(
            "finalmouse-wrong-namespace", RecognitionStatus.CANDIDATE,
            finalmouse_decisions["wrong-namespace"],
        ),
        BenchmarkObservation(
            "unknown-multi-response", RecognitionStatus.CANDIDATE,
            unknown_burst_decision,
        ),
    )
    metrics = score_benchmark(observations)

    assert metrics.cases == 11
    assert metrics.exact_outcome_accuracy == 1.0
    assert metrics.recognized_family_precision == 1.0
    assert metrics.known_family_acquisition_recall == 1.0
    assert metrics.unknown_family_false_recognition == 0.0
    assert metrics.structural_collision_false_recognition == 0.0
    assert metrics.coverage == 5 / 11
    assert metrics.abstention == 5 / 11
    assert metrics.ambiguity == 1 / 11
    assert metrics.identity_blinded_correct == 1
    assert all(not item.decision.write_authorized for item in observations)
