"""Conservative battery, charging, and power-state analysis for Discovery Lab.

The investigator consumes existing selected-device evidence.  It performs no
capture, network activity, charging control, firmware operation, or write.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from hashlib import sha256
from statistics import median
from typing import Iterable, Sequence

from .discovery_lab import (
    BatteryCondition,
    ChargingState,
    FieldSignal,
    LabExperiment,
    LabExperimentPlan,
    LabHypothesis,
    LabInterval,
    PowerAnalysis,
    PowerEvidence,
    PowerFieldCandidate,
    PowerObservationContext,
    PowerSemantic,
    PowerSourceState,
    RoutingStatus,
    TimingRelationship,
)
from .lab_orchestrator import ACTION_TEMPLATES, plan_next_experiment
from .proof_state import ProofState
from .temporal_dialogue import StateFreshness


def _id(prefix: str, *parts: object) -> str:
    return prefix + "-" + sha256(repr(parts).encode("utf-8", "replace")).hexdigest()[:16]


def _unique(items: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item for item in items if item))


def _route_for_report(experiment: LabExperiment, report_id: int | None):
    routing = experiment.routing_analysis
    if routing is None:
        return None
    matches = [
        item for item in routing.evidence
        if item.status is RoutingStatus.CONFIRMED_ROUTE
        and item.source_route.report_id == report_id
        and item.child_identity_candidate is not None
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def _timing_cadence(experiment: LabExperiment) -> int | None:
    profile = experiment.timing_profile
    if profile is None:
        return None
    values = [
        item.median_ns for item in profile.summaries
        if item.relationship is TimingRelationship.PERIODIC_PUSH_CADENCE
        and item.median_ns is not None
    ]
    return int(median(values)) if values else None


def _derive_field_evidence(experiment: LabExperiment, session_id: str) -> tuple[PowerEvidence, ...]:
    analysis = experiment.analysis
    if analysis is None:
        return ()
    cadence = _timing_cadence(experiment)
    result: list[PowerEvidence] = []
    for field in analysis.ranked_fields:
        if FieldSignal.CHANGED not in field.signals and FieldSignal.STATUS_CANDIDATE not in field.signals:
            continue
        observations = [
            item for item in experiment.observations
            if item.stream_id == field.stream_id and field.offset < len(item.payload)
        ]
        values = [item.payload[field.offset] for item in observations]
        if not values:
            continue
        plausible_percentage = all(0 <= value <= 100 for value in values)
        charging_action = experiment.human_action in {
            "connect_charging", "connect_cable", "disconnect_charging", "disconnect_cable",
        }
        if not plausible_percentage and not charging_action:
            continue
        field_id = f"{field.stream_id}:{field.offset}"
        for item in observations:
            value = item.payload[field.offset]
            route = _route_for_report(experiment, item.report_id)
            context = PowerObservationContext.UNKNOWN
            semantic = (
                PowerSemantic.PERCENTAGE_CANDIDATE
                if plausible_percentage else PowerSemantic.UNKNOWN_POWER_STATE
            )
            if charging_action and item.interval is LabInterval.ACTION:
                if experiment.human_action in {"connect_charging", "connect_cable"}:
                    context = PowerObservationContext.CHARGING_CONNECTED
                else:
                    context = PowerObservationContext.CHARGING_DISCONNECTED
            result.append(PowerEvidence(
                evidence_id=_id("power-field", field_id, item.timestamp_ns, value),
                experiment_id=experiment.experiment_id,
                physical_device_context=experiment.physical_device_context,
                connection_generation=experiment.connection_generation,
                session_id=session_id,
                source_observation_ids=(f"{item.source_id}:{item.sequence}",),
                field_id=field_id,
                route_evidence_id=route.evidence_id if route else None,
                route_owner=(
                    _id("route-owner", route.child_identity_candidate) if route else None
                ),
                route_confidence=route.confidence if route else "unknown",
                candidate_semantic=semantic,
                raw_value=value,
                decoded_value=value,
                units_if_proven=None,
                power_source_state=PowerSourceState.UNKNOWN,
                charging_state=ChargingState.UNKNOWN,
                battery_state=BatteryCondition.UNKNOWN,
                freshness=StateFreshness.UNKNOWN,
                timestamp_ns=item.timestamp_ns,
                cadence_ns=cadence,
                context=context,
                confidence="candidate",
                proof_state=ProofState.HYPOTHESIZED,
            ))
        baseline = [
            item for item in observations if item.interval is LabInterval.BASELINE
        ]
        action_observations = [
            item for item in observations if item.interval is LabInterval.ACTION
        ]
        baseline_values = {item.payload[field.offset] for item in baseline}
        action_values = {item.payload[field.offset] for item in action_observations}
        if (
            charging_action
            and len(action_observations) >= 2
            and len(baseline_values) == 1
            and len(action_values) == 1
            and baseline_values != action_values
            and baseline_values | action_values <= {0, 1}
        ):
            latest = max(action_observations, key=lambda item: item.timestamp_ns)
            connecting = experiment.human_action in {"connect_charging", "connect_cable"}
            route = _route_for_report(experiment, latest.report_id)
            result.append(PowerEvidence(
                evidence_id=_id("power-transition", field_id, latest.timestamp_ns),
                experiment_id=experiment.experiment_id,
                physical_device_context=experiment.physical_device_context,
                connection_generation=experiment.connection_generation,
                session_id=session_id,
                source_observation_ids=tuple(
                    f"{item.source_id}:{item.sequence}"
                    for item in (*baseline, *action_observations)
                ),
                field_id=f"{field_id}:charging-transition",
                route_evidence_id=route.evidence_id if route else None,
                route_owner=(
                    _id("route-owner", route.child_identity_candidate) if route else None
                ),
                route_confidence=route.confidence if route else "unknown",
                candidate_semantic=(
                    PowerSemantic.CHARGING if connecting else PowerSemantic.NOT_CHARGING
                ),
                raw_value=latest.payload[field.offset],
                decoded_value=latest.payload[field.offset],
                units_if_proven=None,
                power_source_state=(
                    PowerSourceState.EXTERNAL_POWER
                    if connecting else PowerSourceState.BATTERY_POWER
                ),
                charging_state=(
                    ChargingState.CHARGING if connecting else ChargingState.NOT_CHARGING
                ),
                battery_state=BatteryCondition.UNKNOWN,
                freshness=StateFreshness.FRESH,
                timestamp_ns=latest.timestamp_ns,
                cadence_ns=cadence,
                context=(
                    PowerObservationContext.CHARGING_CONNECTED
                    if connecting else PowerObservationContext.CHARGING_DISCONNECTED
                ),
                confidence="repeated-controlled-transition",
                proof_state=ProofState.RECOGNIZED,
            ))
    return tuple(result)


def _derive_state_evidence(experiment: LabExperiment, session_id: str) -> tuple[PowerEvidence, ...]:
    result: list[PowerEvidence] = []
    cadence = _timing_cadence(experiment)
    for item in (*experiment.state_reads, *experiment.pushed_states):
        semantic_name = item.semantic_state_id.lower()
        if not any(token in semantic_name for token in ("battery", "charge", "power")):
            continue
        value = item.decoded_state
        candidate = PowerSemantic.UNKNOWN_BATTERY_VALUE
        known = False
        units = None
        charging = ChargingState.UNKNOWN
        source = PowerSourceState.UNKNOWN
        battery = BatteryCondition.UNKNOWN
        if "percent" in semantic_name and isinstance(value, (int, float)) and 0 <= value <= 100:
            candidate = PowerSemantic.PERCENTAGE_CONFIRMED
            known = True
            units = "%"
        elif "voltage" in semantic_name and isinstance(value, (int, float)):
            candidate = PowerSemantic.VOLTAGE_CANDIDATE
            known = True
            units = "mV" if "millivolt" in semantic_name or "_mv" in semantic_name else "V"
        elif "charge_complete" in semantic_name or "fully_charged" in semantic_name:
            charging = ChargingState.CHARGE_COMPLETE
            source = PowerSourceState.EXTERNAL_POWER
            battery = BatteryCondition.FULL
            candidate = PowerSemantic.FULL
            known = True
        elif "charging" in semantic_name:
            charging = ChargingState.CHARGING if bool(value) else ChargingState.NOT_CHARGING
            candidate = PowerSemantic.CHARGING if bool(value) else PowerSemantic.NOT_CHARGING
            known = True
        elif "external" in semantic_name:
            source = PowerSourceState.EXTERNAL_POWER if bool(value) else PowerSourceState.BATTERY_POWER
            candidate = PowerSemantic.EXTERNAL_POWER if bool(value) else PowerSemantic.BATTERY_POWER
            known = True
        elif "low" in semantic_name:
            battery = BatteryCondition.LOW_BATTERY if bool(value) else BatteryCondition.NORMAL
            candidate = PowerSemantic.LOW_BATTERY
            known = True
        elif "full" in semantic_name:
            battery = BatteryCondition.FULL if bool(value) else BatteryCondition.NORMAL
            candidate = PowerSemantic.FULL
            known = True
        observation = item.observation
        route = _route_for_report(experiment, observation.report_id)
        result.append(PowerEvidence(
            _id("power-state", semantic_name, observation.timestamp_ns),
            experiment.experiment_id, experiment.physical_device_context,
            experiment.connection_generation, session_id,
            (f"{observation.source_id}:{observation.sequence}",), semantic_name,
            route.evidence_id if route else None,
            _id("route-owner", route.child_identity_candidate) if route else None,
            route.confidence if route else "unknown", candidate, value, value, units,
            source, charging, battery, item.freshness, observation.timestamp_ns,
            cadence, PowerObservationContext.UNKNOWN, known_protocol_semantics=known,
            confidence="known-semantics" if known else "candidate",
            proof_state=ProofState.RECOGNIZED if known else ProofState.HYPOTHESIZED,
        ))
    return tuple(result)


def _directional_support(evidence: Sequence[PowerEvidence]) -> tuple[bool, tuple[str, ...]]:
    numeric = [
        item for item in sorted(evidence, key=lambda item: item.timestamp_ns)
        if isinstance(item.decoded_value, (int, float))
    ]
    reasons: list[str] = []
    supported = False
    discharging = [
        item for item in numeric
        if item.context is PowerObservationContext.DISCHARGING
        or item.power_source_state is PowerSourceState.BATTERY_POWER
    ]
    if len({item.decoded_value for item in discharging}) >= 3:
        values = [float(item.decoded_value) for item in discharging]
        if all(right <= left for left, right in zip(values, values[1:])):
            supported = True
            reasons.append("repeated values decrease monotonically under battery power")
        elif any(right > left for left, right in zip(values, values[1:])):
            reasons.append("candidate rises during an observed discharge sequence")
    charging = [
        item for item in numeric
        if item.context is PowerObservationContext.CHARGING_CONNECTED
        or item.charging_state is ChargingState.CHARGING
    ]
    if len({item.decoded_value for item in charging}) >= 2:
        values = [float(item.decoded_value) for item in charging]
        if all(right >= left for left, right in zip(values, values[1:])):
            supported = True
            reasons.append("repeated values increase monotonically while charging")
        elif any(right < left for left, right in zip(values, values[1:])):
            reasons.append("candidate decreases during an observed charging sequence")
    return supported, tuple(reasons)


def _candidate(field_id: str, evidence: Sequence[PowerEvidence]) -> PowerFieldCandidate:
    ordered = tuple(sorted(evidence, key=lambda item: item.timestamp_ns))
    raw = tuple(item.raw_value for item in ordered)
    decoded = tuple(
        item.decoded_value for item in ordered if item.decoded_value is not None
    )
    sources = _unique(
        source for item in ordered for source in item.source_observation_ids
    )
    contradictions = list(
        contradiction for item in ordered for contradiction in item.contradictions
    )
    numeric = [float(value) for value in decoded if isinstance(value, (int, float))]
    in_percent_range = bool(numeric) and all(0 <= value <= 100 for value in numeric)
    directional, trend_reasons = _directional_support(ordered)
    contradictions.extend(
        reason for reason in trend_reasons if "candidate" in reason
    )
    known = any(item.known_protocol_semantics for item in ordered)
    independent = any(
        item.independent_reference_source is not None
        and isinstance(item.decoded_value, (int, float))
        and isinstance(item.independent_reference_value, (int, float))
        and abs(float(item.decoded_value) - float(item.independent_reference_value)) <= 2.0
        for item in ordered
    )
    declared = {item.candidate_semantic for item in ordered}
    percentage = in_percent_range and (known or independent or directional)
    if PowerSemantic.VOLTAGE_CANDIDATE in declared:
        semantic = PowerSemantic.VOLTAGE_CANDIDATE
        confidence = "known-semantics" if known else "candidate"
    elif percentage:
        semantic = PowerSemantic.PERCENTAGE_CONFIRMED
        confidence = "high" if known or independent else "correlated"
    elif in_percent_range:
        semantic = PowerSemantic.PERCENTAGE_CANDIDATE
        confidence = "candidate"
    elif any(item.candidate_semantic is PowerSemantic.RAW_LEVEL_CANDIDATE for item in ordered):
        semantic = PowerSemantic.RAW_LEVEL_CANDIDATE
        confidence = "candidate"
    else:
        semantic = PowerSemantic.PERCENTAGE_CANDIDATE if in_percent_range else PowerSemantic.RAW_LEVEL_CANDIDATE
        confidence = "candidate"
    reasons = [
        "raw values are retained without an assumed conversion",
        *[reason for reason in trend_reasons if "candidate" not in reason],
    ]
    if known:
        reasons.append("existing protocol semantics identify the field")
    if independent:
        reasons.append("independent source agrees within the retained tolerance")
    return PowerFieldCandidate(
        field_id, semantic, raw, decoded, sources,
        len({item.session_id for item in ordered}), confidence,
        tuple(reasons), _unique(contradictions),
    )


def _decisive(evidence: Sequence[PowerEvidence]) -> tuple[PowerEvidence | None, tuple[str, ...]]:
    if not evidence:
        return None, ()
    fresh = [item for item in evidence if item.freshness is StateFreshness.FRESH]
    decisive = max(fresh or evidence, key=lambda item: (item.timestamp_ns, item.evidence_id))
    contradictions = [item for evidence_item in evidence for item in evidence_item.contradictions]
    stale = [item for item in evidence if item.freshness is StateFreshness.STALE]
    if fresh and any(item.field_id == decisive.field_id and item.raw_value != decisive.raw_value for item in stale):
        contradictions.append("stale cached power state was superseded by different fresh telemetry")
    return decisive, _unique(contradictions)


def _power_plan(
    experiment: LabExperiment,
    *,
    charging_available: bool,
    receiver_cache_ambiguous: bool,
) -> LabExperimentPlan | None:
    if receiver_cache_ambiguous:
        action_id = "POWER_CYCLE_PERSISTENCE"
        question = "Is the power state mouse-local or a receiver cache?"
    elif charging_available:
        action_id = "CHARGING_TRANSITION"
        question = "Which observed field represents charging or battery state?"
    else:
        return None
    action = ACTION_TEMPLATES[action_id]
    hypotheses = (
        LabHypothesis("power-field", question, "candidate field tracks power state", "battery", {action_id: "changes"}),
        LabHypothesis("unrelated-field", question, "candidate field is unrelated telemetry", "battery", {action_id: "stable"}),
    )
    return plan_next_experiment(
        hypotheses, available_actions=(action,), timing_profile=experiment.timing_profile,
    )


def analyze_power_state(
    experiment: LabExperiment,
    *,
    supplied_evidence: Iterable[PowerEvidence] = (),
    cross_session_evidence: Iterable[PowerEvidence] = (),
    session_id: str = "current-lab-session",
    charging_action_available: bool = True,
) -> LabExperiment:
    """Attach conservative power findings and the next safe experiment."""

    if experiment.analysis is None:
        from .discovery_lab import analyze_differential_experiment
        experiment = analyze_differential_experiment(experiment)
    derived = (
        *_derive_field_evidence(experiment, session_id),
        *_derive_state_evidence(experiment, session_id),
    )
    supplied = tuple(supplied_evidence)
    history = tuple(cross_session_evidence)
    evidence = tuple(sorted((*history, *supplied, *derived), key=lambda item: (item.timestamp_ns, item.evidence_id)))
    if any(item.physical_device_context != experiment.physical_device_context for item in evidence):
        raise ValueError("power evidence physical identity does not match the selected device")
    current_experiment_ids = {experiment.experiment_id}
    if any(item.experiment_id not in current_experiment_ids for item in history):
        instance = experiment.physical_device_context.get("instance_fingerprint")
        if not instance or any(
            item.physical_device_context.get("instance_fingerprint") != instance
            for item in history
        ):
            raise ValueError("cross-session power evidence requires exact device-unique identity")

    grouped: dict[str, list[PowerEvidence]] = defaultdict(list)
    battery_field_semantics = {
        PowerSemantic.UNKNOWN_BATTERY_VALUE,
        PowerSemantic.PERCENTAGE_CANDIDATE,
        PowerSemantic.PERCENTAGE_CONFIRMED,
        PowerSemantic.RAW_LEVEL_CANDIDATE,
        PowerSemantic.VOLTAGE_CANDIDATE,
    }
    for item in evidence:
        if item.field_id is not None and item.candidate_semantic in battery_field_semantics:
            grouped[item.field_id].append(item)
    candidates = tuple(
        _candidate(field_id, items) for field_id, items in sorted(grouped.items())
    )
    strongest = sorted(
        candidates,
        key=lambda item: (
            item.semantic is not PowerSemantic.PERCENTAGE_CONFIRMED,
            item.confidence != "high",
            -len(set(map(repr, item.raw_values))),
            item.field_id,
        ),
    )
    chosen = strongest[0] if strongest else None
    chosen_evidence = grouped.get(chosen.field_id, []) if chosen else list(evidence)
    decisive, decisive_contradictions = _decisive(chosen_evidence)
    contradictions = list(decisive_contradictions)
    contradictions.extend(
        contradiction for candidate in candidates for contradiction in candidate.contradictions
    )
    if chosen is not None:
        equally_supported = [
            item for item in candidates
            if item.field_id != chosen.field_id
            and item.semantic is chosen.semantic
            and item.confidence == chosen.confidence
            and len(set(map(repr, item.raw_values))) == len(set(map(repr, chosen.raw_values)))
        ]
        if equally_supported:
            contradictions.append("multiple equally supported battery fields remain ambiguous")
    fresh_by_owner = {
        item.route_owner: item for item in evidence
        if item.route_owner is not None and item.freshness is StateFreshness.FRESH
        and isinstance(item.decoded_value, (int, float))
    }
    if len(fresh_by_owner) >= 2 and len({item.decoded_value for item in fresh_by_owner.values()}) > 1:
        contradictions.append("fresh mouse and receiver-routed power sources disagree")
    for item in evidence:
        if item.independent_reference_source:
            reference = item.independent_reference_value
            observed = item.decoded_value
            if isinstance(reference, (int, float)) and isinstance(observed, (int, float)):
                disagrees = abs(float(reference) - float(observed)) > 2.0
            else:
                disagrees = reference != observed
            if disagrees:
                contradictions.append("independent power reference disagrees with candidate value")

    charging = next((
        item.charging_state for item in reversed(evidence)
        if item.charging_state is not ChargingState.UNKNOWN and item.freshness is not StateFreshness.STALE
    ), ChargingState.UNKNOWN)
    source = next((
        item.power_source_state for item in reversed(evidence)
        if item.power_source_state is not PowerSourceState.UNKNOWN and item.freshness is not StateFreshness.STALE
    ), PowerSourceState.UNKNOWN)
    battery_state = next((
        item.battery_state for item in reversed(evidence)
        if item.battery_state is not BatteryCondition.UNKNOWN and item.freshness is not StateFreshness.STALE
    ), BatteryCondition.UNKNOWN)
    cadence_values = [item.cadence_ns for item in evidence if item.cadence_ns is not None]
    cadence = int(median(cadence_values)) if cadence_values else _timing_cadence(experiment)
    semantic = chosen.semantic if chosen else PowerSemantic.UNKNOWN_BATTERY_VALUE
    units = decisive.units_if_proven if decisive is not None and chosen is not None else None
    if semantic is PowerSemantic.PERCENTAGE_CONFIRMED:
        units = "%"
    value = decisive.decoded_value if decisive is not None and chosen is not None else None
    route_owner = decisive.route_owner if decisive is not None else None
    route_confidence = decisive.route_confidence if decisive is not None else "unknown"
    receiver_cache_ambiguous = bool(
        experiment.routing_analysis is not None
        and any("receiver" in item.lower() for item in experiment.routing_analysis.ambiguities)
    )
    percentage_pending = semantic is PowerSemantic.PERCENTAGE_CANDIDATE
    next_plan = _power_plan(
        experiment,
        charging_available=charging_action_available and charging is ChargingState.UNKNOWN,
        receiver_cache_ambiguous=receiver_cache_ambiguous,
    )
    pending_natural = percentage_pending and next_plan is None
    confidence = chosen.confidence if chosen else "unknown"
    summary: list[str] = []
    if semantic is PowerSemantic.PERCENTAGE_CONFIRMED:
        summary.append(f"Battery: {value}% ({confidence})")
    elif decisive is not None and chosen is not None:
        summary.append(f"Battery candidate: raw {decisive.raw_value!r}; percentage unknown")
    else:
        summary.append("Battery / power state remains unknown.")
    if charging is not ChargingState.UNKNOWN:
        summary.append(f"Charging: {charging.value}")
    if source is not PowerSourceState.UNKNOWN:
        summary.append(f"Power source: {source.value.replace('_', ' ')}")
    if battery_state is not BatteryCondition.UNKNOWN:
        summary.append(f"Battery state: {battery_state.value.replace('_', ' ')}")
    if decisive is not None:
        summary.append(f"Freshness: {decisive.freshness.value.replace('_', ' ')}")
    if route_owner is not None:
        summary.append(f"Source owner: confirmed routed source ({route_confidence})")
    if cadence is not None:
        summary.append(f"Update cadence: approximately {cadence / 1_000_000_000:g} s")
    if pending_natural:
        summary.append("Candidate retained; more evidence may accumulate during normal future use.")

    analysis = PowerAnalysis(
        evidence, candidates, decisive.evidence_id if decisive else None,
        semantic, value, units, charging, source, battery_state,
        decisive.freshness if decisive else StateFreshness.UNKNOWN,
        cadence, route_owner, route_confidence, confidence,
        _unique(contradictions), pending_natural, next_plan, tuple(summary),
    )
    return replace(
        experiment,
        power_evidence=evidence,
        power_analysis=analysis,
        next_plan=next_plan or experiment.next_plan,
    )
