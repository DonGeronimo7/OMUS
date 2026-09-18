from dataclasses import replace
from types import SimpleNamespace

import pytest

from mouse_control.discovery_lab import (
    BatteryCondition,
    ChargingState,
    LabExperiment,
    LabInterval,
    PowerEvidence,
    PowerObservationContext,
    PowerSemantic,
    PowerSourceState,
    ProtocolObservation,
)
from mouse_control.power_investigator import analyze_power_state
from mouse_control.proof_state import ProofState
from mouse_control.temporal_dialogue import StateFreshness


CONTEXT = {
    "bus": 3,
    "vendor_id": 0x046D,
    "product_id": 0xC53F,
    "model_fingerprint": "receiver-model",
    "instance_fingerprint": "device-unique-1",
}


def _experiment(**changes):
    experiment = LabExperiment(
        "power-current", CONTEXT, 2, "power-state fixture", None, (), (),
    )
    return replace(experiment, **changes)


def _evidence(
    value,
    timestamp,
    *,
    field="telemetry:2",
    semantic=PowerSemantic.PERCENTAGE_CANDIDATE,
    experiment_id="power-current",
    session="session-current",
    context=PowerObservationContext.UNKNOWN,
    freshness=StateFreshness.FRESH,
    charging=ChargingState.UNKNOWN,
    source=PowerSourceState.UNKNOWN,
    battery=BatteryCondition.UNKNOWN,
    independent=None,
    known=False,
    cadence=None,
    route_owner=None,
    contradictions=(),
):
    return PowerEvidence(
        evidence_id=f"power-{experiment_id}-{session}-{timestamp}-{field}",
        experiment_id=experiment_id,
        physical_device_context=CONTEXT,
        connection_generation=2,
        session_id=session,
        source_observation_ids=(f"observation-{session}-{timestamp}",),
        field_id=field,
        route_evidence_id="route-evidence" if route_owner else None,
        route_owner=route_owner,
        route_confidence="high" if route_owner else "unknown",
        candidate_semantic=semantic,
        raw_value=value,
        decoded_value=value,
        units_if_proven="%" if known and semantic is PowerSemantic.PERCENTAGE_CONFIRMED else None,
        power_source_state=source,
        charging_state=charging,
        battery_state=battery,
        freshness=freshness,
        timestamp_ns=timestamp,
        cadence_ns=cadence,
        context=context,
        independent_reference_value=independent,
        independent_reference_source="vendor-reference" if independent is not None else None,
        known_protocol_semantics=known,
        confidence="known-semantics" if known else "candidate",
        proof_state=ProofState.RECOGNIZED if known else ProofState.HYPOTHESIZED,
        contradictions=tuple(contradictions),
    )


def test_single_zero_to_hundred_value_is_only_a_percentage_candidate():
    result = analyze_power_state(
        _experiment(), supplied_evidence=(_evidence(73, 10),),
        charging_action_available=False,
    )
    assert result.power_analysis.battery_semantic is PowerSemantic.PERCENTAGE_CANDIDATE
    assert result.power_analysis.battery_units is None
    assert result.power_analysis.pending_natural_observation is True


@pytest.mark.parametrize("proof", ["known", "independent"])
def test_percentage_is_confirmed_only_by_semantics_or_independent_agreement(proof):
    kwargs = {"known": True, "semantic": PowerSemantic.PERCENTAGE_CONFIRMED}
    if proof == "independent":
        kwargs = {"independent": 64}
    result = analyze_power_state(
        _experiment(), supplied_evidence=(_evidence(64, 10, **kwargs),),
    )
    assert result.power_analysis.battery_semantic is PowerSemantic.PERCENTAGE_CONFIRMED
    assert result.power_analysis.battery_value == 64
    assert result.power_analysis.battery_units == "%"


def test_raw_bucket_and_voltage_are_retained_without_invented_conversion():
    raw = analyze_power_state(
        _experiment(), supplied_evidence=(_evidence(
            217, 10, semantic=PowerSemantic.RAW_LEVEL_CANDIDATE,
        ),),
    )
    voltage = analyze_power_state(
        _experiment(), supplied_evidence=(_evidence(
            3.71, 10, semantic=PowerSemantic.VOLTAGE_CANDIDATE, known=True,
        ),),
    )
    assert raw.power_analysis.battery_semantic is PowerSemantic.RAW_LEVEL_CANDIDATE
    assert raw.power_analysis.battery_value == 217
    assert raw.power_analysis.battery_units is None
    assert voltage.power_analysis.battery_semantic is PowerSemantic.VOLTAGE_CANDIDATE
    assert voltage.power_analysis.battery_value == 3.71


def test_explicit_charging_external_power_low_and_full_states_remain_separate():
    evidence = (
        _evidence(True, 10, field=None, semantic=PowerSemantic.CHARGING,
                  charging=ChargingState.CHARGING, source=PowerSourceState.EXTERNAL_POWER),
        _evidence(True, 20, field=None, semantic=PowerSemantic.LOW_BATTERY,
                  battery=BatteryCondition.LOW_BATTERY),
        _evidence(True, 30, field=None, semantic=PowerSemantic.FULL,
                  charging=ChargingState.CHARGE_COMPLETE,
                  source=PowerSourceState.EXTERNAL_POWER,
                  battery=BatteryCondition.FULL),
    )
    result = analyze_power_state(_experiment(), supplied_evidence=evidence)
    assert result.power_analysis.charging_state is ChargingState.CHARGE_COMPLETE
    assert result.power_analysis.power_source_state is PowerSourceState.EXTERNAL_POWER
    assert result.power_analysis.battery_state is BatteryCondition.FULL


def test_repeated_controlled_cable_transition_derives_charging_and_external_power():
    observations = (
        ProtocolObservation("hid", "stream", 10, 1, b"\x10\x00", LabInterval.BASELINE,
                            report_id=0x10, connection_generation=2),
        ProtocolObservation("hid", "stream", 20, 2, b"\x10\x01", LabInterval.ACTION,
                            repeat=1, report_id=0x10, connection_generation=2),
        ProtocolObservation("hid", "stream", 30, 3, b"\x10\x01", LabInterval.ACTION,
                            repeat=2, report_id=0x10, connection_generation=2),
    )
    result = analyze_power_state(_experiment(
        observations=observations, human_action="connect_charging",
    ))
    assert result.power_analysis.charging_state is ChargingState.CHARGING
    assert result.power_analysis.power_source_state is PowerSourceState.EXTERNAL_POWER
    transition = next(
        item for item in result.power_evidence
        if item.candidate_semantic is PowerSemantic.CHARGING
    )
    assert transition.confidence == "repeated-controlled-transition"


def test_fresh_state_supersedes_stale_cache_and_preserves_the_disagreement():
    result = analyze_power_state(_experiment(), supplied_evidence=(
        _evidence(80, 20, freshness=StateFreshness.STALE),
        _evidence(76, 10, freshness=StateFreshness.FRESH),
    ))
    assert result.power_analysis.battery_value == 76
    assert result.power_analysis.freshness is StateFreshness.FRESH
    assert "stale cached power state" in " ".join(result.power_analysis.contradictions)


def test_update_cadence_and_confirmed_route_owner_are_reported_without_granting_authority():
    result = analyze_power_state(_experiment(), supplied_evidence=(
        _evidence(55, 10, cadence=60_000_000_000, route_owner="selected-child"),
    ))
    assert result.power_analysis.cadence_ns == 60_000_000_000
    assert result.power_analysis.route_owner == "selected-child"
    assert result.power_analysis.route_confidence == "high"
    assert result.write_authorized is False
    assert result.power_analysis.write_authorized is False


def test_cross_session_slow_drain_requires_exact_device_and_directional_repetition():
    history = tuple(
        _evidence(
            value, timestamp, experiment_id=f"older-{timestamp}", session=f"day-{timestamp}",
            context=PowerObservationContext.DISCHARGING,
            source=PowerSourceState.BATTERY_POWER,
        )
        for value, timestamp in ((91, 10), (89, 20), (86, 30))
    )
    result = analyze_power_state(_experiment(), cross_session_evidence=history)
    candidate = result.power_analysis.field_candidates[0]
    assert candidate.semantic is PowerSemantic.PERCENTAGE_CONFIRMED
    assert candidate.distinct_sessions == 3

    wrong_device = replace(history[0], physical_device_context={**CONTEXT, "instance_fingerprint": "other"})
    with pytest.raises(ValueError, match="physical identity"):
        analyze_power_state(_experiment(), cross_session_evidence=(wrong_device,))


def test_wrong_direction_and_independent_disagreement_are_retained_as_contradictions():
    evidence = (
        _evidence(40, 10, context=PowerObservationContext.CHARGING_CONNECTED),
        _evidence(38, 20, context=PowerObservationContext.CHARGING_CONNECTED,
                  independent=75),
    )
    result = analyze_power_state(_experiment(), supplied_evidence=evidence)
    text = " ".join(result.power_analysis.contradictions)
    assert "decreases during an observed charging sequence" in text
    assert "independent power reference disagrees" in text


def test_ambiguous_fields_and_mouse_receiver_disagreement_are_not_averaged_away():
    evidence = (
        _evidence(80, 10, field="mouse:2", route_owner="selected-mouse"),
        _evidence(72, 10, field="receiver:4", route_owner="receiver-cache"),
    )
    result = analyze_power_state(_experiment(), supplied_evidence=evidence)
    text = " ".join(result.power_analysis.contradictions)
    assert "multiple equally supported battery fields remain ambiguous" in text
    assert "fresh mouse and receiver-routed power sources disagree" in text


def test_planner_prefers_one_bounded_charging_transition_and_never_waits_for_drain():
    result = analyze_power_state(_experiment(), supplied_evidence=(_evidence(50, 10),))
    plan = result.power_analysis.next_plan
    assert plan.selected_action.action_id == "CHARGING_TRANSITION"
    assert plan.selected_action.physical_effort <= 3
    assert "wait" not in plan.selected_action.human_instruction.lower()
    assert "drain" not in plan.selected_action.human_instruction.lower()


def test_receiver_cache_ambiguity_selects_mouse_power_cycle_experiment():
    routing = SimpleNamespace(ambiguities=("receiver cache ownership is unresolved",))
    result = analyze_power_state(
        _experiment(routing_analysis=routing), supplied_evidence=(_evidence(50, 10),),
    )
    assert result.power_analysis.next_plan.selected_action.action_id == "POWER_CYCLE_PERSISTENCE"


def test_replay_is_deterministic_private_and_preserves_raw_and_interpreted_values():
    result = analyze_power_state(_experiment(), supplied_evidence=(
        _evidence(48, 10, route_owner="serial-secret-owner", independent=48),
    ))
    first = result.replay_fixture()
    assert first == result.replay_fixture()
    serialized = repr(first).lower()
    assert "serial-secret-owner" not in serialized
    assert "vendor-reference" not in serialized
    power = first["power_evidence"][0]
    assert power["raw_value"] == 48
    assert power["decoded_value"] == 48
    assert result.write_authorized is False
