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


class EvidenceTruth(str, Enum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class OperationEvidence:
    """Orthogonal facts demonstrated for one operation; not a proof ladder."""

    transport_accepted: EvidenceTruth = EvidenceTruth.UNKNOWN
    protocol_response_valid: EvidenceTruth = EvidenceTruth.UNKNOWN
    readable_state_changed: EvidenceTruth = EvidenceTruth.UNKNOWN
    physical_effect_verified: EvidenceTruth = EvidenceTruth.UNKNOWN
    reconnect_persistent: EvidenceTruth = EvidenceTruth.UNKNOWN
    power_cycle_persistent: EvidenceTruth = EvidenceTruth.UNKNOWN
    failure_observed: EvidenceTruth = EvidenceTruth.UNKNOWN
    side_effect_after_failure: EvidenceTruth = EvidenceTruth.UNKNOWN
    recovery_required: EvidenceTruth = EvidenceTruth.UNKNOWN
    recovery_verified: EvidenceTruth = EvidenceTruth.UNKNOWN
    evidence_source_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if any(not item.strip() for item in self.evidence_source_ids):
            raise ValueError("evidence source IDs must be non-empty")


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
    demonstrated: OperationEvidence = OperationEvidence()

    @property
    def write_authorized(self) -> bool:
        return self.state is ProofState.PROVEN

    def transition(self, state: ProofState, *, evidence: str) -> "OperationProof":
        if not evidence.strip():
            raise ProofTransitionError("a proof transition requires auditable evidence")
        if state in {ProofState.CONFLICTED, ProofState.REVOKED}:
            return OperationProof(
                self.operation, state, self.evidence + (evidence,), self.demonstrated
            )
        if self.state in {ProofState.CONFLICTED, ProofState.REVOKED}:
            raise ProofTransitionError(f"{self.operation}: {self.state.value} proof cannot be promoted")
        current = _ORDER.index(self.state)
        target = _ORDER.index(state)
        if target != current + 1:
            raise ProofTransitionError(
                f"{self.operation}: invalid proof transition {self.state.value} -> {state.value}"
            )
        return OperationProof(
            self.operation, state, self.evidence + (evidence,), self.demonstrated
        )

    def with_demonstrated(self, demonstrated: OperationEvidence) -> "OperationProof":
        return OperationProof(self.operation, self.state, self.evidence, demonstrated)


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
