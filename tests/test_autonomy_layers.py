# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from mouse_control.active_fingerprint import (
    FingerprintHypothesis, FingerprintProbe, ProbeRisk,
    apply_fingerprint_observation, choose_fingerprint_probe,
)
from mouse_control.advice_compiler import AdviceKind, compile_protocol_advice
from mouse_control.autonomous_planner import (
    CandidateKind, PlannerCandidate, choose_candidate,
)
from mouse_control.evidence_graph import EvidenceGraph, EvidenceNode
from mouse_control.experiment_authority import (
    ExperimentAuthority, ExperimentSpec, StorageEffect,
)
from mouse_control.family_equivalence import (
    EquivalenceObservation, EquivalenceScope, infer_equivalence,
)
from mouse_control.protocol_prior import import_protocol_family_prior
from mouse_control.protocol_repertoire import DEFAULT_REPERTOIRE
from mouse_control.reactive_model import (
    OrderedObservation, OrderedStep, ReactiveState, infer_ordered_grammars,
)


def evidence(graph: EvidenceGraph, claim: str = "fixture") -> str:
    return graph.add(EvidenceNode("source", claim, "test"))


def family(name: str):
    return next(item for item in DEFAULT_REPERTOIRE if item.name == name)


def test_advice_compiler_preserves_provenance_and_never_authorizes_writes() -> None:
    graph = EvidenceGraph()
    fixture = family("wlmouse-beastx-pages")
    imported = import_protocol_family_prior(graph, fixture)
    advice = compile_protocol_advice(
        graph, (fixture,), family_evidence={fixture.name: imported.evidence_ids}
    )
    assert advice
    assert any(item.kind is AdviceKind.REVERSIBLE_EXPERIMENT for item in advice)
    assert all(item.evidence == imported.evidence_ids for item in advice)
    assert all(not item.runtime_write_authorized for item in advice)


def test_invalidated_advice_is_not_compiled() -> None:
    graph = EvidenceGraph()
    fixture = family("darmoshark-dms")
    imported = import_protocol_family_prior(graph, fixture)
    graph.invalidate(imported.source_ids[0], "withdrawn")
    assert compile_protocol_advice(
        graph, (fixture,), family_evidence={fixture.name: imported.evidence_ids}
    ) == ()


def test_fingerprint_prefers_passive_discriminator_before_safe_read() -> None:
    graph = EvidenceGraph()
    eid = evidence(graph)
    hypotheses = (
        FingerprintHypothesis("a", {"descriptor": "x", "query": 1}, (eid,)),
        FingerprintHypothesis("b", {"descriptor": "y", "query": 2}, (eid,)),
    )
    decision = choose_fingerprint_probe(hypotheses, (
        FingerprintProbe("query", ProbeRisk.SAFE_READ, 1, (eid,)),
        FingerprintProbe("descriptor", ProbeRisk.PASSIVE, 10, (eid,)),
    ), valid_evidence=graph.valid_ids)
    assert decision is not None and decision.probe.name == "descriptor"
    assert apply_fingerprint_observation(hypotheses, "descriptor", "y") == (hypotheses[1],)


def test_fingerprint_refuses_invalidated_or_over_risk_probes() -> None:
    graph = EvidenceGraph()
    eid = evidence(graph)
    graph.invalidate(eid, "stale corpus")
    hypotheses = (
        FingerprintHypothesis("a", {"write": 1}, (eid,)),
        FingerprintHypothesis("b", {"write": 2}, (eid,)),
    )
    assert choose_fingerprint_probe(
        hypotheses, (FingerprintProbe("write", ProbeRisk.REVERSIBLE, 1, (eid,)),),
        valid_evidence=graph.valid_ids,
    ) is None


def eligible_authority() -> ExperimentAuthority:
    spec = ExperimentSpec(
        "physical", "channel", "protocol", "set-dpi", (800, 1600), "dpi",
        "restore baseline", StorageEffect.VOLATILE, True, 100, 0, "readback",
        ("disconnect",), source_recipe="reviewed source",
    )
    return ExperimentAuthority.evaluate(
        spec, lab_mode=True, exact_physical_match=True, exact_channel_match=True,
        constrained_grammar=True, baseline_captured=True,
    )


def candidate(name: str, eid: str, **changes) -> PlannerCandidate:
    values = dict(
        name=name, kind=CandidateKind.READ, information_gain=3.0, semantic_value=1.0,
        transfer_value=0.0, mutation_bytes=0, state_uncertainty=0.0,
        runtime_risk=0.0, cost=1.0, generation=4, evidence=(eid,),
    )
    values.update(changes)
    return PlannerCandidate(**values)


def test_planner_ranks_safe_candidates_and_refuses_stale_generation() -> None:
    graph = EvidenceGraph()
    eid = evidence(graph)
    result = choose_candidate((
        candidate("stale", eid, information_gain=99, generation=3),
        candidate("read", eid),
    ), current_generation=4, valid_evidence=graph.valid_ids)
    assert result.candidate is not None and result.candidate.name == "read"
    assert result.refused == (("stale", ("stale connection generation",)),)


def test_planner_requires_existing_authority_baseline_verifier_and_rollback() -> None:
    graph = EvidenceGraph()
    eid = evidence(graph)
    incomplete = candidate("experiment", eid, kind=CandidateKind.REVERSIBLE_EXPERIMENT)
    result = choose_candidate((incomplete,), current_generation=4, valid_evidence=graph.valid_ids)
    assert result.candidate is None
    assert len(result.refused[0][1]) == 4
    complete = candidate(
        "experiment", eid, kind=CandidateKind.REVERSIBLE_EXPERIMENT,
        authority=eligible_authority(), has_baseline=True, has_verifier=True, has_rollback=True,
    )
    assert choose_candidate(
        (complete,), current_generation=4, valid_evidence=graph.valid_ids
    ).candidate == complete


def equivalence(eid: str, *, codec: str = "u16") -> EquivalenceObservation:
    return EquivalenceObservation(
        "model-a", "model-b", "query-set-readback", codec, "echo-and-state",
        ("host-mode",), "canonical-readback", (eid,),
    )


def test_family_equivalence_is_scoped_and_non_authorizing() -> None:
    graph = EvidenceGraph()
    ids = tuple(evidence(graph, f"source-{index}") for index in range(4))
    result = infer_equivalence(
        tuple(equivalence(eid) for eid in ids),
        requested_scope=EquivalenceScope.PROTOCOL_FAMILY,
        valid_evidence=graph.valid_ids,
    )
    assert result.blockers == ()
    assert not result.runtime_write_authorized


def test_family_non_equivalence_and_invalidated_evidence_are_explicit() -> None:
    graph = EvidenceGraph()
    left, right = evidence(graph, "left"), evidence(graph, "right")
    graph.invalidate(right, "retracted")
    result = infer_equivalence(
        (equivalence(left), equivalence(right, codec="lookup")),
        requested_scope=EquivalenceScope.EXACT_MODEL,
        valid_evidence=graph.valid_ids,
    )
    assert "non-equivalent codec" in result.blockers
    assert "missing or invalidated evidence" in result.blockers


def ordered(eid: str, *, final: int = 1600, generation: int = 4) -> OrderedObservation:
    return OrderedObservation(
        "set-dpi", generation, ReactiveState.from_mapping({"mode": "host", "dpi": 800}),
        (
            OrderedStep("query", ReactiveState.from_mapping({"mode": "host", "dpi": 800}), 2),
            OrderedStep("set", ReactiveState.from_mapping({"mode": "host", "dpi": final}), 5),
            OrderedStep("readback", ReactiveState.from_mapping({"mode": "host", "dpi": final}), 3),
            OrderedStep("restore", ReactiveState.from_mapping({"mode": "host", "dpi": 800}), 5),
        ), True, (eid,),
    )


def test_ordered_learner_preserves_sequence_preconditions_timing_and_session_lifetime() -> None:
    graph = EvidenceGraph()
    first, second = evidence(graph, "trace-a"), evidence(graph, "trace-b")
    result = infer_ordered_grammars((ordered(first), ordered(second)))
    assert result.ambiguous_operations == ()
    grammar = result.grammars[0]
    assert grammar.actions == ("query", "set", "readback", "restore")
    assert grammar.maximum_delay_ms == (2, 5, 3, 5)
    assert grammar.generation_lifetime and grammar.restore_required
    assert grammar.preconditions.as_dict()["mode"] == "host"
    assert not grammar.runtime_write_authorized


def test_ordered_learner_abstains_on_unexplained_same_prestate_conflict() -> None:
    graph = EvidenceGraph()
    first, second = evidence(graph, "trace-a"), evidence(graph, "trace-b")
    result = infer_ordered_grammars((ordered(first), ordered(second, final=3200)))
    assert result.grammars == ()
    assert result.ambiguous_operations == ("set-dpi",)
