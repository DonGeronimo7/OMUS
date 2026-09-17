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
    assert _distance_label(254.0) == "254 mm (10 in)"


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
