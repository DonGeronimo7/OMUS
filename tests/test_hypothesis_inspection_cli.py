from types import SimpleNamespace

from mouse_control import hypothesis_inspection_cli
from mouse_control.device_topology import TopologyError
from mouse_control.discovery import MouseDevice


MOUSE = MouseDevice(
    "SIGMACHIP USB Mouse",
    "/dev/input/by-id/usb-SIGMACHIP_USB_Mouse-event-mouse",
    vendor=0x1C4F,
    product=0x0048,
    bustype=3,
)


def test_topology_failure_is_reported_without_escaping_tui(monkeypatch, capsys):
    monkeypatch.setattr(hypothesis_inspection_cli, "get_mouse_devices", lambda: [MOUSE])

    class FailingEngine:
        def __init__(self, **_kwargs):
            pass

        def discover(self, mouse):
            assert mouse is MOUSE
            raise TopologyError("could not correlate hidraw sibling")

    monkeypatch.setattr(hypothesis_inspection_cli, "DiscoveryEngine", FailingEngine)
    assert hypothesis_inspection_cli.main(["--device", "1"]) == 1
    output = capsys.readouterr().out
    assert "SIGMACHIP USB Mouse [1c4f:0048]" in output
    assert "Topology correlation: FAILED SAFELY" in output
    assert "No hardware authority changed" in output


def test_unexpected_inspection_failure_becomes_diagnostic(monkeypatch, capsys):
    monkeypatch.setattr(hypothesis_inspection_cli, "get_mouse_devices", lambda: [MOUSE])

    class FailingEngine:
        def __init__(self, **_kwargs):
            pass

        def discover(self, _mouse):
            raise KeyError("unexpected shape")

    monkeypatch.setattr(hypothesis_inspection_cli, "DiscoveryEngine", FailingEngine)
    assert hypothesis_inspection_cli.main(["--device", "1"]) == 1
    output = capsys.readouterr().out
    assert "Discovery inspection: INTERNAL FAILURE" in output
    assert "KeyError" in output
