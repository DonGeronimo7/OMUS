"""Vendor-neutral mouse sensor calibration from Linux evdev events.

The calibration method intentionally mirrors the principle behind
``mouse-dpi-tool``: evdev relative motion provides sensor counts, a known
physical travel distance turns those counts into DPI, and event-frame timing
provides an observed polling-frequency estimate.

Nothing in this module knows Logitech, Razer, HID++, sensor models, report IDs,
or vendor packet layouts.  The resulting measurements are semantic labels that
automatic discovery can correlate with simultaneously/adjacently observed
hidraw state.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from pathlib import Path
import select
from statistics import median
import time
from typing import Iterable, Literal


EV_SYN = 0x00
EV_REL = 0x02
SYN_REPORT = 0x00
REL_X = 0x00
REL_Y = 0x01

STANDARD_POLLING_RATES_HZ = (125, 250, 500, 1000, 2000, 4000, 8000)


class CalibrationError(ValueError):
    """The captured motion is insufficient or unsuitable for calibration."""


@dataclass(frozen=True)
class CalibrationEvent:
    """Minimal kernel-event representation needed for sensor calibration."""

    timestamp_ns: int
    event_type: int
    code: int
    value: int


@dataclass(frozen=True)
class SensorCalibration:
    """One measured pointer state, independent of any vendor protocol."""

    axis: Literal["x", "y"]
    distance_mm: float
    net_counts: int
    path_counts: int
    cross_axis_counts: int
    straightness: float
    estimated_dpi: float
    motion_frames: int
    peak_polling_hz: float | None
    standard_polling_hz: int | None
    polling_error_fraction: float | None

    @property
    def rounded_dpi(self) -> int:
        return int(round(self.estimated_dpi))


def _event_timestamp_ns(event) -> int:
    """Return a kernel event timestamp in nanoseconds.

    python-evdev exposes ``sec``/``usec`` from ``struct input_event``.  Tests and
    replay callers may instead pass a ``timestamp_ns`` attribute.
    """

    timestamp_ns = getattr(event, "timestamp_ns", None)
    if timestamp_ns is not None:
        return int(timestamp_ns)
    sec = getattr(event, "sec", None)
    usec = getattr(event, "usec", None)
    if sec is None or usec is None:
        raise TypeError("event does not expose timestamp_ns or sec/usec")
    return int(sec) * 1_000_000_000 + int(usec) * 1_000


def normalize_event(event) -> CalibrationEvent:
    return CalibrationEvent(
        timestamp_ns=_event_timestamp_ns(event),
        event_type=int(event.event_type if hasattr(event, "event_type") else event.type),
        code=int(event.code),
        value=int(event.value),
    )


def _motion_frame_timestamps(events: tuple[CalibrationEvent, ...]) -> tuple[int, ...]:
    """Return SYN_REPORT timestamps for frames that contain X/Y motion."""

    frames: list[int] = []
    motion_in_frame = False
    for event in events:
        if event.event_type == EV_REL and event.code in {REL_X, REL_Y} and event.value:
            motion_in_frame = True
        elif event.event_type == EV_SYN and event.code == SYN_REPORT:
            if motion_in_frame:
                frames.append(event.timestamp_ns)
            motion_in_frame = False
    return tuple(frames)


def estimate_peak_polling_hz(
    frame_timestamps_ns: Iterable[int],
) -> tuple[float | None, int | None, float | None]:
    """Estimate the device's highest sustained event frequency.

    Gaming mice may dynamically lower their event rate while moving slowly.
    Rather than averaging pauses into the result, use the median of the fastest
    quartile of positive frame intervals.  The raw estimate is retained and a
    common USB gaming-mouse rate is reported only when it is within 20%.
    """

    timestamps = tuple(int(value) for value in frame_timestamps_ns)
    deltas = sorted(
        after - before
        for before, after in zip(timestamps, timestamps[1:])
        if after > before and after - before >= 50_000  # reject >20 kHz timer/batch artifacts
    )
    if len(deltas) < 3:
        return None, None, None

    count = max(3, ceil(len(deltas) * 0.25))
    representative_ns = float(median(deltas[:count]))
    if representative_ns <= 0:
        return None, None, None
    measured = 1_000_000_000.0 / representative_ns

    standard = min(STANDARD_POLLING_RATES_HZ, key=lambda rate: abs(rate - measured))
    error = abs(measured - standard) / standard
    if error > 0.20:
        return measured, None, error
    return measured, standard, error


def measure_sensor_state(
    events: Iterable[CalibrationEvent],
    *,
    distance_mm: float,
    axis: Literal["x", "y"] = "x",
    minimum_straightness: float = 0.80,
) -> SensorCalibration:
    """Convert a known physical movement into DPI and polling observations.

    ``distance_mm`` is the ruler distance travelled by the mouse.  The user
    should move predominantly along ``axis`` without reversing direction.  DPI
    is simply device counts divided by physical inches travelled.
    """

    if distance_mm <= 0:
        raise CalibrationError("distance_mm must be greater than zero")
    if axis not in {"x", "y"}:
        raise CalibrationError("axis must be 'x' or 'y'")
    if not 0 < minimum_straightness <= 1:
        raise CalibrationError("minimum_straightness must be in (0, 1]")

    captured = tuple(normalize_event(event) for event in events)
    x_values = [
        event.value
        for event in captured
        if event.event_type == EV_REL and event.code == REL_X
    ]
    y_values = [
        event.value
        for event in captured
        if event.event_type == EV_REL and event.code == REL_Y
    ]
    primary = x_values if axis == "x" else y_values
    secondary = y_values if axis == "x" else x_values

    signed_counts = sum(primary)
    net_counts = abs(signed_counts)
    path_counts = sum(abs(value) for value in primary)
    cross_axis_counts = sum(abs(value) for value in secondary)
    if net_counts <= 0 or path_counts <= 0:
        raise CalibrationError(f"no usable REL_{axis.upper()} motion was captured")

    straightness = net_counts / path_counts
    if straightness < minimum_straightness:
        raise CalibrationError(
            f"movement reversed too much for reliable DPI calibration "
            f"(straightness={straightness:.2f}, need >= {minimum_straightness:.2f})"
        )

    inches = distance_mm / 25.4
    dpi = net_counts / inches
    frames = _motion_frame_timestamps(captured)
    peak_hz, standard_hz, polling_error = estimate_peak_polling_hz(frames)

    return SensorCalibration(
        axis=axis,
        distance_mm=float(distance_mm),
        net_counts=net_counts,
        path_counts=path_counts,
        cross_axis_counts=cross_axis_counts,
        straightness=straightness,
        estimated_dpi=dpi,
        motion_frames=len(frames),
        peak_polling_hz=peak_hz,
        standard_polling_hz=standard_hz,
        polling_error_fraction=polling_error,
    )


def capture_evdev_motion(
    path: str | Path,
    *,
    seconds: float,
) -> tuple[CalibrationEvent, ...]:
    """Capture kernel-timestamped evdev events without pointer acceleration.

    This opens the event node read-only and does not grab the device.  The
    kernel timestamps are kept specifically so polling-rate estimation is not
    distorted by userspace batching latency.
    """

    if seconds <= 0:
        raise CalibrationError("seconds must be greater than zero")
    try:
        from evdev import InputDevice
    except ImportError as exc:  # pragma: no cover - project dependency
        raise RuntimeError("python-evdev is required for sensor calibration") from exc

    device = InputDevice(str(path))
    captured: list[CalibrationEvent] = []
    deadline = time.monotonic() + seconds
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            readable, _, _ = select.select([device.fd], [], [], min(remaining, 0.1))
            if not readable:
                continue
            try:
                batch = device.read()
            except BlockingIOError:
                continue
            captured.extend(normalize_event(event) for event in batch)
    finally:
        device.close()
    return tuple(captured)
