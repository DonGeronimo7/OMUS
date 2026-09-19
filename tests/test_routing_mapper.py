from dataclasses import replace

import pytest

from mouse_control.discovery_lab import (
    EffectState,
    LabExperiment,
    LabInterval,
    LabStopReason,
    PersistenceAssessment,
    PersistenceClassification,
    PersistenceLevel,
    ProtocolObservation,
    ProtocolTimingProfile,
    RestorationPlan,
    RouteEndpoint,
    RoutingEvidence,
    RoutingNodeKind,
    RoutingRelationship,
    RoutingStatus,
    TimingClassification,
    TimingRelationship,
    TimingSummary,
)
from mouse_control.proof_state import ProofState
from mouse_control.routing_mapper import (
    analyze_receiver_child_routing,
    compare_route_rediscovery,
)
from mouse_control.temporal_dialogue import (
    DialogueKind,
    DialogueObservation,
    DialogueRecord,
    Direction,
    PushedStateRecord,
    StateFreshness,
)
from mouse_control.trace.models import (
    CaptureSource,
    UrbEventType,
    UsbDirection,
    UsbObservation,
    UsbTransferType,
)


CONTEXT = {
    "bus": 3,
    "vendor_id": 0x046D,
    "product_id": 0xC53F,
    "model_fingerprint": "receiver-model",
}


def _observation(source, value, sequence, *, generation=1):
    return ProtocolObservation(
        source, "shared-route-stream", sequence * 100, sequence,
        bytes((0x10, value, 0x55)), LabInterval.ACTION,
        repeat=max(1, sequence), report_id=0x10,
        connection_generation=generation,
    )


def _experiment(*, observations=(), dialogues=(), pushed=(), timing=None, persistence=None, generation=1):
    return LabExperiment(
        "routing-fixture", CONTEXT, generation, "routing fixture", "controlled route action",
        (), tuple(observations), dialogues=tuple(dialogues), pushed_states=tuple(pushed),
        timing_profile=timing, persistence_assessment=persistence,
    )


def _route_evidence(
    evidence_id,
    child,
    *,
    status=RoutingStatus.CONFIRMED_ROUTE,
    namespace="mouse-config",
    interface=2,
    report=0x10,
    generation=1,
    ambiguity=(),
):
    return RoutingEvidence(
        evidence_id, "routing-fixture", CONTEXT, generation, "usb:046d:c53f",
        child,
        RouteEndpoint(
            "usb-hid", interface_number=interface, endpoint=0x81,
            channel=f"if{interface}", namespace=namespace, report_id=report,
            report_type="input", direction="in",
        ),
        None, child if isinstance(child, int) else None,
        f"target:{child}", (f"source:{evidence_id}",),
        RoutingRelationship.ROUTE_OWNERSHIP, status,
        "high" if status is RoutingStatus.CONFIRMED_ROUTE else "candidate",
        ProofState.RECOGNIZED if status is RoutingStatus.CONFIRMED_ROUTE else ProofState.HYPOTHESIZED,
        ambiguity=tuple(ambiguity),
        reason="controlled fixture evidence",
    )


def test_single_child_receiver_graph_keeps_physical_and_logical_identity_separate():
    result = analyze_receiver_child_routing(
        _experiment(), supplied_evidence=(_route_evidence("one", 1),),
    )
    graph = result.routing_analysis.graph
    assert result.analysis is not None
    kinds = {node.kind for node in graph.nodes}
    assert RoutingNodeKind.PHYSICAL_RECEIVER in kinds
    assert RoutingNodeKind.LOGICAL_CHILD in kinds
    assert any(edge.relationship is RoutingRelationship.RECEIVER_CHILD for edge in graph.edges)
    assert result.write_authorized is False
    assert result.routing_analysis.write_authorized is False


def test_multiple_children_and_receiver_local_namespace_remain_distinct():
    evidence = (
        _route_evidence("child-1", 1, namespace="mouse-config", interface=2),
        _route_evidence("child-2", 2, namespace="telemetry", interface=3, report=0x13),
        _route_evidence("receiver", "receiver-local", namespace="receiver-config", interface=1, report=0x20),
    )
    result = analyze_receiver_child_routing(_experiment(), supplied_evidence=evidence)
    graph = result.routing_analysis.graph
    children = [node for node in graph.nodes if node.kind is RoutingNodeKind.LOGICAL_CHILD]
    receiver_local = [node for node in graph.nodes if node.kind is RoutingNodeKind.RECEIVER_LOCAL]
    assert {node.observed_identifier for node in children} == {1, 2}
    assert len(receiver_local) == 1
    assert receiver_local[0].label == "receiver-local"


def test_shared_pid_internal_target_requires_controlled_cross_child_contrast():
    observations = (
        _observation("mouse", 1, 1), _observation("mouse", 1, 2),
        _observation("other", 2, 3), _observation("other", 2, 4),
    )
    result = analyze_receiver_child_routing(
        _experiment(observations=observations),
        route_labels={"mouse": "selected-mouse", "other": "other-child"},
        receiver_identity="usb:046d:c53f",
    )
    candidate = next(item for item in result.routing_analysis.target_field_candidates if item.offset == 1)
    assert candidate.status is RoutingStatus.CONFIRMED_ROUTE
    assert candidate.values_by_child == {"selected-mouse": 1, "other-child": 2}
    assert any(item.internal_target == 1 for item in result.routing_evidence)


def test_constant_byte_is_not_called_a_target_field():
    observations = (
        _observation("mouse", 1, 1), _observation("mouse", 1, 2),
        _observation("other", 1, 3), _observation("other", 1, 4),
    )
    result = analyze_receiver_child_routing(
        _experiment(observations=observations),
        route_labels={"mouse": "selected-mouse", "other": "other-child"},
    )
    assert not any(item.offset == 1 for item in result.routing_analysis.target_field_candidates)


def _dialogue(*, ambiguous=False, request_tag=1, response_tag=1):
    request = DialogueObservation(
        "out", "physical", "if1", "usb-hid", Direction.OUT,
        "mouse-config", 0x10, 1, 1_000, 1, b"\x10\x01", transaction_tag=request_tag,
    )
    response = DialogueObservation(
        "in", "physical", "if2", "usb-hid", Direction.IN,
        "telemetry", 0x11, 1, 3_300, 2, b"\x11\x01", transaction_tag=response_tag,
    )
    return DialogueRecord(
        DialogueKind.RESPONSE, response, request=request,
        confidence="repeated", ambiguous=ambiguous,
        reason="ambiguous correlation" if ambiguous else "transaction tag and timing agree",
    )


def test_cross_interface_response_preserves_route_asymmetry():
    result = analyze_receiver_child_routing(_experiment(dialogues=(_dialogue(),)))
    evidence = next(
        item for item in result.routing_evidence
        if item.relationship is RoutingRelationship.REQUEST_RESPONSE
    )
    assert evidence.source_route.channel == "if1"
    assert evidence.destination_route.channel == "if2"
    edge = next(
        item for item in result.routing_analysis.graph.edges
        if item.relationship is RoutingRelationship.REQUEST_RESPONSE
    )
    assert edge.asymmetric is True


def test_selected_device_usb_interface_and_endpoint_are_mapped_without_claiming_an_owner():
    def usb(sequence, fingerprint, interface, endpoint):
        return UsbObservation(
            "capture", sequence, sequence * 100, CaptureSource.SYNTHETIC_TEST,
            1, 2, interface, endpoint, UsbDirection.IN, UsbTransferType.INTERRUPT,
            UrbEventType.COMPLETE, sequence, 0, None, 2, 2, b"\x10\x01",
            fingerprint,
        )

    experiment = replace(
        _experiment(),
        usb_observations=(
            usb(1, "receiver-model", 2, 0x81),
            usb(2, "unrelated-device", 7, 0x87),
        ),
    )
    result = analyze_receiver_child_routing(experiment, receiver_identity="usb:046d:c53f")
    usb_evidence = [item for item in result.routing_evidence if item.source_route.transport.startswith("usb:")]
    assert len(usb_evidence) == 1
    assert usb_evidence[0].source_route.interface_number == 2
    assert usb_evidence[0].source_route.endpoint == 0x81
    assert usb_evidence[0].status is RoutingStatus.UNMAPPED
    assert usb_evidence[0].child_identity_candidate is None


def test_timing_strengthens_existing_dialogue_but_does_not_confirm_owner():
    summary = TimingSummary(
        TimingRelationship.REQUEST_RESPONSE_LATENCY, "route", None,
        3, 3, 2_200_000, 2_300_000, 2_400_000, 200_000, (),
        TimingClassification.SHORT_DELAY, "observed",
    )
    timing = ProtocolTimingProfile((), (summary,), (), (), (), ())
    result = analyze_receiver_child_routing(
        _experiment(dialogues=(_dialogue(),), timing=timing),
    )
    evidence = next(item for item in result.routing_evidence if item.relationship is RoutingRelationship.REQUEST_RESPONSE)
    assert evidence.confidence == "timing-supported"
    assert evidence.status is RoutingStatus.CANDIDATE_ROUTE
    assert evidence.child_identity_candidate is None


def test_async_push_on_another_interface_is_correlated_without_merging_interfaces():
    controlled = DialogueObservation(
        "action", "physical", "if1", "usb-hid", Direction.OUT,
        "mouse-config", 0x10, 1, 1_000, 1, b"\x10",
    )
    pushed = DialogueObservation(
        "push", "physical", "if3", "usb-hid", Direction.IN,
        "telemetry", 0x13, 1, 2_000, 2, b"\x13\x01",
    )
    record = PushedStateRecord(
        pushed, "dpi", 1600, StateFreshness.FRESH,
        controlled_action=controlled,
    )
    result = analyze_receiver_child_routing(_experiment(pushed=(record,)))
    evidence = next(item for item in result.routing_evidence if item.relationship is RoutingRelationship.ASYNC_RESPONSE)
    assert evidence.source_route.channel == "if1"
    assert evidence.destination_route.channel == "if3"
    assert evidence.status is RoutingStatus.CANDIDATE_ROUTE


def test_negative_control_separates_children_and_ambiguous_routes_are_refused():
    observations = (
        _observation("selected", 1, 1), _observation("selected", 1, 2),
        _observation("negative-other", 2, 3), _observation("negative-other", 2, 4),
    )
    separated = analyze_receiver_child_routing(
        _experiment(observations=observations),
        route_labels={"selected": "selected-mouse", "negative-other": "other-child"},
        other_child_available=True,
    )
    assert any(item.status is RoutingStatus.CONFIRMED_ROUTE for item in separated.routing_evidence)

    ambiguous = _route_evidence(
        "ambiguous", 1, status=RoutingStatus.AMBIGUOUS_ROUTE,
        ambiguity=("two children produce indistinguishable traffic",),
    )
    unresolved = analyze_receiver_child_routing(
        _experiment(), supplied_evidence=(ambiguous,), other_child_available=True,
    )
    assert unresolved.routing_analysis.ambiguities
    assert unresolved.next_plan.selected_action.action_id == "OTHER_CHILD_ROUTE_CONTROL"
    assert unresolved.routing_evidence[0].write_authorized is False


def test_generation_isolation_and_explicit_route_rediscovery():
    with pytest.raises(ValueError, match="current generation"):
        analyze_receiver_child_routing(
            _experiment(generation=2),
            supplied_evidence=(_route_evidence("old", 1, generation=1),),
        )

    old = analyze_receiver_child_routing(
        _experiment(generation=1), supplied_evidence=(_route_evidence("old", 1),),
    ).routing_analysis.graph
    new_experiment = LabExperiment(
        "routing-new", CONTEXT, 2, "routing fixture", None, (), (),
    )
    new_evidence = replace(
        _route_evidence("new", 1, generation=2, interface=3), experiment_id="routing-new",
    )
    new = analyze_receiver_child_routing(
        new_experiment, supplied_evidence=(new_evidence,),
    ).routing_analysis.graph
    comparison = compare_route_rediscovery(old, new)
    assert comparison.old_generation == 1
    assert comparison.new_generation == 2
    assert comparison.stable_routes
    assert "logical_child:child 1" in comparison.remapped_routes
    assert comparison.automatically_carried_forward is False


def test_persistence_can_support_but_not_prove_receiver_ownership():
    persistence = PersistenceAssessment(
        "dpi", EffectState.STATE_PHYSICALLY_EFFECTIVE,
        (PersistenceClassification.POWER_CYCLE_PERSISTENT,), PersistenceLevel.POWER_CYCLE,
        "effect", (), (), (), LabStopReason.POWER_CYCLE_PERSISTENCE_CONFIRMED,
        None, RestorationPlan(False, 800, 800, None, True), 1.0, "timing",
    )
    ambiguous = _route_evidence(
        "ambiguous", "receiver-local", status=RoutingStatus.AMBIGUOUS_ROUTE,
        ambiguity=("mouse or receiver ownership remains ambiguous",),
    )
    result = analyze_receiver_child_routing(
        _experiment(persistence=persistence), supplied_evidence=(ambiguous,),
    )
    assert any("supports but does not prove" in item for item in result.routing_analysis.ambiguities)
    assert all(item.status is not RoutingStatus.CONFIRMED_ROUTE for item in result.routing_evidence)


def test_replay_is_deterministic_private_and_never_authorizes_writes():
    result = analyze_receiver_child_routing(
        _experiment(), supplied_evidence=(_route_evidence("private", 1),),
    )
    first = result.replay_fixture()
    assert first == result.replay_fixture()
    serialized = repr(first).lower()
    assert "/dev/" not in serialized
    assert "keyboard" not in serialized
    assert "clipboard" not in serialized
    assert "screen" not in serialized
    assert first["routing_evidence"]
    assert first["routing_analysis"]
    assert result.write_authorized is False
