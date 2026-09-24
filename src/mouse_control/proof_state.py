# SPDX-License-Identifier: AGPL-3.0-or-later
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


class CapabilityStage(str, Enum):
    """A projection of concrete predicates, not another experiment lifecycle."""

    UNKNOWN = "unknown"
    READ_PROVEN = "read_proven"
    WRITE_SEMANTICS_KNOWN = "write_semantics_known"
    WRITE_BOUNDED = "write_bounded"
    WRITE_VERIFIED = "write_verified"
    PERSISTENCE_PROVEN = "persistence_proven"


@dataclass(frozen=True)
class CapabilityProof:
    """Current-binding receipt for one operation supplied by a trusted driver.

    Never deserialize this object as authority. Persisted receipts are knowledge
    only: a current owner must establish every predicate again. An implementation
    may supply prior PROVEN verification instead of issuing a ceremonial write.
    Runtime setters still perform their own bounds, policy and readback checks.
    """

    operation: OperationProof
    read_proven: bool = False
    capability_identified: bool = False
    semantics_known: bool = False
    values_bounded: bool = False
    packet_known: bool = False
    shared_state_safe: bool = False
    confirmation_known: bool = False
    failure_known: bool = False
    routing_unambiguous: bool = False
    compatible: bool = False
    volatile_operation: bool = False
    runtime_policy_satisfied: bool = False
    # Persistence is deliberately orthogonal to ordinary write verification.
    persistence_facts: tuple[str, ...] = ()

    @property
    def predicates(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in (
            "read_proven", "capability_identified", "semantics_known",
            "values_bounded", "packet_known", "shared_state_safe",
            "confirmation_known", "failure_known", "routing_unambiguous",
            "compatible", "volatile_operation", "runtime_policy_satisfied",
        )}

    @property
    def blockers(self) -> tuple[str, ...]:
        missing = tuple(name for name, passed in self.predicates.items() if not passed)
        if not self.operation.write_authorized or not self.operation.evidence:
            missing += ("independent_operation_proof",)
        return missing

    @property
    def write_authorized(self) -> bool:
        return not self.blockers

    @property
    def persistent_authorized(self) -> bool:
        required = {"save_commit", "profile_bank", "power_cycle", "flash_behavior",
                    "persistence_mode", "wear_limits", "safe_recovery"}
        demonstrated = self.operation.demonstrated
        return (self.write_authorized and required.issubset(self.persistence_facts)
                and demonstrated.reconnect_persistent is EvidenceTruth.TRUE
                and demonstrated.power_cycle_persistent is EvidenceTruth.TRUE
                and demonstrated.recovery_verified is EvidenceTruth.TRUE)

    @property
    def stage(self) -> CapabilityStage:
        if self.persistent_authorized:
            return CapabilityStage.PERSISTENCE_PROVEN
        if self.write_authorized:
            return CapabilityStage.WRITE_VERIFIED
        if not self.read_proven:
            return CapabilityStage.UNKNOWN
        if not (self.capability_identified and self.semantics_known):
            return CapabilityStage.READ_PROVEN
        if not (self.values_bounded and self.packet_known and self.shared_state_safe):
            return CapabilityStage.WRITE_SEMANTICS_KNOWN
        return CapabilityStage.WRITE_BOUNDED

    def explain(self) -> dict[str, object]:
        return {"operation": self.operation.operation, "stage": self.stage.value,
                "predicates": self.predicates, "blockers": list(self.blockers),
                "sources": list(self.operation.evidence),
                "persistent_authorized": self.persistent_authorized}
