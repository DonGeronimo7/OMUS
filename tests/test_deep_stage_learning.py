from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from mouse_control.guided_discovery import (
    _distance_label,
    run_deep_dpi_stage_learning,
)


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
