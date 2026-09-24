# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pure State / Effect / Persistence analysis for Discovery Lab evidence.

This module compares canonical state evidence across time and connection
generations.  It never correlates a transaction across generations, performs
I/O, or owns a write primitive.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable, Sequence

from .discovery_lab import (
    EffectEvidence,
    EffectState,
    EffectVerificationMethod,
    LabExperiment,
    LabExperimentPlan,
    LabHypothesis,
    LabStopReason,
    PersistenceAssessment,
    PersistenceClassification,
    PersistenceEvidence,
    PersistenceLevel,
    RestorationPlan,
)
from .lab_orchestrator import (
    ACTION_TEMPLATES,
    derive_observation_windows,
    plan_next_experiment,
)
from .temporal_dialogue import DialogueKind, StateFreshness


def derive_immediate_effect_evidence(
    experiment: LabExperiment,
    *,
    target_semantic: str,
) -> EffectEvidence:
    """Project existing Lab analysis and paired physical measurements into effect evidence."""

    analysis = experiment.analysis
    acknowledgements = tuple(
        item for item in experiment.dialogues if item.kind is DialogueKind.ACK
    )
    correlated = tuple(
        item for item in (analysis.ranked_fields if analysis is not None else ())
        if any(signal.value == "action_correlated" for signal in item.signals)
    )
    before_state = None
    after_state = None
    sources: list[str] = []
    if correlated:
        field = correlated[0]
        baseline = field.values_by_interval.get(next(
            interval for interval in field.values_by_interval if interval.value == "baseline"
        ), ())
        action = field.values_by_interval.get(next(
            interval for interval in field.values_by_interval if interval.value == "action"
        ), ())
        before_state = baseline[-1] if baseline else None
        after_state = action[-1] if action else None
        sources.append(f"{field.stream_id}:{field.offset}")
    for item in acknowledgements:
        sources.append(f"{item.observation.source_id}:{item.observation.sequence}")

    physical = (
        experiment.physical_cpi_evidence
        if target_semantic.lower() == "dpi"
        else experiment.physical_polling_evidence
        if target_semantic.lower() == "polling" else ()
    )
    before_physical = next((item for item in physical if item.kind.endswith("_before")), None)
    after_physical = next((item for item in physical if item.kind.endswith("_after")), None)
    if before_physical is not None and after_physical is not None:
        physical_effect = (
            EffectState.STATE_PHYSICALLY_EFFECTIVE
            if before_physical.value != after_physical.value
            else EffectState.STATE_NOT_PHYSICALLY_EFFECTIVE
        )
        sources.extend((*before_physical.evidence_source_ids, *after_physical.evidence_source_ids))
        method = (
            EffectVerificationMethod.PHYSICAL_CPI
            if target_semantic.lower() == "dpi" else EffectVerificationMethod.PHYSICAL_POLLING
        )
        methods = (EffectVerificationMethod.PROTOCOL_READBACK, method)
    else:
        physical_effect = EffectState.STATE_UNKNOWN
        methods = (EffectVerificationMethod.PROTOCOL_READBACK,) if correlated else ()

    fresh_states = [item for item in (*experiment.state_reads, *experiment.pushed_states)
                    if item.semantic_state_id == target_semantic and item.freshness is StateFreshness.FRESH]
    stale_states = [item for item in (*experiment.state_reads, *experiment.pushed_states)
                    if item.semantic_state_id == target_semantic and item.freshness is StateFreshness.STALE]
    if fresh_states:
        after_state = fresh_states[-1].decoded_state
        freshness = StateFreshness.FRESH
        sources.append(
            f"{fresh_states[-1].observation.source_id}:{fresh_states[-1].observation.sequence}"
        )
        methods = tuple(dict.fromkeys((*methods, EffectVerificationMethod.PUSHED_STATE)))
    elif stale_states:
        after_state = stale_states[-1].decoded_state
        freshness = StateFreshness.STALE
    else:
        freshness = StateFreshness.UNKNOWN
    return EffectEvidence(
        experiment_id=experiment.experiment_id,
        physical_device_context=experiment.physical_device_context,
        connection_generation=experiment.connection_generation,
        target_semantic=target_semantic,
        before_state=before_state,
        after_state=after_state,
        request_state=(
            EffectState.REQUEST_ACCEPTED if acknowledgements else EffectState.STATE_UNKNOWN
        ),
        protocol_effect=(EffectState.STATE_REPORTED if correlated or fresh_states else EffectState.STATE_UNKNOWN),
        physical_effect=physical_effect,
        freshness=freshness,
        verification_methods=methods,
        source_observation_ids=_unique(sources),
        confidence="correlated" if correlated else "unknown",
    )


_LEVEL_CLASSIFICATION = {
    PersistenceLevel.SETTLING_IDLE: PersistenceClassification.SESSION_PERSISTENT,
    PersistenceLevel.PROTOCOL_REREAD: PersistenceClassification.SESSION_PERSISTENT,
    PersistenceLevel.DEVICE_RECONNECT: PersistenceClassification.RECONNECT_PERSISTENT,
    PersistenceLevel.RECEIVER_RECONNECT: PersistenceClassification.RECEIVER_RECONNECT_PERSISTENT,
    PersistenceLevel.POWER_CYCLE: PersistenceClassification.POWER_CYCLE_PERSISTENT,
    PersistenceLevel.HOST_SESSION_RESTART: PersistenceClassification.HOST_RESTART_PERSISTENT,
}


def _unique(items: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item for item in items if item))


def _select_decisive_effect(
    evidence: Sequence[EffectEvidence],
) -> tuple[EffectEvidence | None, tuple[str, ...]]:
    """Prefer fresh evidence while retaining stale/fresh disagreement."""

    if not evidence:
        return None, ()
    fresh = [item for item in evidence if item.freshness is StateFreshness.FRESH]
    decisive = fresh[-1] if fresh else evidence[-1]
    contradictions = [item for evidence_item in evidence for item in evidence_item.contradictions]
    stale = [item for item in evidence if item.freshness is StateFreshness.STALE]
    if fresh and any(item.after_state != decisive.after_state for item in stale):
        contradictions.append(
            "stale reported state was superseded by a different fresh state"
        )
    return decisive, _unique(contradictions)


def _effect_state(
    evidence: EffectEvidence | None,
    contradictions: list[str],
) -> EffectState:
    if evidence is None:
        return EffectState.STATE_UNKNOWN
    if (
        evidence.protocol_effect is EffectState.STATE_REPORTED
        and evidence.physical_effect is EffectState.STATE_NOT_PHYSICALLY_EFFECTIVE
    ):
        contradictions.append(
            "protocol state changed but independent physical behavior did not"
        )
        return EffectState.STATE_NOT_PHYSICALLY_EFFECTIVE
    if evidence.physical_effect is EffectState.STATE_REVERTED:
        return EffectState.STATE_REVERTED
    if evidence.physical_effect is EffectState.STATE_PHYSICALLY_EFFECTIVE:
        return EffectState.STATE_PHYSICALLY_EFFECTIVE
    if evidence.protocol_effect is EffectState.STATE_REPORTED:
        return EffectState.STATE_REPORTED
    return EffectState.STATE_UNKNOWN


def _next_action_id(
    strongest: PersistenceLevel | None,
    *,
    receiver_available: bool,
    power_cycle_available: bool,
) -> str | None:
    if strongest is None or strongest is PersistenceLevel.IMMEDIATE_EFFECT:
        return "IDLE_PERSISTENCE"
    if strongest is PersistenceLevel.SETTLING_IDLE:
        return "PROTOCOL_REREAD"
    if strongest is PersistenceLevel.PROTOCOL_REREAD:
        return "RECONNECT_PERSISTENCE"
    if strongest is PersistenceLevel.DEVICE_RECONNECT:
        return "RECEIVER_RECONNECT_PERSISTENCE" if receiver_available else (
            "POWER_CYCLE_PERSISTENCE" if power_cycle_available else None
        )
    if strongest is PersistenceLevel.RECEIVER_RECONNECT:
        return "POWER_CYCLE_PERSISTENCE" if power_cycle_available else None
    return None


def _persistence_plan(
    semantic: str,
    action_id: str,
    experiment: LabExperiment,
) -> LabExperimentPlan:
    action = ACTION_TEMPLATES[action_id]
    question = {
        "IDLE_PERSISTENCE": f"Does the observed {semantic} state survive settling and idle?",
        "PROTOCOL_REREAD": f"Does a fresh {semantic} protocol read still report the effect?",
        "RECONNECT_PERSISTENCE": f"Does the observed {semantic} state survive reconnect?",
        "RECEIVER_RECONNECT_PERSISTENCE": f"Does the observed {semantic} state survive receiver reconnect?",
        "POWER_CYCLE_PERSISTENCE": f"Does the observed {semantic} state survive a device power cycle?",
    }[action_id]
    hypotheses = (
        LabHypothesis(
            f"{semantic}-persists", question, "the observed state persists", semantic,
            {action_id: "persists"},
        ),
        LabHypothesis(
            f"{semantic}-reverts", question, "the observed state reverts", semantic,
            {action_id: "reverts"},
        ),
    )
    return plan_next_experiment(
        hypotheses,
        available_actions=(action,),
        timing_profile=experiment.timing_profile,
    )


def verify_state_effect_persistence(
    experiment: LabExperiment,
    *,
    target_semantic: str,
    effect_evidence: Sequence[EffectEvidence],
    persistence_evidence: Sequence[PersistenceEvidence] = (),
    receiver_available: bool = False,
    power_cycle_available: bool = True,
    user_accepts_disruptive_test: bool = True,
    max_human_cost: int = 15,
) -> LabExperiment:
    """Attach a conservative effect/persistence assessment to one experiment.

    State may be compared across generations only through ``PersistenceEvidence``.
    Existing ``LabExperiment`` validation continues to forbid protocol dialogue
    or pushed-state relationships spanning generations.
    """

    effects = tuple(effect_evidence)
    persistence = tuple(sorted(persistence_evidence, key=lambda item: int(item.level)))
    if any(item.experiment_id != experiment.experiment_id for item in (*effects, *persistence)):
        raise ValueError("effect/persistence evidence belongs to a different experiment")
    if any(item.target_semantic != target_semantic for item in (*effects, *persistence)):
        raise ValueError("effect/persistence evidence targets a different semantic")
    if any(item.physical_device_context != experiment.physical_device_context for item in effects):
        raise ValueError("effect evidence physical identity does not match the experiment")
    if any(item.physical_device_context != experiment.physical_device_context for item in persistence):
        raise ValueError("persistence evidence physical identity does not match the experiment")

    decisive, initial_contradictions = _select_decisive_effect(effects)
    contradictions = list(initial_contradictions)
    effective = _effect_state(decisive, contradictions)
    classifications: list[PersistenceClassification] = []
    confirmed_levels: list[PersistenceLevel] = []

    for item in persistence:
        contradictions.extend(item.contradictions)
        survived = item.survived
        if item.automatic_reversion_observed:
            survived = False
        if (
            survived is True
            and item.level >= PersistenceLevel.PROTOCOL_REREAD
            and item.freshness is not StateFreshness.FRESH
        ):
            contradictions.append(
                f"{item.level.name.lower()} state was not fresh and cannot prove persistence"
            )
            survived = None
        if survived is True:
            confirmed_levels.append(item.level)
            classification = _LEVEL_CLASSIFICATION.get(item.level)
            if classification is not None:
                classifications.append(classification)
        elif survived is False:
            classifications.append(PersistenceClassification.REVERTED)
            if item.level <= PersistenceLevel.DEVICE_RECONNECT:
                classifications.append(PersistenceClassification.VOLATILE)

    commit = next((item for item in persistence if item.commit_observed), None)
    apply = next((item for item in persistence if item.apply_observed), None)
    activation = commit or apply
    if activation is not None and activation.survived is True:
        if commit is not None:
            classifications.append(PersistenceClassification.COMMIT_REQUIRED)
        if apply is not None:
            classifications.append(PersistenceClassification.APPLY_REQUIRED)
        if commit is not None and decisive is not None \
                and decisive.protocol_effect is EffectState.STATE_REPORTED \
                and decisive.physical_effect is not EffectState.STATE_PHYSICALLY_EFFECTIVE:
            classifications.append(PersistenceClassification.VOLATILE_UNTIL_COMMIT)
        if any(method in {
            EffectVerificationMethod.PHYSICAL_CPI,
            EffectVerificationMethod.PHYSICAL_POLLING,
            EffectVerificationMethod.USER_VISIBLE_HARDWARE_STATE,
        } for method in activation.verification_methods):
            effective = EffectState.STATE_PHYSICALLY_EFFECTIVE

    strongest = max(confirmed_levels, default=None)
    if any(item.host_reapplied for item in persistence):
        classifications.append(PersistenceClassification.HOST_STORED)
    elif any(
        item.level is PersistenceLevel.POWER_CYCLE
        and item.survived is True
        and item.freshness is StateFreshness.FRESH
        for item in persistence
    ):
        classifications.append(PersistenceClassification.DEVICE_STORED)
    else:
        classifications.append(PersistenceClassification.UNKNOWN_STORAGE_LOCATION)
    if not classifications:
        classifications.append(PersistenceClassification.UNKNOWN)
    classifications = list(dict.fromkeys(classifications))

    reverted = PersistenceClassification.REVERTED in classifications
    if effective in {EffectState.STATE_UNKNOWN, EffectState.STATE_REPORTED, EffectState.STATE_NOT_PHYSICALLY_EFFECTIVE}:
        stop = LabStopReason.EFFECT_NOT_CONFIRMED
        next_plan = None
    elif activation is not None:
        stop = LabStopReason.COMMIT_REQUIREMENT_IDENTIFIED
        next_plan = None
    elif reverted:
        stop = LabStopReason.STATE_REVERTED
        next_plan = None
    elif strongest is not None and strongest >= PersistenceLevel.POWER_CYCLE:
        stop = (
            LabStopReason.POWER_CYCLE_PERSISTENCE_CONFIRMED
            if strongest is PersistenceLevel.POWER_CYCLE
            else LabStopReason.PERSISTENCE_SUFFICIENTLY_CHARACTERIZED
        )
        next_plan = None
    else:
        action_id = _next_action_id(
            strongest,
            receiver_available=receiver_available,
            power_cycle_available=power_cycle_available,
        )
        if action_id is None:
            stop = LabStopReason.NO_SAFE_HIGH_VALUE_PERSISTENCE_TEST
            next_plan = None
        else:
            candidate = ACTION_TEMPLATES[action_id]
            disruptive = action_id in {
                "RECONNECT_PERSISTENCE", "RECEIVER_RECONNECT_PERSISTENCE",
                "POWER_CYCLE_PERSISTENCE",
            }
            if disruptive and not user_accepts_disruptive_test:
                stop = LabStopReason.USER_DECLINED_DISRUPTIVE_TEST
                next_plan = None
            elif candidate.human_cost > max_human_cost:
                stop = LabStopReason.NO_SAFE_HIGH_VALUE_PERSISTENCE_TEST
                next_plan = None
            else:
                stop = (
                    LabStopReason.RECONNECT_PERSISTENCE_CONFIRMED
                    if strongest is PersistenceLevel.DEVICE_RECONNECT
                    else LabStopReason.EFFECT_CONFIRMED
                )
                next_plan = _persistence_plan(target_semantic, action_id, experiment)

    original = decisive.before_state if decisive is not None else None
    current = (
        persistence[-1].after_state if persistence
        else decisive.after_state if decisive is not None else None
    )
    restored = any(item.user_restored and item.after_state == original for item in persistence)
    restoration_required = (
        original is not None and current is not None and original != current and not restored
    )
    restoration = RestorationPlan(
        required=restoration_required,
        original_state=original,
        current_state=current,
        instruction=(
            "Restore the original state manually or with the same external vendor tool, then verify it."
            if restoration_required else None
        ),
        verified=restored,
        automatic_write_authorized=False,
    )
    windows = derive_observation_windows(experiment.timing_profile)
    assessment = PersistenceAssessment(
        target_semantic=target_semantic,
        effective_state=effective,
        classifications=tuple(classifications),
        strongest_confirmed_level=strongest,
        decisive_effect_evidence=(
            decisive.source_observation_ids[-1]
            if decisive is not None and decisive.source_observation_ids else None
        ),
        retained_effect_evidence=_unique(
            source for item in effects for source in item.source_observation_ids
        ),
        retained_persistence_evidence=_unique(
            source for item in persistence for source in item.source_observation_ids
        ),
        contradictions=_unique(contradictions),
        stop_reason=stop,
        next_plan=next_plan,
        restoration=restoration,
        freshness_wait_seconds=windows.post_action_seconds,
        timing_source=windows.source,
        timing_uncertainty=windows.uncertainty,
    )
    return replace(
        experiment,
        effect_evidence=effects,
        persistence_evidence=persistence,
        persistence_assessment=assessment,
        stop_reason=stop,
        next_plan=next_plan,
    )
