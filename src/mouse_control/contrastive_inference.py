"""Teacher-free contrastive inference for guided HID discovery.

The generic learner must not discard a byte merely because ordinary mouse
traffic also uses that byte.  A HID report can multiplex buttons, motion and
vendor events into the same report.  This module therefore compares *transition
motifs* at a stable report/byte location across guided actions and negative
controls.

A semantic behavior may be validated when a transition motif repeats in every
guided sample and is absent from the control captures.  This validates the
behavior association supplied by the guided experiment; it does not prove a
unique packet field, an absolute DPI value, or any write semantic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable, Iterable

from .event_correlation import CorrelationCandidate, PhysicalAction, RawStreamIdentity
from .protocol_grammar import SemanticBehavior
from .semantic_inference import SemanticHypothesis


Transition = tuple[int, int]
CandidateLocation = tuple[Hashable, int]


@dataclass(frozen=True)
class ContrastiveCandidate:
    """One raw location with a guided-only repeated transition motif."""

    candidate: CorrelationCandidate
    common_transitions: tuple[Transition, ...]
    control_transitions: tuple[Transition, ...]
    distinctive_transitions: tuple[Transition, ...]
    descriptor_roles: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContrastiveRefinement:
    """A teacher-free refinement of the broad correlation result."""

    candidates: tuple[ContrastiveCandidate, ...]
    hypotheses: tuple[SemanticHypothesis, ...]
    suppressed_stage_locations: tuple[CandidateLocation, ...] = ()


def _report_shape(source: Hashable, data: bytes) -> Hashable:
    layout = (len(data), data[0] if data else None)
    if isinstance(source, RawStreamIdentity):
        return (*source.key, *layout)
    return (source, *layout)


def _transitions_for_action(
    action: PhysicalAction,
    candidate: CorrelationCandidate,
) -> frozenset[Transition]:
    sequence: list[int] = []
    for report in action.hid_reports:
        data = bytes(report.data)
        if _report_shape(report.source, data) != candidate.report_key:
            continue
        if candidate.offset >= len(data):
            continue
        sequence.append(data[candidate.offset])

    return frozenset(
        (before, after)
        for before, after in zip(sequence, sequence[1:])
        if before != after
    )


def _common_guided_transitions(
    actions: Iterable[PhysicalAction],
    candidate: CorrelationCandidate,
) -> frozenset[Transition]:
    per_action = tuple(_transitions_for_action(action, candidate) for action in actions)
    if not per_action or any(not transitions for transitions in per_action):
        return frozenset()
    common = set(per_action[0])
    for transitions in per_action[1:]:
        common.intersection_update(transitions)
    return frozenset(common)


def _control_transitions(
    actions: Iterable[PhysicalAction],
    candidate: CorrelationCandidate,
) -> frozenset[Transition]:
    result: set[Transition] = set()
    for action in actions:
        result.update(_transitions_for_action(action, candidate))
    return frozenset(result)


def _location(candidate: CorrelationCandidate) -> CandidateLocation:
    return candidate.report_key, candidate.offset


def refine_teacher_free(learned) -> ContrastiveRefinement:
    """Refine broad guided correlations using transition-level negative evidence.

    The first-pass learner intentionally gathers broadly.  Here we require a raw
    transition pair to occur in every guided action and never in either negative
    control.  Location overlap by itself is not disqualifying: normal pointer
    traffic and a vendor button can legitimately share a report byte.
    """

    if any(
        sample.teacher_state or sample.teacher_before_state
        for sample in learned.samples
    ):
        return ContrastiveRefinement((), tuple(learned.hypotheses))

    guided_actions = tuple(sample.action for sample in learned.samples)
    control_actions = tuple(sample.action for sample in learned.control_samples)
    if len(guided_actions) < 3 or len(control_actions) < 2:
        return ContrastiveRefinement((), tuple(learned.hypotheses))

    refined: list[ContrastiveCandidate] = []
    for candidate in learned.trigger_candidates:
        if candidate.observations < len(guided_actions):
            continue
        common = _common_guided_transitions(guided_actions, candidate)
        if not common:
            continue
        controls = _control_transitions(control_actions, candidate)
        distinctive = common.difference(controls)
        if not distinctive:
            continue
        roles = tuple(
            learned.descriptor_roles.get(
                _location(candidate),
                ("unknown",),
            )
        )
        refined.append(
            ContrastiveCandidate(
                candidate=candidate,
                common_transitions=tuple(sorted(common)),
                control_transitions=tuple(sorted(controls)),
                distinctive_transitions=tuple(sorted(distinctive)),
                descriptor_roles=roles,
            )
        )

    control_locations = {
        _location(candidate)
        for candidate in learned.control_trigger_candidates
    }
    suppressed_stage_locations: set[CandidateLocation] = set()
    hypotheses: list[SemanticHypothesis] = []

    # Rebuild teacher-free DPI-trigger claims from the stronger transition-level
    # evidence.  Also suppress stage-index guesses at locations proven active in
    # ordinary controls: a final pointer byte changing three times is not enough
    # to call it a DPI stage register.
    for hypothesis in learned.hypotheses:
        if hypothesis.behavior is SemanticBehavior.DPI_CYCLE_TRIGGER:
            continue
        if (
            hypothesis.behavior is SemanticBehavior.DPI_STAGE_INDEX
            and hypothesis.report_key is not None
            and hypothesis.offset is not None
            and (hypothesis.report_key, hypothesis.offset) in control_locations
        ):
            suppressed_stage_locations.add((hypothesis.report_key, hypothesis.offset))
            continue
        hypotheses.append(hypothesis)

    for item in refined:
        candidate = item.candidate
        hypotheses.append(
            SemanticHypothesis(
                behavior=SemanticBehavior.DPI_CYCLE_TRIGGER,
                confidence="correlated",
                reason=(
                    f"{len(item.distinctive_transitions)} transition motif(s) repeated in all "
                    f"{len(guided_actions)} guided DPI-button actions and were absent from "
                    f"{len(control_actions)} negative controls"
                ),
                report_key=candidate.report_key,
                offset=candidate.offset,
            )
        )

    if refined:
        hypotheses.append(
            SemanticHypothesis(
                behavior=SemanticBehavior.DPI_CYCLE_TRIGGER,
                confidence="validated",
                reason=(
                    f"teacher-free contrastive learning isolated {len(refined)} raw location(s) "
                    f"with transition motifs repeated across all {len(guided_actions)} guided "
                    f"DPI-button actions and absent from {len(control_actions)} negative controls; "
                    "raw locations remain candidates and no absolute DPI value is inferred"
                ),
            )
        )

    return ContrastiveRefinement(
        candidates=tuple(refined),
        hypotheses=tuple(hypotheses),
        suppressed_stage_locations=tuple(sorted(suppressed_stage_locations, key=repr)),
    )
