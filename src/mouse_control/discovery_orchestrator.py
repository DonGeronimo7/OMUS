"""Offline orchestration of quarantine, grammar inference, and escalation."""
from __future__ import annotations
from dataclasses import dataclass
from .grammar_inference import GrammarAlternative, TraceExample, infer_grammars
from .interface_quarantine import (InterfaceAccess, InterfaceAdmission, InterfacePolicy,
                                   ResearchInterface, admit_interface)


@dataclass(frozen=True)
class DiscoveryEscalation:
    stage: str
    missing_evidence: tuple[str, ...]
    requested_human_action: str


@dataclass(frozen=True)
class DiscoveryAnalysis:
    admission: InterfaceAdmission
    grammars: tuple[GrammarAlternative, ...]
    escalation: DiscoveryEscalation | None


def analyze_unknown_interface(interface: ResearchInterface, *, current_generation: int,
                              policies: tuple[InterfacePolicy, ...],
                              examples: tuple[TraceExample, ...]) -> DiscoveryAnalysis:
    admission = admit_interface(interface, InterfaceAccess.READ,
                                current_generation=current_generation, policies=policies)
    if not admission.admitted:
        return DiscoveryAnalysis(admission, (), DiscoveryEscalation(
            "interface_quarantine", admission.reasons,
            "review the exact interface descriptor and role before active research",
        ))
    grammars = infer_grammars(examples)
    escalation = None
    if not grammars:
        escalation = DiscoveryEscalation(
            "grammar_inference", ("at least two attributed demonstrations",),
            "perform one known vendor action while capture is active",
        )
    elif len(grammars) > 1:
        escalation = DiscoveryEscalation(
            "grammar_inference", ("multiple byte-order grammars fit",),
            "capture a value whose byte order produces distinct bytes",
        )
    return DiscoveryAnalysis(admission, grammars, escalation)
