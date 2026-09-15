"""Guided, read-only behavioral learning for unknown mouse protocols.

A learning session observes repeated user actions across *all* correlated evdev
and hidraw interfaces, takes safe Feature-report snapshots before/after each
action, and asks semantic inference to identify repeated fields.  It never
contains a HID write operation.

Known backends may optionally provide read-only teacher state after each action.
That ground truth can label raw states without teaching the learner any
vendor-specific packet offsets or command IDs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping

from .discovery_models import DeviceNode, PhysicalDevice
from .event_correlation import (
    CorrelationCandidate,
    PhysicalAction,
    capture_action_window,
    detect_repeated_changes,
    detect_repeated_report_fields,
    diff_feature_snapshots,
)
from .hid_descriptor import ParsedHidDescriptor
from .hid_probe import ReadOnlyHidProbe
from .semantic_inference import SemanticHypothesis, infer_stage_hypotheses
from .protocol_grammar import SemanticBehavior


TeacherReader = Callable[[], Mapping[str, int | tuple[int, int] | None]]


@dataclass(frozen=True)
class LearningSample:
    action: PhysicalAction
    teacher_state: Mapping[str, int | tuple[int, int] | None] = field(default_factory=dict)


@dataclass(frozen=True)
class LearningResult:
    samples: tuple[LearningSample, ...]
    feature_candidates: tuple[CorrelationCandidate, ...]
    report_candidates: tuple[CorrelationCandidate, ...]
    hypotheses: tuple[SemanticHypothesis, ...]


class ReadOnlyLearningSession:
    """Observe one physical mouse without issuing any unknown write."""

    def __init__(
        self,
        physical: PhysicalDevice,
        descriptors: Mapping[DeviceNode, ParsedHidDescriptor],
        *,
        probe_factory: Callable[[DeviceNode], ReadOnlyHidProbe] | None = None,
    ) -> None:
        self.physical = physical
        self.descriptors = dict(descriptors)
        self._probe_factory = probe_factory or (
            lambda node: ReadOnlyHidProbe(node.path, sysfs_path=node.sysfs_path)
        )

    @staticmethod
    def _feature_key(node: DeviceNode, report_id: int) -> tuple[object, ...]:
        # No live path: this key is safe to persist if a future profile stores
        # an inferred field location.
        return (
            "feature",
            node.interface_number,
            node.descriptor_sha256,
            report_id,
        )

    def snapshot_features(self) -> dict[tuple[object, ...], bytes]:
        """Read every descriptor-declared Feature report that permits GET_FEATURE."""

        result: dict[tuple[object, ...], bytes] = {}
        for node, descriptor in self.descriptors.items():
            if not descriptor.feature_reports:
                continue
            probe = self._probe_factory(node)
            try:
                snapshot = probe.snapshot_feature_reports(descriptor.feature_reports)
            except (OSError, PermissionError):
                continue
            for report_id, data in snapshot.items():
                result[self._feature_key(node, report_id)] = bytes(data)
        return result

    def observe_action(
        self,
        *,
        seconds: float = 1.5,
        teacher_reader: TeacherReader | None = None,
    ) -> LearningSample:
        """Capture one bounded physical action plus before/after Feature state."""

        before = self.snapshot_features()
        action = capture_action_window(
            evdev_paths=(node.path for node in self.physical.evdev_nodes),
            hidraw_paths=(node.path for node in self.physical.hidraw_nodes),
            seconds=seconds,
        )
        after = self.snapshot_features()
        action.feature_changes = diff_feature_snapshots(before, after)
        teacher_state = dict(teacher_reader()) if teacher_reader is not None else {}
        return LearningSample(action=action, teacher_state=teacher_state)

    def analyze(self, samples: list[LearningSample] | tuple[LearningSample, ...]) -> LearningResult:
        actions = tuple(sample.action for sample in samples)
        feature_candidates = tuple(detect_repeated_changes(actions))
        report_candidates = tuple(detect_repeated_report_fields(actions))

        stage_hypotheses = [
            *infer_stage_hypotheses(feature_candidates),
            *infer_stage_hypotheses(report_candidates),
        ]
        teacher_hypotheses = self._teacher_dpi_hypotheses(
            samples, (*feature_candidates, *report_candidates)
        )

        # Deduplicate equivalent semantic locations while preserving the more
        # useful teacher-labelled hypothesis when both paths found the same field.
        merged: dict[tuple[object, object, object], SemanticHypothesis] = {}
        for hypothesis in (*stage_hypotheses, *teacher_hypotheses):
            key = (hypothesis.behavior, repr(hypothesis.report_key), hypothesis.offset)
            previous = merged.get(key)
            if previous is None or (
                previous.confidence == "correlated" and hypothesis.confidence == "validated"
            ):
                merged[key] = hypothesis

        return LearningResult(
            samples=tuple(samples),
            feature_candidates=feature_candidates,
            report_candidates=report_candidates,
            hypotheses=tuple(merged.values()),
        )

    @staticmethod
    def _teacher_dpi_hypotheses(
        samples: list[LearningSample] | tuple[LearningSample, ...],
        candidates: tuple[CorrelationCandidate, ...],
    ) -> tuple[SemanticHypothesis, ...]:
        """Label candidate raw states when a proven backend supplies current DPI.

        This does not prove that writing the candidate field changes DPI.  It
        only validates a *read-side* raw-state -> DPI relationship.
        """

        teacher_dpi: list[int] = []
        for sample in samples:
            raw = sample.teacher_state.get("dpi")
            if isinstance(raw, tuple):
                value = int(raw[0])
            elif isinstance(raw, int):
                value = raw
            else:
                return ()
            teacher_dpi.append(value)

        result: list[SemanticHypothesis] = []
        for candidate in candidates:
            states = [after for _before, after in candidate.transitions if after is not None]
            if len(states) != len(teacher_dpi):
                continue
            mapping: dict[int, int] = {}
            conflict = False
            for raw, dpi in zip(states, teacher_dpi):
                previous = mapping.get(raw)
                if previous is not None and previous != dpi:
                    conflict = True
                    break
                mapping[raw] = dpi
            if conflict or len(mapping) < 2:
                continue
            result.append(
                SemanticHypothesis(
                    behavior=SemanticBehavior.DPI_VALUE,
                    confidence="validated",
                    reason=(
                        "raw state consistently mapped to teacher-confirmed current DPI "
                        f"across {len(teacher_dpi)} guided actions"
                    ),
                    report_key=candidate.report_key,
                    offset=candidate.offset,
                    mapping=mapping,
                )
            )
        return tuple(result)
