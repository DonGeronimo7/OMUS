from mouse_control.autonomous_dpi_discovery_cli import _same_physical_state


def test_same_physical_state_accepts_calibration_noise():
    assert _same_physical_state(1200.0, 1260.0, 0.15) is True
    assert _same_physical_state(2400.0, 2500.0, 0.15) is True


def test_same_physical_state_rejects_distinct_dpi_stages():
    assert _same_physical_state(1200.0, 1800.0, 0.15) is False
    assert _same_physical_state(1800.0, 2400.0, 0.15) is False


def test_same_physical_state_is_symmetric():
    assert _same_physical_state(1180.0, 1210.0, 0.15) == _same_physical_state(
        1210.0, 1180.0, 0.15
    )
