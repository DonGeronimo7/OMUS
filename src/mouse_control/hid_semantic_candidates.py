"""Read-only, action-conditioned HID state candidate inference.

This is deliberately a candidate layer: a labelled action can explain why a
field matters, but cannot grant protocol write authority or replace physical
calibration.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Sequence

from .hid_behavior import HidBehaviorClass, profile_reports
from .hid_report import DecodedHidReport


class SemanticEvidenceLevel(str, Enum):
    CORRELATED = "correlated"
    VALIDATED = "validated"


class SemanticBehavior(str, Enum):
    CYCLIC_STATE_CANDIDATE = "cyclic_state_candidate"
    DPI_STAGE_INDEX = "dpi_stage_index"


@dataclass(frozen=True)
class SemanticCandidate:
    behavior: SemanticBehavior
    source_field: str
    evidence_level: SemanticEvidenceLevel
    positive_experiments: tuple[str, ...]
    negative_controls: Mapping[str, int]
    observed_values: tuple[int, ...]
    transition_sequence: tuple[tuple[int, int], ...]
    contradictions: tuple[str, ...] = ()
    configured_dpi_mapping: Mapping[int, int] = field(default_factory=dict)
    measured_cpi_mapping: Mapping[int, int] = field(default_factory=dict)


@dataclass(frozen=True)
class PhysicalDpiValidation:
    """Independent physical evidence for one read-only stage-index field."""

    source_field: str
    configured_dpi_mapping: Mapping[int, int]
    measured_cpi_mapping: Mapping[int, int]
    parent_field: str = ""
    member_index: int | None = None
    report_identity: Mapping[str, object] = field(default_factory=dict)
    offset: int | None = None
    observations: int = 0


def _sequence(reports: Sequence[DecodedHidReport], field_id: str) -> tuple[int, ...]:
    return tuple(value.logical_value for report in reports for value in report.values
                 if value.field_id == field_id and value.logical_value is not None)


def infer_action_conditioned_candidates(
    positive: Mapping[str, Sequence[DecodedHidReport]],
    negative: Mapping[str, Sequence[DecodedHidReport]],
    *,
    physical_validations: Mapping[str, PhysicalDpiValidation] | None = None,
) -> tuple[SemanticCandidate, ...]:
    """Find absolute bounded cycles cleanly isolated to a labelled action.

    ``dpi-button`` is the only label promoted to the DPI semantic hypothesis;
    all other labels remain protocol-neutral cyclic-state candidates.
    """
    if not negative:
        return ()
    validations = physical_validations or {}
    result: list[SemanticCandidate] = []
    for label, reports in positive.items():
        profiles = profile_reports(reports)
        for field_id, profile in profiles.items():
            if profile.relative or profile.classification is not HidBehaviorClass.CYCLIC_STATE:
                continue
            sequence = _sequence(reports, field_id)
            transitions = tuple((left, right) for left, right in zip(sequence, sequence[1:])
                                if left != right)
            # A classified cycle already includes a return edge. Require all
            # observed states to be represented by a real transition too.
            if len(profile.unique_values) < 2 or not transitions:
                continue
            controls: dict[str, int] = {}
            contradictions: list[str] = []
            for control, control_reports in negative.items():
                control_values = _sequence(control_reports, field_id)
                changes = sum(left != right for left, right in zip(control_values, control_values[1:]))
                controls[control] = changes
                if changes:
                    contradictions.append(f"{control}: {changes} changes")
            if contradictions:
                continue
            behavior = (SemanticBehavior.DPI_STAGE_INDEX if label == "dpi-button"
                        else SemanticBehavior.CYCLIC_STATE_CANDIDATE)
            validation = validations.get(field_id)
            validated = (
                behavior is SemanticBehavior.DPI_STAGE_INDEX
                and validation is not None
                and set(validation.configured_dpi_mapping) == set(profile.unique_values)
                and set(validation.measured_cpi_mapping) == set(profile.unique_values)
            )
            result.append(SemanticCandidate(
                behavior, field_id,
                (SemanticEvidenceLevel.VALIDATED if validated
                 else SemanticEvidenceLevel.CORRELATED),
                (label,), controls, profile.unique_values, transitions,
                tuple(contradictions),
                (validation.configured_dpi_mapping if validated else {}),
                (validation.measured_cpi_mapping if validated else {})))
    return tuple(sorted(result, key=lambda item: item.source_field))
