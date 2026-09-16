from mouse_control.sensor_calibration import (
    CalibrationError,
    CalibrationEvent,
    EV_REL,
    EV_SYN,
    REL_X,
    REL_Y,
    SYN_REPORT,
    estimate_peak_polling_hz,
    measure_sensor_state,
    measure_sensor_state_auto,
)


def _motion_frames(*, hz: int, frame_count: int, total_x: int = 0, total_y: int = 0):
    interval_ns = int(1_000_000_000 / hz)
    x_base, x_remainder = divmod(total_x, frame_count)
    y_base, y_remainder = divmod(total_y, frame_count)
    events = []
    timestamp = 1_000_000_000
    for index in range(frame_count):
        x_delta = x_base + (1 if index < x_remainder else 0)
        y_delta = y_base + (1 if index < y_remainder else 0)
        if x_delta:
            events.append(CalibrationEvent(timestamp, EV_REL, REL_X, x_delta))
        if y_delta:
            events.append(CalibrationEvent(timestamp, EV_REL, REL_Y, y_delta))
        events.append(CalibrationEvent(timestamp, EV_SYN, SYN_REPORT, 0))
        timestamp += interval_ns
    return events


def test_two_inches_of_1600_counts_measures_800_dpi_at_1000_hz():
    events = _motion_frames(hz=1000, frame_count=100, total_x=1600)
    measured = measure_sensor_state(events, distance_mm=50.8)

    assert measured.estimated_dpi == 800
    assert measured.rounded_dpi == 800
    assert measured.net_counts == 1600
    assert measured.straightness == 1
    assert measured.standard_polling_hz == 1000
    assert 990 <= measured.peak_polling_hz <= 1010


def test_auto_axis_selects_y_when_y_carries_ruler_motion():
    events = _motion_frames(hz=1000, frame_count=100, total_x=20, total_y=1600)
    measured = measure_sensor_state_auto(events, distance_mm=50.8)

    assert measured.axis == "y"
    assert measured.rounded_dpi == 800
    assert measured.net_counts == 1600
    assert measured.cross_axis_counts == 20


def test_auto_axis_selects_x_when_x_carries_ruler_motion():
    events = _motion_frames(hz=500, frame_count=100, total_x=1000, total_y=25)
    measured = measure_sensor_state_auto(events, distance_mm=25.4)

    assert measured.axis == "x"
    assert measured.rounded_dpi == 1000
    assert measured.standard_polling_hz == 500


def test_polling_estimator_prefers_fast_sustained_quartile_over_pause():
    timestamps = [0]
    timestamps.extend(index * 2_000_000 for index in range(1, 21))
    timestamps.append(timestamps[-1] + 100_000_000)

    measured, standard, error = estimate_peak_polling_hz(timestamps)

    assert 495 <= measured <= 505
    assert standard == 500
    assert error is not None and error < 0.02


def test_cross_axis_motion_does_not_change_primary_dpi_measurement():
    events = _motion_frames(hz=1000, frame_count=100, total_x=1600, total_y=100)

    measured = measure_sensor_state(events, distance_mm=50.8)
    assert measured.rounded_dpi == 800
    assert measured.cross_axis_counts == 100


def test_reversing_motion_is_rejected_as_bad_ruler_pass():
    events = [
        CalibrationEvent(1_000_000_000, EV_REL, REL_X, 100),
        CalibrationEvent(1_000_000_000, EV_SYN, SYN_REPORT, 0),
        CalibrationEvent(1_001_000_000, EV_REL, REL_X, -90),
        CalibrationEvent(1_001_000_000, EV_SYN, SYN_REPORT, 0),
    ]

    try:
        measure_sensor_state(events, distance_mm=25.4)
    except CalibrationError as exc:
        assert "reversed too much" in str(exc)
    else:
        raise AssertionError("expected CalibrationError")


def test_no_motion_is_rejected():
    try:
        measure_sensor_state_auto([], distance_mm=25.4)
    except CalibrationError as exc:
        assert "no usable REL_X or REL_Y" in str(exc)
    else:
        raise AssertionError("expected CalibrationError")
