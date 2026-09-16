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


def test_discovery_backend_reuses_calibrated_read_mapping_without_write_authority(tmp_path):
    backend = _backend(tmp_path)
    device = MouseDevice("G305", "/dev/input/test", vendor=0x046D, product=0x4074, bustype=3)

    assert backend.supports_device(device)
    assert backend.supports_dpi(device)
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
