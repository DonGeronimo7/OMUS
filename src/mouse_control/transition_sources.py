"""Protocol-neutral runtime sources for physically calibrated DPI transitions.

The deep learner proves the physical DPI cycle independently from vendor
semantics. This module answers the narrower runtime question: which stable,
Linux-visible observation can represent that already-proven cycle later?

Nothing here grants or executes hardware writes. A transition source is
read-side evidence only.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Hashable, Mapping, Sequence

from .calibrated_discovery import CalibratedDpiState, CalibratedRawMapping
from .event_correlation import RawStreamIdentity, detect_repeated_changes
from .learning_session import LearningSample


ABSOLUTE_SOURCE_KINDS = frozenset({
    "hid_state",
    "feature_state",
    "evdev_absolute_stage",
})
TRIGGER_SOURCE_KINDS = frozenset({
    "hid_cycle_trigger",
    "evdev_cycle_trigger",
})
SUPPORTED_SOURCE_KINDS = ABSOLUTE_SOURCE_KINDS | TRIGGER_SOURCE_KINDS


@dataclass(frozen=True)
class CalibratedTransitionSource:
    """One path-independent read-side representation of a calibrated cycle."""

    kind: str
    cycle_order: tuple[int, ...]
    observations: int
    confidence: str = "validated"
    report_key: object | None = None
    offset: int | None = None
    raw_to_dpi: Mapping[int, int] = field(default_factory=dict)
    interface: Mapping[str, object] = field(default_factory=dict)
    event_type: int | None = None
    code: int | None = None
    press_value: int | None = None
    release_value: int | None = None
    press_pattern: bytes | None = None
    release_pattern: bytes | None = None

    @property
    def absolute(self) -> bool:
        return self.kind in ABSOLUTE_SOURCE_KINDS

    @property
    def ordered_trigger(self) -> bool:
        return self.kind in TRIGGER_SOURCE_KINDS


def _report_shape(source: Hashable, data: bytes) -> Hashable:
    layout = (len(data), data[0] if data else None)
    if isinstance(source, RawStreamIdentity):
        return (*source.key, *layout)
    return (source, *layout)


def _configured_mapping(
    raw_values: Sequence[int],
    states: Sequence[CalibratedDpiState],
) -> dict[int, int] | None:
    if len(raw_values) != len(states):
        return None
    mapping: dict[int, int] = {}
    for raw, state in zip(raw_values, states):
        previous = mapping.get(int(raw))
        dpi = int(state.configured_dpi)
        if previous is not None and previous != dpi:
            return None
        mapping[int(raw)] = dpi
    return mapping if len(mapping) >= 2 else None


def _compressed(values: Sequence[Any]) -> tuple[Any, ...]:
    result: list[Any] = []
    for value in values:
        if not result or result[-1] != value:
            result.append(value)
    return tuple(result)


def _press_release(sequence: Sequence[Any]) -> tuple[Any, Any] | None:
    """Conservatively infer one momentary active state returning to baseline."""

    values = _compressed(sequence)
    if len(values) < 2:
        return None
    release = values[-1]
    active = tuple(dict.fromkeys(value for value in values[:-1] if value != release))
    if len(active) != 1:
        return None
    return active[0], release


def _hid_values(action, report_key: object, offset: int) -> tuple[int, ...]:
    values: list[int] = []
    for report in action.hid_reports:
        data = bytes(report.data)
        if _report_shape(report.source, data) != report_key or offset >= len(data):
            continue
        values.append(int(data[offset]))
    return _compressed(values)


def _hid_packets(action, report_key: object) -> tuple[bytes, ...]:
    packets = [
        bytes(report.data)
        for report in action.hid_reports
        if _report_shape(report.source, bytes(report.data)) == report_key
    ]
    return _compressed(packets)


def _evdev_sequences(
    samples: Sequence[LearningSample],
) -> tuple[dict[tuple[str, int, int], tuple[int, ...]], ...]:
    result: list[dict[tuple[str, int, int], tuple[int, ...]]] = []
    for sample in samples:
        grouped: dict[tuple[str, int, int], list[int]] = defaultdict(list)
        for event in sample.action.evdev_events:
            grouped[(str(event.source), int(event.event_type), int(event.code))].append(
                int(event.value)
            )
        result.append({key: _compressed(values) for key, values in grouped.items()})
    return tuple(result)


def _control_evdev_locations(
    samples: Sequence[LearningSample],
) -> frozenset[tuple[str, int, int]]:
    return frozenset(
        (str(event.source), int(event.event_type), int(event.code))
        for sample in samples
        for event in sample.action.evdev_events
    )


def _source_fingerprint(source: CalibratedTransitionSource) -> tuple[object, ...]:
    return (
        source.kind,
        repr(source.report_key),
        source.offset,
        tuple(sorted((int(k), int(v)) for k, v in source.raw_to_dpi.items())),
        tuple(sorted((str(k), repr(v)) for k, v in source.interface.items())),
        source.event_type,
        source.code,
        source.press_value,
        source.release_value,
        source.press_pattern,
        source.release_pattern,
        source.cycle_order,
    )


def _priority(source: CalibratedTransitionSource) -> int:
    # Absolute state is preferable because it can resynchronize after restart or
    # reconnect. Within trigger sources, a complete repeated packet is more
    # specific than a single field, and hidraw avoids competing with EVIOCGRAB.
    if source.kind == "hid_state":
        return 0
    if source.kind == "feature_state":
        return 1
    if source.kind == "evdev_absolute_stage":
        return 2
    if source.kind == "hid_cycle_trigger" and source.press_pattern is not None:
        return 10
    if source.kind == "hid_cycle_trigger":
        return 11
    if source.kind == "evdev_cycle_trigger":
        return 20
    return 100


def select_preferred_transition_source(
    candidates: Sequence[CalibratedTransitionSource],
) -> tuple[CalibratedTransitionSource, ...]:
    """Choose only an unambiguous source at the strongest available level."""

    deduplicated: dict[tuple[object, ...], CalibratedTransitionSource] = {}
    for source in candidates:
        if source.kind not in SUPPORTED_SOURCE_KINDS:
            continue
        deduplicated.setdefault(_source_fingerprint(source), source)
    ordered = tuple(deduplicated.values())
    for rank in sorted({_priority(source) for source in ordered}):
        group = tuple(source for source in ordered if _priority(source) == rank)
        if len(group) == 1:
            return group
        # Multiple equally strong independent locations are not guessed between.
        # Continue to a weaker but unique channel if one exists.
    return ()


def infer_calibrated_transition_sources(
    transition_samples: Sequence[LearningSample],
    resulting_states: Sequence[CalibratedDpiState],
    *,
    cycle_order: Sequence[int],
    raw_mappings: Sequence[CalibratedRawMapping] = (),
    contrastive_candidates: Sequence[Any] = (),
    guided_report_shapes: Sequence[Any] = (),
    control_samples: Sequence[LearningSample] = (),
    evdev_source_identities: Mapping[str, Mapping[str, object]] | None = None,
    feature_report_metadata: Mapping[object, Mapping[str, object]] | None = None,
) -> tuple[CalibratedTransitionSource, ...]:
    """Infer the best runtime representation of a physically proven DPI cycle.

    Persistent HID/Feature or evdev values are absolute sources. Momentary
    hidraw/evdev button evidence is an ordered transition source. Only one
    unambiguous preferred source is returned; no source grants write authority.
    """

    if len(transition_samples) != len(resulting_states):
        raise ValueError("transition samples and resulting states must have the same length")
    order = tuple(int(value) for value in cycle_order)
    if len(order) < 2:
        return ()

    evdev_identities = evdev_source_identities or {}
    feature_metadata = feature_report_metadata or {}
    candidates: list[CalibratedTransitionSource] = []

    for mapping in raw_mappings:
        candidates.append(
            CalibratedTransitionSource(
                kind="hid_state",
                cycle_order=order,
                observations=int(mapping.observations),
                report_key=mapping.report_key,
                offset=int(mapping.offset),
                raw_to_dpi=dict(mapping.configured_mapping),
            )
        )

    actions = tuple(sample.action for sample in transition_samples)

    for candidate in detect_repeated_changes(actions):
        if candidate.observations != len(resulting_states):
            continue
        after_values = tuple(after for _before, after in candidate.transitions)
        if any(value is None for value in after_values):
            continue
        mapping = _configured_mapping(
            tuple(int(value) for value in after_values if value is not None),
            resulting_states,
        )
        metadata = feature_metadata.get(candidate.report_key)
        if mapping is None or metadata is None:
            continue
        candidates.append(
            CalibratedTransitionSource(
                kind="feature_state",
                cycle_order=order,
                observations=int(candidate.observations),
                report_key=candidate.report_key,
                offset=int(candidate.offset),
                raw_to_dpi=mapping,
                interface=dict(metadata),
            )
        )

    evdev_sequences = _evdev_sequences(transition_samples)
    control_locations = _control_evdev_locations(control_samples)
    if evdev_sequences:
        common = set(evdev_sequences[0])
        for sample in evdev_sequences[1:]:
            common.intersection_update(sample)
        for source, event_type, code in sorted(common):
            location = (source, event_type, code)
            if location in control_locations or event_type in {0, 2}:
                continue
            identity = evdev_identities.get(source)
            if identity is None:
                continue
            raw_values = tuple(int(sample[location][-1]) for sample in evdev_sequences)
            mapping = _configured_mapping(raw_values, resulting_states)
            if mapping is None:
                continue
            candidates.append(
                CalibratedTransitionSource(
                    kind="evdev_absolute_stage",
                    cycle_order=order,
                    observations=len(transition_samples),
                    raw_to_dpi=mapping,
                    interface=dict(identity),
                    event_type=event_type,
                    code=code,
                )
            )

    for shape in guided_report_shapes:
        report_key = getattr(shape, "report_key", None)
        if report_key is None:
            continue
        sequences = tuple(_hid_packets(sample.action, report_key) for sample in transition_samples)
        if any(not sequence for sequence in sequences):
            continue
        motifs = tuple(_press_release(sequence) for sequence in sequences)
        if any(motif is None for motif in motifs) or len(set(motifs)) != 1:
            continue
        press, release = motifs[0]
        if not isinstance(press, bytes) or not isinstance(release, bytes):
            continue
        candidates.append(
            CalibratedTransitionSource(
                kind="hid_cycle_trigger",
                cycle_order=order,
                observations=len(transition_samples),
                report_key=report_key,
                press_pattern=press,
                release_pattern=release,
            )
        )

    for refined in contrastive_candidates:
        candidate = getattr(refined, "candidate", refined)
        report_key = getattr(candidate, "report_key", None)
        offset = getattr(candidate, "offset", None)
        if report_key is None or not isinstance(offset, int):
            continue
        sequences = tuple(
            _hid_values(sample.action, report_key, offset)
            for sample in transition_samples
        )
        if any(not sequence for sequence in sequences):
            continue
        motifs = tuple(_press_release(sequence) for sequence in sequences)
        if any(motif is None for motif in motifs) or len(set(motifs)) != 1:
            continue
        press, release = motifs[0]
        candidates.append(
            CalibratedTransitionSource(
                kind="hid_cycle_trigger",
                cycle_order=order,
                observations=len(transition_samples),
                report_key=report_key,
                offset=offset,
                press_value=int(press),
                release_value=int(release),
            )
        )

    if evdev_sequences:
        common = set(evdev_sequences[0])
        for sample in evdev_sequences[1:]:
            common.intersection_update(sample)
        for source, event_type, code in sorted(common):
            location = (source, event_type, code)
            if location in control_locations or event_type != 1:
                continue
            identity = evdev_identities.get(source)
            if identity is None:
                continue
            motifs = tuple(_press_release(sample[location]) for sample in evdev_sequences)
            if any(motif is None for motif in motifs) or len(set(motifs)) != 1:
                continue
            press, release = motifs[0]
            candidates.append(
                CalibratedTransitionSource(
                    kind="evdev_cycle_trigger",
                    cycle_order=order,
                    observations=len(transition_samples),
                    interface=dict(identity),
                    event_type=event_type,
                    code=code,
                    press_value=int(press),
                    release_value=int(release),
                )
            )

    return select_preferred_transition_source(candidates)
