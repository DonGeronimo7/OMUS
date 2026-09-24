# SPDX-License-Identifier: AGPL-3.0-or-later
"""Compile sourced protocol knowledge into declarative Discovery advice.

Advice narrows research choices.  It is neither an authorization receipt nor a
capability proof, and this module deliberately has no transport access.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .evidence_graph import EvidenceGraph
from .protocol_grammar import ProtocolFamily, SafetyClass


class AdviceKind(str, Enum):
    QUERY = "query"
    REVERSIBLE_EXPERIMENT = "reversible_experiment"
    OBSERVATION = "observation"


@dataclass(frozen=True)
class DiscoveryAdvice:
    identifier: str
    family: str
    operation: str
    kind: AdviceKind
    prerequisite: tuple[str, ...]
    expected_reply: str
    hazards: tuple[str, ...]
    evidence: tuple[str, ...]
    unresolved_proof: tuple[str, ...]

    @property
    def runtime_write_authorized(self) -> bool:
        return False


def compile_protocol_advice(
    graph: EvidenceGraph,
    families: Iterable[ProtocolFamily],
    *,
    family_evidence: dict[str, tuple[str, ...]],
) -> tuple[DiscoveryAdvice, ...]:
    """Compile deterministic, provenance-bound advice from protocol families."""

    result: list[DiscoveryAdvice] = []
    for family in sorted(families, key=lambda item: item.name):
        evidence = family_evidence.get(family.name, ())
        if not evidence or any(item not in graph.valid_ids for item in evidence):
            continue
        for operation in sorted(family.operations, key=lambda item: item.name):
            if operation.safety is SafetyClass.READ_ONLY:
                kind = AdviceKind.QUERY
                unresolved = ()
            elif operation.safety is SafetyClass.REVERSIBLE:
                kind = AdviceKind.REVERSIBLE_EXPERIMENT
                unresolved = (
                    "exact live identity/interface/generation binding",
                    "baseline, readback, rollback, and physical verification",
                )
            else:
                kind = AdviceKind.OBSERVATION
                unresolved = ("operation is not admitted for autonomous execution",)
            hazards = tuple(filter(None, (
                "static evidence is not write authority",
                "persistent-state risk" if operation.automatic_experiment_allowed is False else "",
            )))
            result.append(DiscoveryAdvice(
                identifier=f"{family.name}:{operation.name}",
                family=family.name,
                operation=operation.name,
                kind=kind,
                prerequisite=tuple(operation.prerequisite),
                expected_reply=f"request_length={operation.request_length}",
                hazards=hazards,
                evidence=evidence,
                unresolved_proof=unresolved,
            ))
    return tuple(result)
