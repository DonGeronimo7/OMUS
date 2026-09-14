"""Support reports remain local, deterministic, and write-free."""
from pathlib import Path
from unittest.mock import Mock, patch

from mouse_control import cli
from mouse_control.discovery import MouseDevice
from mouse_control.hardware.generic import GenericBackend
from mouse_control.support import _descriptor_details, probe, render_report

MOUSE = MouseDevice("Turtle Beach Kone II", "/dev/input/event99", vendor=0x1E7D, product=0x2E27)


def report_model():
    return {"mouse_control": {"Version": "0.7.4"}, "system": {"Distribution": "Test Linux", "Kernel": "1"}, "device": {"Manufacturer": "Turtle Beach", "Product": "Kone II", "USB VID:PID": "1e7d:2e27"}, "interfaces": {"evdev": "accessible", "hidraw": "None detected", "Kernel driver": "Unknown"}, "input": {"Buttons": "BTN_SIDE", "Relative motion": "yes"}, "hid": {"Report descriptor": "Not found"}, "backend": {"Selected backend": "Generic HID / evdev", "DPI": "Unsupported", "Polling rate": "Unsupported", "Hardware control": "generic input/remapping only"}, "guided": {}, "errors": []}


def test_report_is_deterministic_and_has_no_paths_or_personal_values():
    output = render_report(report_model())
    assert output == render_report(report_model())
    assert "[Device]" in output and "/home/" not in output and "event99" not in output


def test_descriptor_serialization_includes_layout_hash_and_raw_hex():
    details = _descriptor_details(bytes.fromhex("05010902a1018501750895038102950191029502b102c0"))
    assert details["Raw descriptor (hex)"] == "05010902a1018501750895038102950191029502b102c0"
    assert "ID 1: Input 3 × 8 bits" in details["Report layout"]
    assert "ID 1: Output 1 × 8 bits" in details["Report layout"]
    assert "ID 1: Feature 2 × 8 bits" in details["Report layout"]
    assert "page 0x0001:0x0002" in details["Usages"]


def test_probe_uses_backend_reads_only_and_never_calls_writes():
    backend = Mock(spec=GenericBackend)
    backend.name = "Generic HID / evdev"
    backend.supports_dpi.return_value = False
    backend.supports_polling_rate.return_value = False
    with patch("mouse_control.support._sysfs", return_value=({}, [], [])), patch("mouse_control.support._capabilities", return_value=({}, [])):
        probe(MOUSE, backend)
    backend.set_dpi.assert_not_called()
    backend.set_polling_rate.assert_not_called()


def test_support_command_saves_local_report_without_backend_writes(monkeypatch, tmp_path):
    backend = Mock(spec=GenericBackend)
    backend.name = "Generic HID / evdev"
    monkeypatch.setattr(cli, "get_mouse_devices", lambda: [MOUSE])
    monkeypatch.setattr(cli, "get_backend", lambda device: backend)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr("builtins.input", lambda prompt: "1" if prompt.strip() == ">" else "y")
    with patch("mouse_control.support.probe", return_value=report_model()):
        assert cli.run_support() == 0
    assert len(list(tmp_path.glob("mouse-control-*-report.txt"))) == 1
    assert backend.method_calls == []
