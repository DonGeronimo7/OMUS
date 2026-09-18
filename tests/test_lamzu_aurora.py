from pathlib import Path
from types import SimpleNamespace

import pytest
from evdev import ecodes

from mouse_control import discovery as discovery_module
from mouse_control.discovery_lab import (
    ChargingState, LabExperiment, PowerSemantic, RouteEndpoint, RoutingStatus,
)
from mouse_control.discovery_models import DeviceNode, HidReportDefinition, PhysicalDevice
from mouse_control.hid_descriptor import ParsedHidDescriptor
from mouse_control.lamzu_aurora import (
    AuroraKnowledgeError,
    AuroraStatusAction,
    AURORA_BUTTON_ACTIONS,
    AURORA_RECEIVER_INDICATOR_MEANINGS,
    LAMZU_AURORA_LEGACY,
    LAMZU_AURORA_MODERN,
    LAMZU_LEGACY_FLASH_SEMANTICS,
    build_read_request,
    dangerous_operation_names,
    decode_angle_tune,
    decode_battery_read,
    decode_event,
    decode_lod_tenths_mm,
    decode_routed_identity,
    decode_sensor_model,
    encode_angle_tune,
    encode_lod_tenths_mm,
    encode_rapid_trigger,
    encode_scroll_bhop,
    event_to_pushed_states,
    is_lamzu_bootloader_identity,
    lamzu_model,
    legacy_checksum,
    normalize_response,
    operation,
    operation_is_automatic_experiment,
    receiver_identity_ambiguity,
    status_action,
    status_dialogue_kind,
)
from mouse_control.power_investigator import analyze_power_state
from mouse_control.protocol_grammar import DeviceIdentityRole, SafetyClass, WriteScope
from mouse_control.protocol_repertoire import (
    RecognitionStatus,
    SemanticExchange,
    match_repertoire,
    recognize_open_set,
)
from mouse_control.routing_mapper import aurora_routed_identity_evidence
from mouse_control.temporal_dialogue import (
    DialogueKind, DialogueObservation, Direction, StateEvidence, StateFreshness,
)


def _node(vendor=0x37B0, product=0x0030):
    return DeviceNode(
        Path("/dev/hidraw-fixture"), None, "hidraw", "hidraw", 3,
        vendor, product, 2, parent_key="lamzu-parent",
    )


def _physical(node):
    return PhysicalDevice(
        "LAMZU fixture", node.vendor_id, node.product_id, node.bus, None,
        hidraw_nodes=[node], model_fingerprint="lamzu-model",
        instance_fingerprint="lamzu-instance",
    )


def _descriptor(*reports):
    return ParsedHidDescriptor(raw=b"", reports=tuple(reports))


def _modern_descriptor():
    return _descriptor(
        HidReportDefinition(0, "feature", 64, (0xFF00,)),
        HidReportDefinition(4, "input", 7, (0xFF00,)),
    )


def _response(command, payload=b"", *, alignment=0, status=0xA1, target=2, page=0):
    canonical = bytearray(64)
    canonical[0] = status
    canonical[2] = target
    canonical[3] = len(payload)
    canonical[4] = page
    canonical[5] = command
    canonical[6:6 + len(payload)] = payload
    return bytes(canonical) if alignment == 0 else b"\x00" + bytes(canonical[:-1])


def test_modern_family_selects_control_and_notification_collections_and_recognizes():
    node = _node()
    candidates = match_repertoire(_physical(node), {node: _modern_descriptor()})
    modern = next(item for item in candidates if item.family.name == LAMZU_AURORA_MODERN.name)
    assert modern.exact_identity is False
    assert modern.write_authorized is False

    request = build_read_request("battery/charging")
    normalized = normalize_response(_response(0x83, b"\x00\x54"), expected_command=0x83)
    decision = recognize_open_set(
        _physical(node), {node: _modern_descriptor()},
        exchanges={LAMZU_AURORA_MODERN.name: (
            SemanticExchange(request, normalized.canonical_frame, 0, 0),
        )},
    )
    assert decision.status is RecognitionStatus.RECOGNIZED
    assert decision.family == LAMZU_AURORA_MODERN.name
    assert decision.write_authorized is False

    missing_notification = _descriptor(
        HidReportDefinition(0, "feature", 64, (0xFF00,)),
    )
    assert not any(
        item.family.name == LAMZU_AURORA_MODERN.name
        for item in match_repertoire(_physical(node), {node: missing_notification})
    )


@pytest.mark.parametrize("alignment", [0, 1])
def test_response_alignment_is_normalized_before_semantic_use(alignment):
    result = normalize_response(
        _response(0x83, b"\x01\x64", alignment=alignment), expected_command=0x83,
    )
    assert result.alignment == alignment
    assert result.status == 0xA1
    assert result.command == 0x83
    assert result.payload == b"\x01\x64"


def test_vendor_status_policy_is_bounded_and_timing_values_are_only_priors():
    assert status_action(0xA1) is AuroraStatusAction.COMPLETE
    assert status_action(0x02) is AuroraStatusAction.COMPLETE
    assert status_action(0x20, receive_polls=2) is AuroraStatusAction.POLL_RECEIVE
    assert status_action(0xB0, resends=1) is AuroraStatusAction.RESEND
    assert status_dialogue_kind(0x20) is DialogueKind.BUSY_PENDING
    assert status_dialogue_kind(0xB0) is DialogueKind.RESPONSE_POLL
    with pytest.raises(AuroraKnowledgeError, match="poll limit"):
        status_action(0x20, receive_polls=100)
    with pytest.raises(AuroraKnowledgeError, match="resend limit"):
        status_action(0xB0, resends=3)
    assert LAMZU_AURORA_MODERN.status_timing.delay_priors_ms == (15, 20, 30, 100)


def test_battery_read_and_async_push_feed_existing_power_investigator_without_99_fudge():
    read = decode_battery_read(b"\x01\x64")
    assert (read.percent, read.charging) == (100, True)
    observation = DialogueObservation(
        "lamzu", "lamzu-instance", "notification", "hid", Direction.IN,
        "lamzu.aurora.events", 4, 2, 1_000, 1, b"\x04\x03\x64\x01",
        grammar="lamzu-aurora-event",
    )
    pushed = event_to_pushed_states(observation)
    assert decode_event(observation.payload).values["percent"] == read.percent
    stale_read = StateEvidence(
        DialogueObservation(
            "lamzu", "lamzu-instance", "control", "hid", Direction.IN,
            "lamzu.control", 0, 2, 500, 0, b"\xa1\x00\x02\x02\x00\x83\x00\x50",
            grammar="lamzu-aurora-control",
        ),
        "lamzu.battery_percent", 80, StateFreshness.STALE,
        ("superseded vendor read fixture",),
    )
    experiment = LabExperiment(
        "lamzu-power", {
            "vendor_id": 0x37B0, "product_id": 0x0030,
            "model_fingerprint": "lamzu-model", "instance_fingerprint": "lamzu-instance",
        }, 2, "LAMZU battery fixture", None, (), (), pushed_states=pushed,
        state_reads=(stale_read,),
    )
    analyzed = analyze_power_state(experiment)
    assert analyzed.power_analysis.battery_semantic is PowerSemantic.PERCENTAGE_CONFIRMED
    assert analyzed.power_analysis.battery_value == 100
    assert analyzed.power_analysis.charging_state is ChargingState.CHARGING
    assert "stale cached power state" in " ".join(analyzed.power_analysis.contradictions)
    assert analyzed.power_analysis.write_authorized is False


@pytest.mark.parametrize(
    ("payload", "name"),
    (
        (b"\x04\x01\x02\x06\x40\x0c\x80", "dpi"),
        (b"\x04\x02", "profile"),
        (b"\x04\x06\x01", "connection"),
        (b"\x04\x07\x13", "lod"),
        (b"\x04\x08\x04", "polling"),
        (b"\x04\x0d\x01\x01", "performance"),
    ),
)
def test_async_report4_event_repertoire(payload, name):
    assert decode_event(payload).name == name


def test_dpi_event_uses_be16_xy_and_performance_dependency_is_joint():
    dpi = decode_event(b"\x04\x01\x03\x06\x40\x0c\x80")
    assert dpi.values == {"active_stage": 3, "x_dpi": 1600, "y_dpi": 3200}
    performance = decode_event(b"\x04\x0d\x01\x01")
    assert performance.values["mode"] == "20k"
    with pytest.raises(AuroraKnowledgeError, match="prerequisite"):
        decode_event(b"\x04\x0d\x00\x01")
    dependency = LAMZU_AURORA_MODERN.dependencies[0]
    assert dependency.dependent == "Tracking/20K"
    assert dependency.disable_dependent_when_unmet


@pytest.mark.parametrize(
    ("code", "name", "maximum", "step", "fine"),
    ((1, "3395", 26000, 50, False), (2, "3950", 30000, 50, False),
     (4, "3955", 50000, 1, True)),
)
def test_sensor_model_vendor_logic(code, name, maximum, step, fine):
    sensor = decode_sensor_model(code, catalog_max_dpi=50000 if code == 4 else None)
    assert (sensor.name, sensor.dpi_max, sensor.dpi_increment, sensor.fine_lod) == (
        name, maximum, step, fine,
    )
    if code == 4:
        assert decode_sensor_model(4).dpi_max == 40000


@pytest.mark.parametrize("tenths", [7, 10, 13, 15, 17, 20])
def test_fine_lod_transform_roundtrips_vendor_domain(tenths):
    assert decode_lod_tenths_mm(encode_lod_tenths_mm(tenths)) == tenths


def test_angle_tune_rapid_trigger_and_scroll_bhop_semantics_are_exact():
    assert encode_angle_tune(-12) == 0xF4
    assert decode_angle_tune(0xF4) == -12
    assert encode_rapid_trigger(1, left=True, right=False) == b"\x01\x01\x00"
    assert encode_rapid_trigger(2, left=False, right=True) == b"\x02\x00\x01"
    assert encode_scroll_bhop(1, mode=2, window_ms=600) == b"\x01\x02\x02\x58"
    with pytest.raises(AuroraKnowledgeError):
        encode_scroll_bhop(1, mode=1, window_ms=600)
    rapid = operation("Rapid Trigger")
    bhop = operation("Scroll Bhop")
    assert (rapid.page, rapid.read_command, rapid.write_command) == (0, 0x9A, 0x1A)
    assert (bhop.page, bhop.read_command, bhop.write_command) == (0, 0x99, 0x19)


def test_modern_command_repertoire_covers_global_sensor_indicator_button_and_macro_knowledge():
    names = {item.name for item in LAMZU_AURORA_MODERN.operations}
    assert {
        "mouse firmware", "dongle firmware", "EID/device variant",
        "battery/charging", "active profile", "sleep", "debounce", "polling",
        "DPI stages", "active DPI", "maximum DPI", "LOD", "sensor model",
        "X/Y DPI split", "angle snapping", "Angle Tune", "Motion Sync",
        "ripple control", "High-Speed/Competition", "Tracking/20K",
        "Rapid Trigger", "Scroll Bhop", "DPI indicator", "DPI stage colors",
        "receiver light/effect", "button actions", "button combinations",
        "macro allocate", "macro delete", "macro data write", "macro size",
        "macro data read", "routed VID/PID",
    } <= names
    assert AURORA_RECEIVER_INDICATOR_MEANINGS[6] == "battery"
    assert AURORA_RECEIVER_INDICATOR_MEANINGS[12] == "signal"
    assert {"macro", "dpi_lock", "report_rate_switch"} <= set(AURORA_BUTTON_ACTIONS)


def test_routed_identity_recipe_preserves_0032_vs_002e_ambiguity():
    request = build_read_request("routed VID/PID", arguments=b"\x02")
    assert request[2:7] == b"\x01\x06\x00\x8b\x02"
    identity = decode_routed_identity(b"\x37\xb0\x00\x2e")
    assert (identity.vendor_id, identity.product_id) == (0x37B0, 0x002E)
    assert receiver_identity_ambiguity(0x0032, 0x002E) is not None

    experiment = LabExperiment(
        "route", {
            "vendor_id": 0x37B0, "product_id": 0x0032,
            "model_fingerprint": "receiver", "instance_fingerprint": "receiver-1",
        }, 1, "routed identity", None, (), (),
    )
    evidence = aurora_routed_identity_evidence(
        experiment, identity,
        source_route=RouteEndpoint(
            "hid-feature", namespace="lamzu.control", report_id=0,
            report_type="feature", direction="in",
        ),
        source_observation_ids=("reply:1",), receiver_usb_pid=0x0032,
    )
    assert evidence.status is RoutingStatus.AMBIGUOUS_ROUTE
    assert evidence.internal_target == 1
    assert evidence.ambiguity
    assert evidence.write_authorized is False


def test_catalog_is_vendor_declared_and_bootloaders_are_not_configurable():
    thorn = lamzu_model(0x37B0, 0x0030)
    assert thorn is not None and thorn.configurable
    assert dict(thorn.capabilities)["maximum_dpi"] == 50000
    assert thorn.vendor_evidence == "vendor_declared"
    for product in (0x0041, 0x0033, 0x0018, 0x0002):
        assert is_lamzu_bootloader_identity(0x37B0, product)
        assert lamzu_model(0x37B0, product).role is DeviceIdentityRole.BOOTLOADER


def test_bootloader_is_filtered_from_the_normal_mouse_picker(monkeypatch):
    class Device:
        name = "LAMZU DFU"
        phys = "usb-dfu"
        path = "/dev/input/event-dfu"
        info = SimpleNamespace(vendor=0x37B0, product=0x0041, bustype=3)

        def capabilities(self, verbose=False):
            return {ecodes.EV_REL: [], ecodes.EV_KEY: []}

        def close(self):
            pass

    monkeypatch.setattr(
        discovery_module, "_iter_candidate_paths", lambda: iter((Device.path,)),
    )
    monkeypatch.setattr(discovery_module, "InputDevice", lambda _path: Device())
    assert discovery_module.get_mouse_devices() == []


def test_legacy_report8_is_separate_and_checksum_discriminates_it():
    node = _node(vendor=0x3554, product=0x9999)
    reports = _descriptor(
        HidReportDefinition(8, "output", 16, (0xFF00,)),
        HidReportDefinition(8, "input", 16, (0xFF00,)),
    )
    request = bytearray(15)
    request[0] = 0x04
    frame = bytes(request) + bytes((legacy_checksum(bytes(request)),))
    decision = recognize_open_set(
        _physical(node), {node: reports},
        exchanges={LAMZU_AURORA_LEGACY.name: (SemanticExchange(frame, frame, 8, 8),)},
    )
    assert decision.status is RecognitionStatus.RECOGNIZED
    assert decision.family == LAMZU_AURORA_LEGACY.name
    assert LAMZU_AURORA_LEGACY.name != LAMZU_AURORA_MODERN.name
    assert LAMZU_AURORA_LEGACY.write_scope is WriteScope.NEVER
    assert {"polling", "dpi_values", "button_functions", "macros"} <= set(
        LAMZU_LEGACY_FLASH_SEMANTICS
    )


def test_dangerous_commands_and_vendor_setters_never_gain_automatic_authority():
    names = dangerous_operation_names()
    assert {
        "factory/default reset", "VID/PID write", "pairing operations",
        "DFU/bootloader entry", "flash erase", "firmware programming",
        "arbitrary target enumeration", "unknown command probing",
    } <= set(names)
    assert not operation_is_automatic_experiment("battery/charging")
    assert not operation_is_automatic_experiment("Rapid Trigger")
    assert operation("Rapid Trigger").safety is SafetyClass.REVERSIBLE
    assert LAMZU_AURORA_MODERN.write_scope is WriteScope.NEVER
    assert not LAMZU_AURORA_MODERN.can_authorize_write(
        exact_model=True, family_handshake_proven=True,
    )
    with pytest.raises(AuroraKnowledgeError):
        build_read_request("factory/default reset")
