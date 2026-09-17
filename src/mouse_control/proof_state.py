"""Operation-scoped proof lifecycle for protocol knowledge."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProofState(str, Enum):
    UNKNOWN = "unknown"
    OBSERVED = "observed"
    RECOGNIZED = "recognized"
    DECODED = "decoded"
    HYPOTHESIZED = "hypothesized"
    EXPERIMENT_ELIGIBLE = "experiment_eligible"
    EXPERIMENTED = "experimented"
    VERIFIED = "verified"
    PROVEN = "proven"
    CONFLICTED = "conflicted"
    REVOKED = "revoked"


class ProofTransitionError(ValueError):
    """A proof transition skipped required evidence stages."""


_ORDER = (
    ProofState.UNKNOWN, ProofState.OBSERVED, ProofState.RECOGNIZED,
    ProofState.DECODED, ProofState.HYPOTHESIZED, ProofState.EXPERIMENT_ELIGIBLE,
    ProofState.EXPERIMENTED, ProofState.VERIFIED, ProofState.PROVEN,
)


@dataclass(frozen=True)
class OperationProof:
    """Proof for one semantic operation, never an entire device."""

    operation: str
    state: ProofState = ProofState.UNKNOWN
    evidence: tuple[str, ...] = ()

    @property
    def write_authorized(self) -> bool:
        return self.state is ProofState.PROVEN

    def transition(self, state: ProofState, *, evidence: str) -> "OperationProof":
        if not evidence.strip():
            raise ProofTransitionError("a proof transition requires auditable evidence")
        if state in {ProofState.CONFLICTED, ProofState.REVOKED}:
            return OperationProof(self.operation, state, self.evidence + (evidence,))
        if self.state in {ProofState.CONFLICTED, ProofState.REVOKED}:
            raise ProofTransitionError(f"{self.operation}: {self.state.value} proof cannot be promoted")
        current = _ORDER.index(self.state)
        target = _ORDER.index(state)
        if target != current + 1:
            raise ProofTransitionError(
                f"{self.operation}: invalid proof transition {self.state.value} -> {state.value}"
            )
        return OperationProof(self.operation, state, self.evidence + (evidence,))


def proof_state_from_evidence(levels: tuple[str, ...], *, conflicted: bool = False) -> ProofState:
    """Map legacy evidence levels into the richer reporting vocabulary."""
    if conflicted:
        return ProofState.CONFLICTED
    normalized = {item.lower() for item in levels}
    if "proven" in normalized:
        return ProofState.PROVEN
    if "validated" in normalized:
        return ProofState.VERIFIED
    if "correlated" in normalized:
        return ProofState.RECOGNIZED
    if "observed" in normalized:
        return ProofState.OBSERVED
    return ProofState.UNKNOWN

