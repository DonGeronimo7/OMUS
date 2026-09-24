# SPDX-License-Identifier: AGPL-3.0-or-later
"""Honest open-set metrics for project-owned protocol recognition fixtures."""

from __future__ import annotations

from dataclasses import dataclass

from .protocol_repertoire import OpenSetRecognition, RecognitionStatus


@dataclass(frozen=True)
class BenchmarkObservation:
    """Expected and observed result for one independently reconstructed case."""

    case_id: str
    expected_status: RecognitionStatus
    decision: OpenSetRecognition
    expected_family: str | None = None
    identity_blinded: bool = False


@dataclass(frozen=True)
class FamilyMetrics:
    family: str
    correct: int
    total: int

    @property
    def recall(self) -> float:
        return self.correct / self.total if self.total else 0.0


@dataclass(frozen=True)
class BenchmarkMetrics:
    cases: int
    exact_outcomes: int
    recognized: int
    correctly_recognized: int
    known_positive_cases: int
    unknown_cases: int
    unknown_false_recognitions: int
    collision_cases: int
    collision_false_recognitions: int
    candidate_cases: int
    ambiguous_cases: int
    identity_blinded_cases: int
    identity_blinded_correct: int
    per_family: tuple[FamilyMetrics, ...]

    @staticmethod
    def _ratio(numerator: int, denominator: int) -> float:
        return numerator / denominator if denominator else 0.0

    @property
    def exact_outcome_accuracy(self) -> float:
        return self._ratio(self.exact_outcomes, self.cases)

    @property
    def recognized_family_precision(self) -> float:
        return self._ratio(self.correctly_recognized, self.recognized)

    @property
    def known_family_acquisition_recall(self) -> float:
        return self._ratio(self.correctly_recognized, self.known_positive_cases)

    @property
    def unknown_family_false_recognition(self) -> float:
        return self._ratio(self.unknown_false_recognitions, self.unknown_cases)

    @property
    def structural_collision_false_recognition(self) -> float:
        return self._ratio(self.collision_false_recognitions, self.collision_cases)

    @property
    def coverage(self) -> float:
        return self._ratio(self.recognized, self.cases)

    @property
    def abstention(self) -> float:
        unknown = self.cases - self.recognized - self.candidate_cases - self.ambiguous_cases
        return self._ratio(unknown + self.candidate_cases, self.cases)

    @property
    def ambiguity(self) -> float:
        return self._ratio(self.ambiguous_cases, self.cases)


def score_benchmark(observations: tuple[BenchmarkObservation, ...]) -> BenchmarkMetrics:
    """Score exact open-set outcomes without treating abstention as recognition."""

    per_family_totals: dict[str, int] = {}
    per_family_correct: dict[str, int] = {}
    exact = recognized = correctly_recognized = 0
    known_positive = unknown_cases = unknown_false = 0
    collision_cases = collision_false = candidate_cases = ambiguous_cases = 0
    identity_blinded = identity_blinded_correct = 0

    for observation in observations:
        decision = observation.decision
        exact_match = (
            decision.status is observation.expected_status
            and (
                observation.expected_status is not RecognitionStatus.RECOGNIZED
                or decision.family == observation.expected_family
            )
        )
        exact += int(exact_match)
        recognized += int(decision.status is RecognitionStatus.RECOGNIZED)
        candidate_cases += int(decision.status is RecognitionStatus.CANDIDATE)
        ambiguous_cases += int(decision.status is RecognitionStatus.AMBIGUOUS)

        if observation.expected_status is RecognitionStatus.RECOGNIZED:
            known_positive += 1
            assert observation.expected_family is not None
            per_family_totals[observation.expected_family] = (
                per_family_totals.get(observation.expected_family, 0) + 1
            )
            correct = decision.status is RecognitionStatus.RECOGNIZED and (
                decision.family == observation.expected_family
            )
            correctly_recognized += int(correct)
            per_family_correct[observation.expected_family] = (
                per_family_correct.get(observation.expected_family, 0) + int(correct)
            )
        if observation.expected_status is RecognitionStatus.UNKNOWN:
            unknown_cases += 1
            unknown_false += int(decision.status is RecognitionStatus.RECOGNIZED)
        if observation.expected_status is RecognitionStatus.AMBIGUOUS:
            collision_cases += 1
            collision_false += int(decision.status is RecognitionStatus.RECOGNIZED)
        if observation.identity_blinded:
            identity_blinded += 1
            identity_blinded_correct += int(exact_match)

    families = tuple(
        FamilyMetrics(name, per_family_correct.get(name, 0), total)
        for name, total in sorted(per_family_totals.items())
    )
    return BenchmarkMetrics(
        len(observations), exact, recognized, correctly_recognized,
        known_positive, unknown_cases, unknown_false,
        collision_cases, collision_false, candidate_cases, ambiguous_cases,
        identity_blinded, identity_blinded_correct, families,
    )
