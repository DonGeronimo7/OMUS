"""Reactive event-condition-action model for learned peripheral behavior.

This is an explainable state representation for observations such as profile
changes, configuration modes, reconnects and asynchronous device pushes.  The
model is deliberately semantic and read/research-side: rules contain no packet
bytes and never grant hardware write authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
from typing import Iterable, Mapping


Scalar = int | str | bool | None


class ReactiveModelError(ValueError):
    pass


class AmbiguousReactiveTransition(ReactiveModelError):
    pass


def _pairs(values: Mapping[str, Scalar] | Iterable[tuple[str, Scalar]]) -> tuple[tuple[str, Scalar], ...]:
    items = tuple(values.items()) if isinstance(values, Mapping) else tuple(values)
    if any(not key or not isinstance(key, str) for key, _ in items):
        raise ReactiveModelError("reactive state keys must be non-empty strings")
    if len({key for key, _ in items}) != len(items):
        raise ReactiveModelError("reactive state keys must be unique")
    return tuple(sorted(items))


@dataclass(frozen=True)
class ReactiveState:
    values: tuple[tuple[str, Scalar], ...]

    @classmethod
    def from_mapping(cls, values: Mapping[str, Scalar]) -> "ReactiveState":
        return cls(_pairs(values))

    def __post_init__(self) -> None:
        if self.values != _pairs(self.values):
            raise ReactiveModelError("reactive state must be canonical and unique")

    def as_dict(self) -> dict[str, Scalar]:
        return dict(self.values)


@dataclass(frozen=True)
class ReactiveEvent:
    name: str
    parameters: tuple[tuple[str, Scalar], ...] = ()

    @classmethod
    def create(cls, name: str, **parameters: Scalar) -> "ReactiveEvent":
        return cls(name, _pairs(parameters))

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ReactiveModelError("reactive event name is required")
        if self.parameters != _pairs(self.parameters):
            raise ReactiveModelError("reactive event parameters must be canonical")


@dataclass(frozen=True)
class StateCondition:
    field: str
    equals: Scalar


@dataclass(frozen=True)
class StateEffect:
    field: str
    value: Scalar


@dataclass(frozen=True)
class ReactiveRule:
    name: str
    event: ReactiveEvent
    conditions: tuple[StateCondition, ...]
    effects: tuple[StateEffect, ...]
    evidence: tuple[str, ...] = ()

    @property
    def runtime_write_authorized(self) -> bool:
        return False

    def matches(self, state: ReactiveState, event: ReactiveEvent) -> bool:
        if event != self.event:
            return False
        values = state.as_dict()
        return all(values.get(item.field) == item.equals for item in self.conditions)

    def apply(self, state: ReactiveState) -> ReactiveState:
        values = state.as_dict()
        for effect in self.effects:
            values[effect.field] = effect.value
        return ReactiveState.from_mapping(values)


@dataclass(frozen=True)
class ReactiveObservation:
    event: ReactiveEvent
    before: ReactiveState
    after: ReactiveState
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReactiveInference:
    rules: tuple[ReactiveRule, ...]
    ambiguous_events: tuple[ReactiveEvent, ...]


@dataclass(frozen=True)
class ReactiveApplication:
    before: ReactiveState
    event: ReactiveEvent
    after: ReactiveState
    rule: ReactiveRule | None


class ReactiveModel:
    def __init__(self, rules: Iterable[ReactiveRule] = ()) -> None:
        self.rules = tuple(rules)

    def apply(self, state: ReactiveState, event: ReactiveEvent) -> ReactiveApplication:
        matches = tuple(rule for rule in self.rules if rule.matches(state, event))
        if len(matches) > 1:
            raise AmbiguousReactiveTransition(
                f"{event.name}: {len(matches)} reactive rules match the same state"
            )
        if not matches:
            return ReactiveApplication(state, event, state, None)
        rule = matches[0]
        return ReactiveApplication(state, event, rule.apply(state), rule)


@dataclass(frozen=True)
class OrderedStep:
    """One semantic step in a generation-bound transaction dialogue."""

    action: str
    state: ReactiveState
    delay_ms: int = 0

    def __post_init__(self) -> None:
        if not self.action.strip() or self.delay_ms < 0:
            raise ReactiveModelError("ordered steps require an action and nonnegative delay")


@dataclass(frozen=True)
class OrderedObservation:
    operation: str
    generation: int
    preconditions: ReactiveState
    steps: tuple[OrderedStep, ...]
    restored: bool
    evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.operation.strip() or self.generation < 0 or not self.steps or not self.evidence:
            raise ReactiveModelError("ordered observations require operation, generation, steps, and evidence")


@dataclass(frozen=True)
class OrderedGrammar:
    operation: str
    preconditions: ReactiveState
    actions: tuple[str, ...]
    state_sequence: tuple[ReactiveState, ...]
    maximum_delay_ms: tuple[int, ...]
    generation_lifetime: bool
    restore_required: bool
    evidence: tuple[str, ...]

    @property
    def runtime_write_authorized(self) -> bool:
        return False


@dataclass(frozen=True)
class OrderedInference:
    grammars: tuple[OrderedGrammar, ...]
    ambiguous_operations: tuple[str, ...]


def infer_ordered_grammars(
    observations: Iterable[OrderedObservation], *, minimum_observations: int = 2,
) -> OrderedInference:
    """Infer repeated ordered/register dialogue, abstaining on hidden state.

    Preconditions, action order, intermediate register state, timing bounds,
    connection lifetime and restore semantics are retained.  Conflicting traces
    under the same visible pre-state are reported as ambiguous.
    """

    if minimum_observations < 1:
        raise ValueError("minimum_observations must be positive")
    grouped: dict[tuple[str, ReactiveState], list[OrderedObservation]] = defaultdict(list)
    for observation in observations:
        grouped[(observation.operation, observation.preconditions)].append(observation)
    grammars: list[OrderedGrammar] = []
    ambiguous: set[str] = set()
    for (operation, preconditions), rows in sorted(grouped.items(), key=lambda item: repr(item[0])):
        eligible = tuple(rows)
        if len(eligible) < minimum_observations:
            continue
        signatures = {
            (tuple(step.action for step in row.steps), tuple(step.state for step in row.steps), row.restored)
            for row in eligible
        }
        if len(signatures) != 1:
            ambiguous.add(operation)
            continue
        actions, states, restored = next(iter(signatures))
        delays = tuple(max(row.steps[index].delay_ms for row in eligible)
                       for index in range(len(actions)))
        evidence = tuple(dict.fromkeys(ref for row in eligible for ref in row.evidence))
        grammars.append(OrderedGrammar(
            operation, preconditions, actions, states, delays,
            generation_lifetime=len({row.generation for row in eligible}) == 1,
            restore_required=restored, evidence=evidence,
        ))
    return OrderedInference(tuple(grammars), tuple(sorted(ambiguous)))


def _effect_signature(observation: ReactiveObservation) -> tuple[tuple[str, Scalar], ...]:
    before, after = observation.before.as_dict(), observation.after.as_dict()
    keys = sorted(set(before) | set(after))
    return tuple((key, after.get(key)) for key in keys if before.get(key) != after.get(key))


def _stable_before_values(observations: tuple[ReactiveObservation, ...]) -> dict[str, Scalar]:
    if not observations:
        return {}
    states = [item.before.as_dict() for item in observations]
    common = set(states[0])
    for state in states[1:]:
        common &= set(state)
    return {
        key: states[0][key]
        for key in common
        if all(state[key] == states[0][key] for state in states[1:])
    }


def infer_reactive_rules(
    observations: Iterable[ReactiveObservation],
    *,
    minimum_observations: int = 2,
) -> ReactiveInference:
    """Infer deterministic ECA hypotheses from repeated observed transitions.

    If the same event has multiple effects, rules are emitted only when stable
    *pre-state* fields unambiguously distinguish every effect group.  Otherwise
    that event is reported as ambiguous rather than inventing hidden state.
    """

    if minimum_observations < 1:
        raise ValueError("minimum_observations must be positive")
    by_event: dict[ReactiveEvent, list[ReactiveObservation]] = defaultdict(list)
    for observation in observations:
        by_event[observation.event].append(observation)

    rules: list[ReactiveRule] = []
    ambiguous: list[ReactiveEvent] = []
    for event in sorted(by_event, key=lambda item: (item.name, item.parameters)):
        event_observations = tuple(by_event[event])
        by_effect: dict[tuple[tuple[str, Scalar], ...], list[ReactiveObservation]] = defaultdict(list)
        for observation in event_observations:
            by_effect[_effect_signature(observation)].append(observation)
        eligible = {
            signature: tuple(group)
            for signature, group in by_effect.items()
            if len(group) >= minimum_observations
        }
        if not eligible:
            continue

        stable = {signature: _stable_before_values(group) for signature, group in eligible.items()}
        conditions: dict[tuple[tuple[str, Scalar], ...], tuple[StateCondition, ...]] = {}
        if len(eligible) == 1:
            signature = next(iter(eligible))
            conditions[signature] = ()
        else:
            distinguishable = True
            for signature in eligible:
                useful: list[StateCondition] = []
                current = stable[signature]
                for field, value in sorted(current.items()):
                    if all(
                        other == signature
                        or field not in stable[other]
                        or stable[other][field] != value
                        for other in eligible
                    ):
                        useful.append(StateCondition(field, value))
                if not useful:
                    distinguishable = False
                    break
                conditions[signature] = tuple(useful)
            if not distinguishable:
                ambiguous.append(event)
                continue

        for index, (signature, group) in enumerate(sorted(eligible.items(), key=repr), start=1):
            evidence = tuple(dict.fromkeys(eid for item in group for eid in item.evidence))
            effects = tuple(StateEffect(field, value) for field, value in signature)
            rules.append(ReactiveRule(
                f"{event.name}:{index}", event, conditions[signature], effects, evidence
            ))

    return ReactiveInference(tuple(rules), tuple(ambiguous))
