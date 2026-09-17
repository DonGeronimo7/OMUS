from __future__ import annotations

from types import SimpleNamespace

from mouse_control.calibrated_discovery import CalibratedDpiState, CalibratedRawMapping
from mouse_control.event_correlation import (
    FeatureChange,
    PhysicalAction,
    RawStreamIdentity,
    TimedEvdevEvent,
    TimedReport,
)
from mouse_control.learning_session import LearningSample
from mouse_control.transition_sources import infer_calibrated_transition_sources


def state(dpi):
    return CalibratedDpiState(dpi, float(dpi), 1000, "high")


def sample(index, *, reports=(), evdev=(), features=()):
    return LearningSample(
        action=PhysicalAction(
            start_ns=index * 100,
            end_ns=index * 100 + 50,
            hid_reports=list(reports),
            evdev_events=list(evdev),
            feature_changes=list(features),
        )
    )


def identity():
    return RawStreamIdentity(3, 0x1234, 0x5678, 2, "descriptor")


def report_key():
    return ("input", 3, 0x1234, 0x5678, 2, "descriptor", 5, 0x11)


def test_persistent_hid_state_is_preferred_absolute_source():
    mapping = CalibratedRawMapping(
        report_key=report_key(),
        offset=4,
        configured_mapping={1: 800, 2: 1500, 3: 2000},
        measured_cpi_mapping={1: 800, 2: 1500, 3: 2000},
        observations=3,
    )
    sources = infer_calibrated_transition_sources(
        (sample(1), sample(2), sample(3)),
        (state(800), state(1500), state(2000)),
        cycle_order=(800, 1500, 2000),
        raw_mappings=(mapping,),
    )
    assert len(sources) == 1
    assert sources[0].kind == "hid_state"
    assert dict(sources[0].raw_to_dpi) == {1: 800, 2: 1500, 3: 2000}


def test_feature_state_can_be_absolute_runtime_source_without_hid_input_state():
    key = ("feature", 2, "descriptor", 7)
    samples = tuple(
        sample(index, features=(FeatureChange(key, 4, before, after),))
        for index, before, after in ((1, 1, 2), (2, 2, 3), (3, 3, 1))
    )
    sources = infer_calibrated_transition_sources(
        samples,
        (state(1500), state(2000), state(800)),
        cycle_order=(800, 1500, 2000),
        feature_report_metadata={
            key: {
                "bus": 3,
                "vendor_id": 0x1234,
                "product_id": 0x5678,
                "interface_number": 2,
                "descriptor_sha256": "descriptor",
                "report_id": 7,
                "report_length": 8,
            }
        },
    )
    assert len(sources) == 1
    assert sources[0].kind == "feature_state"
    assert dict(sources[0].raw_to_dpi) == {2: 1500, 3: 2000, 1: 800}


def test_transient_hid_press_release_becomes_ordered_cycle_trigger():
    stream = identity()
    guided = []
    for index in range(3):
        guided.append(
            sample(
                index + 1,
                reports=(
                    TimedReport(index * 100 + 1, stream, b"\x11\x00\x00\x00\x00"),
                    TimedReport(index * 100 + 2, stream, b"\x11\x00\x00\x00\x20"),
                    TimedReport(index * 100 + 3, stream, b"\x11\x00\x00\x00\x00"),
                ),
            )
        )
    candidate = SimpleNamespace(
        candidate=SimpleNamespace(report_key=report_key(), offset=4)
    )
    sources = infer_calibrated_transition_sources(
        tuple(guided),
        (state(1500), state(2000), state(800)),
        cycle_order=(800, 1500, 2000),
        contrastive_candidates=(candidate,),
    )
    assert len(sources) == 1
    source = sources[0]
    assert source.kind == "hid_cycle_trigger"
    assert source.press_value == 0x20
    assert source.release_value == 0


def test_evdev_button_trigger_is_path_independent():
    guided = tuple(
        sample(
            index,
            evdev=(
                TimedEvdevEvent(index * 100 + 1, "/dev/input/event2", 1, 277, 1),
                TimedEvdevEvent(index * 100 + 2, "/dev/input/event2", 1, 277, 0),
            ),
        )
        for index in range(1, 4)
    )
    controls = (
        sample(10, evdev=(TimedEvdevEvent(1001, "/dev/input/event2", 2, 0, 20),)),
    )
    sources = infer_calibrated_transition_sources(
        guided,
        (state(1500), state(2000), state(800)),
        cycle_order=(800, 1500, 2000),
        control_samples=controls,
        evdev_source_identities={
            "/dev/input/event2": {
                "bus": 3,
                "vendor_id": 0x1234,
                "product_id": 0x5678,
                "interface_number": None,
                "descriptor_sha256": None,
                "name": "Mouse",
                "phys": "usb-test/input0",
                "uniq": "",
            }
        },
    )
    assert len(sources) == 1
    source = sources[0]
    assert source.kind == "evdev_cycle_trigger"
    assert source.event_type == 1
    assert source.code == 277
    assert source.press_value == 1
    assert source.release_value == 0
    assert "/dev/input/event2" not in repr(source.interface)


def test_ambiguous_absolute_hid_fields_fall_back_to_unique_evdev_trigger():
    first = CalibratedRawMapping(
        report_key=report_key(),
        offset=3,
        configured_mapping={1: 800, 2: 1500},
        measured_cpi_mapping={1: 800, 2: 1500},
        observations=2,
    )
    second = CalibratedRawMapping(
        report_key=report_key(),
        offset=4,
        configured_mapping={4: 800, 5: 1500},
        measured_cpi_mapping={4: 800, 5: 1500},
        observations=2,
    )
    guided = tuple(
        sample(
            index,
            evdev=(
                TimedEvdevEvent(index * 100 + 1, "/dev/input/event2", 1, 277, 1),
                TimedEvdevEvent(index * 100 + 2, "/dev/input/event2", 1, 277, 0),
            ),
        )
        for index in range(1, 3)
    )
    sources = infer_calibrated_transition_sources(
        guided,
        (state(1500), state(800)),
        cycle_order=(800, 1500),
        raw_mappings=(first, second),
        evdev_source_identities={
            "/dev/input/event2": {
                "bus": 3,
                "vendor_id": 0x1234,
                "product_id": 0x5678,
                "interface_number": None,
                "descriptor_sha256": None,
                "name": "Mouse",
                "phys": "usb-test/input0",
                "uniq": "",
            }
        },
    )
    assert len(sources) == 1
    assert sources[0].kind == "evdev_cycle_trigger"
