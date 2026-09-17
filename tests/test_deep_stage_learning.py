from pathlib import Path


def test_deep_stage_learning_uses_full_calibrated_methodology():
    source = Path("src/mouse_control/guided_discovery.py").read_text()
    required = (
        "capture_calibrated_motion",
        "measure_sensor_state_auto",
        "summarize_calibrations",
        "refine_teacher_free",
        "infer_calibrated_raw_mappings",
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
