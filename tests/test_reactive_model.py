# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import pytest

from mouse_control.reactive_model import (
    AmbiguousReactiveTransition, ReactiveEvent, ReactiveModel, ReactiveObservation,
    ReactiveRule, ReactiveState, StateCondition, StateEffect, infer_reactive_rules,
)


def state(**values):
    return ReactiveState.from_mapping(values)


def test_repeated_event_infers_explainable_unconditional_effect() -> None:
    event = ReactiveEvent.create("set_dpi", value=1600)
    inference = infer_reactive_rules((
        ReactiveObservation(event, state(dpi=800, profile=0), state(dpi=1600, profile=0), ("e1",)),
        ReactiveObservation(event, state(dpi=1200, profile=0), state(dpi=1600, profile=0), ("e2",)),
    ))
    assert not inference.ambiguous_events
    assert len(inference.rules) == 1
    rule = inference.rules[0]
    assert rule.conditions == ()
    assert rule.effects == (StateEffect("dpi", 1600),)
    assert rule.evidence == ("e1", "e2")
    assert not rule.runtime_write_authorized
    applied = ReactiveModel(inference.rules).apply(state(dpi=800, profile=0), event)
    assert applied.after == state(dpi=1600, profile=0)


def test_same_event_with_two_effects_infers_state_conditions_when_observed() -> None:
    event = ReactiveEvent.create("reconnect")
    observations = (
        ReactiveObservation(event, state(onboard=True, dpi=800), state(onboard=True, dpi=800), ("a1",)),
        ReactiveObservation(event, state(onboard=True, dpi=1200), state(onboard=True, dpi=1200), ("a2",)),
        ReactiveObservation(event, state(onboard=False, dpi=800), state(onboard=False, dpi=1600), ("b1",)),
        ReactiveObservation(event, state(onboard=False, dpi=1200), state(onboard=False, dpi=1600), ("b2",)),
    )
    inference = infer_reactive_rules(observations)
    assert not inference.ambiguous_events
    assert len(inference.rules) == 2
    by_condition = {rule.conditions: rule for rule in inference.rules}
    assert (StateCondition("onboard", True),) in by_condition
    assert (StateCondition("onboard", False),) in by_condition
    model = ReactiveModel(inference.rules)
    assert model.apply(state(onboard=False, dpi=800), event).after.as_dict()["dpi"] == 1600
    assert model.apply(state(onboard=True, dpi=800), event).after.as_dict()["dpi"] == 800


def test_conflicting_hidden_state_is_reported_ambiguous_not_guessed() -> None:
    event = ReactiveEvent.create("profile_button")
    observations = (
        ReactiveObservation(event, state(profile=0), state(profile=1), ("a",)),
        ReactiveObservation(event, state(profile=0), state(profile=1), ("b",)),
        ReactiveObservation(event, state(profile=0), state(profile=2), ("c",)),
        ReactiveObservation(event, state(profile=0), state(profile=2), ("d",)),
    )
    inference = infer_reactive_rules(observations)
    assert inference.rules == ()
    assert inference.ambiguous_events == (event,)


def test_single_observation_does_not_become_rule_by_default() -> None:
    event = ReactiveEvent.create("async_push")
    inference = infer_reactive_rules((
        ReactiveObservation(event, state(dpi=800), state(dpi=1600), ("one",)),
    ))
    assert inference.rules == ()


def test_model_refuses_overlapping_rules() -> None:
    event = ReactiveEvent.create("tick")
    rules = (
        ReactiveRule("a", event, (), (StateEffect("x", 1),)),
        ReactiveRule("b", event, (), (StateEffect("x", 2),)),
    )
    with pytest.raises(AmbiguousReactiveTransition):
        ReactiveModel(rules).apply(state(x=0), event)
