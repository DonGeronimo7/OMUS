"""Project-owned open-set corpus and metric regression tests."""

from pathlib import Path

from mouse_control.discovery_models import DeviceNode, HidReportDefinition, PhysicalDevice
from mouse_control.hid_descriptor import ParsedHidDescriptor
from mouse_control.protocol_benchmark import BenchmarkObservation, score_benchmark
from mouse_control.protocol_repertoire import (
    RecognitionStatus, SemanticExchange, recognize_open_set,
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
    )
    metrics = score_benchmark(observations)

    assert metrics.cases == 6
    assert metrics.exact_outcome_accuracy == 1.0
    assert metrics.recognized_family_precision == 1.0
    assert metrics.known_family_acquisition_recall == 1.0
    assert metrics.unknown_family_false_recognition == 0.0
    assert metrics.structural_collision_false_recognition == 0.0
    assert metrics.coverage == 2 / 6
    assert metrics.abstention == 3 / 6
    assert metrics.ambiguity == 1 / 6
    assert metrics.identity_blinded_correct == 1
    assert all(not item.decision.write_authorized for item in observations)
