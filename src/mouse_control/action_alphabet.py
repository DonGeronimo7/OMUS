"""Conservative symbolic action alphabet derived from PeripheralIR.

The alphabet is intentionally semantic.  It contains no transport bytes and no
write authority; it only tells a state learner which *legal questions* and
bounded neighbor experiments exist.  Compilation/execution remains the job of
``discovery_execution`` plus the existing ExperimentAuthority/TransactionEngine.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence

from .experiment_authority import StorageEffect
from .peripheral_ir import CapabilityKind, PeripheralIR


class SymbolicActionKind(str, Enum):
    QUERY = "query"
    SET_NEIGHBOR = "set_neighbor"


@dataclass(frozen=True)
class SymbolicAction:
    name: str
    kind: SymbolicActionKind
    capability: CapabilityKind
    value: int | None = None
    evidence: tuple[str, ...] = ()

    @property
    def runtime_write_authorized(self) -> bool:
        return False


def synthesize_action_alphabet(
    ir: PeripheralIR,
    baselines: Mapping[CapabilityKind, int],
) -> tuple[SymbolicAction, ...]:
    """Return safe semantic inputs for incremental active/state learning.

    Every capability receives a query symbol.  A setter symbol is emitted only
    when the baseline is legal and the IR already records volatile storage,
    rollback and verification semantics.  The setter is restricted to the
    nearest legal neighbor; this function never invents arbitrary values.
    """

    result: list[SymbolicAction] = []
    for capability in ir.capabilities:
        result.append(SymbolicAction(
            name=f"QUERY_{capability.kind.value.upper()}",
            kind=SymbolicActionKind.QUERY,
            capability=capability.kind,
            evidence=capability.evidence,
        ))
        baseline = baselines.get(capability.kind)
        if baseline is None:
            continue
        if not capability.domain.contains(baseline):
            raise ValueError(f"{capability.kind.value} baseline is outside the IR domain")
        if (
            capability.storage is not StorageEffect.VOLATILE
            or not capability.rollback.strip()
            or not capability.verification.strip()
        ):
            continue
        target = capability.domain.neighbor(baseline)
        if target is None:
            continue
        result.append(SymbolicAction(
            name=f"SET_{capability.kind.value.upper()}_{target}",
            kind=SymbolicActionKind.SET_NEIGHBOR,
            capability=capability.kind,
            value=target,
            evidence=capability.evidence,
        ))
    return tuple(result)


def extend_action_alphabet(
    existing: Sequence[SymbolicAction],
    additions: Sequence[SymbolicAction],
) -> tuple[SymbolicAction, ...]:
    """Incrementally extend an alphabet without forcing state relearning."""

    result = list(existing)
    seen = {(item.kind, item.capability, item.value) for item in existing}
    for item in additions:
        key = (item.kind, item.capability, item.value)
        if key not in seen:
            result.append(item)
            seen.add(key)
    return tuple(result)
