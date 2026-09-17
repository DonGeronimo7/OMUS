from __future__ import annotations

import errno
import json
from dataclasses import replace
from pathlib import Path
import threading
from unittest.mock import Mock, patch

import pytest

from mouse_control.discovery import MouseDevice
from mouse_control.discovery_models import DeviceNode, PhysicalDevice
from mouse_control.hardware import HardwareSupervisor
from mouse_control.hardware.base import HardwareError
from mouse_control.hardware.discovery_backend import DiscoveryBackend
from mouse_control.hid_descriptor import parse_report_descriptor
from mouse_control.notifications import DpiEventMonitor, DpiMonitorSupervisor
from mouse_control.remapper import MouseRemapper
from evdev import ecodes


def _physical() -> PhysicalDevice:
    node = DeviceNode(
        path=Path("/dev/hidraw-test"),
        sysfs_path=None,
        subsystem="hidraw",
        node_type="hidraw",
        bus=3,
        vendor_id=0x046D,
        product_id=0x4074,
        interface_number=2,
        descriptor_sha256="descriptor-hash",
    )
    return PhysicalDevice(
        name="G305",
        vendor_id=0x046D,
        product_id=0x4074,
        bus=3,
        parent_path=None,
        hidraw_nodes=[node],
        model_fingerprint="model-fingerprint",
        instance_fingerprint="instance-fingerprint",
    )


def _profile() -> dict:
    return {
        "schema_version": 1,
        "profile_kind": "calibrated-read-only",
        "identity": {"vendor_id": 0x046D, "product_id": 0x4074, "bus": 3},
        "fingerprints": {
            "model": "model-fingerprint",
            "instance": "instance-fingerprint",
        },
        "dpi_cycle": {
            "configured_order": [800, 1500, 2000, 2500, 3000],
            "states": [],
            "wrap_confirmed": True,
            "semantic_evidence": "physically-calibrated",
        },
        "action_reports": [],
        "raw_mappings": [
            {
                "report": {
                    "report_type": "input",
                    "bus": 3,
                    "vendor_id": 0x046D,
                    "product_id": 0x4074,
                    "interface_number": 2,
                    "descriptor_sha256": "descriptor-hash",
                    "report_length": 20,
                    "report_id": 0x11,
                },
                "offset": 4,
                "descriptor_roles": ["vendor"],
                "raw_to_configured_dpi": {
                    "0": 800,
                    "1": 1500,
                    "2": 2000,
                    "3": 2500,
                    "4": 3000,
                },
                "raw_to_measured_cpi": {
                    "0": 817,
                    "1": 1539,
                    "2": 2047,
                    "3": 2550,
                    "4": 3072,
                },
                "observations": 5,
                "confidence": "correlated",
                "write_authorized": False,
            }
        ],
        "write_authorized": False,
    }


def _backend(tmp_path: Path) -> DiscoveryBackend:
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    (profile_dir / "g305.json").write_text(json.dumps(_profile()), encoding="utf-8")
    physical = _physical()
    return DiscoveryBackend(
        profile_directory=profile_dir,
        topology_builder=lambda _device: physical,
    )


def _schema_v2_profile(source: dict) -> dict:
    profile = _profile()
    profile["schema_version"] = 2
    profile["transition_sources"] = [{**source, "write_authorized": False}]
    return profile


def _backend_with_profile(tmp_path: Path, profile: dict, physical: PhysicalDevice) -> DiscoveryBackend:
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir(parents=True)
    (profile_dir / "profile.json").write_text(json.dumps(profile), encoding="utf-8")
    return DiscoveryBackend(profile_directory=profile_dir, topology_builder=lambda _device: physical)


def test_discovery_backend_reuses_calibrated_read_mapping_without_write_authority(tmp_path):
    backend = _backend(tmp_path)
    device = MouseDevice("G305", "/dev/input/test", vendor=0x046D, product=0x4074, bustype=3)

    assert backend.supports_device(device)
    # supports_dpi() is the historical writable-control contract. Learned
    # profiles expose DPI through capabilities/events without becoming writable.
    assert not backend.supports_dpi(device)
    assert backend.supports_dpi_events(device)
    assert not backend.supports_dpi_monitoring(device)
    assert backend.get_dpi_values(device) == [800, 1500, 2000, 2500, 3000]

    caps = backend.get_capabilities(device)
    assert caps.dpi.readable
    assert caps.dpi.events
    assert not caps.dpi.writable
    assert not caps.dpi.active_stage_readable

    packet = bytearray(20)
    packet[0] = 0x11
    packet[4] = 3
    assert backend._decode_report(bytes(packet)) == 2500

    with pytest.raises(HardwareError):
        backend.set_dpi(device, 3000)


def test_discovery_backend_emits_confirmed_value_without_writable_stage(tmp_path):
    backend = _backend(tmp_path)
    device = MouseDevice("G305", "/dev/input/test", vendor=0x046D, product=0x4074, bustype=3)
    assert backend.supports_device(device)

    packet = bytearray(20)
    packet[0] = 0x11
    packet[4] = 4
    callback = Mock()
    ready = Mock()

    with patch("mouse_control.hardware.discovery_backend.os.open", return_value=77), \
         patch("mouse_control.hardware.discovery_backend.os.close"), \
         patch("mouse_control.hardware.discovery_backend.select.select", return_value=([77], [], [])), \
         patch("mouse_control.hardware.discovery_backend.os.read", side_effect=[bytes(packet), b""]):
        with pytest.raises(HardwareError, match="disconnected"):
            backend.watch_dpi_events(device, callback, threading.Event(), ready)

    ready.assert_called_once_with()
    callback.assert_called_once()
    state = callback.call_args.args[0]
    assert state.confirmed
    assert state.display_value == 3000
    assert state.active_stage is None


def test_discovery_backend_remains_safe_fallback_without_learned_profile(tmp_path):
    backend = DiscoveryBackend(
        profile_directory=tmp_path / "missing",
        topology_builder=lambda _device: _physical(),
    )
    device = MouseDevice("unknown", "/dev/input/test", vendor=0x1234, product=0x5678, bustype=3)

    assert backend.supports_device(device)
    assert not backend.supports_dpi(device)
    assert not backend.supports_dpi_events(device)
    assert not backend.get_capabilities(device).dpi.writable


def test_schema_v2_hid_state_binds_by_stable_interface_and_refuses_ambiguity(tmp_path):
    source = {
        "kind": "hid_state",
        "cycle_order": [800, 1500, 2000],
        "observations": 3,
        "confidence": "validated",
        "report": {
            "report_type": "input", "bus": 3, "vendor_id": 0x046D,
            "product_id": 0x4074, "interface_number": 2,
            "descriptor_sha256": "descriptor-hash", "report_length": 5,
            "report_id": 2,
        },
        "offset": 4,
        "raw_to_configured_dpi": {"0": 800, "1": 1500, "2": 2000},
    }
    physical = _physical()
    backend = _backend_with_profile(tmp_path, _schema_v2_profile(source), physical)
    device = MouseDevice("G305", "/dev/input/test", vendor=0x046D, product=0x4074, bustype=3)
    assert backend.supports_device(device)
    assert backend._binding is not None
    assert backend._binding.kind == "hid_state"
    assert not backend.supports_dpi(device)
    assert backend.supports_dpi_events(device)

    duplicate = PhysicalDevice(**{
        **physical.__dict__,
        "hidraw_nodes": [physical.hidraw_nodes[0], physical.hidraw_nodes[0]],
    })
    ambiguous_dir = tmp_path / "ambiguous"
    ambiguous_dir.mkdir()
    ambiguous = _backend_with_profile(ambiguous_dir, _schema_v2_profile(source), duplicate)
    assert ambiguous.supports_device(device)
    assert ambiguous._binding is None
    assert not ambiguous.supports_dpi_events(device)


def test_validated_descriptor_member_decodes_absolute_state_and_blocks_raw_fallback(tmp_path):
    descriptor_bytes = bytes.fromhex(
        "06 00 FF 09 02 A1 01 85 11 75 08 95 13 15 00 26 FF 00 "
        "09 02 81 00 09 02 91 00 C0")
    descriptor = parse_report_descriptor(descriptor_bytes)
    field = descriptor.fields[0]
    sysfs = tmp_path / "hidraw-device"
    sysfs.mkdir()
    (sysfs / "report_descriptor").write_bytes(descriptor_bytes)
    physical = _physical()
    physical.hidraw_nodes = [replace(
        physical.hidraw_nodes[0], sysfs_path=sysfs,
        descriptor_sha256=descriptor.fingerprint)]
    report = {
        "report_type": "input", "bus": 3, "vendor_id": 0x046D,
        "product_id": 0x4074, "interface_number": 2,
        "descriptor_sha256": descriptor.fingerprint, "report_length": 20,
        "report_id": 17,
    }
    source = {
        "kind": "hid_state", "cycle_order": [800, 1500, 2000, 2500, 3000],
        "observations": 5, "confidence": "validated", "report": report,
        "offset": 4,
        "raw_to_configured_dpi": {str(i): dpi for i, dpi in enumerate((800, 1500, 2000, 2500, 3000))},
        "raw_to_measured_cpi": {str(i): cpi for i, cpi in enumerate((823, 1543, 2048, 2567, 3067))},
        "field_id": field.member_stable_id(descriptor.fingerprint, 3),
        "parent_field_id": field.stable_id(descriptor.fingerprint),
        "member_index": 3, "semantic_evidence": "validated",
    }
    profile = _schema_v2_profile(source)
    profile["raw_mappings"][0]["report"] = report
    backend = _backend_with_profile(tmp_path / "valid", profile, physical)
    device = MouseDevice("G305", "/dev/input/test", vendor=0x046D, product=0x4074, bustype=3)
    assert backend.supports_device(device)
    assert backend._binding is not None and backend._binding.descriptor is not None
    assert not backend.supports_dpi(device)

    def packet(raw):
        return bytes([0x11, 1, 7, 16, raw] + [0] * 15)

    states = [backend._decode_calibrated_hid(packet(raw)) for raw in (0, 0, 1, 2, 3, 4, 0)]
    assert [state.display_value if state else None for state in states] == [800, None, 1500, 2000, 2500, 3000, 800]
    notifier = Mock()
    monitor = DpiEventMonitor(
        backend, device, [800, 1500, 2000, 2500, 3000], 800, notifier)
    for state in states:
        if state is not None:
            monitor.handle_state(state)
    assert [call.args[0] for call in notifier.notify_dpi.call_args_list] == [
        800, 1500, 2000, 2500, 3000, 800,
    ]
    with pytest.raises(HardwareError):
        backend.set_dpi(device, 1500)

    invalid = json.loads(json.dumps(profile))
    invalid["transition_sources"][0]["field_id"] = "HID-FINVALID/member-3"
    refused = _backend_with_profile(tmp_path / "invalid", invalid, physical)
    assert refused.supports_device(device)
    assert refused._binding is None
    assert not refused.supports_dpi_events(device)


@pytest.mark.parametrize("disconnect_errno", [errno.EIO, errno.ENODEV])
@pytest.mark.parametrize("resync_raw_values", [(0, 1, 0), (4, 4)])
def test_descriptor_backed_monitor_rebinds_after_disconnect_without_duplicate_notification(
        tmp_path, disconnect_errno, resync_raw_values):
    descriptor_bytes = bytes.fromhex(
        "06 00 FF 09 02 A1 01 85 11 75 08 95 13 15 00 26 FF 00 "
        "09 02 81 00 09 02 91 00 C0")
    descriptor = parse_report_descriptor(descriptor_bytes)
    field = descriptor.fields[0]
    old_sysfs = tmp_path / "old-interface"
    new_sysfs = tmp_path / "replacement-interface"
    old_sysfs.mkdir()
    new_sysfs.mkdir()
    (old_sysfs / "report_descriptor").write_bytes(descriptor_bytes)
    (new_sysfs / "report_descriptor").write_bytes(descriptor_bytes)

    old_physical = _physical()
    old_physical.hidraw_nodes = [replace(
        old_physical.hidraw_nodes[0], path=Path("/dev/hidraw3"),
        sysfs_path=old_sysfs, descriptor_sha256=descriptor.fingerprint)]
    new_physical = _physical()
    new_physical.hidraw_nodes = [replace(
        new_physical.hidraw_nodes[0], path=Path("/dev/hidraw9"),
        sysfs_path=new_sysfs, descriptor_sha256=descriptor.fingerprint)]

    report = {
        "report_type": "input", "bus": 3, "vendor_id": 0x046D,
        "product_id": 0x4074, "interface_number": 2,
        "descriptor_sha256": descriptor.fingerprint, "report_length": 20,
        "report_id": 17,
    }
    source = {
        "kind": "hid_state", "cycle_order": [800, 1500, 2000, 2500, 3000],
        "observations": 5, "confidence": "validated", "report": report,
        "offset": 4,
        "raw_to_configured_dpi": {str(i): dpi for i, dpi in enumerate(
            (800, 1500, 2000, 2500, 3000))},
        "raw_to_measured_cpi": {str(i): cpi for i, cpi in enumerate(
            (823, 1543, 2048, 2567, 3067))},
        "field_id": field.member_stable_id(descriptor.fingerprint, 3),
        "parent_field_id": field.stable_id(descriptor.fingerprint),
        "member_index": 3, "semantic_evidence": "validated",
    }
    profile = _schema_v2_profile(source)
    profile["raw_mappings"][0]["report"] = report
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    (profile_dir / "profile.json").write_text(json.dumps(profile), encoding="utf-8")
    device = MouseDevice("G305", "/dev/input/event3", vendor=0x046D,
                         product=0x4074, bustype=3)
    learned_dpi_store = Mock()
    learned_polling_store = Mock()
    learned_action_store = Mock()

    def make_backend(physical):
        result = DiscoveryBackend(
            profile_directory=profile_dir,
            topology_builder=lambda _device: physical,
            learned_operation_store=learned_dpi_store,
            learned_polling_store=learned_polling_store,
            learned_action_store=learned_action_store,
            allow_writes=False,
        )
        assert result.supports_device(device)
        assert result._binding is not None
        return result

    initial = make_backend(old_physical)
    lifecycle = []

    def replace_backend(_device):
        lifecycle.append("rediscover")
        return make_backend(new_physical)

    hardware = HardwareSupervisor(
        initial, device, replace_backend, device_resolver=lambda _device: device)
    shutdown = threading.Event()
    notifier = Mock()

    def notify(_dpi):
        if notifier.notify_dpi.call_count == 2:
            shutdown.set()

    notifier.notify_dpi.side_effect = notify
    monitor = DpiMonitorSupervisor(
        hardware, device, lambda _device: hardware,
        [800, 1500, 2000, 2500, 3000], 0, shutdown,
        notifier=notifier, retry_interval=0,
    )

    def packet(raw):
        return bytes([0x11, 1, 7, 16, raw] + [0] * 15)

    final_resync_raw = resync_raw_values[-1]
    first_live_raw = 1 if final_resync_raw == 0 else 0
    reads = {
        10: iter((packet(4), OSError(disconnect_errno, "device lost"))),
        11: iter(tuple(packet(raw) for raw in resync_raw_values) +
                 (packet(final_resync_raw), packet(first_live_raw))),
    }
    replacement_selects = 0

    def read(fd, _length):
        value = next(reads[fd])
        if isinstance(value, BaseException):
            raise value
        return value

    def close(fd):
        lifecycle.append(f"close:{fd}")

    def select_ready(fds, _w, _x, _timeout):
        nonlocal replacement_selects
        if fds == [11]:
            if replacement_selects == len(resync_raw_values):
                replacement_selects += 1
                return [], [], []
            replacement_selects += 1
        return fds, [], []

    with patch("mouse_control.hardware.discovery_backend.os.open",
               side_effect=[10, 11]) as opened, \
         patch("mouse_control.hardware.discovery_backend.os.close", side_effect=close), \
         patch("mouse_control.hardware.discovery_backend.select.select",
               side_effect=select_ready), \
         patch("mouse_control.hardware.discovery_backend.os.read", side_effect=read):
        monitor._run()

    assert [call.args[0] for call in notifier.notify_dpi.call_args_list] == [
        3000, 1500 if first_live_raw == 1 else 800,
    ]
    assert [entry.args[0] for entry in opened.call_args_list] == [
        "/dev/hidraw3", "/dev/hidraw9",
    ]
    assert lifecycle.index("close:10") < lifecycle.index("rediscover")
    assert hardware.generation == 1
    replacement = hardware.current_backend
    assert replacement._binding is not None
    assert replacement._binding.node.path == Path("/dev/hidraw9")
    assert replacement._binding.descriptor is not None
    assert replacement._binding.field_id == source["field_id"]
    assert replacement._allow_writes is False
    assert not replacement.supports_dpi(device)
    learned_dpi_store.find_for_physical.assert_not_called()
    learned_polling_store.find_for_physical.assert_not_called()
    learned_action_store.find_for_physical.assert_not_called()
    assert lifecycle.count("close:10") == 1
    assert lifecycle.count("close:11") == 1


@pytest.mark.parametrize("replacement_kind", ["ambiguous", "malformed-descriptor"])
def test_descriptor_backed_rebind_refuses_unsafe_replacement(
        tmp_path, replacement_kind):
    descriptor_bytes = bytes.fromhex(
        "06 00 FF 09 02 A1 01 85 11 75 08 95 13 15 00 26 FF 00 "
        "09 02 81 00 09 02 91 00 C0")
    descriptor = parse_report_descriptor(descriptor_bytes)
    field = descriptor.fields[0]
    original_sysfs = tmp_path / "original"
    replacement_sysfs = tmp_path / "replacement"
    original_sysfs.mkdir()
    replacement_sysfs.mkdir()
    (original_sysfs / "report_descriptor").write_bytes(descriptor_bytes)
    (replacement_sysfs / "report_descriptor").write_bytes(
        b"\x85" if replacement_kind == "malformed-descriptor" else descriptor_bytes)
    original = _physical()
    original.hidraw_nodes = [replace(
        original.hidraw_nodes[0], path=Path("/dev/hidraw3"),
        sysfs_path=original_sysfs, descriptor_sha256=descriptor.fingerprint)]
    replacement = _physical()
    replacement.hidraw_nodes = [replace(
        replacement.hidraw_nodes[0], path=Path("/dev/hidraw9"),
        sysfs_path=replacement_sysfs, descriptor_sha256=descriptor.fingerprint)]
    if replacement_kind == "ambiguous":
        replacement = replace(replacement, ambiguous=True)

    report = {
        "report_type": "input", "bus": 3, "vendor_id": 0x046D,
        "product_id": 0x4074, "interface_number": 2,
        "descriptor_sha256": descriptor.fingerprint, "report_length": 20,
        "report_id": 17,
    }
    source = {
        "kind": "hid_state", "cycle_order": [800, 1500],
        "observations": 2, "confidence": "validated", "report": report,
        "offset": 4, "raw_to_configured_dpi": {"0": 800, "1": 1500},
        "raw_to_measured_cpi": {"0": 823, "1": 1543},
        "field_id": field.member_stable_id(descriptor.fingerprint, 3),
        "parent_field_id": field.stable_id(descriptor.fingerprint),
        "member_index": 3, "semantic_evidence": "validated",
    }
    profile = _schema_v2_profile(source)
    profile["raw_mappings"][0]["report"] = report
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    (profile_dir / "profile.json").write_text(json.dumps(profile), encoding="utf-8")
    device = MouseDevice("G305", "/dev/input/event3", vendor=0x046D,
                         product=0x4074, bustype=3)

    def backend_for(physical):
        result = DiscoveryBackend(
            profile_directory=profile_dir,
            topology_builder=lambda _device: physical,
            allow_writes=False,
        )
        result.supports_device(device)
        return result

    initial = backend_for(original)
    assert initial._binding is not None
    supervisor = HardwareSupervisor(
        initial, device, lambda _device: backend_for(replacement))

    assert supervisor.rebind(0, force=True)
    rebound = supervisor.current_backend
    assert rebound._binding is None
    assert not rebound.supports_dpi_events(device)
    assert not rebound.supports_dpi(device)


def test_schema_v2_hid_trigger_tracks_read_only_without_set_dpi(tmp_path):
    source = {
        "kind": "hid_cycle_trigger",
        "cycle_order": [800, 1500, 2000],
        "observations": 3,
        "confidence": "validated",
        "report": {
            "report_type": "input", "bus": 3, "vendor_id": 0x046D,
            "product_id": 0x4074, "interface_number": 2,
            "descriptor_sha256": "descriptor-hash", "report_length": 5,
            "report_id": 2,
        },
        "press_pattern_hex": "0220000000",
        "release_pattern_hex": "0200000000",
    }
    backend = _backend_with_profile(tmp_path, _schema_v2_profile(source), _physical())
    device = MouseDevice("G305", "/dev/input/test", vendor=0x046D, product=0x4074, bustype=3)
    assert backend.supports_device(device)
    assert backend._read_only_tracker is not None
    assert backend._decode_calibrated_hid(bytes.fromhex("0220000000")) is None
    backend._read_only_tracker.seed(800)
    state = backend._decode_calibrated_hid(bytes.fromhex("0220000000"))
    assert state is not None and state.display_value == 1500
    assert state.confirmed and not state.cycle_trigger and state.active_stage is None
    assert backend._decode_calibrated_hid(bytes.fromhex("0220000000")) is None
    backend._decode_calibrated_hid(bytes.fromhex("0200000000"))
    assert backend._decode_calibrated_hid(bytes.fromhex("0220000000")).display_value == 2000
    assert not backend.supports_dpi(device)


def test_evdev_transition_uses_remapper_owner_and_preserves_passthrough(tmp_path):
    physical = _physical()
    evdev = DeviceNode(
        path=Path("/dev/input/event-test"), sysfs_path=None, subsystem="input",
        node_type="event", bus=3, vendor_id=0x046D, product_id=0x4074,
        interface_number=1, name="G305", descriptor_sha256=None,
    )
    physical.evdev_nodes = [evdev]
    source = {
        "kind": "evdev_cycle_trigger", "cycle_order": [800, 1500, 2000],
        "observations": 3, "confidence": "validated",
        "interface": {"bus": 3, "vendor_id": 0x046D, "product_id": 0x4074,
                      "interface_number": 1, "name": "G305"},
        "event_type": ecodes.EV_KEY, "code": ecodes.BTN_EXTRA,
        "press_value": 1, "release_value": 0,
    }
    backend = _backend_with_profile(tmp_path, _schema_v2_profile(source), physical)
    device = MouseDevice("G305", str(evdev.path), vendor=0x046D, product=0x4074, bustype=3)
    assert backend.supports_device(device)
    backend._read_only_tracker.seed(800)
    stop = threading.Event()
    ready = threading.Event()
    seen = []
    watcher = threading.Thread(
        target=backend.watch_dpi_events,
        args=(device, seen.append, stop, ready.set),
        daemon=True,
    )
    watcher.start()
    assert ready.wait(0.5)

    remapper = MouseRemapper(str(evdev.path), {}, target_device=device, event_observer=backend)
    remapper.ui = Mock()
    remapper._handle(ecodes.EV_KEY, ecodes.BTN_EXTRA, 1)
    remapper._handle(ecodes.EV_KEY, ecodes.BTN_EXTRA, 1)
    remapper._handle(ecodes.EV_KEY, ecodes.BTN_EXTRA, 0)
    stop.set()
    watcher.join(0.5)

    assert [state.display_value for state in seen] == [1500]
    assert remapper.ui.write.call_args_list[0].args == (ecodes.EV_KEY, ecodes.BTN_EXTRA, 1)
    assert remapper.ui.write.call_args_list[-1].args == (ecodes.EV_KEY, ecodes.BTN_EXTRA, 0)


def test_feature_state_source_stays_explicitly_unsupported_without_polling_owner(tmp_path):
    source = {
        "kind": "feature_state", "cycle_order": [800, 1500],
        "observations": 2, "confidence": "validated",
        "interface": {"bus": 3, "vendor_id": 0x046D, "product_id": 0x4074,
                      "interface_number": 2, "descriptor_sha256": "descriptor-hash"},
        "offset": 4, "raw_to_configured_dpi": {"0": 800, "1": 1500},
    }
    profile = _schema_v2_profile(source)
    profile["raw_mappings"] = []
    backend = _backend_with_profile(tmp_path, profile, _physical())
    device = MouseDevice("G305", "/dev/input/test", vendor=0x046D, product=0x4074, bustype=3)

    assert backend.supports_device(device)
    assert backend._binding is None
    assert not backend.supports_dpi_events(device)
    assert not backend.get_capabilities(device).dpi.readable
