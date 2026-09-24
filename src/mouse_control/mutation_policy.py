"""Evidence-based mutation safety maps for bounded protocol experiments.

The model adapts the useful idea behind region-aware protocol mutation without
assuming that a byte/bit which merely *changes* is safe to write.  It separates
independently mutable bits from restricted, source-declared immutable, coupled,
and still-unknown regions.

This module performs no I/O.  Its output is a guard that experiment planners can
apply to candidate reports before any transaction authority is considered.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Sequence


class MutationClassification(str, Enum):
    UNKNOWN = "unknown"
    INDEPENDENT = "independently_mutable"
    RESTRICTED = "restricted"
    IMMUTABLE = "immutable"
    COUPLED = "coupled"


class MutationOutcome(str, Enum):
    ACCEPTED_VERIFIED = "accepted_verified"
    REJECTED = "rejected"
    NO_EFFECT = "no_effect"
    TRANSPORT_FAILURE = "transport_failure"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class MutationTrial:
    baseline: bytes
    candidate: bytes
    outcome: MutationOutcome
    context: str = ""

    def __post_init__(self) -> None:
        if not self.baseline or len(self.baseline) != len(self.candidate):
            raise ValueError("mutation trial requires equal non-empty frames")
        if not isinstance(self.outcome, MutationOutcome):
            raise ValueError("mutation trial outcome must be explicit")

    @property
    def changed_bits(self) -> frozenset[int]:
        return changed_bits(self.baseline, self.candidate)


@dataclass(frozen=True)
class MutationRegion:
    start_bit: int
    end_bit: int
    classification: MutationClassification
    coupled_group: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.start_bit < 0 or self.end_bit < self.start_bit:
            raise ValueError("invalid mutation region")


@dataclass(frozen=True)
class MutationSafetyMap:
    frame_size: int
    classifications: tuple[MutationClassification, ...]
    coupled_groups: tuple[tuple[int, ...], ...] = ()
    evidence_trials: int = 0

    def __post_init__(self) -> None:
        if self.frame_size <= 0 or len(self.classifications) != self.frame_size * 8:
            raise ValueError("mutation map size does not match its bit classifications")
        normalized = tuple(tuple(sorted(set(group))) for group in self.coupled_groups)
        if normalized != self.coupled_groups:
            raise ValueError("coupled groups must be sorted unique tuples")
        for group in self.coupled_groups:
            if len(group) < 2 or any(bit < 0 or bit >= self.frame_size * 8 for bit in group):
                raise ValueError("invalid coupled mutation group")
            if any(self.classifications[bit] is not MutationClassification.COUPLED for bit in group):
                raise ValueError("coupled group contains a non-coupled bit")

    def classification(self, bit: int) -> MutationClassification:
        if bit < 0 or bit >= len(self.classifications):
            raise IndexError(bit)
        return self.classifications[bit]

    @property
    def regions(self) -> tuple[MutationRegion, ...]:
        """Coalesce adjacent bits with the same classification for reporting."""
        regions: list[MutationRegion] = []
        start = 0
        current = self.classifications[0]
        for bit in range(1, len(self.classifications) + 1):
            if bit < len(self.classifications) and self.classifications[bit] is current:
                continue
            group: tuple[int, ...] = ()
            if current is MutationClassification.COUPLED:
                matching = [
                    candidate for candidate in self.coupled_groups
                    if any(start <= member < bit for member in candidate)
                ]
                if len(matching) == 1:
                    group = matching[0]
            regions.append(MutationRegion(start, bit - 1, current, group))
            if bit < len(self.classifications):
                start = bit
                current = self.classifications[bit]
        return tuple(regions)

    def allows(self, baseline: bytes, candidate: bytes) -> bool:
        if len(baseline) != self.frame_size or len(candidate) != self.frame_size:
            return False
        changed = changed_bits(baseline, candidate)
        if not changed:
            return True
        # An exact coupled group may be changed as one unit.  A subset is not
        # independently safe unless those bits separately earned INDEPENDENT.
        for group in self.coupled_groups:
            if changed == frozenset(group):
                return True
        return all(
            self.classifications[bit] is MutationClassification.INDEPENDENT
            for bit in changed
        )

    def require_candidate(self, baseline: bytes, candidate: bytes) -> None:
        if len(baseline) != self.frame_size or len(candidate) != self.frame_size:
            raise ValueError("candidate frame does not match mutation map size")
        changed = changed_bits(baseline, candidate)
        if not changed:
            return
        if self.allows(baseline, candidate):
            return
        details = ", ".join(
            f"bit {bit}:{self.classifications[bit].value}"
            for bit in sorted(changed)
        )
        raise ValueError(f"candidate changes are not mutation-safe ({details})")


def changed_bits(baseline: bytes, candidate: bytes) -> frozenset[int]:
    if len(baseline) != len(candidate):
        raise ValueError("frames must have equal length")
    result: set[int] = set()
    for byte_index, (left, right) in enumerate(zip(baseline, candidate)):
        delta = left ^ right
        for bit in range(8):
            if delta & (1 << bit):
                result.add(byte_index * 8 + bit)
    return frozenset(result)


def infer_mutation_safety(
    trials: Sequence[MutationTrial],
    *,
    declared_immutable_bits: Iterable[int] = (),
) -> MutationSafetyMap:
    """Infer a conservative mutation map from explicit controlled trials.

    Rules are intentionally asymmetric:

    * a verified successful singleton mutation proves independent mutability;
    * a rejected/no-effect singleton proves only RESTRICTED, never immutable;
    * if such singleton failures succeed only as the same multi-bit mutation,
      the involved bits are marked COUPLED;
    * transport failures/unknown outcomes do not classify a bit;
    * IMMUTABLE is reserved for separately sourced declarations supplied by the
      caller and therefore wins over experimental inference.
    """

    observations = tuple(trials)
    if not observations:
        raise ValueError("at least one mutation trial is required")
    frame_sizes = {len(trial.baseline) for trial in observations}
    if len(frame_sizes) != 1:
        raise ValueError("mutation trials must use one stable frame size")
    frame_size = next(iter(frame_sizes))
    bit_count = frame_size * 8
    immutable = frozenset(int(bit) for bit in declared_immutable_bits)
    if any(bit < 0 or bit >= bit_count for bit in immutable):
        raise ValueError("declared immutable bit is outside the frame")

    singleton_success: set[int] = set()
    singleton_failure: set[int] = set()
    successful_groups: set[tuple[int, ...]] = set()
    for trial in observations:
        changed = trial.changed_bits
        if not changed:
            continue
        if trial.outcome is MutationOutcome.ACCEPTED_VERIFIED:
            if len(changed) == 1:
                singleton_success.update(changed)
            else:
                successful_groups.add(tuple(sorted(changed)))
        elif trial.outcome in {MutationOutcome.REJECTED, MutationOutcome.NO_EFFECT} and len(changed) == 1:
            singleton_failure.update(changed)

    # A successful combination is evidence of coupling only when every bit in
    # that combination was independently tried and failed and none succeeded on
    # its own. This avoids declaring coincidental multi-bit edits safe.
    coupled_groups: list[tuple[int, ...]] = []
    coupled_bits: set[int] = set()
    for group in sorted(successful_groups):
        members = set(group)
        if members and members.issubset(singleton_failure) and not members.intersection(singleton_success):
            coupled_groups.append(group)
            coupled_bits.update(members)

    classifications = [MutationClassification.UNKNOWN] * bit_count
    for bit in singleton_failure:
        classifications[bit] = MutationClassification.RESTRICTED
    for bit in coupled_bits:
        classifications[bit] = MutationClassification.COUPLED
    for bit in singleton_success:
        classifications[bit] = MutationClassification.INDEPENDENT
    for bit in immutable:
        classifications[bit] = MutationClassification.IMMUTABLE

    return MutationSafetyMap(
        frame_size=frame_size,
        classifications=tuple(classifications),
        coupled_groups=tuple(coupled_groups),
        evidence_trials=len(observations),
    )
