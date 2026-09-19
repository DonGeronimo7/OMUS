"""Vendor-neutral mouse sensor calibration from Linux evdev events.

The calibration method intentionally mirrors the useful principle behind
``mouse-dpi-tool`` while making the measurement suitable for automatic
discovery: raw evdev motion provides sensor counts, a known physical travel
distance turns those counts into a DPI estimate, and kernel event timing
provides an observed polling-frequency estimate.

Nothing in this module knows Logitech, Razer, HID++, sensor models, report IDs,
or vendor packet layouts. The resulting measurements are semantic labels that
automatic discovery can correlate with simultaneously/adjacently observed
hidraw state.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, hypot
from pathlib import Path
import select
from statistics import median
import time
from typing import Iterable, Literal


EV_SYN = 0x00
EV_REL = 0x02
SYN_REPORT = 0x00
SYN_DROPPED = 0x03
REL_X = 0x00
REL_Y = 0x01

STANDARD_POLLING_RATES_HZ = (125, 250, 500, 1000, 2000, 4000, 8000)
DEFAULT_SEGMENT_IDLE_SECONDS = 0.75


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
    segment_count: int = 1
    segment_duration_s: float = 0.0
    axis_dominance: float = 1.0

    @property
    def rounded_dpi(self) -> int:
        return int(round(self.estimated_dpi))


@dataclass(frozen=True)
class CalibrationSummary:
    """Robust aggregate of repeated ruler passes at one unchanged DPI state."""

    passes: tuple[SensorCalibration, ...]
    estimated_dpi: float
    rounded_dpi: int
    median_absolute_deviation: float
    relative_mad: float
    standard_polling_hz: int | None
    confidence: Literal["high", "medium", "low"]


def _event_timestamp_ns(event) -> int:
    """Return a kernel event timestamp in nanoseconds."""

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


def _normalize_capture(events: Iterable[CalibrationEvent]) -> tuple[CalibrationEvent, ...]:
    captured = tuple(normalize_event(event) for event in events)
    if any(
        event.event_type == EV_SYN and event.code == SYN_DROPPED
        for event in captured
    ):
        raise CalibrationError(
            "kernel reported SYN_DROPPED during calibration; input events were lost, "
            "so DPI cannot be measured reliably"
        )
    return captured


@dataclass(frozen=True)
class _MotionFrame:
    start_index: int
    end_index: int
    timestamp_ns: int
    x: int
    y: int

    @property
    def magnitude(self) -> float:
        return hypot(self.x, self.y)


def _motion_frames(captured: tuple[CalibrationEvent, ...]) -> tuple[_MotionFrame, ...]:
    """Collapse evdev REL events into SYN-delimited physical motion frames."""

    frames: list[_MotionFrame] = []
    frame_start = 0
    x = 0
    y = 0
    for index, event in enumerate(captured):
        if event.event_type == EV_REL:
            if event.code == REL_X:
                x += event.value
            elif event.code == REL_Y:
                y += event.value
        elif event.event_type == EV_SYN and event.code == SYN_REPORT:
            if x or y:
                frames.append(_MotionFrame(frame_start, index, event.timestamp_ns, x, y))
            frame_start = index + 1
            x = 0
            y = 0
    return tuple(frames)


def isolate_motion_segment(
    events: Iterable[CalibrationEvent],
    *,
    idle_gap_seconds: float = DEFAULT_SEGMENT_IDLE_SECONDS,
) -> tuple[tuple[CalibrationEvent, ...], int]:
    """Return the strongest contiguous deliberate-motion segment.

    Setup/repositioning motion before or after the ruler pass must not inflate
    the DPI estimate. Motion frames are therefore split whenever there is a
    meaningful idle gap; the segment containing the greatest vector travel is
    retained. The number of observed segments is returned for diagnostics.
    """

    if idle_gap_seconds <= 0:
        raise CalibrationError("idle_gap_seconds must be greater than zero")
    captured = _normalize_capture(events)
    frames = _motion_frames(captured)
    if not frames:
        raise CalibrationError("no usable REL_X or REL_Y motion was captured")

    gap_ns = int(idle_gap_seconds * 1_000_000_000)
    groups: list[list[_MotionFrame]] = [[frames[0]]]
    for frame in frames[1:]:
        if frame.timestamp_ns - groups[-1][-1].timestamp_ns > gap_ns:
            groups.append([frame])
        else:
            groups[-1].append(frame)

    best = max(groups, key=lambda group: sum(frame.magnitude for frame in group))
    start = best[0].start_index
    end = best[-1].end_index + 1
    return captured[start:end], len(groups)


def _axis_values(
    captured: tuple[CalibrationEvent, ...],
) -> tuple[list[int], list[int]]:
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
    return x_values, y_values


def _motion_frame_timestamps(events: tuple[CalibrationEvent, ...]) -> tuple[int, ...]:
    return tuple(frame.timestamp_ns for frame in _motion_frames(events))


def estimate_peak_polling_hz(
    frame_timestamps_ns: Iterable[int],
) -> tuple[float | None, int | None, float | None]:
    """Estimate the device's highest sustained event frequency robustly.

    Gaming mice may dynamically lower their event rate while moving slowly.
    The median of the fastest quartile is less vulnerable than a single maximum
    to scheduling/timestamp outliers while still recovering the highest
    sustained rate. A standard gaming-mouse rate is returned only when the raw
    estimate is sufficiently close.
    """

    timestamps = tuple(int(value) for value in frame_timestamps_ns)
    deltas = sorted(
        after - before
        for before, after in zip(timestamps, timestamps[1:])
        if after > before and after - before >= 50_000
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


def _segment_duration(captured: tuple[CalibrationEvent, ...]) -> float:
    frames = _motion_frames(captured)
    if len(frames) < 2:
        return 0.0
    return (frames[-1].timestamp_ns - frames[0].timestamp_ns) / 1_000_000_000.0


def _measure_axis(
    captured: tuple[CalibrationEvent, ...],
    *,
    distance_mm: float,
    axis: Literal["x", "y"],
    minimum_straightness: float,
    segment_count: int,
) -> SensorCalibration:
    x_values, y_values = _axis_values(captured)
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
    total_axis_path = path_counts + cross_axis_counts
    dominance = path_counts / total_axis_path if total_axis_path else 1.0

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
        segment_count=segment_count,
        segment_duration_s=_segment_duration(captured),
        axis_dominance=dominance,
    )


def measure_sensor_state(
    events: Iterable[CalibrationEvent],
    *,
    distance_mm: float,
    axis: Literal["x", "y"] = "x",
    minimum_straightness: float = 0.80,
    isolate_segment: bool = True,
) -> SensorCalibration:
    """Convert a known physical movement into DPI and polling observations."""

    if distance_mm <= 0:
        raise CalibrationError("distance_mm must be greater than zero")
    if axis not in {"x", "y"}:
        raise CalibrationError("axis must be 'x' or 'y'")
    if not 0 < minimum_straightness <= 1:
        raise CalibrationError("minimum_straightness must be in (0, 1]")

    if isolate_segment:
        captured, segment_count = isolate_motion_segment(events)
    else:
        captured = _normalize_capture(events)
        segment_count = 1
    return _measure_axis(
        captured,
        distance_mm=distance_mm,
        axis=axis,
        minimum_straightness=minimum_straightness,
        segment_count=segment_count,
    )


def measure_sensor_state_auto(
    events: Iterable[CalibrationEvent],
    *,
    distance_mm: float,
    minimum_straightness: float = 0.80,
    isolate_segment: bool = True,
) -> SensorCalibration:
    """Measure DPI without asking which Linux axis carries the ruler motion.

    The deliberate movement segment is isolated first. Both REL_X and REL_Y are
    then inspected. The dominant axis remains a useful diagnostic label, while
    DPI itself is calculated from the two-dimensional net displacement. This
    keeps mouse orientation from becoming a hidden calibration error.
    """

    if distance_mm <= 0:
        raise CalibrationError("distance_mm must be greater than zero")
    if not 0 < minimum_straightness <= 1:
        raise CalibrationError("minimum_straightness must be in (0, 1]")

    if isolate_segment:
        captured, segment_count = isolate_motion_segment(events)
    else:
        captured = _normalize_capture(events)
        segment_count = 1

    frames = _motion_frames(captured)
    if not frames:
        raise CalibrationError("no usable REL_X or REL_Y motion was captured")

    x_net_signed = sum(frame.x for frame in frames)
    y_net_signed = sum(frame.y for frame in frames)
    x_path = sum(abs(frame.x) for frame in frames)
    y_path = sum(abs(frame.y) for frame in frames)
    vector_net = hypot(x_net_signed, y_net_signed)
    vector_path = sum(frame.magnitude for frame in frames)
    if vector_net <= 0 or vector_path <= 0:
        raise CalibrationError("no usable REL_X or REL_Y motion was captured")

    straightness = vector_net / vector_path
    if straightness < minimum_straightness:
        raise CalibrationError(
            f"movement reversed too much for reliable DPI calibration "
            f"(straightness={straightness:.2f}, need >= {minimum_straightness:.2f})"
        )

    axis: Literal["x", "y"] = "x" if x_path >= y_path else "y"
    dominant_path = max(x_path, y_path)
    cross_path = min(x_path, y_path)
    axis_total = dominant_path + cross_path
    dominance = dominant_path / axis_total if axis_total else 1.0

    inches = distance_mm / 25.4
    dpi = vector_net / inches
    timestamps = tuple(frame.timestamp_ns for frame in frames)
    peak_hz, standard_hz, polling_error = estimate_peak_polling_hz(timestamps)

    return SensorCalibration(
        axis=axis,
        distance_mm=float(distance_mm),
        net_counts=int(round(vector_net)),
        path_counts=int(round(vector_path)),
        cross_axis_counts=cross_path,
        straightness=straightness,
        estimated_dpi=dpi,
        motion_frames=len(frames),
        peak_polling_hz=peak_hz,
        standard_polling_hz=standard_hz,
        polling_error_fraction=polling_error,
        segment_count=segment_count,
        segment_duration_s=_segment_duration(captured),
        axis_dominance=dominance,
    )


def summarize_calibrations(
    passes: Iterable[SensorCalibration],
) -> CalibrationSummary:
    """Combine repeated passes using a median and robust dispersion metric."""

    samples = tuple(passes)
    if not samples:
        raise CalibrationError("at least one calibration pass is required")

    dpis = tuple(sample.estimated_dpi for sample in samples)
    dpi = float(median(dpis))
    deviations = tuple(abs(value - dpi) for value in dpis)
    mad = float(median(deviations))
    relative_mad = mad / dpi if dpi > 0 else 1.0

    standard_rates = [
        sample.standard_polling_hz
        for sample in samples
        if sample.standard_polling_hz is not None
    ]
    standard_polling = None
    if standard_rates:
        # Deterministic mode: prefer the lower rate on a tie rather than
        # inventing precision from too few samples.
        standard_polling = max(
            sorted(set(standard_rates)),
            key=lambda rate: (standard_rates.count(rate), -rate),
        )

    minimum_straightness = min(sample.straightness for sample in samples)
    if len(samples) >= 3 and relative_mad <= 0.05 and minimum_straightness >= 0.95:
        confidence: Literal["high", "medium", "low"] = "high"
    elif relative_mad <= 0.12 and minimum_straightness >= 0.85:
        confidence = "medium"
    else:
        confidence = "low"

    return CalibrationSummary(
        passes=samples,
        estimated_dpi=dpi,
        rounded_dpi=int(round(dpi)),
        median_absolute_deviation=mad,
        relative_mad=relative_mad,
        standard_polling_hz=standard_polling,
        confidence=confidence,
    )


def capture_evdev_motion(
    path: str | Path,
    *,
    seconds: float,
    exclusive: bool = True,
) -> tuple[CalibrationEvent, ...]:
    """Capture kernel-timestamped physical evdev events."""

    if seconds <= 0:
        raise CalibrationError("seconds must be greater than zero")
    try:
        from evdev import InputDevice
    except ImportError as exc:  # pragma: no cover - project dependency
        raise RuntimeError("python-evdev is required for sensor calibration") from exc

    device = InputDevice(str(path))
    grabbed = False
    if exclusive:
        try:
            device.grab()
            grabbed = True
        except OSError as exc:
            device.close()
            raise CalibrationError(
                "could not exclusively grab the physical mouse event stream; "
                "stop OMUS and any other program that has grabbed the mouse, "
                "then retry calibration"
            ) from exc

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
        if grabbed:
            try:
                device.ungrab()
            except OSError:
                pass
        device.close()
    return tuple(captured)
