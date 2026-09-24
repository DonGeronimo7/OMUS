# SPDX-License-Identifier: AGPL-3.0-or-later
"""Choose safe discovery experiments by expected information gain.

This module is deliberately protocol-neutral.  Callers describe the outcomes
each remaining hypothesis predicts; the planner chooses the experiment whose
outcome partitions those hypotheses most evenly.  It never performs I/O and
therefore cannot grant write authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log2
from typing import Hashable, Mapping, Sequence


@dataclass(frozen=True)
class ExperimentHypothesis:
    name: str
    predicted_outcomes: Mapping[str, Hashable]
    weight: float = 1.0


@dataclass(frozen=True)
class ExperimentChoice:
    experiment: str
    information_gain_bits: float
    possible_outcomes: tuple[Hashable, ...]


def _entropy(weights: Sequence[float]) -> float:
    total = sum(weights)
    if total <= 0:
        return 0.0
    return -sum((weight / total) * log2(weight / total) for weight in weights if weight > 0)


def choose_experiment(
    hypotheses: Sequence[ExperimentHypothesis],
    *,
    allowed_experiments: Sequence[str] | None = None,
) -> ExperimentChoice | None:
    """Return the deterministic maximum-information experiment.

    Experiments missing from any hypothesis are excluded: an unspecified
    outcome is not evidence.  Experiments that cannot distinguish at least two
    outcomes have zero gain and are not returned.
    """

    active = tuple(item for item in hypotheses if item.weight > 0)
    if len(active) < 2:
        return None
    names = set(allowed_experiments or ())
    if allowed_experiments is None:
        names = set.intersection(*(set(item.predicted_outcomes) for item in active))

    prior = _entropy([item.weight for item in active])
    total = sum(item.weight for item in active)
    ranked: list[ExperimentChoice] = []
    for experiment in sorted(names):
        if any(experiment not in item.predicted_outcomes for item in active):
            continue
        groups: dict[Hashable, list[float]] = {}
        for item in active:
            groups.setdefault(item.predicted_outcomes[experiment], []).append(item.weight)
        if len(groups) < 2:
            continue
        remaining = sum(
            (sum(weights) / total) * _entropy(weights)
            for weights in groups.values()
        )
        ranked.append(
            ExperimentChoice(
                experiment,
                prior - remaining,
                tuple(sorted(groups, key=repr)),
            )
        )
    if not ranked:
        return None
    return min(ranked, key=lambda item: (-item.information_gain_bits, item.experiment))
