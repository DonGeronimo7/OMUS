"""Canonical offline Discovery decision pipeline and explainable trace."""
from __future__ import annotations
from dataclasses import dataclass
from .active_fingerprint import (FingerprintDecision, FingerprintHypothesis, FingerprintProbe,
                                 choose_fingerprint_probe)
from .advice_compiler import DiscoveryAdvice, compile_protocol_advice
from .evidence_graph import EvidenceGraph
from .genome_catalog import compile_family_genome
from .grammar_inference import GrammarAlternative, TraceExample, infer_grammars
from .interface_quarantine import (InterfaceAccess, InterfaceAdmission, InterfacePolicy,
                                   ResearchInterface, admit_interface)
from .protocol_genome import ingest_genome_device
from .protocol_grammar import ProtocolFamily
from .protocol_prior import import_protocol_family_prior


@dataclass(frozen=True)
class DecisionStep:
    phase: str
    decision: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class DiscoveryResult:
    admission: InterfaceAdmission
    fingerprint: FingerprintDecision | None
    advice: tuple[DiscoveryAdvice, ...]
    grammars: tuple[GrammarAlternative, ...]
    genome_ids: tuple[str, ...]
    trace: tuple[DecisionStep, ...]
    human_action: str | None


def run_discovery_pipeline(graph: EvidenceGraph, *, interface: ResearchInterface,
                           current_generation: int, policies: tuple[InterfacePolicy, ...],
                           families: tuple[ProtocolFamily, ...],
                           hypotheses: tuple[FingerprintHypothesis, ...],
                           probes: tuple[FingerprintProbe, ...],
                           examples: tuple[TraceExample, ...]) -> DiscoveryResult:
    trace = []
    admission = admit_interface(interface, InterfaceAccess.READ,
                                current_generation=current_generation, policies=policies)
    trace.append(DecisionStep("interface_quarantine", "admitted" if admission.admitted else "refused",
                              admission.reasons))
    if not admission.admitted:
        return DiscoveryResult(admission, None, (), (), (), tuple(trace),
                               "review the exact interface descriptor and role")
    family_evidence = {}
    genome_ids = []
    for family in families:
        imported = import_protocol_family_prior(graph, family)
        family_evidence[family.name] = imported.evidence_ids
        genome_ids.extend(ingest_genome_device(graph, compile_family_genome(
            family, evidence=imported.evidence_ids)))
    trace.append(DecisionStep("protocol_genome", f"loaded {len(families)} family records", ()))
    fingerprint = choose_fingerprint_probe(hypotheses, probes, valid_evidence=graph.valid_ids)
    if fingerprint:
        trace.append(DecisionStep("active_fingerprint", fingerprint.probe.name,
                                  (fingerprint.reason, "mutation: none")))
    advice = compile_protocol_advice(graph, families, family_evidence=family_evidence)
    trace.append(DecisionStep("advice", f"compiled {len(advice)} operation candidates", ()))
    grammars = infer_grammars(examples)
    trace.append(DecisionStep("grammar", f"retained {len(grammars)} alternatives", ()))
    human = None
    if not fingerprint and len(hypotheses) > 1:
        human = "capture one discriminating vendor or physical action"
    elif len(grammars) > 1:
        human = "capture a value that distinguishes the remaining encodings"
    elif not grammars:
        human = "capture two attributed demonstrations of one semantic operation"
    if human:
        trace.append(DecisionStep("escalation", "human evidence required", (human,)))
    return DiscoveryResult(admission, fingerprint, advice, grammars, tuple(genome_ids),
                           tuple(trace), human)
