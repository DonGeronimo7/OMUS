"""Conservative authorization model for bounded discovery experiments.

This module describes eligibility only.  It intentionally owns no transport or
write primitive and cannot grant runtime PROVEN authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class StorageEffect(str, Enum):
    VOLATILE = "volatile"
    PERSISTENT = "persistent"
    UNKNOWN = "unknown"


class ExperimentEligibility(str, Enum):
    BLOCKED = "blocked"
    ELIGIBLE = "eligible"


@dataclass(frozen=True)
class ExperimentSpec:
    physical_identity: str
    channel_identity: str
    protocol_context: str
    operation: str
    legal_values: tuple[int, ...]
    expected_effect: str
    restore_plan: str
    storage: StorageEffect
    idempotent: bool
    timeout_ms: int
    retries: int
    verification: str
    abort_conditions: tuple[str, ...]
    source_recipe: str | None = None

    def __post_init__(self) -> None:
        if not self.physical_identity or not self.channel_identity or not self.operation:
            raise ValueError("experiment requires exact physical, channel, and operation identity")
        if self.timeout_ms <= 0 or self.retries < 0:
            raise ValueError("experiment timeout/retries are invalid")


@dataclass(frozen=True)
class ExperimentAuthority:
    spec: ExperimentSpec
    eligibility: ExperimentEligibility
    reasons: tuple[str, ...]
    runtime_write_authorized: bool = False

    @classmethod
    def evaluate(
        cls, spec: ExperimentSpec, *, lab_mode: bool, exact_physical_match: bool,
        exact_channel_match: bool, constrained_grammar: bool, baseline_captured: bool,
    ) -> "ExperimentAuthority":
        reasons: list[str] = []
        if not lab_mode:
            reasons.append("explicit discovery/lab mode is required")
        if not exact_physical_match:
            reasons.append("physical identity is not an exact unambiguous match")
        if not exact_channel_match:
            reasons.append("configuration channel is not an exact match")
        if not (spec.source_recipe or constrained_grammar):
            reasons.append("no source-backed recipe or sufficiently constrained grammar")
        if not spec.legal_values:
            reasons.append("legal parameter domain is empty")
        if spec.storage is not StorageEffect.VOLATILE:
            reasons.append("only known-volatile experiments are currently eligible")
        if not spec.idempotent:
            reasons.append("operation is not known to be idempotent")
        if not baseline_captured or not spec.restore_plan.strip():
            reasons.append("trustworthy baseline and restore plan are required")
        if not spec.verification.strip() or spec.verification == "none":
            reasons.append("semantic verification is required")
        eligibility = ExperimentEligibility.BLOCKED if reasons else ExperimentEligibility.ELIGIBLE
        return cls(spec, eligibility, tuple(reasons), runtime_write_authorized=False)

