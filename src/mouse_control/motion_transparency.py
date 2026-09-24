# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only production-path motion transparency measurement and analysis."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
import json
from pathlib import Path
from statistics import median
import threading
from typing import Iterable

from evdev import ecodes


MotionEvent = tuple[int, int]


@dataclass(frozen=True)
class MotionFrame:
    events: tuple[MotionEvent, ...]
    timestamp_ns: int
    arrival_ns: int


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _rate(frames: tuple[MotionFrame, ...]) -> float | None:
    if len(frames) < 2:
        return None
    elapsed = frames[-1].timestamp_ns - frames[0].timestamp_ns
    return None if elapsed <= 0 else (len(frames) - 1) * 1_000_000_000 / elapsed


def analyze_motion_transparency(
    physical: Iterable[MotionFrame],
    virtual: Iterable[MotionFrame],
    *,
    syn_dropped: int = 0,
) -> dict[str, object]:
    """Compare exact ordered REL_X/REL_Y events and their frame partitions."""

    physical_frames = tuple(physical)
    virtual_frames = tuple(virtual)
    physical_signatures = tuple(frame.events for frame in physical_frames)
    virtual_signatures = tuple(frame.events for frame in virtual_frames)
    frame_matcher = SequenceMatcher(None, physical_signatures, virtual_signatures, autojunk=False)
    matched_pairs: list[tuple[int, int]] = []
    dropped_frames = duplicated_frames = 0
    for tag, i1, i2, j1, j2 in frame_matcher.get_opcodes():
        if tag == "equal":
            matched_pairs.extend((i1 + offset, j1 + offset) for offset in range(i2 - i1))
        else:
            dropped_frames += i2 - i1
            duplicated_frames += j2 - j1

    physical_events = tuple(event for frame in physical_frames for event in frame.events)
    virtual_events = tuple(event for frame in virtual_frames for event in frame.events)
    dropped_events = duplicated_events = modified_events = ordering_violations = 0
    if physical_events != virtual_events and Counter(physical_events) == Counter(virtual_events):
        ordering_violations = 1
    else:
        event_matcher = SequenceMatcher(None, physical_events, virtual_events, autojunk=False)
        for tag, i1, i2, j1, j2 in event_matcher.get_opcodes():
            if tag == "equal":
                continue
            left = physical_events[i1:i2]
            right = virtual_events[j1:j2]
            paired = min(len(left), len(right))
            for before, after in zip(left[:paired], right[:paired]):
                if before[0] == after[0] and before[1] != after[1]:
                    modified_events += 1
                else:
                    dropped_events += 1
                    duplicated_events += 1
            dropped_events += len(left) - paired
            duplicated_events += len(right) - paired

    physical_boundaries: set[int] = set()
    virtual_boundaries: set[int] = set()
    total = 0
    for frame in physical_frames[:-1]:
        total += len(frame.events)
        physical_boundaries.add(total)
    total = 0
    for frame in virtual_frames[:-1]:
        total += len(frame.events)
        virtual_boundaries.add(total)
    if physical_events == virtual_events:
        missing_boundaries = physical_boundaries - virtual_boundaries
        extra_boundaries = virtual_boundaries - physical_boundaries
        framing_violations = len(missing_boundaries | extra_boundaries)
        unexpected_coalescing = len(missing_boundaries)
    else:
        framing_violations = dropped_frames + duplicated_frames
        unexpected_coalescing = 0

    latencies_ms = [
        (virtual_frames[virtual_index].arrival_ns
         - physical_frames[physical_index].arrival_ns) / 1_000_000
        for physical_index, virtual_index in matched_pairs
        if virtual_frames[virtual_index].arrival_ns
        >= physical_frames[physical_index].arrival_ns
    ]
    latency_median = median(latencies_ms) if latencies_ms else None
    absolute_deviations = (
        [abs(value - latency_median) for value in latencies_ms]
        if latency_median is not None else []
    )
    spike_threshold = (
        latency_median + max(1.0, 6 * median(absolute_deviations))
        if latency_median is not None else None
    )
    latency_spikes = (
        sum(value > spike_threshold for value in latencies_ms)
        if spike_threshold is not None else 0
    )
    batched_frames = sum(
        after.timestamp_ns == before.timestamp_ns
        for before, after in zip(virtual_frames, virtual_frames[1:])
    )

    failures = {
        "insufficient_motion_frames": int(
            len(physical_frames) < 2 or len(virtual_frames) < 2
        ),
        "modified_rel_events": modified_events,
        "dropped_motion_events": dropped_events,
        "duplicated_motion_events": duplicated_events,
        "ordering_violations": ordering_violations,
        "unexpected_coalescing": unexpected_coalescing,
        "framing_violations": framing_violations,
        "syn_dropped": syn_dropped,
    }
    return {
        "pass": all(value == 0 for value in failures.values()),
        "physical_motion_frames": len(physical_frames),
        "virtual_motion_frames": len(virtual_frames),
        "matched_frames": len(matched_pairs),
        "dropped_frames": dropped_frames,
        "duplicated_frames": duplicated_frames,
        **failures,
        "physical_motion_events": len(physical_events),
        "virtual_motion_events": len(virtual_events),
        "physical_effective_frame_rate_hz": _rate(physical_frames),
        "virtual_effective_frame_rate_hz": _rate(virtual_frames),
        "forwarding_latency_ms": {
            "minimum": min(latencies_ms) if latencies_ms else None,
            "median": latency_median,
            "p95": _percentile(latencies_ms, 0.95),
            "p99": _percentile(latencies_ms, 0.99),
            "maximum": max(latencies_ms) if latencies_ms else None,
        },
        "latency_spikes": latency_spikes,
        "batched_frames": batched_frames,
    }


class MotionTransparencyDiagnostic:
    """Collect physical and virtual motion at the production remapper boundary."""

    def __init__(self, output: Path, workload: str) -> None:
        self.output = output
        self.workload = workload
        self._lock = threading.Lock()
        self._physical: list[MotionFrame] = []
        self._virtual: list[MotionFrame] = []
        self._virtual_pending: list[MotionEvent] = []
        self._syn_dropped = 0

    def physical_frame(
        self,
        events: Iterable[tuple[int, int, int]],
        timestamp_ns: int,
        arrival_ns: int,
    ) -> None:
        motion = tuple(
            (code, value)
            for event_type, code, value in events
            if event_type == ecodes.EV_REL and code in {ecodes.REL_X, ecodes.REL_Y}
        )
        if motion:
            with self._lock:
                self._physical.append(MotionFrame(motion, timestamp_ns, arrival_ns))

    def virtual_event(self, event_type: int, code: int, value: int) -> None:
        if event_type == ecodes.EV_REL and code in {ecodes.REL_X, ecodes.REL_Y}:
            with self._lock:
                self._virtual_pending.append((code, value))

    def virtual_frame(self, timestamp_ns: int) -> None:
        with self._lock:
            if self._virtual_pending:
                self._virtual.append(
                    MotionFrame(tuple(self._virtual_pending), timestamp_ns, timestamp_ns)
                )
                self._virtual_pending.clear()

    def dropped(self) -> None:
        with self._lock:
            self._syn_dropped += 1

    def write_report(self, *, wake_samples: Iterable[object] = ()) -> dict[str, object]:
        with self._lock:
            physical = tuple(self._physical)
            virtual = tuple(self._virtual)
            dropped = self._syn_dropped
        summary = analyze_motion_transparency(physical, virtual, syn_dropped=dropped)
        wake_cycles = []
        for index, sample in enumerate(wake_samples, 1):
            recognized_ms, full_ready_ms, first_input_ms = sample.durations_ms()
            wake_cycles.append({
                "cycle": index,
                "source": sample.source,
                "wake_detected": recognized_ms is not None,
                "first_virtual_input_ms": first_input_ms,
                "full_omus_ready_ms": full_ready_ms,
                "t0_ns": sample.t0_ns,
                "t1_ns": sample.t1_ns,
                "t2_ns": sample.t2_ns,
                "t3_ns": sample.t3_ns,
            })
        report = {
            "diagnostic": "OMUS motion transparency",
            "workload": self.workload,
            "measurement_boundary": (
                "physical evdev frame received by MouseRemapper to virtual uinput "
                "frame submitted by MouseRemapper"
            ),
            "summary": summary,
            "wake_cycles": wake_cycles,
            "physical_frames": [asdict(frame) for frame in physical],
            "virtual_frames": [asdict(frame) for frame in virtual],
        }
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return summary
