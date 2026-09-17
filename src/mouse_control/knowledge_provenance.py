"""Conflict-aware provenance records for reusable protocol knowledge."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgeClaim:
    claim_id: str
    source: str
    source_revision: str
    operation: str
    context: str
    derived_from: tuple[str, ...] = ()
    independent_evidence: tuple[str, ...] = ()
    conflicts_with: tuple[str, ...] = ()

    @property
    def conflicted(self) -> bool:
        return bool(self.conflicts_with)


def operation_conflicts(claims: tuple[KnowledgeClaim, ...], operation: str, context: str) -> tuple[KnowledgeClaim, ...]:
    """Return only conflicts affecting the requested operation/context."""
    return tuple(
        claim for claim in claims
        if claim.operation == operation and claim.context == context and claim.conflicted
    )
