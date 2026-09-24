# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from mouse_control.guided_discovery import (
    _distance_label,
    run_deep_dpi_stage_learning,
)
from mouse_control.transition_sources import CalibratedTransitionSource
from mouse_control.discovery_models import DeviceNode


def test_deep_stage_learning_uses_full_calibrated_methodology():
    source = Path("src/mouse_control/guided_discovery.py").read_text()
    required = (
        "capture_calibrated_motion",
        "measure_sensor_state_auto",
        "summarize_calibrations",
        "refine_teacher_free",
        "infer_calibrated_raw_mappings",
        "infer_calibrated_transition_sources",
        "calibrated_cycle_hypothesis",
        "calibrated_profile_data",
        "save_calibrated_profile",
    )
    for name in required:
        assert name in source
    assert "wrap_confirmed" in source
    assert "Write authority" not in source  # service does not grant authority


def test_tui_prompts_for_deeper_learning_after_automatic_discovery():
    source = Path("src/mouse_control/setup_tui_curses.py").read_text()
    assert "Continue to deeper protocol learning?" in source
    assert "run_deep_dpi_stage_learning" in source
    assert "No unknown DPI or polling configuration write will be sent." in source


def test_default_ruler_distance_shows_ten_inches():
    assert _distance_label(254.0) == "10 inches (254 mm)"


def test_existing_exact_device_calibration_is_reused_without_prompting(tmp_path):
    profile = {
        "dpi_cycle": {
            "wrap_confirmed": True,
            "states": [
                {
                    "configured_dpi": 800,
                    "measured_cpi": 812.0,
                    "polling_hz": 1000,
                    "confidence": "high",
                }
            ],
        },
        "transition_sources": [{"kind": "hid_cycle_trigger"}],
    }
    result = SimpleNamespace(device=SimpleNamespace(ambiguous=False))
    engine = SimpleNamespace(descriptors={})
    prompt = Mock()
    progress = Mock()
    existing_path = tmp_path / "calibrated.json"

    with patch(
        "mouse_control.guided_discovery.find_calibrated_profile",
        return_value=(existing_path, profile),
    ):
        outcome = run_deep_dpi_stage_learning(
            SimpleNamespace(path="/dev/input/test"),
            result,
            engine,
            prompt=prompt,
            progress=progress,
        )

    assert outcome.reused_profile
    assert outcome.profile_path == existing_path
    assert outcome.wrap_confirmed
    assert outcome.measured_cycle[0].configured_dpi == 800
    prompt.assert_not_called()


def test_physical_only_calibration_is_saved_without_runtime_source(tmp_path):
    device = SimpleNamespace(
        ambiguous=False,
        hidraw_nodes=[object()],
        evdev_nodes=[],
        vendor_id=0x1234,
        product_id=0x5678,
        bus=3,
        model_fingerprint="model",
        instance_fingerprint=None,
    )
    result = SimpleNamespace(device=device)
    sample = SimpleNamespace(
        action=SimpleNamespace(hid_reports=(), evdev_events=(), feature_changes=()),
    )
    session = Mock(descriptors={})
    session.observe_action.return_value = sample
    session.analyze.return_value = SimpleNamespace(samples=(), report_candidates=())
    calibration = SimpleNamespace(
        rounded_dpi=800,
        straightness=1.0,
    )
    summaries = iter(
        (
            SimpleNamespace(estimated_dpi=800.0, confidence="high", standard_polling_hz=1000),
            SimpleNamespace(estimated_dpi=1500.0, confidence="high", standard_polling_hz=1000),
            SimpleNamespace(estimated_dpi=800.0, confidence="high", standard_polling_hz=1000),
        )
    )
    saved_path = tmp_path / "physical-only.json"
    progress = Mock()

    with (
        patch("mouse_control.guided_discovery.find_calibrated_profile", return_value=None),
        patch(
            "mouse_control.guided_discovery.capture_calibrated_motion",
            return_value=SimpleNamespace(sample=sample, calibration_events=()),
        ),
        patch("mouse_control.guided_discovery.measure_sensor_state_auto", return_value=calibration),
        patch("mouse_control.guided_discovery.summarize_calibrations", side_effect=lambda _items: next(summaries)),
        patch(
            "mouse_control.guided_discovery.refine_teacher_free",
            return_value=SimpleNamespace(report_shapes=(), candidates=(), hypotheses=()),
        ),
        patch("mouse_control.guided_discovery.infer_calibrated_transition_sources", return_value=()),
        patch("mouse_control.guided_discovery.save_calibrated_profile", return_value=saved_path) as save,
    ):
        outcome = run_deep_dpi_stage_learning(
            SimpleNamespace(path="/dev/input/test"),
            result,
            SimpleNamespace(descriptors={object(): object()}),
            prompt=lambda _step: True,
            progress=progress,
            calibration_passes=1,
            session_factory=lambda *_args: session,
        )

    assert outcome.profile_path == saved_path
    assert outcome.transition_sources == ()
    saved_profile = save.call_args.args[0]
    assert saved_profile["schema_version"] == 2
    assert saved_profile["transition_sources"] == []
    assert saved_profile["write_authorized"] is False
    progress.assert_any_call("• Physical calibration saved; runtime source still unresolved")


def test_physical_only_profile_retries_runtime_learning_without_ruler(tmp_path):
    states = [
        {"configured_dpi": dpi, "measured_cpi": float(dpi),
         "polling_hz": 1000, "confidence": "high"}
        for dpi in (800, 1500, 800)
    ]
    profile = {
        "dpi_cycle": {"configured_order": [800, 1500], "states": states,
                      "wrap_confirmed": True},
        "transition_sources": [],
        "raw_mappings": [],
    }
    device = SimpleNamespace(ambiguous=False, hidraw_nodes=[object()], evdev_nodes=[])
    result = SimpleNamespace(device=device)
    sample = SimpleNamespace(
        action=SimpleNamespace(hid_reports=(), evdev_events=(), feature_changes=()),
    )
    learned = SimpleNamespace(samples=(), report_candidates=())
    session = Mock(descriptors={})
    session.observe_action.return_value = sample
    session.analyze.return_value = learned
    existing_path = tmp_path / "physical-only.json"

    with (
        patch("mouse_control.guided_discovery.find_calibrated_profile",
              return_value=(existing_path, profile)),
        patch("mouse_control.guided_discovery.capture_calibrated_motion") as ruler,
        patch("mouse_control.guided_discovery.refine_teacher_free",
              return_value=SimpleNamespace(report_shapes=(), candidates=(), hypotheses=())),
        patch("mouse_control.guided_discovery.infer_calibrated_transition_sources",
              return_value=()),
    ):
        outcome = run_deep_dpi_stage_learning(
            SimpleNamespace(path="/dev/input/test"), result,
            SimpleNamespace(descriptors={object(): object()}),
            prompt=lambda _step: True,
            calibration_passes=1,
            session_factory=lambda *_args: session,
        )

    assert outcome.reused_profile
    assert outcome.profile_path == existing_path
    assert outcome.transition_sources == ()
    assert session.observe_action.call_count == 2
    ruler.assert_not_called()


def test_runtime_source_can_be_added_later_without_repeating_calibration(tmp_path):
    states = [
        {"configured_dpi": dpi, "measured_cpi": float(dpi),
         "polling_hz": 1000, "confidence": "high"}
        for dpi in (800, 1500, 800)
    ]
    profile = {
        "dpi_cycle": {"configured_order": [800, 1500], "states": states,
                      "wrap_confirmed": True},
        "transition_sources": [], "raw_mappings": [],
    }
    node = DeviceNode(
        path=Path("/dev/hidraw-test"), sysfs_path=None, subsystem="hidraw",
        node_type="hidraw", bus=3, vendor_id=0x1234, product_id=0x5678,
        interface_number=1, descriptor_sha256="descriptor",
    )
    device = SimpleNamespace(
        ambiguous=False, hidraw_nodes=[node], evdev_nodes=[], vendor_id=0x1234,
        product_id=0x5678, bus=3, model_fingerprint="model",
        instance_fingerprint=None,
    )
    sample = SimpleNamespace(
        action=SimpleNamespace(hid_reports=(), evdev_events=(), feature_changes=()),
    )
    session = Mock(descriptors={})
    session.observe_action.return_value = sample
    session.analyze.return_value = SimpleNamespace(samples=(), report_candidates=())
    source = CalibratedTransitionSource(
        kind="hid_cycle_trigger", cycle_order=(800, 1500), observations=2,
        report_key=("input", 3, 0x1234, 0x5678, 1, "descriptor", 5, 2),
        press_pattern=bytes.fromhex("0220000000"),
        release_pattern=bytes.fromhex("0200000000"),
    )
    saved_path = tmp_path / "upgraded.json"

    with (
        patch("mouse_control.guided_discovery.find_calibrated_profile",
              return_value=(tmp_path / "physical-only.json", profile)),
        patch("mouse_control.guided_discovery.capture_calibrated_motion") as ruler,
        patch("mouse_control.guided_discovery.refine_teacher_free",
              return_value=SimpleNamespace(report_shapes=(), candidates=(), hypotheses=())),
        patch("mouse_control.guided_discovery.infer_calibrated_transition_sources",
              return_value=(source,)),
        patch("mouse_control.guided_discovery.save_calibrated_profile",
              return_value=saved_path) as save,
    ):
        outcome = run_deep_dpi_stage_learning(
            SimpleNamespace(path="/dev/input/test"), SimpleNamespace(device=device),
            SimpleNamespace(descriptors={node: object()}), prompt=lambda _step: True,
            calibration_passes=1, session_factory=lambda *_args: session,
        )

    assert outcome.profile_path == saved_path
    assert outcome.transition_sources == (source,)
    assert save.call_args.args[0]["transition_sources"][0]["kind"] == "hid_cycle_trigger"
    ruler.assert_not_called()
