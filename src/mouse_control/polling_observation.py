"""Reusable read-only current polling-rate observation for setup and diagnostics."""
from __future__ import annotations

from .polling_measurement import PollingMeasurement, analyze_polling_timestamps
from .sensor_calibration import (
    EV_REL,
    EV_SYN,
    REL_X,
    REL_Y,
    SYN_REPORT,
    capture_evdev_motion,
    normalize_event,
)


def motion_frame_timestamps(events) -> tuple[int, ...]:
    """Return kernel timestamps for SYN frames that contained relative motion."""
    timestamps: list[int] = []
    motion = False
    for raw in events:
        event = normalize_event(raw)
        if event.event_type == EV_REL and event.code in (REL_X, REL_Y):
            motion = motion or event.value != 0
        elif event.event_type == EV_SYN and event.code == SYN_REPORT:
            if motion:
                timestamps.append(event.timestamp_ns)
            motion = False
    return tuple(timestamps)


def measure_current_polling(
    event_path: str,
    *,
    seconds: float = 3.0,
    exclusive: bool = True,
) -> PollingMeasurement:
    """Measure the current report-rate fundamental without writing hardware."""
    if seconds <= 0:
        raise ValueError("seconds must be greater than zero")
    captured = capture_evdev_motion(event_path, seconds=seconds, exclusive=exclusive)
    return analyze_polling_timestamps(motion_frame_timestamps(captured))
