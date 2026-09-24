# SPDX-License-Identifier: AGPL-3.0-or-later
"""Replay-driven protocol timing extraction for canonical Lab experiments.

The profiler consumes relationships already established by temporal dialogue,
burst, pushed-state, and lifecycle evidence.  It never sleeps, captures, polls,
or writes hardware, and raw durations remain authoritative when a distribution
is too small to classify.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from hashlib import sha256
from math import log2
from statistics import median
from typing import Sequence

from .discovery_lab import (
    BurstTimingRecord,
    BusyPollCycle,
    LabExperiment,
    LabInterval,
    LabLifecycleEvent,
    LabRecommendation,
    LabTimingObservation,
    LifecycleEventKind,
    ProtocolTimingProfile,
    TimingClassification,
    TimingDelta,
    TimingRelationship,
    TimingSummary,
)
from .information_gain import ExperimentHypothesis, choose_experiment
from .proof_state import ProofState
from .temporal_dialogue import (
    BurstCompletionReason,
    DialogueKind,
    DialogueObservation,
    DialogueRecord,
    PushedStateAssociation,
    PushedStateRecord,
    StateFreshness,
)


def _observation_id(item: DialogueObservation) -> str:
    return f"{item.source_id}:{item.generation}:{item.sequence}"


def _interval_at(experiment: LabExperiment, timestamp_ns: int) -> tuple[LabInterval | None, int]:
    matches = [
        item for item in experiment.intervals
        if item.started_ns <= timestamp_ns <= item.ended_ns
    ]
    if len(matches) != 1:
        return None, 0
    return matches[0].interval, matches[0].repeat


def _timing_id(
    experiment_id: str,
    relationship: TimingRelationship,
    source_ids: Sequence[str],
    start_ns: int,
    end_ns: int,
) -> str:
    material = repr((experiment_id, relationship.value, tuple(source_ids), start_ns, end_ns)).encode()
    return "timing-" + sha256(material).hexdigest()[:20]


def _timing(
    experiment: LabExperiment,
    relationship: TimingRelationship,
    *,
    source_ids: Sequence[str],
    start_ns: int,
    end_ns: int,
    generation: int,
    confidence: str,
    classification: TimingClassification = TimingClassification.UNKNOWN,
    freshness: StateFreshness | None = None,
    context: str = "",
) -> LabTimingObservation | None:
    if end_ns < start_ns or generation < 0:
        return None
    interval, repeat = _interval_at(experiment, start_ns)
    retained_ids = tuple(source_ids)
    return LabTimingObservation(
        timing_id=_timing_id(
            experiment.experiment_id, relationship, retained_ids, start_ns, end_ns,
        ),
        experiment_id=experiment.experiment_id,
        physical_device_context=experiment.physical_device_context,
        connection_generation=generation,
        source_observation_ids=retained_ids,
        start_timestamp_ns=start_ns,
        end_timestamp_ns=end_ns,
        duration_ns=end_ns - start_ns,
        relationship=relationship,
        confidence=confidence,
        evidence_state=ProofState.RECOGNIZED,
        classification=classification,
        interval=interval,
        repeat=repeat,
        freshness=freshness,
        context=context,
    )


def _request_key(record: DialogueRecord) -> tuple[object, ...] | None:
    request = record.request
    if request is None:
        return None
    return request.source_id, request.physical_id, request.generation, request.sequence


def _dialogue_timings(
    experiment: LabExperiment,
) -> tuple[list[LabTimingObservation], list[BusyPollCycle]]:
    timings: list[LabTimingObservation] = []
    grouped: dict[tuple[object, ...], list[DialogueRecord]] = defaultdict(list)
    for record in experiment.dialogues:
        key = _request_key(record)
        if key is not None:
            grouped[key].append(record)
        request = record.request
        if request is None or request.generation != record.observation.generation:
            continue
        relationship = None
        if record.kind is DialogueKind.RESPONSE:
            relationship = TimingRelationship.REQUEST_RESPONSE_LATENCY
        elif record.kind is DialogueKind.WRITE_ACKNOWLEDGEMENT:
            relationship = TimingRelationship.REQUEST_ACK_LATENCY
        if relationship is not None:
            item = _timing(
                experiment,
                relationship,
                source_ids=(_observation_id(request), _observation_id(record.observation)),
                start_ns=request.timestamp_ns,
                end_ns=record.observation.timestamp_ns,
                generation=request.generation,
                confidence=record.confidence,
                context=request.grammar or request.report_namespace,
            )
            if item is not None:
                timings.append(item)

    cycles: list[BusyPollCycle] = []
    for records in grouped.values():
        ordered = sorted(records, key=lambda item: item.observation.timestamp_ns)
        request = ordered[0].request
        assert request is not None
        busy = [item for item in ordered if item.kind is DialogueKind.BUSY_PENDING]
        polls = [item for item in ordered if item.kind is DialogueKind.RESPONSE_POLL]
        ready = [
            item for item in ordered
            if item.kind in {DialogueKind.RESPONSE, DialogueKind.WRITE_ACKNOWLEDGEMENT}
        ]
        if not busy:
            continue
        poll_intervals: list[int] = []
        for left, right in zip(polls, polls[1:]):
            item = _timing(
                experiment,
                TimingRelationship.BUSY_POLL_INTERVAL,
                source_ids=(
                    _observation_id(left.observation), _observation_id(right.observation),
                ),
                start_ns=left.observation.timestamp_ns,
                end_ns=right.observation.timestamp_ns,
                generation=request.generation,
                confidence="structural",
                classification=TimingClassification.BUSY_POLL,
                context=request.grammar or request.report_namespace,
            )
            if item is not None:
                timings.append(item)
                poll_intervals.append(item.duration_ns)
        final = ready[-1].observation if ready else None
        busy_duration = None
        time_to_ready = None
        if final is not None:
            busy_duration = final.timestamp_ns - busy[0].observation.timestamp_ns
            time_to_ready = final.timestamp_ns - request.timestamp_ns
            item = _timing(
                experiment,
                TimingRelationship.BUSY_TO_READY_LATENCY,
                source_ids=(
                    _observation_id(busy[0].observation), _observation_id(final),
                ),
                start_ns=busy[0].observation.timestamp_ns,
                end_ns=final.timestamp_ns,
                generation=request.generation,
                confidence="structural",
                classification=TimingClassification.BUSY_POLL,
                context=request.grammar or request.report_namespace,
            )
            if item is not None:
                timings.append(item)
        source_ids = tuple(
            _observation_id(item.observation)
            for item in (*busy, *polls, *ready)
        )
        cycles.append(BusyPollCycle(
            request_source_id=_observation_id(request),
            connection_generation=request.generation,
            poll_count=len(polls),
            poll_intervals_ns=tuple(poll_intervals),
            busy_duration_ns=busy_duration,
            time_to_ready_ns=time_to_ready,
            source_observation_ids=source_ids,
        ))
    return timings, cycles


def _burst_timings(
    experiment: LabExperiment,
) -> tuple[list[LabTimingObservation], list[BurstTimingRecord]]:
    result: list[LabTimingObservation] = []
    retained: list[BurstTimingRecord] = []
    for burst in experiment.bursts:
        request = burst.request
        context = burst.grammar or request.report_namespace
        if burst.responses:
            first = burst.responses[0]
            item = _timing(
                experiment,
                TimingRelationship.BURST_TRIGGER_TO_FIRST_RESPONSE,
                source_ids=(_observation_id(request), _observation_id(first)),
                start_ns=request.timestamp_ns,
                end_ns=first.timestamp_ns,
                generation=burst.generation,
                confidence=burst.confidence,
                classification=TimingClassification.BURST,
                context=context,
            )
            if item is not None:
                result.append(item)
        for left, right in zip(burst.responses, burst.responses[1:]):
            item = _timing(
                experiment,
                TimingRelationship.BURST_INTER_RESPONSE_GAP,
                source_ids=(_observation_id(left), _observation_id(right)),
                start_ns=left.timestamp_ns,
                end_ns=right.timestamp_ns,
                generation=burst.generation,
                confidence=burst.confidence,
                classification=TimingClassification.BURST,
                context=context,
            )
            if item is not None:
                result.append(item)
        if (
            burst.completion_reason is BurstCompletionReason.QUIET_INTERVAL
            and burst.last_response_timestamp_ns is not None
            and burst.completion_timestamp_ns is not None
        ):
            item = _timing(
                experiment,
                TimingRelationship.BURST_QUIET_INTERVAL,
                source_ids=(
                    _observation_id(burst.responses[-1]),
                    f"burst-complete:{request.sequence}",
                ),
                start_ns=burst.last_response_timestamp_ns,
                end_ns=burst.completion_timestamp_ns,
                generation=burst.generation,
                confidence="bounded-replay-time",
                classification=TimingClassification.BURST,
                context=context,
            )
            if item is not None:
                result.append(item)
        end_ns = burst.completion_timestamp_ns or burst.last_response_timestamp_ns
        if end_ns is not None:
            item = _timing(
                experiment,
                TimingRelationship.BURST_DURATION,
                source_ids=(
                    _observation_id(request), f"burst-complete:{request.sequence}",
                ),
                start_ns=request.timestamp_ns,
                end_ns=end_ns,
                generation=burst.generation,
                confidence=burst.confidence,
                classification=TimingClassification.BURST,
                context=f"{context}:{burst.completion_reason.value}:{burst.response_count}",
            )
            if item is not None:
                result.append(item)
        retained.append(BurstTimingRecord(
            request_source_id=_observation_id(request),
            connection_generation=burst.generation,
            trigger_to_first_response_ns=(
                burst.responses[0].timestamp_ns - request.timestamp_ns
                if burst.responses else None
            ),
            inter_response_gaps_ns=tuple(
                right.timestamp_ns - left.timestamp_ns
                for left, right in zip(burst.responses, burst.responses[1:])
            ),
            quiet_interval_ns=(
                burst.completion_timestamp_ns - burst.last_response_timestamp_ns
                if burst.completion_timestamp_ns is not None
                and burst.last_response_timestamp_ns is not None
                and burst.completion_reason is BurstCompletionReason.QUIET_INTERVAL
                else None
            ),
            overall_duration_ns=(
                end_ns - request.timestamp_ns if end_ns is not None else None
            ),
            response_count=burst.response_count,
            completion_reason=burst.completion_reason.value,
            source_observation_ids=(
                _observation_id(request),
                *tuple(_observation_id(item) for item in burst.responses),
            ),
        ))
    return result, retained


def _pushed_state_timings(experiment: LabExperiment) -> list[LabTimingObservation]:
    result: list[LabTimingObservation] = []
    streams: dict[tuple[object, ...], list[PushedStateRecord]] = defaultdict(list)
    for record in experiment.pushed_states:
        observation = record.observation
        if not record.accepted:
            continue
        key = (
            observation.physical_id, observation.generation,
            record.semantic_state_id, observation.channel_id,
        )
        streams[key].append(record)
        context = record.semantic_state_id
        if record.association is PushedStateAssociation.NUDGED and record.nudge is not None:
            item = _timing(
                experiment,
                TimingRelationship.NUDGE_TO_PUSH_LATENCY,
                source_ids=(
                    _observation_id(record.nudge), _observation_id(observation),
                ),
                start_ns=record.nudge.timestamp_ns,
                end_ns=observation.timestamp_ns,
                generation=observation.generation,
                confidence="correlated-nudge-association",
                freshness=record.freshness,
                context=context,
            )
            if item is not None:
                result.append(item)
        if record.controlled_action is not None:
            item = _timing(
                experiment,
                TimingRelationship.ACTION_TO_STATE_CHANGE_LATENCY,
                source_ids=(
                    _observation_id(record.controlled_action), _observation_id(observation),
                ),
                start_ns=record.controlled_action.timestamp_ns,
                end_ns=observation.timestamp_ns,
                generation=observation.generation,
                confidence="controlled-action-correlation",
                freshness=record.freshness,
                context=context,
            )
            if item is not None:
                result.append(item)
    for records in streams.values():
        ordered = sorted(records, key=lambda item: item.observation.timestamp_ns)
        for left, right in zip(ordered, ordered[1:]):
            if right.periodic_index != left.periodic_index + 1:
                continue
            item = _timing(
                experiment,
                TimingRelationship.PERIODIC_PUSH_CADENCE,
                source_ids=(
                    _observation_id(left.observation), _observation_id(right.observation),
                ),
                start_ns=left.observation.timestamp_ns,
                end_ns=right.observation.timestamp_ns,
                generation=right.observation.generation,
                confidence="observed-periodic-sequence",
                classification=TimingClassification.PERIODIC,
                freshness=right.freshness,
                context=right.semantic_state_id,
            )
            if item is not None:
                result.append(item)
    return result


def _stale_state_timings(experiment: LabExperiment) -> list[LabTimingObservation]:
    result: list[LabTimingObservation] = []
    pushes = sorted(
        (item for item in experiment.pushed_states if item.accepted),
        key=lambda item: item.observation.timestamp_ns,
    )
    for read in experiment.state_reads:
        if read.freshness is StateFreshness.FRESH:
            continue
        read_observation = read.observation
        candidates = [
            item for item in pushes
            if item.semantic_state_id == read.semantic_state_id
            and item.observation.physical_id == read_observation.physical_id
            and item.observation.generation == read_observation.generation
            and item.observation.timestamp_ns >= read_observation.timestamp_ns
            and item.decoded_state != read.decoded_state
            and item.freshness is StateFreshness.FRESH
        ]
        if not candidates:
            continue
        pushed = candidates[0]
        item = _timing(
            experiment,
            TimingRelationship.READ_TO_FRESH_STATE_LATENCY,
            source_ids=(
                _observation_id(read_observation), _observation_id(pushed.observation),
            ),
            start_ns=read_observation.timestamp_ns,
            end_ns=pushed.observation.timestamp_ns,
            generation=read_observation.generation,
            confidence="later-fresh-push-supersedes-read",
            classification=TimingClassification.SETTLING_DELAY,
            freshness=(
                StateFreshness.STALE
                if read.freshness in {StateFreshness.STALE, StateFreshness.UNKNOWN}
                else read.freshness
            ),
            context=read.semantic_state_id,
        )
        if item is not None:
            result.append(item)
    return result


def _lifecycle_timings(experiment: LabExperiment) -> list[LabTimingObservation]:
    result: list[LabTimingObservation] = []
    events = sorted(experiment.lifecycle_events, key=lambda item: item.timestamp_ns)
    disconnects = [item for item in events if item.kind is LifecycleEventKind.DISCONNECT]
    for disconnect in disconnects:
        commits = [
            item.observation for item in experiment.dialogues
            if item.kind is DialogueKind.COMMIT_APPLY
            and item.observation.generation == disconnect.connection_generation
            and item.observation.timestamp_ns <= disconnect.timestamp_ns
        ]
        if commits:
            commit = max(commits, key=lambda item: item.timestamp_ns)
            item = _timing(
                experiment,
                TimingRelationship.DISCONNECT_LATENCY,
                source_ids=(
                    _observation_id(commit), disconnect.source_observation_id,
                ),
                start_ns=commit.timestamp_ns,
                end_ns=disconnect.timestamp_ns,
                generation=disconnect.connection_generation,
                confidence="commit-precedes-explicit-disconnect",
                classification=TimingClassification.RECONNECT_BOUND,
                context="commit-to-disconnect",
            )
            if item is not None:
                result.append(item)
        previous = [
            item for item in events
            if item.kind is LifecycleEventKind.LAST_VALID_STATE
            and item.connection_generation == disconnect.connection_generation
            and item.timestamp_ns <= disconnect.timestamp_ns
        ]
        if previous:
            last = previous[-1]
            item = _lifecycle_timing(
                experiment, TimingRelationship.DISCONNECT_LATENCY,
                last, disconnect, disconnect.connection_generation,
            )
            if item is not None:
                result.append(item)
        attachments = [
            item for item in events
            if item.kind is LifecycleEventKind.ATTACH
            and item.connection_generation > disconnect.connection_generation
            and item.timestamp_ns >= disconnect.timestamp_ns
        ]
        if not attachments:
            continue
        attachment = attachments[0]
        item = _lifecycle_timing(
            experiment, TimingRelationship.RECONNECT_DURATION,
            disconnect, attachment, attachment.connection_generation,
        )
        if item is not None:
            result.append(item)
        first_valid = [
            event for event in events
            if event.kind is LifecycleEventKind.FIRST_VALID_STATE
            and event.connection_generation == attachment.connection_generation
            and event.timestamp_ns >= attachment.timestamp_ns
        ]
        if first_valid:
            item = _lifecycle_timing(
                experiment, TimingRelationship.RECONNECT_TO_FIRST_VALID_STATE,
                attachment, first_valid[0], attachment.connection_generation,
            )
            if item is not None:
                result.append(item)
    return result


def _lifecycle_timing(
    experiment: LabExperiment,
    relationship: TimingRelationship,
    start: LabLifecycleEvent,
    end: LabLifecycleEvent,
    generation: int,
) -> LabTimingObservation | None:
    return _timing(
        experiment,
        relationship,
        source_ids=(start.source_observation_id, end.source_observation_id),
        start_ns=start.timestamp_ns,
        end_ns=end.timestamp_ns,
        generation=generation,
        confidence="explicit-lifecycle-evidence",
        classification=TimingClassification.RECONNECT_BOUND,
        context=f"generation:{start.connection_generation}->{end.connection_generation}",
    )


def _reject_outliers(values: Sequence[int]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    retained = tuple(sorted(int(value) for value in values))
    if len(retained) < 4:
        return retained, ()
    centre = median(retained)
    deviations = tuple(abs(value - centre) for value in retained)
    mad = median(deviations)
    if mad == 0:
        accepted = tuple(value for value in retained if value == centre)
        rejected = tuple(value for value in retained if value != centre)
        return (accepted or retained), rejected
    limit = 3 * mad
    accepted = tuple(value for value in retained if abs(value - centre) <= limit)
    rejected = tuple(value for value in retained if abs(value - centre) > limit)
    return (accepted or retained), rejected


def _explicit_classification(relationship: TimingRelationship) -> TimingClassification:
    if relationship in {
        TimingRelationship.BUSY_POLL_INTERVAL,
        TimingRelationship.BUSY_TO_READY_LATENCY,
    }:
        return TimingClassification.BUSY_POLL
    if relationship in {
        TimingRelationship.BURST_TRIGGER_TO_FIRST_RESPONSE,
        TimingRelationship.BURST_INTER_RESPONSE_GAP,
        TimingRelationship.BURST_QUIET_INTERVAL,
        TimingRelationship.BURST_DURATION,
    }:
        return TimingClassification.BURST
    if relationship is TimingRelationship.PERIODIC_PUSH_CADENCE:
        return TimingClassification.PERIODIC
    if relationship is TimingRelationship.READ_TO_FRESH_STATE_LATENCY:
        return TimingClassification.SETTLING_DELAY
    if relationship in {
        TimingRelationship.DISCONNECT_LATENCY,
        TimingRelationship.RECONNECT_DURATION,
        TimingRelationship.RECONNECT_TO_FIRST_VALID_STATE,
    }:
        return TimingClassification.RECONNECT_BOUND
    return TimingClassification.UNKNOWN


def _summaries(
    observations: Sequence[LabTimingObservation],
) -> tuple[TimingSummary, ...]:
    groups: dict[tuple[object, ...], list[LabTimingObservation]] = defaultdict(list)
    for item in observations:
        groups[(item.relationship, item.context, item.interval)].append(item)
    result: list[TimingSummary] = []
    for (relationship, context, interval), items in groups.items():
        accepted, rejected = _reject_outliers([item.duration_ns for item in items])
        enough = len(accepted) >= 2
        result.append(TimingSummary(
            relationship=relationship,
            context=str(context),
            interval=interval,
            sample_count=len(items),
            accepted_count=len(accepted),
            minimum_ns=min(accepted) if accepted else None,
            median_ns=int(median(accepted)) if accepted else None,
            maximum_ns=max(accepted) if accepted else None,
            spread_ns=(max(accepted) - min(accepted)) if accepted else None,
            rejected_durations_ns=rejected,
            classification=(
                _explicit_classification(relationship)
                if enough or _explicit_classification(relationship) is not TimingClassification.UNKNOWN
                else TimingClassification.UNKNOWN
            ),
            confidence=("repeated" if enough else "insufficient-samples"),
        ))
    return tuple(sorted(result, key=lambda item: (
        item.relationship.value, item.context,
        item.interval.value if item.interval is not None else "",
    )))


def _differentials(
    summaries: Sequence[TimingSummary],
) -> tuple[tuple[TimingSummary, ...], tuple[TimingDelta, ...]]:
    indexed = {
        (item.relationship, item.context, item.interval): item
        for item in summaries
    }
    updated = list(summaries)
    deltas: list[TimingDelta] = []
    for item in summaries:
        if item.interval is not LabInterval.BASELINE or item.median_ns is None:
            continue
        action = indexed.get((item.relationship, item.context, LabInterval.ACTION))
        if action is None or action.median_ns is None or item.median_ns <= 0:
            continue
        ratio = action.median_ns / item.median_ns
        if 2 / 3 < ratio < 1.5:
            continue
        delta = action.median_ns - item.median_ns
        deltas.append(TimingDelta(
            relationship=item.relationship,
            context=item.context,
            baseline_median_ns=item.median_ns,
            action_median_ns=action.median_ns,
            ratio=ratio,
            delta_ns=delta,
            score=50.0 * abs(log2(ratio)),
            reason=(
                "controlled-action timing distribution differs materially from baseline; "
                "timing alone does not assign operation semantics"
            ),
        ))
        if item.accepted_count >= 2 and action.accepted_count >= 2:
            baseline_class = (
                TimingClassification.IMMEDIATE if ratio >= 1.5
                else TimingClassification.SETTLING_DELAY
            )
            action_class = (
                TimingClassification.SETTLING_DELAY if ratio >= 1.5
                else TimingClassification.IMMEDIATE
            )
            updated = [
                replace(summary, classification=baseline_class)
                if summary is item else
                replace(summary, classification=action_class)
                if summary is action else summary
                for summary in updated
            ]
    return tuple(updated), tuple(sorted(deltas, key=lambda item: -item.score))


def _timing_recommendation(
    observations: Sequence[LabTimingObservation],
    summaries: Sequence[TimingSummary],
    cycles: Sequence[BusyPollCycle],
) -> LabRecommendation | None:
    candidates: list[tuple[str, str]] = []
    relationships = {item.relationship for item in observations}
    if {
        TimingRelationship.NUDGE_TO_PUSH_LATENCY,
        TimingRelationship.PERIODIC_PUSH_CADENCE,
    } <= relationships:
        candidates.append((
            "repeat-without-nudge",
            "Distinguish periodic delivery from a nudge-caused state push.",
        ))
    stale = [
        item for item in summaries
        if item.relationship is TimingRelationship.READ_TO_FRESH_STATE_LATENCY
    ]
    if stale and max(item.accepted_count for item in stale) < 3:
        candidates.append((
            "repeat-request-push-timing",
            "Distinguish a stale immediate read from a consistently slow fresh response.",
        ))
    if cycles and len(cycles) < 2:
        candidates.append((
            "extend-busy-observation-window",
            "Measure whether busy/poll cadence and time-to-ready repeat consistently.",
        ))
    ranked: list[LabRecommendation] = []
    for experiment, reason in candidates:
        choice = choose_experiment((
            ExperimentHypothesis("stable-pattern", {experiment: "repeats"}),
            ExperimentHypothesis("context-dependent-pattern", {experiment: "changes"}),
        ), allowed_experiments=(experiment,))
        if choice is not None:
            ranked.append(LabRecommendation(
                choice.experiment, choice.information_gain_bits, reason, False,
            ))
    return min(ranked, key=lambda item: (-item.information_gain_bits, item.experiment)) if ranked else None


def profile_experiment_timing(experiment: LabExperiment) -> LabExperiment:
    """Attach canonical timing evidence derived only from recorded timestamps."""

    observations, cycles = _dialogue_timings(experiment)
    burst_observations, burst_timings = _burst_timings(experiment)
    observations.extend(burst_observations)
    observations.extend(_pushed_state_timings(experiment))
    observations.extend(_stale_state_timings(experiment))
    observations.extend(_lifecycle_timings(experiment))
    observations.sort(key=lambda item: (
        item.start_timestamp_ns, item.end_timestamp_ns,
        item.relationship.value, item.timing_id,
    ))
    summaries = _summaries(observations)
    summaries, differentials = _differentials(summaries)
    summary_classes = {
        (item.relationship, item.context, item.interval): item.classification
        for item in summaries
    }
    observations = [
        replace(
            item,
            classification=summary_classes.get(
                (item.relationship, item.context, item.interval),
                item.classification,
            ),
        )
        if item.classification is TimingClassification.UNKNOWN else item
        for item in observations
    ]
    contradictions = tuple(
        f"{item.relationship.value}:{item.context} has only {item.accepted_count} accepted sample"
        for item in summaries
        if item.accepted_count < 2
    )
    profile = ProtocolTimingProfile(
        observations=tuple(observations),
        summaries=summaries,
        busy_poll_cycles=tuple(cycles),
        burst_timings=tuple(burst_timings),
        differentials=differentials,
        contradictions=contradictions,
        next_recommended_experiment=_timing_recommendation(observations, summaries, cycles),
    )
    return replace(experiment, timing_profile=profile)
