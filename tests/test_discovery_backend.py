from __future__ import annotations

import json
from pathlib import Path
import threading
from unittest.mock import Mock, patch

import pytest

from mouse_control.discovery import MouseDevice
from mouse_control.discovery_models import DeviceNode, PhysicalDevice
from mouse_control.hardware.base import HardwareError
from mouse_control.hardware.discovery_backend import DiscoveryBackend
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
    profile_dir.mkdir()
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
