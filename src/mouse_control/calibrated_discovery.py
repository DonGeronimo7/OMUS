# SPDX-License-Identifier: AGPL-3.0-or-later
"""Physical CPI/polling evidence correlated with read-only HID discovery.

This module joins two independently safe evidence streams:

* Linux evdev relative motion, measured against a known physical distance; and
* passive hidraw/GET_FEATURE observations from the already-correlated mouse.

The user may provide configured DPI stage labels, but those labels never affect
physical CPI measurement. Unknown HID remains read-only. Correlation can prove
that a raw state accompanies a calibrated DPI state; it cannot authorize a
write transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import selectors
import time
from typing import Mapping, Sequence

from .event_correlation import (
    PhysicalAction,
    TimedEvdevEvent,
    TimedReport,
    detect_repeated_report_fields,
    diff_feature_snapshots,
    suppress_duplicates,
)
from .learning_session import LearningSample, ReadOnlyLearningSession
from .protocol_grammar import CodecKind, CodecSpec, SemanticBehavior
from .semantic_inference import SemanticHypothesis
from .sensor_calibration import CalibrationEvent


@dataclass(frozen=True)
class CalibratedCapture:
    """One simultaneous physical-motion and HID observation window."""

    sample: LearningSample
    calibration_events: tuple[CalibrationEvent, ...]


@dataclass(frozen=True)
class CalibratedDpiState:
    """Protocol-neutral evidence for one configured DPI stage."""

    configured_dpi: int
    measured_cpi: float
    polling_hz: int | None
    confidence: str

    @property
    def physical_deviation_fraction(self) -> float:
        return (self.measured_cpi - self.configured_dpi) / self.configured_dpi


@dataclass(frozen=True)
class CalibratedRawMapping:
    """A read-side raw field correlated with calibrated DPI states.

    Multiple packet fields may co-vary with the same physical state, so this is
    intentionally *correlated* evidence rather than a unique/proven writable
    location.
    """

    report_key: object
    offset: int
    configured_mapping: Mapping[int, int]
    measured_cpi_mapping: Mapping[int, int]
    observations: int
    descriptor_roles: tuple[str, ...] = ()

    @property
    def hypothesis(self) -> SemanticHypothesis:
        return SemanticHypothesis(
            behavior=SemanticBehavior.DPI_VALUE,
            confidence="correlated",
            reason=(
                f"raw state mapped consistently across {self.observations} guided DPI-cycle "
                "transitions whose resulting states were independently calibrated by physical motion"
            ),
            report_key=self.report_key,
            offset=self.offset,
            codec=CodecSpec(CodecKind.LOOKUP, values=dict(self.configured_mapping)),
            mapping=dict(self.configured_mapping),
        )


def _kernel_timestamp_ns(event) -> int:
    sec = getattr(event, "sec", None)
    usec = getattr(event, "usec", None)
    if sec is None or usec is None:
        return time.monotonic_ns()
    return int(sec) * 1_000_000_000 + int(usec) * 1_000


def capture_calibrated_motion(
    session: ReadOnlyLearningSession,
    *,
    evdev_path: str | Path,
    seconds: float,
) -> CalibratedCapture:
    """Capture one ruler pass and every readable correlated hidraw sibling.

    The physical evdev node is exclusively grabbed so desktop consumers cannot
    interfere with the calibration pass. The grab is an input-routing control,
    not a hardware write. hidraw siblings are opened O_RDONLY|O_NONBLOCK and no
    SET_REPORT/HIDIOCSFEATURE operation exists here.

    Two clocks are intentionally preserved: monotonic receive time is used for
    cross-interface event correlation, while the kernel evdev timestamp is used
    for CPI/polling measurement so userspace batching does not distort timing.
    """

    if seconds <= 0:
        raise ValueError("seconds must be greater than zero")

    try:
        from evdev import InputDevice
    except ImportError as exc:  # pragma: no cover - project dependency
        raise RuntimeError("python-evdev is required for calibrated discovery") from exc

    before = session.snapshot_features()
    readable_hidraw, unreadable_hidraw = session.hidraw_access_report()
    source_map = session._hidraw_source_map(readable_hidraw)

    device = InputDevice(os.fspath(evdev_path))
    selector = selectors.DefaultSelector()
    hid_fds: list[int] = []
    evdev_events: list[TimedEvdevEvent] = []
    calibration_events: list[CalibrationEvent] = []
    reports: list[TimedReport] = []
    start_ns = time.monotonic_ns()
    deadline = time.monotonic() + seconds
    grabbed = False

    try:
        try:
            device.grab()
            grabbed = True
        except OSError as exc:
            raise PermissionError(
                "could not exclusively grab the physical mouse for calibrated discovery; "
                "stop OMUS and other grabbers, then retry"
            ) from exc

        selector.register(device.fd, selectors.EVENT_READ, ("evdev", device))
        for path in readable_hidraw:
            live_path = os.fspath(path)
            fd = os.open(live_path, os.O_RDONLY | os.O_NONBLOCK)
            hid_fds.append(fd)
            selector.register(
                fd,
                selectors.EVENT_READ,
                ("hidraw", source_map.get(live_path, live_path), live_path),
            )

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            for key, _mask in selector.select(timeout=min(remaining, 0.1)):
                kind = key.data[0]
                receive_ns = time.monotonic_ns()
                if kind == "hidraw":
                    _kind, logical_source, live_path = key.data
                    try:
                        data = os.read(key.fd, 4096)
                    except BlockingIOError:
                        continue
                    if data:
                        reports.append(
                            TimedReport(
                                receive_ns,
                                logical_source,
                                data,
                                diagnostic_source=live_path,
                            )
                        )
                    continue

                _kind, source = key.data
                try:
                    batch = source.read()
                except BlockingIOError:
                    continue
                for event in batch:
                    event_receive_ns = time.monotonic_ns()
                    event_type = int(event.type)
                    code = int(event.code)
                    value = int(event.value)
                    evdev_events.append(
                        TimedEvdevEvent(
                            timestamp_ns=event_receive_ns,
                            source=source.path,
                            event_type=event_type,
                            code=code,
                            value=value,
                        )
                    )
                    calibration_events.append(
                        CalibrationEvent(
                            timestamp_ns=_kernel_timestamp_ns(event),
                            event_type=event_type,
                            code=code,
                            value=value,
                        )
                    )
    finally:
        selector.close()
        for fd in hid_fds:
            os.close(fd)
        if grabbed:
            try:
                device.ungrab()
            except OSError:
                pass
        device.close()

    after = session.snapshot_features()
    action = PhysicalAction(
        start_ns=start_ns,
        end_ns=time.monotonic_ns(),
        evdev_events=evdev_events,
        hid_reports=suppress_duplicates(reports),
        feature_changes=diff_feature_snapshots(before, after),
    )
    return CalibratedCapture(
        sample=LearningSample(
            action=action,
            unreadable_hidraw_paths=unreadable_hidraw,
        ),
        calibration_events=tuple(calibration_events),
    )


def infer_calibrated_raw_mappings(
    transition_samples: Sequence[LearningSample],
    resulting_states: Sequence[CalibratedDpiState],
    *,
    allowed_report_keys: set[object] | frozenset[object] | None = None,
    descriptor_roles: Mapping[tuple[object, int], tuple[str, ...]] | None = None,
) -> tuple[CalibratedRawMapping, ...]:
    """Map post-transition raw values onto physically calibrated DPI states.

    ``transition_samples[i]`` is the DPI-button action that entered
    ``resulting_states[i]``. Candidate packet locations remain correlated even
    when the physical state is high-confidence because several bytes may change
    together. This function never creates write authority.
    """

    if len(transition_samples) != len(resulting_states):
        raise ValueError("transition samples and resulting states must have the same length")
    if len(transition_samples) < 2:
        return ()

    actions = tuple(sample.action for sample in transition_samples)
    roles = descriptor_roles or {}
    result: list[CalibratedRawMapping] = []
    for candidate in detect_repeated_report_fields(actions):
        if allowed_report_keys is not None and candidate.report_key not in allowed_report_keys:
            continue
        raw_states = tuple(after for _before, after in candidate.transitions if after is not None)
        if len(raw_states) != len(resulting_states):
            continue

        configured: dict[int, int] = {}
        measured: dict[int, int] = {}
        conflict = False
        for raw, state in zip(raw_states, resulting_states):
            previous = configured.get(raw)
            if previous is not None and previous != state.configured_dpi:
                conflict = True
                break
            configured[raw] = state.configured_dpi
            measured[raw] = int(round(state.measured_cpi))
        if conflict or len(configured) < 2:
            continue

        result.append(
            CalibratedRawMapping(
                report_key=candidate.report_key,
                offset=candidate.offset,
                configured_mapping=configured,
                measured_cpi_mapping=measured,
                observations=candidate.observations,
                descriptor_roles=roles.get((candidate.report_key, candidate.offset), ("unknown",)),
            )
        )

    return tuple(
        sorted(
            result,
            key=lambda item: (-item.observations, repr(item.report_key), item.offset),
        )
    )


def calibrated_cycle_hypothesis(states: Sequence[CalibratedDpiState]) -> SemanticHypothesis | None:
    """Validate the semantic DPI cycle independently of any raw byte location."""

    samples = tuple(states)
    if len(samples) < 2:
        return None
    all_high = all(state.confidence == "high" for state in samples)
    deviations = tuple(abs(state.physical_deviation_fraction) for state in samples)
    physical_agreement = max(deviations, default=1.0) <= 0.15
    confidence = "validated" if all_high and physical_agreement else "correlated"
    return SemanticHypothesis(
        behavior=SemanticBehavior.DPI_CYCLE_TRIGGER,
        confidence=confidence,
        reason=(
            f"{len(samples)} guided DPI-cycle transitions were followed by independent "
            "physical CPI/polling calibration; raw packet locations remain correlated only"
        ),
    )
