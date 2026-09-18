from dataclasses import replace
from types import SimpleNamespace

import pytest

from mouse_control.discovery_lab import (
    ActionSafetyClass,
    ControlledAction,
    ControlledActionType,
    DiscoveryLabCancelled,
    HypothesisDisposition,
    LabHypothesis,
    LabInstrument,
    LabStopReason,
    PhysicalEvidence,
    ProtocolTimingProfile,
    TimingClassification,
    TimingRelationship,
    TimingSummary,
)
from mouse_control.event_correlation import PhysicalAction, TimedReport
from mouse_control.lab_orchestrator import (
    ACTION_TEMPLATES,
    execute_lab_plan,
    plan_next_experiment,
)
from mouse_control.learning_session import LearningSample


def _hypotheses():
    return (
        LabHypothesis(
            "direct", "Which field is DPI?", "direct DPI value", "dpi",
            {"DPI_STAGE_CHANGE": "step", "MULTI_DPI_STAGE_SEQUENCE": "numeric"},
        ),
        LabHypothesis(
            "index", "Which field is DPI?", "stage index", "dpi",
            {"DPI_STAGE_CHANGE": "step", "MULTI_DPI_STAGE_SEQUENCE": "index"},
        ),
        LabHypothesis(
            "pulse", "Which field is DPI?", "button pulse", "dpi",
            {"DPI_STAGE_CHANGE": "pulse", "MULTI_DPI_STAGE_SEQUENCE": "pulse"},
        ),
    )


def _physical():
    return SimpleNamespace(
        ambiguous=False, bus=3, vendor_id=1, product_id=2,
        model_fingerprint="model", instance_fingerprint="instance",
    )


class _Session:
    calls = 0

    def __init__(self, physical, descriptors):
        pass

    def observe_action(self, *, seconds):
        assert 0 < seconds <= 10
        type(self).calls += 1
        call = type(self).calls
        value = 0x20 if call in {2, 3} else 0x10
        return LearningSample(PhysicalAction(
            call * 100, call * 100 + 50,
            hid_reports=[TimedReport(call * 100 + 1, ("stable", 1), bytes((1, value)))],
        ))


def test_highest_information_safe_action_is_selected_and_cpi_is_automatic():
    plan = plan_next_experiment(_hypotheses())
    assert plan.selected_action.action_id == "MULTI_DPI_STAGE_SEQUENCE"
    assert plan.expected_information_gain_bits > 0
    assert plan.repeat_count == 3
    assert plan.negative_control.action_id == "MOUSE_MOVEMENT"
    assert LabInstrument.CPI_VERIFIER in plan.instruments
    assert plan.write_authorized is False


def test_unsafe_action_is_rejected_and_equal_information_prefers_lower_effort():
    cheap = ControlledAction(
        "cheap", ControlledActionType.MOUSE_BUTTON_PRESS, "cheap",
        ActionSafetyClass.PHYSICAL_ONLY, "press once", physical_effort=1,
    )
    costly = replace(cheap, action_id="costly", label="costly", physical_effort=8)
    unsafe = replace(
        cheap, action_id="unsafe", label="unsafe",
        safety_class=ActionSafetyClass.BOUNDED_ENGINE_EXPERIMENT,
    )
    hypotheses = (
        LabHypothesis("a", "q", "a", "button", {"cheap": 0, "costly": 0, "unsafe": 1}),
        LabHypothesis("b", "q", "b", "button", {"cheap": 1, "costly": 1, "unsafe": 0}),
    )
    plan = plan_next_experiment(hypotheses, available_actions=(unsafe, costly, cheap))
    assert plan.selected_action.action_id == "cheap"
    assert "unsafe" not in {item.action_id for item in plan.candidate_actions}


def test_repeat_count_and_polling_instrument_follow_question():
    hypotheses = (
        LabHypothesis("p1", "Polling?", "125 Hz", "polling", {"MOUSE_MOVEMENT": 125}),
        LabHypothesis("p2", "Polling?", "1000 Hz", "polling", {"MOUSE_MOVEMENT": 1000}),
    )
    plan = plan_next_experiment(
        hypotheses, available_actions=(ACTION_TEMPLATES["MOUSE_MOVEMENT"],),
    )
    assert plan.repeat_count == 5
    assert LabInstrument.POLLING_VERIFIER in plan.instruments


def test_timing_profile_derives_bounded_windows_and_records_source():
    summary = TimingSummary(
        TimingRelationship.READ_TO_FRESH_STATE_LATENCY, "state", None,
        3, 3, 100_000_000, 200_000_000, 400_000_000, 300_000_000, (),
        TimingClassification.SETTLING_DELAY, "observed",
    )
    profile = ProtocolTimingProfile((), (summary,), (), (), (), ())
    plan = plan_next_experiment(_hypotheses(), timing_profile=profile)
    assert plan.windows.source == "ProtocolTimingProfile"
    assert plan.windows.post_action_seconds >= 1.0
    assert plan.windows.baseline_seconds <= 10.0
    default = plan_next_experiment(_hypotheses()).windows
    assert default.uncertainty is not None


def test_completed_plan_runs_verifier_analyzer_updates_and_stops():
    _Session.calls = 0
    hypothesis = LabHypothesis(
        "only", "Which field changes?", "the action field", "dpi",
        {"DPI_STAGE_CHANGE": "changed"},
    )
    plan = plan_next_experiment(
        (hypothesis,), available_actions=(ACTION_TEMPLATES["DPI_STAGE_CHANGE"],),
    )
    invoked = []

    def verify(received):
        invoked.append(received.plan_id)
        return (PhysicalEvidence("cpi", 800, "CPI"),)

    events = []
    experiment = execute_lab_plan(
        _physical(), {}, plan, prompt=lambda step: True,
        progress=events.append, session_factory=_Session,
        verifier_runners={LabInstrument.CPI_VERIFIER: verify},
    )
    assert invoked == [plan.plan_id]
    assert experiment.analysis is not None
    assert experiment.physical_cpi_evidence[0].value == 800
    assert experiment.hypothesis_updates[0].after is HypothesisDisposition.STRENGTHENED
    assert experiment.stop_reason is LabStopReason.HYPOTHESIS_RESOLVED
    assert events[-1].completed == events[-1].total
    assert experiment.write_authorized is False


def test_completed_plan_can_feed_the_effect_persistence_verifier():
    _Session.calls = 0
    hypothesis = LabHypothesis(
        "only", "Which field changes?", "the action field", "dpi",
        {"DPI_STAGE_CHANGE": "changed"},
    )
    plan = plan_next_experiment(
        (hypothesis,), available_actions=(ACTION_TEMPLATES["DPI_STAGE_CHANGE"],),
    )
    received = []

    def effect_verifier(experiment):
        received.append(experiment.analysis is not None)
        return replace(experiment, confidence="effect-checked")

    experiment = execute_lab_plan(
        _physical(), {}, plan, prompt=lambda step: True,
        session_factory=_Session, effect_verifier=effect_verifier,
    )
    assert received == [True]
    assert experiment.confidence == "effect-checked"
    assert experiment.write_authorized is False


def test_completed_plan_can_feed_the_receiver_child_route_mapper():
    _Session.calls = 0
    hypothesis = LabHypothesis(
        "only", "Which route changes?", "selected route", "routing",
        {"OTHER_CHILD_ROUTE_CONTROL": "changed"},
    )
    plan = plan_next_experiment(
        (hypothesis,), available_actions=(ACTION_TEMPLATES["OTHER_CHILD_ROUTE_CONTROL"],),
    )
    received = []

    def route_mapper(experiment):
        received.append(experiment.analysis is not None)
        return replace(experiment, confidence="route-checked")

    experiment = execute_lab_plan(
        _physical(), {}, plan, prompt=lambda step: True,
        session_factory=_Session, route_mapper=route_mapper,
    )
    assert received == [True]
    assert experiment.confidence == "route-checked"
    assert experiment.write_authorized is False


def test_completed_plan_can_feed_the_power_state_investigator():
    _Session.calls = 0
    hypothesis = LabHypothesis(
        "only", "Which field is power state?", "selected power field", "charging",
        {"CHARGING_TRANSITION": "changed"},
    )
    plan = plan_next_experiment(
        (hypothesis,), available_actions=(ACTION_TEMPLATES["CHARGING_TRANSITION"],),
    )
    received = []

    def power_investigator(experiment):
        received.append(experiment.analysis is not None)
        return replace(experiment, confidence="power-checked")

    experiment = execute_lab_plan(
        _physical(), {}, plan, prompt=lambda step: True,
        session_factory=_Session, power_investigator=power_investigator,
    )
    assert received == [True]
    assert experiment.confidence == "power-checked"
    assert experiment.write_authorized is False


def test_power_related_plan_invokes_the_investigator_automatically():
    _Session.calls = 0
    hypotheses = (
        LabHypothesis(
            "power", "Which field is power state?", "power field", "charging",
            {"CHARGING_TRANSITION": "changed"},
        ),
        LabHypothesis(
            "unrelated", "Which field is power state?", "unrelated field", "charging",
            {"CHARGING_TRANSITION": "stable"},
        ),
    )
    plan = plan_next_experiment(
        hypotheses, available_actions=(ACTION_TEMPLATES["CHARGING_TRANSITION"],),
    )
    experiment = execute_lab_plan(
        _physical(), {}, plan, prompt=lambda step: True, session_factory=_Session,
    )
    assert experiment.power_analysis is not None
    assert experiment.power_analysis.write_authorized is False


def test_unresolved_ambiguity_recalculates_the_next_best_experiment():
    _Session.calls = 0
    plan = plan_next_experiment(_hypotheses())
    experiment = execute_lab_plan(
        _physical(), {}, plan, prompt=lambda step: True, session_factory=_Session,
    )
    assert experiment.stop_reason is None
    assert experiment.next_plan is not None
    assert experiment.next_plan.selected_action.action_id == "DPI_STAGE_CHANGE"
    assert experiment.next_plan.selected_action.action_id != plan.selected_action.action_id


def test_negative_control_rejects_candidate_and_preserves_negative_evidence():
    class Contradicting(_Session):
        calls = 0

        def observe_action(self, *, seconds):
            sample = super().observe_action(seconds=seconds)
            if type(self).calls == 5:
                return LearningSample(PhysicalAction(
                    500, 550, hid_reports=[TimedReport(501, ("stable", 1), b"\x01\x20")],
                ))
            return sample

    Contradicting.calls = 0
    source = "stream:390e4a5072a449b8"
    hypothesis = LabHypothesis(
        "candidate", "Field?", "candidate field", "dpi",
        {"DPI_STAGE_CHANGE": "changed"}, candidate_field=(f"{source}:input:2:1", 1),
    )
    plan = plan_next_experiment(
        (hypothesis,), available_actions=(ACTION_TEMPLATES["DPI_STAGE_CHANGE"],),
    )
    experiment = execute_lab_plan(
        _physical(), {}, plan, prompt=lambda step: True, session_factory=Contradicting,
    )
    actual = next(item for item in experiment.analysis.ranked_fields if item.offset == 1)
    experiment = replace(
        experiment,
        plan=replace(plan, target_hypotheses=(replace(hypothesis, candidate_field=(actual.stream_id, 1)),)),
    )
    from mouse_control.lab_orchestrator import update_hypotheses
    update = update_hypotheses(experiment.plan.target_hypotheses, experiment)[0]
    assert update.after is HypothesisDisposition.REJECTED
    assert update.negative_evidence


def test_no_safe_experiment_and_user_cancellation_are_explicit():
    unsafe = ControlledAction(
        "write", ControlledActionType.CUSTOM_LABELLED_ACTION, "write",
        ActionSafetyClass.BOUNDED_ENGINE_EXPERIMENT, "do not run",
    )
    hypotheses = (
        LabHypothesis("a", "q", "a", "unknown", {"write": 0}),
        LabHypothesis("b", "q", "b", "unknown", {"write": 1}),
    )
    stopped = plan_next_experiment(hypotheses, available_actions=(unsafe,))
    assert stopped.selected_action is None
    assert stopped.stop_reason is LabStopReason.INSUFFICIENT_SAFE_ACTIONS

    plan = plan_next_experiment(
        _hypotheses(), available_actions=(ACTION_TEMPLATES["MULTI_DPI_STAGE_SEQUENCE"],),
    )
    with pytest.raises(DiscoveryLabCancelled, match="user_cancelled"):
        execute_lab_plan(_physical(), {}, plan, prompt=lambda step: False, session_factory=_Session)


def test_plan_and_result_replay_are_deterministic_and_privacy_redacted():
    _Session.calls = 0
    plan = plan_next_experiment(
        (LabHypothesis("one", "q", "claim", "dpi", {"DPI_STAGE_CHANGE": 1}),),
        available_actions=(ACTION_TEMPLATES["DPI_STAGE_CHANGE"],),
    )
    experiment = execute_lab_plan(
        _physical(), {}, plan, prompt=lambda step: True, session_factory=_Session,
    )
    assert plan.replay_fixture() == plan.replay_fixture()
    first = experiment.replay_fixture()
    assert first == experiment.replay_fixture()
    serialized = repr(first).lower()
    assert "/dev/" not in serialized
    assert "keyboard" not in serialized
    assert "clipboard" not in serialized
    assert "screen" not in serialized
    assert "evdev" not in serialized
