# SPDX-License-Identifier: AGPL-3.0-or-later
from dataclasses import replace
from types import SimpleNamespace

import pytest

from mouse_control.discovery_lab import (
    EffectEvidence,
    EffectState,
    EffectVerificationMethod,
    LabExperiment,
    LabInterval,
    LabStopReason,
    PhysicalEvidence,
    PersistenceClassification,
    PersistenceEvidence,
    PersistenceLevel,
    ProtocolTimingProfile,
    TimingClassification,
    TimingRelationship,
    TimingSummary,
)
from mouse_control.persistence_verifier import (
    derive_immediate_effect_evidence,
    verify_state_effect_persistence,
)
from mouse_control.temporal_dialogue import (
    DialogueKind,
    DialogueObservation,
    DialogueRecord,
    Direction,
    StateFreshness,
)


CONTEXT = {
    "vendor_id": 0x1234,
    "product_id": 0x5678,
    "model_fingerprint": "model",
    "path": "/dev/hidraw9",
}


def _experiment(*, timing_profile=None):
    return LabExperiment(
        "effect-fixture", CONTEXT, 1, "effect fixture", "external demonstration",
        (), (), timing_profile=timing_profile,
    )


def _effect(
    *,
    before=800,
    after=1600,
    request=EffectState.REQUEST_ACCEPTED,
    protocol=EffectState.STATE_REPORTED,
    physical=EffectState.STATE_PHYSICALLY_EFFECTIVE,
    freshness=StateFreshness.FRESH,
    source="effect-1",
    contradictions=(),
):
    return EffectEvidence(
        "effect-fixture", CONTEXT, 1, "dpi", before, after,
        request_state=request,
        protocol_effect=protocol,
        physical_effect=physical,
        freshness=freshness,
        verification_methods=(
            EffectVerificationMethod.PROTOCOL_READBACK,
            EffectVerificationMethod.PHYSICAL_CPI,
        ),
        source_observation_ids=(source,),
        confidence="verified",
        contradictions=contradictions,
    )


def _persistence(
    level,
    *,
    survived=True,
    before=1600,
    after=1600,
    before_generation=1,
    after_generation=None,
    freshness=StateFreshness.FRESH,
    source=None,
    **kwargs,
):
    if after_generation is None:
        after_generation = before_generation + (1 if level >= PersistenceLevel.DEVICE_RECONNECT else 0)
    return PersistenceEvidence(
        "effect-fixture", CONTEXT, "dpi", level, before, after,
        before_generation, after_generation, survived, freshness,
        (EffectVerificationMethod.PROTOCOL_READBACK, EffectVerificationMethod.PHYSICAL_CPI),
        (source or f"persistence-{int(level)}",),
        level.name.lower(),
        **kwargs,
    )


def _verify(effect, persistence=(), **kwargs):
    return verify_state_effect_persistence(
        _experiment(), target_semantic="dpi", effect_evidence=effect,
        persistence_evidence=persistence, **kwargs,
    )


def test_ack_without_physical_effect_is_not_success():
    evidence = _effect(
        before=None, after=None, protocol=EffectState.STATE_UNKNOWN,
        physical=EffectState.STATE_UNKNOWN, freshness=StateFreshness.UNKNOWN,
    )
    result = _verify((evidence,))
    assert result.persistence_assessment.effective_state is EffectState.STATE_UNKNOWN
    assert result.stop_reason is LabStopReason.EFFECT_NOT_CONFIRMED
    assert result.next_plan is None


def test_existing_analysis_and_paired_physical_measurements_project_to_effect_evidence():
    experiment = replace(
        _experiment(),
        analysis=SimpleNamespace(ranked_fields=(SimpleNamespace(
            stream_id="dpi-stream", offset=2,
            signals=(SimpleNamespace(value="action_correlated"),),
            values_by_interval={LabInterval.BASELINE: (8,), LabInterval.ACTION: (16,)},
        ),)),
        physical_cpi_evidence=(
            PhysicalEvidence("physical_cpi_before", 800, "CPI", evidence_source_ids=("cpi-before",)),
            PhysicalEvidence("physical_cpi_after", 1600, "CPI", evidence_source_ids=("cpi-after",)),
        ),
    )
    evidence = derive_immediate_effect_evidence(experiment, target_semantic="dpi")
    assert evidence.protocol_effect is EffectState.STATE_REPORTED
    assert evidence.physical_effect is EffectState.STATE_PHYSICALLY_EFFECTIVE
    assert EffectVerificationMethod.PHYSICAL_CPI in evidence.verification_methods


def test_protocol_readback_and_independent_physical_effect_are_confirmed():
    result = _verify((_effect(),))
    assessment = result.persistence_assessment
    assert assessment.effective_state is EffectState.STATE_PHYSICALLY_EFFECTIVE
    assert assessment.stop_reason is LabStopReason.EFFECT_CONFIRMED
    assert assessment.next_plan.selected_action.action_id == "IDLE_PERSISTENCE"


def test_protocol_physical_disagreement_is_an_explicit_contradiction():
    result = _verify((_effect(physical=EffectState.STATE_NOT_PHYSICALLY_EFFECTIVE),))
    assessment = result.persistence_assessment
    assert assessment.effective_state is EffectState.STATE_NOT_PHYSICALLY_EFFECTIVE
    assert any("physical behavior did not" in item for item in assessment.contradictions)
    assert assessment.stop_reason is LabStopReason.EFFECT_NOT_CONFIRMED


def test_stale_read_is_retained_but_superseded_by_fresh_state():
    stale = _effect(after=1600, freshness=StateFreshness.STALE, source="stale")
    fresh = _effect(after=800, freshness=StateFreshness.FRESH, source="fresh")
    result = _verify((stale, fresh))
    assessment = result.persistence_assessment
    assert assessment.decisive_effect_evidence == "fresh"
    assert assessment.retained_effect_evidence == ("stale", "fresh")
    assert any("superseded" in item for item in assessment.contradictions)


def test_idle_and_reread_advance_only_their_exact_ladder_levels():
    idle = _verify((_effect(),), (_persistence(PersistenceLevel.SETTLING_IDLE),))
    assert PersistenceClassification.SESSION_PERSISTENT in idle.persistence_assessment.classifications
    assert idle.persistence_assessment.strongest_confirmed_level is PersistenceLevel.SETTLING_IDLE
    assert idle.next_plan.selected_action.action_id == "PROTOCOL_REREAD"

    reread = _verify((_effect(),), (_persistence(PersistenceLevel.PROTOCOL_REREAD),))
    assert reread.persistence_assessment.strongest_confirmed_level is PersistenceLevel.PROTOCOL_REREAD
    assert PersistenceClassification.RECONNECT_PERSISTENT not in reread.persistence_assessment.classifications
    assert reread.next_plan.selected_action.action_id == "RECONNECT_PERSISTENCE"


def test_reconnect_survival_and_reversion_are_distinct():
    survived = _verify((_effect(),), (_persistence(PersistenceLevel.DEVICE_RECONNECT),))
    assert PersistenceClassification.RECONNECT_PERSISTENT in survived.persistence_assessment.classifications
    assert PersistenceClassification.POWER_CYCLE_PERSISTENT not in survived.persistence_assessment.classifications
    assert survived.next_plan.selected_action.action_id == "POWER_CYCLE_PERSISTENCE"

    reverted = _verify(
        (_effect(),),
        (_persistence(PersistenceLevel.DEVICE_RECONNECT, survived=False, after=800),),
    )
    assert PersistenceClassification.REVERTED in reverted.persistence_assessment.classifications
    assert reverted.stop_reason is LabStopReason.STATE_REVERTED


def test_receiver_reconnect_survival_is_not_power_cycle_persistence():
    result = _verify(
        (_effect(),),
        (_persistence(PersistenceLevel.RECEIVER_RECONNECT),),
    )
    assessment = result.persistence_assessment
    assert PersistenceClassification.RECEIVER_RECONNECT_PERSISTENT in assessment.classifications
    assert PersistenceClassification.POWER_CYCLE_PERSISTENT not in assessment.classifications
    assert result.next_plan.selected_action.action_id == "POWER_CYCLE_PERSISTENCE"


def test_power_cycle_survival_supports_device_storage_but_reversion_does_not():
    survived = _verify((_effect(),), (_persistence(PersistenceLevel.POWER_CYCLE),))
    classes = survived.persistence_assessment.classifications
    assert PersistenceClassification.POWER_CYCLE_PERSISTENT in classes
    assert PersistenceClassification.DEVICE_STORED in classes
    assert survived.stop_reason is LabStopReason.POWER_CYCLE_PERSISTENCE_CONFIRMED

    reverted = _verify(
        (_effect(),),
        (_persistence(PersistenceLevel.POWER_CYCLE, survived=False, after=800),),
    )
    assert PersistenceClassification.DEVICE_STORED not in reverted.persistence_assessment.classifications
    assert reverted.stop_reason is LabStopReason.STATE_REVERTED


def test_commit_apply_requirement_is_detected_without_inventing_a_command():
    reported = _effect(physical=EffectState.STATE_UNKNOWN)
    commit = _persistence(
        PersistenceLevel.PROTOCOL_REREAD,
        commit_observed=True,
    )
    result = _verify((reported,), (commit,))
    classes = result.persistence_assessment.classifications
    assert PersistenceClassification.COMMIT_REQUIRED in classes
    assert PersistenceClassification.VOLATILE_UNTIL_COMMIT in classes
    assert result.stop_reason is LabStopReason.COMMIT_REQUIREMENT_IDENTIFIED

    apply = _persistence(
        PersistenceLevel.PROTOCOL_REREAD,
        apply_observed=True,
    )
    applied = _verify((reported,), (apply,))
    assert PersistenceClassification.APPLY_REQUIRED in applied.persistence_assessment.classifications
    assert PersistenceClassification.COMMIT_REQUIRED not in applied.persistence_assessment.classifications


def test_automatic_reversion_and_host_reapplication_are_retained():
    automatic = _persistence(
        PersistenceLevel.SETTLING_IDLE,
        survived=True,
        after=800,
        automatic_reversion_observed=True,
        reversion_cause="observed timeout",
    )
    reverted = _verify((_effect(),), (automatic,))
    assert PersistenceClassification.REVERTED in reverted.persistence_assessment.classifications
    assert reverted.persistence_evidence[0].reversion_cause == "observed timeout"

    host = _persistence(
        PersistenceLevel.HOST_SESSION_RESTART,
        survived=False,
        after=1600,
        host_reapplied=True,
    )
    host_result = _verify((_effect(),), (host,))
    assert PersistenceClassification.HOST_STORED in host_result.persistence_assessment.classifications
    assert PersistenceClassification.DEVICE_STORED not in host_result.persistence_assessment.classifications

    host_survived = _verify(
        (_effect(),),
        (_persistence(PersistenceLevel.HOST_SESSION_RESTART),),
    )
    host_classes = host_survived.persistence_assessment.classifications
    assert PersistenceClassification.HOST_RESTART_PERSISTENT in host_classes
    assert PersistenceClassification.UNKNOWN_STORAGE_LOCATION in host_classes
    assert PersistenceClassification.DEVICE_STORED not in host_classes


def test_reconnect_requires_generation_boundary_and_stale_state_cannot_prove_survival():
    with pytest.raises(ValueError, match="generation boundary"):
        _persistence(
            PersistenceLevel.DEVICE_RECONNECT,
            before_generation=1,
            after_generation=1,
        )
    stale = _persistence(
        PersistenceLevel.DEVICE_RECONNECT,
        freshness=StateFreshness.STALE,
    )
    result = _verify((_effect(),), (stale,))
    assert result.persistence_assessment.strongest_confirmed_level is None
    assert any("not fresh" in item for item in result.persistence_assessment.contradictions)


def test_state_comparison_may_cross_generations_but_protocol_dialogue_may_not():
    persistence = _persistence(PersistenceLevel.DEVICE_RECONNECT)
    result = _verify((_effect(),), (persistence,))
    assert result.persistence_assessment.strongest_confirmed_level is PersistenceLevel.DEVICE_RECONNECT

    request = DialogueObservation(
        "capture", "physical", "channel", "usb-hid", Direction.OUT,
        "fixture", 1, 1, 1, 1, b"\x01",
    )
    response = DialogueObservation(
        "capture", "physical", "channel", "usb-hid", Direction.IN,
        "fixture", 2, 2, 2, 2, b"\x01",
    )
    with pytest.raises(ValueError, match="cannot cross connection generations"):
        replace(
            _experiment(),
            dialogues=(DialogueRecord(DialogueKind.RESPONSE, response, request=request),),
        )


def test_timing_profile_drives_freshness_wait():
    summary = TimingSummary(
        TimingRelationship.READ_TO_FRESH_STATE_LATENCY, "dpi", None,
        3, 3, 100_000_000, 200_000_000, 400_000_000, 300_000_000, (),
        TimingClassification.SETTLING_DELAY, "observed",
    )
    experiment = _experiment(timing_profile=ProtocolTimingProfile((), (summary,), (), (), (), ()))
    result = verify_state_effect_persistence(
        experiment, target_semantic="dpi", effect_evidence=(_effect(),),
    )
    assert result.persistence_assessment.timing_source == "ProtocolTimingProfile"
    assert result.persistence_assessment.freshness_wait_seconds >= 1.0
    assert result.persistence_assessment.timing_uncertainty is None


def test_human_effort_or_declined_disruption_stops_escalation():
    reread = (_persistence(PersistenceLevel.PROTOCOL_REREAD),)
    costly = _verify((_effect(),), reread, max_human_cost=1)
    assert costly.stop_reason is LabStopReason.NO_SAFE_HIGH_VALUE_PERSISTENCE_TEST
    declined = _verify((_effect(),), reread, user_accepts_disruptive_test=False)
    assert declined.stop_reason is LabStopReason.USER_DECLINED_DISRUPTIVE_TEST


def test_manual_restoration_is_requested_but_never_authorized_automatically():
    result = _verify((_effect(before=800, after=1600),))
    restoration = result.persistence_assessment.restoration
    assert restoration.required is True
    assert restoration.instruction
    assert restoration.automatic_write_authorized is False
    assert result.write_authorized is False

    restored = _persistence(
        PersistenceLevel.SETTLING_IDLE,
        survived=False,
        before=1600,
        after=800,
        user_restored=True,
    )
    restored_result = _verify((_effect(before=800, after=1600),), (restored,))
    assert restored_result.persistence_assessment.restoration.verified is True
    assert restored_result.persistence_assessment.restoration.required is False


def test_replay_is_deterministic_redacted_and_retains_effect_findings():
    persistence = _persistence(PersistenceLevel.DEVICE_RECONNECT)
    result = _verify((_effect(source="/dev/hidraw9:effect"),), (persistence,))
    first = result.replay_fixture()
    assert first == result.replay_fixture()
    serialized = repr(first).lower()
    assert "/dev/hidraw" not in serialized
    assert "keyboard" not in serialized
    assert "clipboard" not in serialized
    assert "screen" not in serialized
    assert first["effect_evidence"]
    assert first["persistence_evidence"]
    assert first["persistence_assessment"]
    assert result.persistence_assessment.write_authorized is False
