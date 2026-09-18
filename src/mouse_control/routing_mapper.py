"""Evidence-driven receiver/child routing analysis for Discovery Lab.

The mapper consumes existing selected-device observations.  It never probes
child IDs, scans receiver slots, opens hardware, or grants write authority.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from hashlib import sha256
from typing import Iterable, Mapping, Sequence

from .discovery_lab import (
    LabExperiment,
    LabExperimentPlan,
    LabHypothesis,
    PersistenceClassification,
    ProofState,
    ReceiverChildGraph,
    RouteEdge,
    RouteEndpoint,
    RouteNode,
    RouteRediscoveryComparison,
    RoutingAnalysis,
    RoutingEvidence,
    RoutingNodeKind,
    RoutingRelationship,
    RoutingStatus,
    TargetFieldCandidate,
    analyze_differential_experiment,
)
from .lab_orchestrator import ACTION_TEMPLATES, plan_next_experiment


def _id(prefix: str, *parts: object) -> str:
    return prefix + "-" + sha256(repr(parts).encode("utf-8", "replace")).hexdigest()[:16]


def _route_node_id(route: RouteEndpoint) -> str:
    return _id("route", route.identity)


def _dialogue_route(observation) -> RouteEndpoint:
    return RouteEndpoint(
        transport=observation.transport,
        channel=observation.channel_id,
        namespace=observation.report_namespace,
        report_id=observation.report_id,
        direction=observation.direction.value,
    )


def _target_candidates(
    experiment: LabExperiment,
    route_labels: Mapping[str, str],
) -> tuple[tuple[TargetFieldCandidate, ...], tuple[RoutingEvidence, ...]]:
    def label_for(item):
        return route_labels.get(
            f"{item.source_id}:{item.sequence}", route_labels.get(item.source_id),
        )

    labelled = [item for item in experiment.observations if label_for(item) is not None]
    grouped: dict[str, list] = defaultdict(list)
    for item in labelled:
        grouped[item.stream_id].append(item)
    candidates: list[TargetFieldCandidate] = []
    evidence: list[RoutingEvidence] = []
    for stream_id, observations in sorted(grouped.items()):
        width = min((len(item.payload) for item in observations), default=0)
        for offset in range(width):
            values: dict[str, set[int]] = defaultdict(set)
            source_ids: dict[str, list[str]] = defaultdict(list)
            counts: dict[str, int] = defaultdict(int)
            for item in observations:
                label = label_for(item)
                assert label is not None
                values[label].add(item.payload[offset])
                source_ids[label].append(f"{item.source_id}:{item.sequence}")
                counts[label] += 1
            if len(values) < 2 or any(len(items) != 1 for items in values.values()):
                continue
            scalar = {label: next(iter(items)) for label, items in values.items()}
            distinct = len(set(scalar.values())) == len(scalar)
            if len(set(scalar.values())) == 1:
                continue  # A constant byte is not routing evidence.
            repeated = min(counts.values()) >= 2
            status = (
                RoutingStatus.CONFIRMED_ROUTE if distinct and repeated
                else RoutingStatus.CANDIDATE_ROUTE if distinct
                else RoutingStatus.AMBIGUOUS_ROUTE
            )
            contradictions = () if distinct else (
                "one observed target value maps to multiple controlled child labels",
            )
            all_sources = tuple(sorted({source for items in source_ids.values() for source in items}))
            candidates.append(TargetFieldCandidate(
                stream_id, offset, scalar, len(observations), status,
                "high" if status is RoutingStatus.CONFIRMED_ROUTE else "candidate",
                all_sources, contradictions,
            ))
            for label, value in sorted(scalar.items()):
                child_sources = tuple(sorted(set(source_ids[label])))
                evidence.append(RoutingEvidence(
                    evidence_id=_id("target", stream_id, offset, label, value),
                    experiment_id=experiment.experiment_id,
                    physical_device_context=experiment.physical_device_context,
                    connection_generation=experiment.connection_generation,
                    receiver_identity=None,
                    child_identity_candidate=label,
                    source_route=RouteEndpoint(
                        "hid", namespace=stream_id, report_id=(
                            observations[0].report_id if observations else None
                        ), direction="input",
                    ),
                    destination_route=None,
                    internal_target=value,
                    route_tag=f"{stream_id}:byte:{offset}",
                    source_observation_ids=child_sources,
                    relationship=RoutingRelationship.TARGET_FIELD_CANDIDATE,
                    status=status,
                    confidence="high" if status is RoutingStatus.CONFIRMED_ROUTE else "candidate",
                    proof_state=(
                        ProofState.RECOGNIZED
                        if status is RoutingStatus.CONFIRMED_ROUTE else ProofState.HYPOTHESIZED
                    ),
                    contradictions=contradictions,
                    ambiguity=contradictions,
                    reason="controlled cross-child labels discriminate this observed byte",
                ))
    return tuple(candidates), tuple(evidence)


def _existing_route_evidence(
    experiment: LabExperiment,
    receiver_identity: str | None,
) -> tuple[RoutingEvidence, ...]:
    result: list[RoutingEvidence] = []
    expected_fingerprint = experiment.physical_device_context.get("model_fingerprint")
    for item in experiment.usb_observations:
        if expected_fingerprint and item.physical_device_fingerprint != expected_fingerprint:
            continue
        source = f"{item.capture_id}:{item.sequence}"
        route = RouteEndpoint(
            transport=f"usb:{item.transfer_type.value}",
            interface_number=item.interface_number,
            endpoint=item.endpoint,
            direction=item.direction.value,
            report_id=item.payload[0] if item.payload else None,
        )
        result.append(RoutingEvidence(
            _id("usb-route", source), experiment.experiment_id,
            experiment.physical_device_context, experiment.connection_generation,
            receiver_identity, None, route, None, None, None, (source,),
            RoutingRelationship.REPORT_ROUTE, RoutingStatus.UNMAPPED, "observed",
            reason="selected-device USB route observed; logical owner remains unknown",
        ))
    for index, item in enumerate(experiment.logical_records):
        if item.generation != experiment.connection_generation:
            continue
        sources = tuple(
            f"{frame.source_id}:{frame.sequence}" for frame in item.source_frames
        ) or (f"logical:{index}",)
        transport = item.source_frames[0].transport if item.source_frames else "logical-record"
        route = RouteEndpoint(
            transport=transport,
            channel=item.channel_id,
            namespace=item.report_namespace,
            report_id=item.report_id,
            logical_record_type=item.record_type,
        )
        result.append(RoutingEvidence(
            _id("logical-route", item.grammar, index), experiment.experiment_id,
            experiment.physical_device_context, experiment.connection_generation,
            receiver_identity, None, route, None, None, item.grammar, sources,
            RoutingRelationship.INTERFACE_NAMESPACE, RoutingStatus.UNMAPPED, "observed",
            reason="logical record route observed without assuming semantic ownership",
        ))
    timing_supported = bool(
        experiment.timing_profile is not None
        and any(summary.accepted_count >= 2 for summary in experiment.timing_profile.summaries)
    )
    for index, item in enumerate(experiment.dialogues):
        if item.request is None:
            continue
        request = item.request
        response = item.observation
        sources = (
            f"{request.source_id}:{request.sequence}",
            f"{response.source_id}:{response.sequence}",
        )
        contradictions = ()
        if request.transaction_tag is not None and response.transaction_tag is not None \
                and request.transaction_tag != response.transaction_tag:
            contradictions = ("request and response transaction tags disagree",)
        ambiguous = item.ambiguous or bool(contradictions)
        result.append(RoutingEvidence(
            _id("dialogue-route", index, sources), experiment.experiment_id,
            experiment.physical_device_context, experiment.connection_generation,
            receiver_identity, None, _dialogue_route(request), _dialogue_route(response),
            request.transaction_tag, str(request.transaction_tag) if request.transaction_tag is not None else None,
            sources, RoutingRelationship.REQUEST_RESPONSE,
            RoutingStatus.AMBIGUOUS_ROUTE if ambiguous else RoutingStatus.CANDIDATE_ROUTE,
            "timing-supported" if timing_supported and not ambiguous else item.confidence,
            ProofState.HYPOTHESIZED, contradictions,
            (item.reason or "dialogue route is ambiguous",) if ambiguous else (),
            "existing dialogue correlation supports an asymmetric route; timing alone does not establish ownership",
        ))
    for index, item in enumerate(experiment.pushed_states):
        if item.controlled_action is None or item.observation.generation != experiment.connection_generation:
            continue
        sources = (
            f"{item.controlled_action.source_id}:{item.controlled_action.sequence}",
            f"{item.observation.source_id}:{item.observation.sequence}",
        )
        result.append(RoutingEvidence(
            _id("async-route", index, sources), experiment.experiment_id,
            experiment.physical_device_context, experiment.connection_generation,
            receiver_identity, None, _dialogue_route(item.controlled_action),
            _dialogue_route(item.observation), item.observation.transaction_tag,
            str(item.observation.transaction_tag) if item.observation.transaction_tag is not None else None,
            sources, RoutingRelationship.ASYNC_RESPONSE,
            RoutingStatus.CANDIDATE_ROUTE, "correlated", ProofState.HYPOTHESIZED,
            reason="controlled action is associated with an asynchronous state route",
        ))
    return tuple(result)


def _routing_plan(
    experiment: LabExperiment,
    ambiguities: Sequence[str],
    *,
    other_child_available: bool,
) -> LabExperimentPlan | None:
    if not ambiguities:
        return None
    receiver_mouse = any(
        "receiver" in item.lower() and "mouse" in item.lower() for item in ambiguities
    )
    if receiver_mouse:
        action_id = "POWER_CYCLE_PERSISTENCE"
    elif other_child_available:
        action_id = "OTHER_CHILD_ROUTE_CONTROL"
    else:
        action_id = "MULTI_DPI_STAGE_SEQUENCE"
    action = ACTION_TEMPLATES[action_id]
    question = "Which logical child or receiver route owns the unresolved traffic?"
    hypotheses = (
        LabHypothesis("route-selected-child", question, "selected child owns the route", "routing", {action_id: "selected-child"}),
        LabHypothesis("route-other-owner", question, "another child or receiver owns the route", "routing", {action_id: "other-owner"}),
    )
    return plan_next_experiment(
        hypotheses, available_actions=(action,), timing_profile=experiment.timing_profile,
    )


def _graph(
    experiment: LabExperiment,
    evidence: Sequence[RoutingEvidence],
) -> ReceiverChildGraph:
    nodes: dict[str, RouteNode] = {}
    edges: list[RouteEdge] = []
    for item in evidence:
        receiver_id = None
        if item.receiver_identity is not None:
            receiver_id = _id("receiver", item.receiver_identity)
            nodes.setdefault(receiver_id, RouteNode(
                receiver_id, RoutingNodeKind.PHYSICAL_RECEIVER, "physical receiver",
                experiment.connection_generation, item.receiver_identity, item.confidence,
            ))
        child_id = None
        if item.child_identity_candidate is not None:
            receiver_local = str(item.child_identity_candidate).lower() in {
                "receiver", "receiver-local", "dongle", "dongle-local",
            }
            child_id = _id("owner", item.child_identity_candidate)
            nodes.setdefault(child_id, RouteNode(
                child_id,
                RoutingNodeKind.RECEIVER_LOCAL if receiver_local else RoutingNodeKind.LOGICAL_CHILD,
                "receiver-local" if receiver_local else f"child {item.child_identity_candidate}",
                experiment.connection_generation, item.child_identity_candidate, item.confidence,
            ))
            if receiver_id is not None and not receiver_local:
                edges.append(RouteEdge(
                    receiver_id, child_id, RoutingRelationship.RECEIVER_CHILD,
                    (item.evidence_id,), item.status, item.confidence,
                ))
            elif receiver_id is not None:
                edges.append(RouteEdge(
                    receiver_id, child_id, RoutingRelationship.ROUTE_OWNERSHIP,
                    (item.evidence_id,), item.status, item.confidence,
                ))
        source_id = _route_node_id(item.source_route)
        nodes.setdefault(source_id, RouteNode(
            source_id,
            RoutingNodeKind.REPORT if item.source_route.report_id is not None else RoutingNodeKind.NAMESPACE,
            _route_label(item.source_route), experiment.connection_generation,
            item.internal_target, item.confidence,
        ))
        if child_id is not None:
            edges.append(RouteEdge(
                child_id, source_id, RoutingRelationship.ROUTE_OWNERSHIP,
                (item.evidence_id,), item.status, item.confidence,
            ))
        if item.destination_route is not None:
            destination_id = _route_node_id(item.destination_route)
            nodes.setdefault(destination_id, RouteNode(
                destination_id,
                RoutingNodeKind.REPORT if item.destination_route.report_id is not None else RoutingNodeKind.NAMESPACE,
                _route_label(item.destination_route), experiment.connection_generation,
                None, item.confidence,
            ))
            edges.append(RouteEdge(
                source_id, destination_id, item.relationship, (item.evidence_id,),
                item.status, item.confidence,
                asymmetric=item.source_route.identity != item.destination_route.identity,
            ))
    contradictions = tuple(dict.fromkeys(
        contradiction for item in evidence for contradiction in item.contradictions
    ))
    ambiguities = tuple(dict.fromkeys(
        ambiguity for item in evidence for ambiguity in item.ambiguity
    ))
    return ReceiverChildGraph(
        experiment.experiment_id, experiment.physical_device_context,
        experiment.connection_generation,
        tuple(sorted(nodes.values(), key=lambda node: node.node_id)),
        tuple(sorted(edges, key=lambda edge: (
            edge.source_node_id, edge.destination_node_id, edge.relationship.value,
        ))),
        contradictions, ambiguities,
    )


def _route_label(route: RouteEndpoint) -> str:
    parts = [route.transport]
    if route.interface_number is not None:
        parts.append(f"interface {route.interface_number}")
    if route.endpoint is not None:
        parts.append(f"endpoint {route.endpoint:#x}")
    if route.channel:
        parts.append(f"channel {route.channel}")
    if route.namespace:
        parts.append(f"namespace {route.namespace}")
    if route.report_id is not None:
        parts.append(f"report {route.report_id:#x}")
    return ", ".join(parts)


def analyze_receiver_child_routing(
    experiment: LabExperiment,
    *,
    route_labels: Mapping[str, str] | None = None,
    supplied_evidence: Iterable[RoutingEvidence] = (),
    receiver_identity: str | None = None,
    other_child_available: bool = False,
) -> LabExperiment:
    """Attach a generation-isolated receiver/child route graph to an experiment."""

    if experiment.analysis is None:
        experiment = analyze_differential_experiment(experiment)

    if receiver_identity is None:
        value = experiment.physical_device_context.get("receiver_identity")
        receiver_identity = str(value) if value is not None else None
    candidates, inferred_targets = _target_candidates(experiment, route_labels or {})
    if receiver_identity is not None:
        inferred_targets = tuple(
            replace(item, receiver_identity=receiver_identity) for item in inferred_targets
        )
    observed = _existing_route_evidence(experiment, receiver_identity)
    supplied = tuple(supplied_evidence)
    all_evidence = (*supplied, *inferred_targets, *observed)
    if any(item.experiment_id != experiment.experiment_id for item in all_evidence):
        raise ValueError("routing evidence belongs to a different experiment")
    if any(item.physical_device_context != experiment.physical_device_context for item in all_evidence):
        raise ValueError("routing evidence physical identity does not match the experiment")
    if any(item.connection_generation != experiment.connection_generation for item in all_evidence):
        raise ValueError("routing evidence must be rediscovered for the current generation")

    graph = _graph(experiment, all_evidence)
    contradictions = tuple(dict.fromkeys((
        *graph.contradictions,
        *(item for candidate in candidates for item in candidate.contradictions),
    )))
    ambiguities = list(graph.ambiguities)
    ambiguities.extend(
        f"{candidate.stream_id} byte {candidate.offset} has ambiguous child ownership"
        for candidate in candidates if candidate.status is RoutingStatus.AMBIGUOUS_ROUTE
    )
    if not any(item.status is RoutingStatus.CONFIRMED_ROUTE for item in all_evidence):
        ambiguities.append("no logical child route has sufficient controlled contrast")
    if receiver_identity is not None and not any(
        item.child_identity_candidate is not None for item in all_evidence
    ):
        ambiguities.append("receiver is observed but child ownership is unmapped")
    ambiguities = list(dict.fromkeys(ambiguities))

    persistence = experiment.persistence_assessment
    if persistence is not None and any(
        item is PersistenceClassification.POWER_CYCLE_PERSISTENT
        for item in persistence.classifications
    ) and any("receiver" in item.lower() for item in ambiguities):
        ambiguities.append(
            "state survived a selected-device power cycle; this supports but does not prove receiver ownership"
        )
    next_plan = _routing_plan(
        experiment, ambiguities, other_child_available=other_child_available,
    )
    summary = tuple(
        f"{node.label}: {node.confidence}"
        for node in graph.nodes
        if node.kind in {RoutingNodeKind.LOGICAL_CHILD, RoutingNodeKind.RECEIVER_LOCAL}
    )
    if not summary:
        summary = ("Logical route ownership remains unknown.",)
    analysis = RoutingAnalysis(
        tuple(all_evidence), graph, candidates, contradictions,
        tuple(ambiguities), next_plan, summary,
    )
    return replace(
        experiment,
        routing_evidence=tuple(all_evidence),
        routing_analysis=analysis,
        next_plan=next_plan or experiment.next_plan,
    )


def compare_route_rediscovery(
    old: ReceiverChildGraph,
    new: ReceiverChildGraph,
) -> RouteRediscoveryComparison:
    """Compare graph evidence without carrying old-generation authority forward."""

    if old.connection_generation == new.connection_generation:
        raise ValueError("route rediscovery comparison requires different generations")
    if old.physical_device_context != new.physical_device_context:
        raise ValueError("route rediscovery requires the same exact physical identity")
    old_labels = {f"{node.kind.value}:{node.label}" for node in old.nodes}
    new_labels = {f"{node.kind.value}:{node.label}" for node in new.nodes}
    stable = tuple(sorted(old_labels & new_labels))
    old_node_labels = {
        node.node_id: f"{node.kind.value}:{node.label}" for node in old.nodes
    }
    new_node_labels = {
        node.node_id: f"{node.kind.value}:{node.label}" for node in new.nodes
    }

    def ownership(graph, labels):
        result = defaultdict(set)
        for edge in graph.edges:
            if edge.relationship is not RoutingRelationship.ROUTE_OWNERSHIP:
                continue
            source = labels.get(edge.source_node_id)
            destination = labels.get(edge.destination_node_id)
            if source and destination:
                result[source].add(destination)
        return result

    old_ownership = ownership(old, old_node_labels)
    new_ownership = ownership(new, new_node_labels)
    remapped = tuple(sorted(
        owner for owner in set(old_ownership) & set(new_ownership)
        if old_ownership[owner] != new_ownership[owner]
    ))
    return RouteRediscoveryComparison(
        old.physical_device_context,
        old.connection_generation,
        new.connection_generation,
        stable,
        remapped,
        tuple(sorted(old_labels - new_labels)),
        tuple(sorted(new_labels - old_labels)),
        automatically_carried_forward=False,
    )
