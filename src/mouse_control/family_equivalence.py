"""Evidence-scoped protocol-family equivalence hypotheses."""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Iterable


class EquivalenceScope(IntEnum):
    EXACT_INSTANCE = 0
    EXACT_MODEL = 1
    FIRMWARE_FAMILY = 2
    RECEIVER_FAMILY = 3
    PROTOCOL_FAMILY = 4


@dataclass(frozen=True)
class EquivalenceObservation:
    left: str
    right: str
    grammar: str
    codec: str
    reply_semantics: str
    prerequisites: tuple[str, ...]
    verification: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class FamilyEquivalence:
    left: str
    right: str
    scope: EquivalenceScope
    evidence: tuple[str, ...]
    blockers: tuple[str, ...]

    @property
    def runtime_write_authorized(self) -> bool:
        return False


def infer_equivalence(
    observations: Iterable[EquivalenceObservation], *, requested_scope: EquivalenceScope,
    valid_evidence: frozenset[str],
) -> FamilyEquivalence:
    items = tuple(observations)
    if not items:
        raise ValueError("equivalence requires observations")
    pair = (items[0].left, items[0].right)
    blockers: list[str] = []
    if any((item.left, item.right) != pair for item in items):
        blockers.append("mixed device pairs")
    fields = ("grammar", "codec", "reply_semantics", "prerequisites", "verification")
    for field in fields:
        if len({getattr(item, field) for item in items}) != 1:
            blockers.append(f"non-equivalent {field}")
    evidence = tuple(dict.fromkeys(ref for item in items for ref in item.evidence))
    if not evidence or any(ref not in valid_evidence for ref in evidence):
        blockers.append("missing or invalidated evidence")
    minimum = {EquivalenceScope.EXACT_INSTANCE: 1, EquivalenceScope.EXACT_MODEL: 2,
               EquivalenceScope.FIRMWARE_FAMILY: 3, EquivalenceScope.RECEIVER_FAMILY: 3,
               EquivalenceScope.PROTOCOL_FAMILY: 4}[requested_scope]
    if len(items) < minimum:
        blockers.append(f"scope requires at least {minimum} independent observations")
    return FamilyEquivalence(pair[0], pair[1], requested_scope, evidence, tuple(blockers))
