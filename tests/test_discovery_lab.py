from types import SimpleNamespace

import pytest

from mouse_control import discovery_lab
from mouse_control.discovery_lab import DiscoveryTool, discovery_tool_specs, selected_device_number


def test_catalog_exposes_full_proven_discovery_ladder():
    specs = discovery_tool_specs()
    assert [spec.tool for spec in specs] == [
        DiscoveryTool.SENSOR_CALIBRATION,
        DiscoveryTool.DPI_WRITE_TRACE,
        DiscoveryTool.DPI_WRITE_PROMOTION,
        DiscoveryTool.POLLING_ONBOARD_TRACE,
        DiscoveryTool.POLLING_HOST_TRACE,
        DiscoveryTool.POLLING_PROMOTION,
    ]
    assert specs[0].writes_hardware is False
    assert specs[2].promotion is True
    assert specs[-1].promotion is True


def test_selected_device_number_is_one_based_and_refuses_foreign_device():
    first = SimpleNamespace(name="one")
    second = SimpleNamespace(name="two")
    assert selected_device_number((first, second), second) == 2
    with pytest.raises(ValueError):
        selected_device_number((first, second), SimpleNamespace(name="three"))


def test_run_discovery_tool_passes_selected_device_and_guard(monkeypatch):
    first = SimpleNamespace(name="one")
    second = SimpleNamespace(name="two")
    calls = []

    def fake_main(argv):
        calls.append(argv)
        return 0

    monkeypatch.setattr(
        discovery_lab,
        "_runner",
        lambda tool: (fake_main, ["--authorize-reversible-replay"]),
    )
    result = discovery_lab.run_discovery_tool(
        DiscoveryTool.DPI_WRITE_PROMOTION,
        devices=(first, second),
        selected=second,
    )
    assert result == 0
    assert calls == [["--device", "2", "--authorize-reversible-replay"]]
