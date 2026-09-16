from types import SimpleNamespace

import pytest

from mouse_control import discovery_lab
from mouse_control.discovery_lab import DiscoveryTool, discovery_tool_specs, selected_device_number


def test_catalog_exposes_complete_discovery_ladder():
    specs = discovery_tool_specs()
    assert [spec.tool for spec in specs] == [
        DiscoveryTool.SENSOR_CALIBRATION,
        DiscoveryTool.CALIBRATED_DPI_DISCOVERY,
        DiscoveryTool.POLLING_PHYSICAL_VERIFY,
        DiscoveryTool.DPI_WRITE_TRACE,
        DiscoveryTool.DPI_WRITE_PROMOTION,
        DiscoveryTool.DPI_GENERALIZATION,
        DiscoveryTool.LEARNED_ACTION_CAPTURE,
        DiscoveryTool.POLLING_ONBOARD_TRACE,
        DiscoveryTool.POLLING_HOST_TRACE,
        DiscoveryTool.POLLING_REPLAY,
        DiscoveryTool.POLLING_STATE_MACHINE,
        DiscoveryTool.POLLING_PROMOTION,
    ]
    assert specs[0].writes_hardware is False
    assert specs[1].writes_hardware is False
    assert specs[2].writes_hardware is True
    assert next(spec for spec in specs if spec.tool is DiscoveryTool.DPI_WRITE_PROMOTION).promotion is True
    assert next(spec for spec in specs if spec.tool is DiscoveryTool.POLLING_PROMOTION).promotion is True
    assert {spec.evidence_phase for spec in specs} >= {
        "calibrate", "correlate", "infer", "validate", "generalize", "prove", "persist"
    }


def test_selected_device_number_is_one_based_and_refuses_foreign_device():
    first = SimpleNamespace(name="one")
    second = SimpleNamespace(name="two")
    assert selected_device_number((first, second), second) == 2
    with pytest.raises(ValueError):
        selected_device_number((first, second), SimpleNamespace(name="three"))


def test_run_discovery_tool_passes_selected_device_guard_and_tui_args(monkeypatch):
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
        extra_args=["--passes", "4"],
    )
    assert result == 0
    assert calls == [[
        "--device", "2", "--authorize-reversible-replay", "--passes", "4"
    ]]
