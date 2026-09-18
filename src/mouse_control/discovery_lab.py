"""Canonical read-only experiments and differential protocol analysis.

The Discovery Lab composes the project's existing observation layers.  It does
not own a HID transport and it never executes protocol writes.  Live TUI runs
use :class:`ReadOnlyLearningSession`; replay and future Lab instruments can
provide the same canonical observations directly.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from enum import Enum
from hashlib import sha256
from statistics import median
from typing import Any, Callable, Iterable, Mapping, Sequence

from .dependency_inference import DependencyInference, infer_dependencies
from .information_gain import ExperimentHypothesis, choose_experiment
from .integrity_inference import IntegrityHypothesis, infer_integrity
from .learning_session import LearningSample, ReadOnlyLearningSession
from .logical_record import LogicalRecord
from .proof_state import ProofState
from .semantic_inference import SemanticHypothesis
from .temporal_dialogue import (
    BurstDialogueResult,
    DialogueKind,
    DialogueRecord,
    PushedStateRecord,
    StateEvidence,
    StateFreshness,
)
from .trace.models import UsbObservation


class LabInterval(str, Enum):
    BASELINE = "baseline"
    ACTION = "action"
    POST_ACTION = "post_action"
    NEGATIVE_CONTROL = "negative_control"


class TimingRelationship(str, Enum):
    REQUEST_RESPONSE_LATENCY = "request_response_latency"
    REQUEST_ACK_LATENCY = "request_ack_latency"
    BUSY_POLL_INTERVAL = "busy_poll_interval"
    BUSY_TO_READY_LATENCY = "busy_to_ready_latency"
    BURST_TRIGGER_TO_FIRST_RESPONSE = "burst_trigger_to_first_response"
    BURST_INTER_RESPONSE_GAP = "burst_inter_response_gap"
    BURST_QUIET_INTERVAL = "burst_quiet_interval"
    BURST_DURATION = "burst_duration"
    NUDGE_TO_PUSH_LATENCY = "nudge_to_push_latency"
    PERIODIC_PUSH_CADENCE = "periodic_push_cadence"
    ACTION_TO_STATE_CHANGE_LATENCY = "action_to_state_change_latency"
    READ_TO_FRESH_STATE_LATENCY = "read_to_fresh_state_latency"
    DISCONNECT_LATENCY = "disconnect_latency"
    RECONNECT_DURATION = "reconnect_duration"
    RECONNECT_TO_FIRST_VALID_STATE = "reconnect_to_first_valid_state"


class TimingClassification(str, Enum):
    IMMEDIATE = "immediate"
    SHORT_DELAY = "short_delay"
    SETTLING_DELAY = "settling_delay"
    PERIODIC = "periodic"
    BUSY_POLL = "busy_poll"
    BURST = "burst"
    RECONNECT_BOUND = "reconnect_bound"
    UNKNOWN = "unknown"


class LifecycleEventKind(str, Enum):
    LAST_VALID_STATE = "last_valid_state"
    DISCONNECT = "disconnect"
    ATTACH = "attach"
    FIRST_VALID_STATE = "first_valid_state"


class FieldSignal(str, Enum):
    CONSTANT = "constant"
    CHANGED = "changed"
    ACTION_CORRELATED = "action_correlated"
    COUNTER_CANDIDATE = "counter_candidate"
    LENGTH_CANDIDATE = "length_candidate"
    STATUS_CANDIDATE = "status_candidate"
    INTEGRITY_CANDIDATE = "integrity_candidate"
    STALE_OR_PADDING = "stale_or_padding"


@dataclass(frozen=True)
class ProtocolObservation:
    """One path-independent protocol frame assigned to a Lab interval."""

    source_id: str
    stream_id: str
    timestamp_ns: int
    sequence: int
    payload: bytes
    interval: LabInterval
    repeat: int = 0
    direction: str = "input"
    report_id: int | None = None
    connection_generation: int = 0

    def __post_init__(self) -> None:
        if not self.source_id or not self.stream_id:
            raise ValueError("observation source and stream identities are required")
        if self.timestamp_ns < 0 or self.sequence < 0 or self.repeat < 0:
            raise ValueError("observation time, sequence, and repeat must be non-negative")
        if self.connection_generation < 0:
            raise ValueError("connection generation must be non-negative")


@dataclass(frozen=True)
class FieldTransition:
    stream_id: str
    offset: int
    before: int | None
    after: int | None
    interval: LabInterval
    repeat: int


@dataclass(frozen=True)
class LabIntervalRecord:
    interval: LabInterval
    repeat: int
    started_ns: int
    ended_ns: int
    observation_count: int
    human_action: str | None = None


@dataclass(frozen=True)
class PhysicalEvidence:
    kind: str
    value: float | int | str
    unit: str | None = None
    confidence: str = "observed"
    evidence_source_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class LabLifecycleEvent:
    kind: LifecycleEventKind
    timestamp_ns: int
    connection_generation: int
    source_observation_id: str
    confidence: str = "observed"

    def __post_init__(self) -> None:
        if self.timestamp_ns < 0 or self.connection_generation < 0:
            raise ValueError("lifecycle timestamps and generations must be non-negative")
        if not self.source_observation_id:
            raise ValueError("lifecycle evidence requires a source observation ID")


@dataclass(frozen=True)
class LabTimingObservation:
    timing_id: str
    experiment_id: str
    physical_device_context: Mapping[str, object]
    connection_generation: int
    source_observation_ids: tuple[str, ...]
    start_timestamp_ns: int
    end_timestamp_ns: int
    duration_ns: int
    relationship: TimingRelationship
    confidence: str
    evidence_state: ProofState = ProofState.OBSERVED
    classification: TimingClassification = TimingClassification.UNKNOWN
    interval: LabInterval | None = None
    repeat: int = 0
    freshness: StateFreshness | None = None
    context: str = ""

    def __post_init__(self) -> None:
        if not self.timing_id or not self.experiment_id:
            raise ValueError("timing and experiment IDs are required")
        if not self.physical_device_context or not self.source_observation_ids:
            raise ValueError("timing evidence requires device context and source observations")
        if self.connection_generation < 0 or self.repeat < 0:
            raise ValueError("timing generation and repeat must be non-negative")
        if self.start_timestamp_ns < 0 or self.end_timestamp_ns < self.start_timestamp_ns:
            raise ValueError("timing timestamps are invalid")
        if self.duration_ns != self.end_timestamp_ns - self.start_timestamp_ns:
            raise ValueError("timing duration must equal end minus start")


@dataclass(frozen=True)
class TimingSummary:
    relationship: TimingRelationship
    context: str
    interval: LabInterval | None
    sample_count: int
    accepted_count: int
    minimum_ns: int | None
    median_ns: int | None
    maximum_ns: int | None
    spread_ns: int | None
    rejected_durations_ns: tuple[int, ...]
    classification: TimingClassification
    confidence: str


@dataclass(frozen=True)
class BusyPollCycle:
    request_source_id: str
    connection_generation: int
    poll_count: int
    poll_intervals_ns: tuple[int, ...]
    busy_duration_ns: int | None
    time_to_ready_ns: int | None
    source_observation_ids: tuple[str, ...]


@dataclass(frozen=True)
class BurstTimingRecord:
    request_source_id: str
    connection_generation: int
    trigger_to_first_response_ns: int | None
    inter_response_gaps_ns: tuple[int, ...]
    quiet_interval_ns: int | None
    overall_duration_ns: int | None
    response_count: int
    completion_reason: str
    source_observation_ids: tuple[str, ...]


@dataclass(frozen=True)
class TimingDelta:
    relationship: TimingRelationship
    context: str
    baseline_median_ns: int
    action_median_ns: int
    ratio: float
    delta_ns: int
    score: float
    reason: str


@dataclass(frozen=True)
class ProtocolTimingProfile:
    observations: tuple[LabTimingObservation, ...]
    summaries: tuple[TimingSummary, ...]
    busy_poll_cycles: tuple[BusyPollCycle, ...]
    burst_timings: tuple[BurstTimingRecord, ...]
    differentials: tuple[TimingDelta, ...]
    contradictions: tuple[str, ...]
    next_recommended_experiment: LabRecommendation | None = None


@dataclass(frozen=True)
class RankedFieldEvidence:
    stream_id: str
    offset: int
    signals: tuple[FieldSignal, ...]
    score: float
    observations: int
    action_repeats: int
    values_by_interval: Mapping[LabInterval, tuple[int, ...]]
    reasons: tuple[str, ...]
    contradictions: tuple[str, ...] = ()


@dataclass(frozen=True)
class TimingEvidence:
    stream_id: str
    median_gap_ns: Mapping[LabInterval, int]
    action_ratio: float | None
    changed: bool


@dataclass(frozen=True)
class EchoEvidence:
    request_source: str
    response_source: str
    exact: bool
    reason: str


@dataclass(frozen=True)
class TransactionDifference:
    kind: str
    request_source: str
    response_source: str
    changed_offsets: tuple[int, ...]
    request_length: int
    response_length: int
    latency_ns: int | None


@dataclass(frozen=True)
class LabRecommendation:
    experiment: str
    information_gain_bits: float
    reason: str
    requires_hardware_write: bool = False


@dataclass(frozen=True)
class LabSemanticHypothesis:
    label: str
    confidence: str
    reason: str
    stream_id: str
    offset: int


@dataclass(frozen=True)
class DifferentialAnalysis:
    ranked_fields: tuple[RankedFieldEvidence, ...]
    timing: tuple[TimingEvidence, ...]
    integrity: Mapping[str, tuple[IntegrityHypothesis, ...]]
    echoes: tuple[EchoEvidence, ...]
    transaction_differences: tuple[TransactionDifference, ...]
    timing_deltas: tuple[TimingDelta, ...]
    dependencies: DependencyInference
    semantic_hypotheses: tuple[SemanticHypothesis | LabSemanticHypothesis, ...]
    contradictions: tuple[str, ...]
    next_recommended_experiment: LabRecommendation | None


@dataclass(frozen=True)
class LabExperiment:
    """Canonical evidence record shared by every Discovery Lab instrument."""

    experiment_id: str
    physical_device_context: Mapping[str, object]
    connection_generation: int
    purpose: str
    human_action: str | None
    intervals: tuple[LabIntervalRecord, ...]
    observations: tuple[ProtocolObservation, ...]
    feature_transitions: tuple[FieldTransition, ...] = ()
    usb_observations: tuple[UsbObservation, ...] = ()
    logical_records: tuple[LogicalRecord, ...] = ()
    dialogues: tuple[DialogueRecord, ...] = ()
    bursts: tuple[BurstDialogueResult, ...] = ()
    pushed_states: tuple[PushedStateRecord, ...] = ()
    state_reads: tuple[StateEvidence, ...] = ()
    lifecycle_events: tuple[LabLifecycleEvent, ...] = ()
    physical_cpi_evidence: tuple[PhysicalEvidence, ...] = ()
    physical_polling_evidence: tuple[PhysicalEvidence, ...] = ()
    provenance: tuple[str, ...] = ()
    proof_state: ProofState = ProofState.OBSERVED
    confidence: str = "observed"
    timing_profile: ProtocolTimingProfile | None = None
    analysis: DifferentialAnalysis | None = None

    def __post_init__(self) -> None:
        if not self.experiment_id or not self.purpose:
            raise ValueError("experiment ID and purpose are required")
        if self.connection_generation < 0:
            raise ValueError("connection generation must be non-negative")
        if not self.physical_device_context:
            raise ValueError("exact physical device context is required")
        if any(item.connection_generation != self.connection_generation for item in self.observations):
            raise ValueError("observations cannot cross connection generations")
        dialogue_generations = {
            item.observation.generation for item in self.dialogues
        } | {
            item.request.generation for item in self.dialogues if item.request is not None
        }
        temporal_generations = dialogue_generations | {
            item.generation for item in self.bursts
        } | {
            item.observation.generation for item in self.pushed_states
        } | {
            item.observation.generation for item in self.state_reads
        }
        if temporal_generations - {self.connection_generation}:
            raise ValueError(
                "protocol relationships cannot cross connection generations; "
                "use explicit lifecycle evidence for reconnect timing"
            )

    @property
    def write_authorized(self) -> bool:
        """Lab observations never grant or inherit hardware write authority."""

        return False

    def replay_fixture(self) -> dict[str, object]:
        """Return a deterministic, local fixture without volatile device paths.

        The fixture intentionally contains protocol frames, not evdev events,
        typed keys, diagnostic live paths, clipboard contents, or screen data.
        """

        context = {
            str(key): value
            for key, value in sorted(self.physical_device_context.items())
            if str(key) not in {"path", "parent_path", "sysfs_path", "diagnostic_source"}
        }
        observations = sorted(
            self.observations,
            key=lambda item: (
                item.interval.value, item.repeat, item.stream_id,
                item.timestamp_ns, item.sequence,
            ),
        )
        redact_id = lambda value: "id:" + sha256(str(value).encode("utf-8", "replace")).hexdigest()[:16]
        timing = self.timing_profile
        return {
            "schema": 1,
            "experiment_id": self.experiment_id,
            "physical_device_context": context,
            "connection_generation": self.connection_generation,
            "purpose": self.purpose,
            "human_action": self.human_action,
            "observations": [
                {
                    "source_id": redact_id(item.source_id),
                    "stream_id": redact_id(item.stream_id),
                    "timestamp_ns": item.timestamp_ns,
                    "sequence": item.sequence,
                    "payload_hex": item.payload.hex(),
                    "interval": item.interval.value,
                    "repeat": item.repeat,
                    "direction": item.direction,
                    "report_id": item.report_id,
                }
                for item in observations
            ],
            "timing_observations": [
                {
                    "timing_id": item.timing_id,
                    "relationship": item.relationship.value,
                    "source_observation_ids": [
                        redact_id(source_id) for source_id in item.source_observation_ids
                    ],
                    "connection_generation": item.connection_generation,
                    "start_timestamp_ns": item.start_timestamp_ns,
                    "end_timestamp_ns": item.end_timestamp_ns,
                    "duration_ns": item.duration_ns,
                    "confidence": item.confidence,
                    "evidence_state": item.evidence_state.value,
                    "classification": item.classification.value,
                    "interval": item.interval.value if item.interval is not None else None,
                    "repeat": item.repeat,
                    "freshness": item.freshness.value if item.freshness is not None else None,
                    "context": item.context,
                }
                for item in (timing.observations if timing is not None else ())
            ],
            "timing_summaries": [
                {
                    "relationship": item.relationship.value,
                    "context": item.context,
                    "interval": item.interval.value if item.interval is not None else None,
                    "sample_count": item.sample_count,
                    "accepted_count": item.accepted_count,
                    "minimum_ns": item.minimum_ns,
                    "median_ns": item.median_ns,
                    "maximum_ns": item.maximum_ns,
                    "spread_ns": item.spread_ns,
                    "rejected_durations_ns": list(item.rejected_durations_ns),
                    "classification": item.classification.value,
                    "confidence": item.confidence,
                }
                for item in (timing.summaries if timing is not None else ())
            ],
        }


def _stable_source(source: object) -> str:
    key = getattr(source, "key", source)
    encoded = repr(key).encode("utf-8", "replace")
    return "stream:" + sha256(encoded).hexdigest()[:16]


def _sample_observations(
    sample: LearningSample,
    interval: LabInterval,
    repeat: int,
    generation: int,
) -> tuple[ProtocolObservation, ...]:
    result: list[ProtocolObservation] = []
    for sequence, report in enumerate(sorted(sample.action.hid_reports, key=lambda item: item.timestamp_ns)):
        source_id = _stable_source(report.source)
        payload = bytes(report.data)
        result.append(ProtocolObservation(
            source_id=source_id,
            stream_id=f"{source_id}:input:{len(payload)}:{payload[0] if payload else 'none'}",
            timestamp_ns=report.timestamp_ns,
            sequence=sequence,
            payload=payload,
            interval=interval,
            repeat=repeat,
            report_id=payload[0] if payload else None,
            connection_generation=generation,
        ))
    return tuple(result)


def _sample_transitions(
    sample: LearningSample,
    interval: LabInterval,
    repeat: int,
) -> tuple[FieldTransition, ...]:
    return tuple(
        FieldTransition(
            _stable_source(change.report_key), change.offset,
            change.before, change.after, interval, repeat,
        )
        for change in sample.action.feature_changes
    )


def _interval_record(
    sample: LearningSample,
    interval: LabInterval,
    repeat: int,
    action: str | None,
) -> LabIntervalRecord:
    return LabIntervalRecord(
        interval, repeat, sample.action.start_ns, sample.action.end_ns,
        len(sample.action.hid_reports), action,
    )


def _field_values(
    observations: Sequence[ProtocolObservation], offset: int,
) -> dict[LabInterval, tuple[int, ...]]:
    return {
        interval: tuple(item.payload[offset] for item in observations if item.interval is interval)
        for interval in LabInterval
    }


def _counter_candidate(values: Sequence[int]) -> bool:
    if len(values) < 3 or len(set(values)) < 3:
        return False
    deltas = tuple((right - left) & 0xFF for left, right in zip(values, values[1:]))
    return bool(deltas) and len(set(deltas)) == 1 and deltas[0] != 0


def _rank_stream_fields(
    stream_id: str,
    observations: Sequence[ProtocolObservation],
    transitions: Sequence[FieldTransition],
) -> tuple[RankedFieldEvidence, ...]:
    width = max((len(item.payload) for item in observations), default=0)
    action_repeats = len({item.repeat for item in observations if item.interval is LabInterval.ACTION})
    result: list[RankedFieldEvidence] = []
    for offset in range(width):
        available = [item for item in observations if offset < len(item.payload)]
        by_interval = _field_values(available, offset)
        all_values = tuple(item.payload[offset] for item in available)
        baseline = set(by_interval[LabInterval.BASELINE])
        action = set(by_interval[LabInterval.ACTION])
        negative = set(by_interval[LabInterval.NEGATIVE_CONTROL])
        signals: list[FieldSignal] = []
        reasons: list[str] = []
        contradictions: list[str] = []
        score = 0.0
        if len(set(all_values)) == 1:
            signals.append(FieldSignal.CONSTANT); score += 1
            reasons.append("one value across every retained interval")
        else:
            signals.append(FieldSignal.CHANGED); score += 10
            reasons.append("byte changed in the experiment")
        action_changed = bool(action and baseline and action != baseline)
        control_separates = not negative or negative == baseline or action.isdisjoint(negative)
        if action_changed and control_separates:
            signals.append(FieldSignal.ACTION_CORRELATED); score += 100 + 5 * action_repeats
            reasons.append("action values differ from baseline and the selected negative control")
        elif action_changed and negative and action & negative:
            contradictions.append("negative control reproduced an action value")
            score -= 25
        ordered = [item.payload[offset] for item in sorted(available, key=lambda item: (item.timestamp_ns, item.sequence))]
        if _counter_candidate(ordered):
            signals.append(FieldSignal.COUNTER_CANDIDATE); score += 45
            reasons.append("a stable non-zero modulo-256 increment spans at least three values")
        if len(available) >= 3 and all(
            item.payload[offset] in {len(item.payload), max(0, len(item.payload) - 1)}
            for item in available
        ):
            signals.append(FieldSignal.LENGTH_CANDIDATE); score += 40
            reasons.append("byte equals the transport length or length excluding report ID")
        if 1 < len(set(all_values)) <= 8 and all(
            len(set(by_interval[interval])) <= 2 for interval in LabInterval
        ):
            signals.append(FieldSignal.STATUS_CANDIDATE); score += 25
            reasons.append("small value domain is stable within experiment intervals")
        if offset >= width - 2 and set(all_values) <= {0x00, 0xFF}:
            signals.append(FieldSignal.STALE_OR_PADDING); score -= 5
            reasons.append("constant conventional fill byte occurs in the trailing region")

        matching_transitions = [
            item for item in transitions if item.stream_id == stream_id and item.offset == offset
        ]
        action_feature = [item for item in matching_transitions if item.interval is LabInterval.ACTION]
        control_feature = [item for item in matching_transitions if item.interval is LabInterval.NEGATIVE_CONTROL]
        if action_feature and not control_feature and FieldSignal.ACTION_CORRELATED not in signals:
            signals.append(FieldSignal.ACTION_CORRELATED); score += 90 + 5 * len(action_feature)
            reasons.append("read-only Feature snapshots changed during action repeats but not control")

        result.append(RankedFieldEvidence(
            stream_id, offset, tuple(signals), score, len(available),
            action_repeats, by_interval, tuple(reasons), tuple(contradictions),
        ))
    return tuple(result)


def _rank_feature_transitions(
    transitions: Sequence[FieldTransition],
) -> tuple[RankedFieldEvidence, ...]:
    """Rank read-only GET_FEATURE before/after differences as first-class fields."""

    grouped: dict[tuple[str, int], list[FieldTransition]] = defaultdict(list)
    for item in transitions:
        grouped[(item.stream_id, item.offset)].append(item)
    result: list[RankedFieldEvidence] = []
    for (stream_id, offset), items in grouped.items():
        by_interval = {
            interval: tuple(
                value
                for item in items if item.interval is interval
                for value in (item.before, item.after)
                if value is not None
            )
            for interval in LabInterval
        }
        action = [item for item in items if item.interval is LabInterval.ACTION]
        negative = [item for item in items if item.interval is LabInterval.NEGATIVE_CONTROL]
        signals = [FieldSignal.CHANGED]
        reasons = ["read-only Feature snapshot changed across an interval"]
        contradictions: list[str] = []
        score = 10.0
        if action and not negative:
            signals.append(FieldSignal.ACTION_CORRELATED)
            score += 100 + 5 * len({item.repeat for item in action})
            reasons.append("Feature field changed during controlled repeats but not the negative control")
        elif action and negative:
            contradictions.append("negative control also changed the Feature field")
            score -= 25
        values = {value for interval_values in by_interval.values() for value in interval_values}
        if 1 < len(values) <= 8:
            signals.append(FieldSignal.STATUS_CANDIDATE)
            score += 25
            reasons.append("Feature field has a small observed value domain")
        result.append(RankedFieldEvidence(
            stream_id=f"feature:{stream_id}", offset=offset,
            signals=tuple(signals), score=score, observations=len(items),
            action_repeats=len({item.repeat for item in action}),
            values_by_interval=by_interval, reasons=tuple(reasons),
            contradictions=tuple(contradictions),
        ))
    return tuple(result)


def _timing_evidence(
    stream_id: str, observations: Sequence[ProtocolObservation],
) -> TimingEvidence:
    gaps: dict[LabInterval, int] = {}
    for interval in LabInterval:
        times = sorted(item.timestamp_ns for item in observations if item.interval is interval)
        values = [right - left for left, right in zip(times, times[1:]) if right > left]
        if values:
            gaps[interval] = int(median(values))
    action = gaps.get(LabInterval.ACTION)
    baseline = gaps.get(LabInterval.BASELINE)
    ratio = None
    changed = False
    if action and baseline:
        ratio = max(action, baseline) / min(action, baseline)
        changed = ratio >= 1.5
    return TimingEvidence(stream_id, gaps, ratio, changed)


def _echoes(dialogues: Sequence[DialogueRecord]) -> tuple[EchoEvidence, ...]:
    result: list[EchoEvidence] = []
    for record in dialogues:
        if record.request is None:
            continue
        exact = record.request.payload == record.observation.payload
        if record.kind is DialogueKind.ECHO or exact:
            result.append(EchoEvidence(
                f"{record.request.source_id}:{record.request.sequence}",
                f"{record.observation.source_id}:{record.observation.sequence}",
                exact,
                record.reason or ("exact request/response payload echo" if exact else "dialogue classified as echo"),
            ))
    return tuple(result)


def _transaction_differences(
    dialogues: Sequence[DialogueRecord],
) -> tuple[TransactionDifference, ...]:
    result: list[TransactionDifference] = []
    for record in dialogues:
        if record.request is None:
            continue
        request = record.request
        response = record.observation
        width = max(len(request.payload), len(response.payload))
        changed = tuple(
            offset for offset in range(width)
            if (request.payload[offset] if offset < len(request.payload) else None)
            != (response.payload[offset] if offset < len(response.payload) else None)
        )
        latency = response.timestamp_ns - request.timestamp_ns
        result.append(TransactionDifference(
            kind=record.kind.value,
            request_source=f"{request.source_id}:{request.sequence}",
            response_source=f"{response.source_id}:{response.sequence}",
            changed_offsets=changed,
            request_length=len(request.payload),
            response_length=len(response.payload),
            latency_ns=latency if latency >= 0 else None,
        ))
    return tuple(result)


def _interval_at(
    intervals: Sequence[LabIntervalRecord], timestamp_ns: int,
) -> tuple[LabInterval, int] | None:
    matches = [
        item for item in intervals
        if item.started_ns <= timestamp_ns <= item.ended_ns
    ]
    if len(matches) != 1:
        return None
    return matches[0].interval, matches[0].repeat


def _project_existing_evidence(experiment: LabExperiment) -> tuple[ProtocolObservation, ...]:
    """Project existing USB/logical evidence into the common differential view."""

    projected: list[ProtocolObservation] = list(experiment.observations)
    for item in experiment.usb_observations:
        located = _interval_at(experiment.intervals, item.timestamp_ns)
        if located is None or not item.payload:
            continue
        interval, repeat = located
        projected.append(ProtocolObservation(
            source_id=item.capture_id,
            stream_id=(
                f"usb:{item.interface_number}:{item.endpoint}:"
                f"{item.direction.value}:{item.transfer_type.value}"
            ),
            timestamp_ns=item.timestamp_ns,
            sequence=item.sequence,
            payload=item.payload,
            interval=interval,
            repeat=repeat,
            direction=item.direction.value,
            report_id=item.payload[0],
            connection_generation=experiment.connection_generation,
        ))
    for index, item in enumerate(experiment.logical_records):
        located = _interval_at(experiment.intervals, item.start_timestamp_ns)
        if located is None or not item.data or item.generation != experiment.connection_generation:
            continue
        interval, repeat = located
        source = item.source_frames[0].source_id if item.source_frames else item.grammar
        projected.append(ProtocolObservation(
            source_id=source,
            stream_id=(
                f"logical:{item.grammar}:{item.channel_id}:"
                f"{item.report_namespace}:{item.report_id}"
            ),
            timestamp_ns=item.start_timestamp_ns,
            sequence=index,
            payload=item.data,
            interval=interval,
            repeat=repeat,
            direction="logical",
            report_id=item.report_id,
            connection_generation=item.generation,
        ))
    return tuple(projected)


def _recommend(
    fields: Sequence[RankedFieldEvidence],
    timing_profile: ProtocolTimingProfile | None = None,
) -> LabRecommendation | None:
    candidates = [item for item in fields if FieldSignal.ACTION_CORRELATED in item.signals][:4]
    field_recommendation: LabRecommendation
    if not candidates:
        field_recommendation = LabRecommendation(
            "repeat-controlled-action", 0.0,
            "No action-specific field survived the negative control; collect another isolated repeat.",
        )
    else:
        hypotheses = []
        for item in candidates:
            name = f"{item.stream_id}:byte-{item.offset}"
            hypotheses.append(ExperimentHypothesis(name, {
                "repeat-controlled-action": ("changes", item.offset),
                "alternate-negative-control": ("unchanged", len(item.contradictions)),
                "idle-persistence-check": ("persists", FieldSignal.STATUS_CANDIDATE in item.signals),
            }))
        choice = choose_experiment(hypotheses)
        field_recommendation = (
            LabRecommendation(
                choice.experiment, choice.information_gain_bits,
                "Chosen deterministically from the remaining field hypotheses by expected information gain.",
            )
            if choice is not None else
            LabRecommendation(
                "alternate-negative-control", 0.0,
                "The leading correlation needs a distinct ordinary-use control before stronger semantics.",
            )
        )
    timing_recommendation = (
        timing_profile.next_recommended_experiment if timing_profile is not None else None
    )
    if timing_recommendation is None:
        return field_recommendation
    return min(
        (field_recommendation, timing_recommendation),
        key=lambda item: (-item.information_gain_bits, item.experiment),
    )


def analyze_differential_experiment(
    experiment: LabExperiment,
    *,
    semantic_values: Sequence[int] = (),
    semantic_hypotheses: Iterable[SemanticHypothesis] = (),
) -> LabExperiment:
    """Analyze one canonical experiment without performing I/O."""

    if experiment.timing_profile is None:
        from .protocol_timing import profile_experiment_timing

        experiment = profile_experiment_timing(experiment)

    canonical_observations = _project_existing_evidence(experiment)
    streams: dict[str, list[ProtocolObservation]] = defaultdict(list)
    for item in canonical_observations:
        streams[item.stream_id].append(item)
    fields = [
        item
        for stream_id, observations in streams.items()
        for item in _rank_stream_fields(
            stream_id, observations, experiment.feature_transitions,
        )
    ]
    fields.extend(_rank_feature_transitions(experiment.feature_transitions))
    integrity: dict[str, tuple[IntegrityHypothesis, ...]] = {}
    for stream_id, observations in streams.items():
        candidates = infer_integrity([item.payload for item in observations])
        integrity[stream_id] = candidates
        for hypothesis in candidates:
            for index, item in enumerate(fields):
                if item.stream_id == stream_id and item.offset == hypothesis.offset:
                    fields[index] = replace(
                        item,
                        signals=item.signals + (FieldSignal.INTEGRITY_CANDIDATE,),
                        score=item.score + 55,
                        reasons=item.reasons + (
                            f"{hypothesis.algorithm} validates every aligned frame",
                        ),
                    )
    fields.sort(key=lambda item: (-item.score, item.stream_id, item.offset))

    dependencies = DependencyInference((), ())
    action_frames = [
        item.payload for item in canonical_observations
        if item.interval is LabInterval.ACTION
    ]
    if semantic_values and len(action_frames) == len(semantic_values):
        dependencies = infer_dependencies(action_frames, semantic_values)
    contradictions = tuple(
        f"{item.stream_id} byte {item.offset}: {message}"
        for item in fields for message in item.contradictions
    ) + tuple(
        f"logical record {item.grammar} is {item.completeness.value} with {item.integrity.value} integrity"
        for item in experiment.logical_records
        if item.completeness.value != "complete" or item.integrity.value == "invalid"
    )
    derived_semantics = tuple(
        LabSemanticHypothesis(
            label=f"correlates-with:{experiment.human_action or 'controlled-action'}",
            confidence="correlated",
            reason=(
                "field changed with repeated labelled actions and was separated "
                "from the selected negative control"
            ),
            stream_id=item.stream_id,
            offset=item.offset,
        )
        for item in fields
        if FieldSignal.ACTION_CORRELATED in item.signals
    )
    analysis = DifferentialAnalysis(
        ranked_fields=tuple(fields),
        timing=tuple(
            _timing_evidence(stream_id, observations)
            for stream_id, observations in sorted(streams.items())
        ),
        integrity=integrity,
        echoes=_echoes(experiment.dialogues),
        transaction_differences=_transaction_differences(experiment.dialogues),
        timing_deltas=(
            experiment.timing_profile.differentials
            if experiment.timing_profile is not None else ()
        ),
        dependencies=dependencies,
        semantic_hypotheses=(*tuple(semantic_hypotheses), *derived_semantics),
        contradictions=contradictions,
        next_recommended_experiment=_recommend(fields, experiment.timing_profile),
    )
    state = ProofState.HYPOTHESIZED if any(
        FieldSignal.ACTION_CORRELATED in item.signals for item in fields
    ) else ProofState.OBSERVED
    return replace(
        experiment,
        proof_state=state,
        confidence="correlated" if state is ProofState.HYPOTHESIZED else "observed",
        analysis=analysis,
    )


@dataclass(frozen=True)
class LabStep:
    current: int
    total: int
    title: str
    instruction: str

    @property
    def index(self) -> int:
        """Compatibility with the existing guided-step TUI presenter."""

        return self.current

    @property
    def instructions(self) -> str:
        return self.instruction


class DiscoveryLabCancelled(RuntimeError):
    pass


def run_read_only_differential_lab(
    physical: Any,
    descriptors: Mapping[Any, Any],
    *,
    prompt: Callable[[LabStep], bool],
    progress: Callable[[str], None] | None = None,
    connection_generation: int = 0,
    action_label: str = "press one physical DPI/profile/button control",
    repeat_count: int = 3,
    seconds: float = 1.5,
    session_factory: Callable[..., ReadOnlyLearningSession] = ReadOnlyLearningSession,
) -> LabExperiment:
    """Run the first Lab instrument using only selected-device read operations."""

    if repeat_count < 2 or seconds <= 0:
        raise ValueError("the Lab requires at least two positive repeats and a positive window")
    if getattr(physical, "ambiguous", False):
        raise PermissionError("physical identity is ambiguous; the Lab refuses capture")
    report = progress or (lambda _message: None)
    session = session_factory(physical, descriptors)
    samples: list[tuple[LabInterval, int, LearningSample, str | None]] = []
    total = repeat_count + 3
    plan = [
        (LabInterval.BASELINE, 0, "Baseline", "Leave the selected mouse completely untouched.", None),
        *[
            (LabInterval.ACTION, repeat_index, "Controlled action", f"Keep the mouse still and {action_label} exactly once.", action_label)
            for repeat_index in range(1, repeat_count + 1)
        ],
        (LabInterval.POST_ACTION, 0, "Post-action", "Leave the selected mouse untouched after the action.", None),
        (
            LabInterval.NEGATIVE_CONTROL, 0, "Negative control",
            "Move the selected mouse normally and left-click once; do not use the labelled control.",
            "ordinary motion and one left click",
        ),
    ]
    for current, (interval, repeat, title, instruction, human_action) in enumerate(plan, 1):
        if not prompt(LabStep(current, total, title, instruction)):
            raise DiscoveryLabCancelled("Discovery Lab cancelled")
        report(f"Capturing {interval.value.replace('_', ' ')} interval {current}/{total}…")
        sample = session.observe_action(seconds=seconds)
        samples.append((interval, repeat, sample, human_action))

    observations = tuple(
        observation
        for interval, repeat, sample, _action in samples
        for observation in _sample_observations(sample, interval, repeat, connection_generation)
    )
    transitions = tuple(
        transition
        for interval, repeat, sample, _action in samples
        for transition in _sample_transitions(sample, interval, repeat)
    )
    intervals = tuple(
        _interval_record(sample, interval, repeat, action)
        for interval, repeat, sample, action in samples
    )
    context = {
        "bus": physical.bus,
        "vendor_id": physical.vendor_id,
        "product_id": physical.product_id,
        "model_fingerprint": physical.model_fingerprint,
        "instance_fingerprint": physical.instance_fingerprint,
    }
    identity_material = repr((sorted(context.items()), connection_generation, intervals[0].started_ns)).encode()
    experiment = LabExperiment(
        experiment_id="lab-" + sha256(identity_material).hexdigest()[:20],
        physical_device_context=context,
        connection_generation=connection_generation,
        purpose="Differential Protocol Analyzer controlled-action experiment",
        human_action=action_label,
        intervals=intervals,
        observations=observations,
        feature_transitions=transitions,
        provenance=tuple(
            f"{item.source_id}:{item.sequence}" for item in observations
        ),
    )
    report("Analyzing fields, timing, controls, dependencies, and integrity…")
    return analyze_differential_experiment(experiment)
