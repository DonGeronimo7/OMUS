"""Research orchestration policy for Automatic Discovery.

This module deliberately separates three things that were historically mixed:

* runtime authority -- only PROVEN operations may write during normal use;
* reversible research probes -- DEMONSTRATED exact-model grammars may be tested
  under explicit setup/research authorization; and
* deeper read-side learning -- used when an unknown device has no executable
  write grammar yet, so Mouse Control can still learn stage events/notifications.

A structural repertoire match is evidence about *where to investigate*.  It is
never write authority by itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .learned_operations import LearnedOperationState
from .information_gain import ExperimentChoice, ExperimentHypothesis, choose_experiment
from .protocol_grammar import SemanticBehavior, WriteScope


class ResearchStatus(str, Enum):
    PROVEN = "proven"
    REVERSIBLE_PROBE_READY = "reversible-probe-ready"
    STRUCTURAL_CANDIDATE = "structural-candidate"
    KNOWN_READ_ONLY = "known-read-only"
    NO_EVIDENCE = "no-evidence"


@dataclass(frozen=True)
class CapabilityResearchPlan:
    semantic: str
    status: ResearchStatus
    candidate_transports: tuple[str, ...] = ()
    reason: str = ""

    @property
    def probe_ready(self) -> bool:
        return self.status is ResearchStatus.REVERSIBLE_PROBE_READY

    @property
    def writable(self) -> bool:
        return self.status is ResearchStatus.PROVEN


@dataclass(frozen=True)
class DiscoveryResearchPlan:
    dpi: CapabilityResearchPlan
    polling: CapabilityResearchPlan
    unknown_protocol: bool
    deeper_learning_recommended: bool
    reason: str
    next_experiment: ExperimentChoice | None = None

    @property
    def reversible_probe_available(self) -> bool:
        return self.dpi.probe_ready or self.polling.probe_ready


def _candidate_transports(repertoire_candidates: Iterable[object]) -> tuple[str, ...]:
    transports: set[str] = set()
    for candidate in repertoire_candidates:
        family = getattr(candidate, "family", None)
        if family is None or getattr(family, "write_scope", WriteScope.NEVER) is WriteScope.NEVER:
            continue
        for transport in getattr(family, "transports", ()):
            transports.add(getattr(transport, "value", str(transport)))
    return tuple(sorted(transports))


def _next_repertoire_experiment(repertoire_candidates: Iterable[object]) -> ExperimentChoice | None:
    """Choose the read-only transport observation that best splits candidates."""

    candidates = tuple(repertoire_candidates)
    transports = sorted({
        getattr(transport, "value", str(transport))
        for candidate in candidates
        for transport in getattr(getattr(candidate, "family", None), "transports", ())
    })
    hypotheses = tuple(
        ExperimentHypothesis(
            name=getattr(candidate.family, "name", repr(candidate.family)),
            weight=max(1.0, float(getattr(candidate, "score", 1))),
            predicted_outcomes={
                f"observe:{transport}": transport in {
                    getattr(item, "value", str(item))
                    for item in getattr(candidate.family, "transports", ())
                }
                for transport in transports
            },
        )
        for candidate in candidates
        if getattr(candidate, "family", None) is not None
    )
    return choose_experiment(hypotheses)


def build_discovery_research_plan(
    result,
    repertoire_candidates,
    *,
    learned_operation_store,
    learned_polling_store,
) -> DiscoveryResearchPlan:
    """Build the next safe research step from evidence already collected.

    This function never opens hardware and never grants authority.  Its output is
    an auditable orchestration decision consumed by setup.
    """
    protocol_known = result.protocol is not None
    repertoire_candidates = tuple(repertoire_candidates)
    transports = _candidate_transports(repertoire_candidates)
    next_experiment = _next_repertoire_experiment(repertoire_candidates)

    def capability_proven(name: str) -> bool:
        capability = result.capabilities.get(name)
        return bool(capability and capability.writable)

    if protocol_known:
        dpi = CapabilityResearchPlan(
            "dpi",
            ResearchStatus.PROVEN if capability_proven("dpi") else ResearchStatus.KNOWN_READ_ONLY,
            reason=(
                "Known protocol exposes a proven writable DPI operation."
                if capability_proven("dpi")
                else "Known protocol was identified; its DPI policy remains authoritative."
            ),
        )
        polling = CapabilityResearchPlan(
            "report_rate",
            ResearchStatus.PROVEN if capability_proven("report_rate") else ResearchStatus.KNOWN_READ_ONLY,
            reason=(
                "Known protocol exposes a proven writable polling operation."
                if capability_proven("report_rate")
                else "Known protocol was identified; its polling policy remains authoritative."
            ),
        )
        return DiscoveryResearchPlan(
            dpi=dpi,
            polling=polling,
            unknown_protocol=False,
            deeper_learning_recommended=False,
            reason="A proven protocol implementation is already bound; do not substitute speculative generic learning.",
            next_experiment=None,
        )

    dpi_status = ResearchStatus.PROVEN if capability_proven("dpi") else ResearchStatus.NO_EVIDENCE
    dpi_reason = "PROVEN exact-model learned DPI operation is already available." if capability_proven("dpi") else ""
    if dpi_status is not ResearchStatus.PROVEN:
        found = learned_operation_store.find_for_physical(
            result.device,
            behavior=SemanticBehavior.DPI_VALUE,
            proven_only=False,
        )
        if found is not None:
            _path, operation = found
            if operation.state is LearnedOperationState.DEMONSTRATED:
                dpi_status = ResearchStatus.REVERSIBLE_PROBE_READY
                dpi_reason = (
                    "An exact-model DEMONSTRATED DPI grammar exists. Discovery may run a bounded reversible "
                    "generic probe, but normal runtime writes remain disabled until physical promotion."
                )

    polling_status = ResearchStatus.PROVEN if capability_proven("report_rate") else ResearchStatus.NO_EVIDENCE
    polling_reason = (
        "PROVEN exact-model learned polling state machine is already available."
        if capability_proven("report_rate") else ""
    )
    if polling_status is not ResearchStatus.PROVEN:
        found = learned_polling_store.find_for_physical(result.device, proven_only=False)
        if found is not None:
            _path, operation = found
            state = getattr(operation, "state", None)
            if getattr(state, "value", state) == "demonstrated":
                polling_status = ResearchStatus.REVERSIBLE_PROBE_READY
                polling_reason = (
                    "An exact-model DEMONSTRATED polling state machine exists. Discovery may run its bounded "
                    "generic replay/promotion methodology; runtime writes remain disabled until promotion."
                )

    if transports:
        if dpi_status is ResearchStatus.NO_EVIDENCE:
            dpi_status = ResearchStatus.STRUCTURAL_CANDIDATE
            dpi_reason = (
                "Descriptor/repertoire evidence exposes a plausible writable transport, but no executable DPI "
                "transaction grammar has been demonstrated yet."
            )
        if polling_status is ResearchStatus.NO_EVIDENCE:
            polling_status = ResearchStatus.STRUCTURAL_CANDIDATE
            polling_reason = (
                "Descriptor/repertoire evidence exposes a plausible writable transport, but no executable polling "
                "transaction grammar has been demonstrated yet."
            )

    if not dpi_reason:
        dpi_reason = "No evidence-backed DPI write transaction could be constructed during automatic discovery."
    if not polling_reason:
        polling_reason = "No evidence-backed polling write transaction could be constructed during automatic discovery."

    probe_ready = (
        dpi_status is ResearchStatus.REVERSIBLE_PROBE_READY
        or polling_status is ResearchStatus.REVERSIBLE_PROBE_READY
    )
    any_proven = (
        dpi_status is ResearchStatus.PROVEN
        or polling_status is ResearchStatus.PROVEN
    )
    # Deeper stage learning is the fallback only after an unknown device has no
    # immediately executable generic research probe.  Structural candidates are
    # still useful inputs to deeper learning; they do not block it.
    deeper = not any_proven and not probe_ready
    reason = (
        "A demonstrated reversible write grammar is ready for research verification before deeper learning."
        if probe_ready
        else (
            "Automatic Discovery found no executable generic write grammar. Offer deeper protocol learning so "
            "stage/event behavior can be calibrated and persisted without granting write authority."
            if deeper
            else "Writable authority is already proven for at least one hardware capability."
        )
    )
    return DiscoveryResearchPlan(
        dpi=CapabilityResearchPlan("dpi", dpi_status, transports, dpi_reason),
        polling=CapabilityResearchPlan("report_rate", polling_status, transports, polling_reason),
        unknown_protocol=True,
        deeper_learning_recommended=deeper,
        reason=reason,
        next_experiment=next_experiment if deeper else None,
    )
