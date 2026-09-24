"""Rank bounded Discovery candidates without executing or authorizing them."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .experiment_authority import ExperimentAuthority, ExperimentEligibility


class CandidateKind(str, Enum):
    PASSIVE = "passive"
    READ = "read"
    REVERSIBLE_EXPERIMENT = "reversible_experiment"


@dataclass(frozen=True)
class PlannerCandidate:
    name: str
    kind: CandidateKind
    information_gain: float
    semantic_value: float
    transfer_value: float
    mutation_bytes: int
    state_uncertainty: float
    runtime_risk: float
    cost: float
    generation: int
    evidence: tuple[str, ...]
    authority: ExperimentAuthority | None = None
    has_baseline: bool = False
    has_verifier: bool = False
    has_rollback: bool = False

    @property
    def runtime_write_authorized(self) -> bool:
        return False


@dataclass(frozen=True)
class PlannerDecision:
    candidate: PlannerCandidate | None
    refused: tuple[tuple[str, tuple[str, ...]], ...]


def choose_candidate(
    candidates: Iterable[PlannerCandidate], *, current_generation: int,
    valid_evidence: frozenset[str], maximum_candidates: int = 128,
) -> PlannerDecision:
    """Choose a deterministic safe candidate and explain every refusal."""

    items = tuple(candidates)
    if len(items) > maximum_candidates:
        raise ValueError("candidate search bound exceeded")
    admitted: list[PlannerCandidate] = []
    refused: list[tuple[str, tuple[str, ...]]] = []
    for item in items:
        reasons: list[str] = []
        if item.generation != current_generation:
            reasons.append("stale connection generation")
        if not item.evidence or any(ref not in valid_evidence for ref in item.evidence):
            reasons.append("missing or invalidated evidence")
        if item.kind is CandidateKind.REVERSIBLE_EXPERIMENT:
            if item.authority is None or item.authority.eligibility is not ExperimentEligibility.ELIGIBLE:
                reasons.append("existing ExperimentAuthority did not admit candidate")
            if not item.has_baseline:
                reasons.append("baseline missing")
            if not item.has_verifier:
                reasons.append("success/failure verifier missing")
            if not item.has_rollback:
                reasons.append("rollback plan missing")
        if reasons:
            refused.append((item.name, tuple(reasons)))
        else:
            admitted.append(item)
    if not admitted:
        return PlannerDecision(None, tuple(refused))
    def score(item: PlannerCandidate) -> float:
        benefit = item.information_gain + item.semantic_value + item.transfer_value
        penalty = item.mutation_bytes + item.state_uncertainty + item.runtime_risk + item.cost
        return benefit - penalty
    selected = min(admitted, key=lambda item: (-score(item), item.kind.value, item.name))
    return PlannerDecision(selected, tuple(refused))
