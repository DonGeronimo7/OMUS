# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deterministic passive/read-first active protocol fingerprinting."""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Hashable, Iterable, Mapping

from .information_gain import ExperimentHypothesis, choose_experiment


class ProbeRisk(IntEnum):
    PASSIVE = 0
    SAFE_READ = 1
    REVERSIBLE = 2


@dataclass(frozen=True)
class FingerprintProbe:
    name: str
    risk: ProbeRisk
    cost: int
    evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.name or self.cost < 0 or not self.evidence:
            raise ValueError("fingerprint probes require name, nonnegative cost, and evidence")

    @property
    def runtime_write_authorized(self) -> bool:
        return False


@dataclass(frozen=True)
class FingerprintHypothesis:
    name: str
    predictions: Mapping[str, Hashable]
    evidence: tuple[str, ...]
    weight: float = 1.0


@dataclass(frozen=True)
class FingerprintDecision:
    probe: FingerprintProbe
    information_gain_bits: float
    reason: str
    candidates: tuple[str, ...]


def choose_fingerprint_probe(
    hypotheses: Iterable[FingerprintHypothesis],
    probes: Iterable[FingerprintProbe],
    *,
    valid_evidence: frozenset[str],
    maximum_risk: ProbeRisk = ProbeRisk.SAFE_READ,
) -> FingerprintDecision | None:
    """Choose maximum information within the lowest available risk class."""

    active = tuple(item for item in hypotheses if item.weight > 0 and item.evidence
                   and all(ref in valid_evidence for ref in item.evidence))
    admitted = tuple(item for item in probes if item.risk <= maximum_risk
                     and all(ref in valid_evidence for ref in item.evidence))
    if len(active) < 2 or not admitted:
        return None
    for risk in sorted({item.risk for item in admitted}):
        tier = tuple(item for item in admitted if item.risk is risk)
        choice = choose_experiment(
            tuple(ExperimentHypothesis(item.name, item.predictions, item.weight) for item in active),
            allowed_experiments=tuple(item.name for item in tier),
        )
        if choice is None:
            continue
        matches = [item for item in tier if item.name == choice.experiment]
        probe = min(matches, key=lambda item: (item.cost, item.name))
        return FingerprintDecision(
            probe, choice.information_gain_bits,
            f"selected {risk.name.lower()} discriminator before higher-risk probes",
            tuple(sorted(item.name for item in active)),
        )
    return None


def apply_fingerprint_observation(
    hypotheses: Iterable[FingerprintHypothesis], probe: str, outcome: Hashable
) -> tuple[FingerprintHypothesis, ...]:
    """Eliminate candidates contradicted by one recorded observation."""

    return tuple(item for item in hypotheses if item.predictions.get(probe) == outcome)
