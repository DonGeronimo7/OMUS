"""Persisted exact-model learned polling state machines.

Polling is intentionally modeled separately from the simple learned DPI transaction
grammar. A polling operation owns an explicit control-state query and two learned
branches:

* Onboard-start: query -> learned takeover/verification/write/read continuation.
* Host-start: query -> learned write/read continuation.

Teacher corpora remain non-authoritative. This module can infer a DEMONSTRATED
state machine from them, but write authority exists only after an explicit
physical promotion records generic readback for every demonstrated rate,
independent physical timing, one persistent raw HID session, and verified rollback.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import json
import os
from pathlib import Path
import pwd
from tempfile import NamedTemporaryFile
from typing import Any, Mapping, Sequence

from .learned_operations import (
    LearnedOperationError,
    LearnedOperationState,
    StableDeviceIdentity,
    StableInterfaceIdentity,
    get_learned_operation_directory,
    operation_matches_physical,
)
from .polling_replay import (
    PacketPattern,
    PollingReplayError,
    PollingReplayGrammar,
    ReplayStep,
    infer_polling_replay_grammar,
)
from .protocol_grammar import SafetyClass, SemanticBehavior, WriteScope


LEARNED_POLLING_SCHEMA_VERSION = 1


class PollingControlState(str, Enum):
    ONBOARD = "onboard"
    HOST = "host"


class LearnedPollingOperationError(LearnedOperationError):
    """A learned polling state machine is malformed, ambiguous, or unsafe."""


@dataclass(frozen=True)
class LearnedPollingOperation:
    behavior: SemanticBehavior
    state: LearnedOperationState
    identity: StableDeviceIdentity
    interface: StableInterfaceIdentity
    demonstrated_rates: tuple[int, ...]
    raw_to_hz: Mapping[int, int]
    control_query_request: PacketPattern
    control_query_response: PacketPattern
    control_state_offset: int
    onboard_state_raw: int
    host_state_raw: int
    onboard_steps: tuple[ReplayStep, ...]
    host_steps: tuple[ReplayStep, ...]
    safety: SafetyClass = SafetyClass.REVERSIBLE
    write_scope: WriteScope = WriteScope.EXACT_MODEL
    promotion_evidence: Mapping[str, Any] | None = None

    @property
    def write_authorized(self) -> bool:
        return self.state is LearnedOperationState.PROVEN

    def accepts(self, rate_hz: int) -> bool:
        return int(rate_hz) in self.demonstrated_rates

    def raw_for_rate(self, rate_hz: int) -> int:
        rate = int(rate_hz)
        if not self.accepts(rate):
            raise LearnedPollingOperationError(
                f"{rate} Hz was not physically promoted as part of the demonstrated set"
            )
        matches = [raw for raw, semantic in self.raw_to_hz.items() if int(semantic) == rate]
        if len(matches) != 1:
            raise LearnedPollingOperationError(
                f"expected one raw encoding for {rate} Hz, found {len(matches)}"
            )
        return int(matches[0])

    def _control_step(self, state: PollingControlState) -> ReplayStep:
        values = list(self.control_query_response.bytes_)
        if self.control_state_offset < 0 or self.control_state_offset >= len(values):
            raise LearnedPollingOperationError("control-state offset is outside the reply")
        if values[self.control_state_offset] is not None:
            raise LearnedPollingOperationError(
                "persisted control query must wildcard exactly the learned state byte"
            )
        values[self.control_state_offset] = (
            self.onboard_state_raw
            if state is PollingControlState.ONBOARD
            else self.host_state_raw
        )
        if any(value is None for value in values):
            raise LearnedPollingOperationError(
                "control query response contains unresolved wildcard bytes"
            )
        return ReplayStep(
            request=self.control_query_request,
            response=PacketPattern(tuple(int(value) for value in values)),
        )

    def replay_grammar(self, state: PollingControlState) -> PollingReplayGrammar:
        continuation = (
            self.onboard_steps
            if state is PollingControlState.ONBOARD
            else self.host_steps
        )
        steps = (self._control_step(state),) + tuple(continuation)
        write_indexes = [
            index
            for index, step in enumerate(steps)
            if step.request_semantic_offset is not None
        ]
        read_indexes = [
            index
            for index, step in enumerate(steps)
            if step.response_semantic_offset is not None
        ]
        if len(write_indexes) != 1 or len(read_indexes) != 1:
            raise LearnedPollingOperationError(
                "each polling branch must contain exactly one semantic write and readback"
            )
        return PollingReplayGrammar(
            steps=steps,
            write_step_index=write_indexes[0],
            read_step_index=read_indexes[0],
            raw_to_hz=dict(self.raw_to_hz),
            demonstrated_rates=self.demonstrated_rates,
        )


def _exact_identity_from_profile(profile: Mapping[str, object]) -> tuple[object, ...]:
    identity = profile.get("identity")
    fingerprints = profile.get("fingerprints")
    interface = profile.get("interface")
    if not isinstance(identity, Mapping):
        return ()
    if not isinstance(fingerprints, Mapping):
        return ()
    if not isinstance(interface, Mapping):
        return ()
    return (
        identity.get("bus"),
        identity.get("vendor_id"),
        identity.get("product_id"),
        fingerprints.get("model"),
        fingerprints.get("instance"),
        interface.get("bus"),
        interface.get("vendor_id"),
        interface.get("product_id"),
        interface.get("interface_number"),
        interface.get("descriptor_sha256"),
    )


def infer_learned_polling_operation(
    onboard_profile: Mapping[str, object],
    host_profile: Mapping[str, object],
    *,
    identity: StableDeviceIdentity,
    interface: StableInterfaceIdentity,
) -> LearnedPollingOperation:
    """Infer one two-branch polling state machine without granting write authority."""

    if onboard_profile.get("profile_kind") != "polling-demonstrations":
        raise LearnedPollingOperationError("expected an Onboard-start polling corpus")
    if host_profile.get("profile_kind") != "polling-host-demonstrations":
        raise LearnedPollingOperationError("expected a Host-start polling corpus")
    if onboard_profile.get("write_authorized") is not False:
        raise LearnedPollingOperationError("Onboard teacher corpus must remain read-only")
    if host_profile.get("write_authorized") is not False:
        raise LearnedPollingOperationError("Host teacher corpus must remain read-only")

    onboard_identity = _exact_identity_from_profile(onboard_profile)
    host_identity = _exact_identity_from_profile(host_profile)
    if onboard_identity and host_identity and onboard_identity != host_identity:
        raise LearnedPollingOperationError(
            "Onboard and Host corpora describe different stable devices/interfaces"
        )

    try:
        onboard = infer_polling_replay_grammar(onboard_profile)
        host = infer_polling_replay_grammar(host_profile)
    except PollingReplayError as exc:
        raise LearnedPollingOperationError(str(exc)) from exc

    if tuple(onboard.demonstrated_rates) != tuple(host.demonstrated_rates):
        raise LearnedPollingOperationError(
            "Onboard and Host corpora do not demonstrate the same polling-rate set"
        )
    if dict(onboard.raw_to_hz) != dict(host.raw_to_hz):
        raise LearnedPollingOperationError(
            "Onboard and Host corpora disagree on polling raw-value encoding"
        )
    if not onboard.steps or not host.steps:
        raise LearnedPollingOperationError("polling branches must contain a control query")

    onboard_query = onboard.steps[0]
    host_query = host.steps[0]
    if onboard_query.request_semantic_offset is not None:
        raise LearnedPollingOperationError("Onboard control query unexpectedly carries rate data")
    if host_query.request_semantic_offset is not None:
        raise LearnedPollingOperationError("Host control query unexpectedly carries rate data")
    if onboard_query.response_semantic_offset is not None:
        raise LearnedPollingOperationError("Onboard control query unexpectedly reads rate data")
    if host_query.response_semantic_offset is not None:
        raise LearnedPollingOperationError("Host control query unexpectedly reads rate data")
    if onboard_query.request.bytes_ != host_query.request.bytes_:
        raise LearnedPollingOperationError(
            "Onboard and Host corpora do not share one control-state query request"
        )
    if any(value is None for value in onboard_query.request.bytes_):
        raise LearnedPollingOperationError("control-state query request is not fully resolved")

    onboard_response = onboard_query.response.bytes_
    host_response = host_query.response.bytes_
    if len(onboard_response) != len(host_response):
        raise LearnedPollingOperationError(
            "Onboard and Host control-state replies have different lengths"
        )
    if any(value is None for value in onboard_response + host_response):
        raise LearnedPollingOperationError(
            "control-state replies are not fully resolved in the teacher corpora"
        )
    differences = [
        index
        for index, (left, right) in enumerate(zip(onboard_response, host_response))
        if left != right
    ]
    if len(differences) != 1:
        raise LearnedPollingOperationError(
            f"expected one learned control-state byte, found {len(differences)}"
        )
    state_offset = differences[0]
    onboard_raw = int(onboard_response[state_offset])
    host_raw = int(host_response[state_offset])
    if onboard_raw == host_raw:
        raise LearnedPollingOperationError("learned control states are not distinct")

    generalized_response = list(int(value) for value in onboard_response)
    generalized_response[state_offset] = None

    # The Onboard-start branch must itself demonstrate that the control
    # transition reached the same Host state recognized by the Host-start corpus.
    if not any(
        step.response.bytes_ == host_query.response.bytes_
        for step in onboard.steps[1:]
    ):
        raise LearnedPollingOperationError(
            "Onboard branch does not contain an observed verification of Host state"
        )

    operation = LearnedPollingOperation(
        behavior=SemanticBehavior.REPORT_RATE_HZ,
        state=LearnedOperationState.DEMONSTRATED,
        identity=identity,
        interface=interface,
        demonstrated_rates=tuple(int(rate) for rate in onboard.demonstrated_rates),
        raw_to_hz={int(raw): int(rate) for raw, rate in onboard.raw_to_hz.items()},
        control_query_request=onboard_query.request,
        control_query_response=PacketPattern(tuple(generalized_response)),
        control_state_offset=state_offset,
        onboard_state_raw=onboard_raw,
        host_state_raw=host_raw,
        onboard_steps=tuple(onboard.steps[1:]),
        host_steps=tuple(host.steps[1:]),
    )
    # Structural validation also reconstructs both executable replay grammars.
    validate_learned_polling_operation(operation)
    return operation


def promote_polling_operation(
    operation: LearnedPollingOperation,
    *,
    rate_evidence: Sequence[Mapping[str, Any]],
    rollback_evidence: Mapping[str, Any],
    state_evidence: Mapping[str, Any] | None = None,
) -> LearnedPollingOperation:
    """Promote only after every demonstrated rate is independently verified."""

    if operation.state is LearnedOperationState.PROVEN:
        return operation
    if operation.safety is not SafetyClass.REVERSIBLE:
        raise LearnedPollingOperationError("only reversible polling writes may be promoted")
    if operation.write_scope is not WriteScope.EXACT_MODEL:
        raise LearnedPollingOperationError("initial polling writes must be exact-model scoped")

    expected = set(operation.demonstrated_rates)
    seen: set[int] = set()
    normalized: list[dict[str, Any]] = []
    for item in rate_evidence:
        try:
            target = int(item["target_hz"])
            readback = int(item["generic_readback_hz"])
            consensus = int(item["physical_consensus_hz"])
            confidence = str(item["confidence"])
            branch = str(item["branch"])
        except (KeyError, TypeError, ValueError) as exc:
            raise LearnedPollingOperationError(
                f"invalid polling promotion evidence: {exc}"
            ) from exc
        if target not in expected:
            raise LearnedPollingOperationError(
                f"promotion evidence contains undemonstrated rate {target} Hz"
            )
        if target in seen:
            raise LearnedPollingOperationError(
                f"duplicate promotion evidence for {target} Hz"
            )
        if readback != target:
            raise LearnedPollingOperationError(
                f"generic readback did not confirm {target} Hz"
            )
        if consensus != target:
            raise LearnedPollingOperationError(
                f"physical timing did not confirm {target} Hz"
            )
        if confidence not in {"high", "medium"}:
            raise LearnedPollingOperationError(
                f"physical timing confidence for {target} Hz is too low"
            )
        if branch not in {
            PollingControlState.ONBOARD.value,
            PollingControlState.HOST.value,
        }:
            raise LearnedPollingOperationError("unknown polling control branch in evidence")
        seen.add(target)
        normalized.append(dict(item))

    if seen != expected:
        missing = sorted(expected - seen)
        raise LearnedPollingOperationError(
            f"physical promotion did not verify every demonstrated rate; missing {missing}"
        )
    if not normalized:
        raise LearnedPollingOperationError("polling promotion evidence is empty")
    if normalized[0].get("branch") != PollingControlState.ONBOARD.value:
        raise LearnedPollingOperationError(
            "the first promoted polling transition must exercise the Onboard-start branch"
        )
    if any(
        item.get("branch") != PollingControlState.HOST.value
        for item in normalized[1:]
    ):
        raise LearnedPollingOperationError(
            "all transitions after the first must exercise the Host-start branch"
        )

    if rollback_evidence.get("success") is not True:
        raise LearnedPollingOperationError("exact polling rollback was not verified")
    try:
        original_rate = int(rollback_evidence["original_rate_hz"])
        restored_rate = int(rollback_evidence["restored_rate_hz"])
        original_mode = int(rollback_evidence["original_control_raw"])
        restored_mode = int(rollback_evidence["restored_control_raw"])
    except (KeyError, TypeError, ValueError) as exc:
        raise LearnedPollingOperationError(
            f"rollback evidence is incomplete: {exc}"
        ) from exc
    if restored_rate != original_rate or restored_mode != original_mode:
        raise LearnedPollingOperationError(
            "restored polling/control state does not equal the recorded original state"
        )

    extra_state = dict(state_evidence or {})
    if extra_state.get("persistent_generic_session") is not True:
        raise LearnedPollingOperationError(
            "promotion must prove one persistent generic HID session"
        )
    if extra_state.get("native_reopened_between_generic_writes") is not False:
        raise LearnedPollingOperationError(
            "native backend must remain closed between generic polling writes"
        )

    evidence = {
        "verified_rates": normalized,
        "persistent_session": True,
        "rollback": dict(rollback_evidence),
        "state_evidence": extra_state,
    }
    return replace(
        operation,
        state=LearnedOperationState.PROVEN,
        promotion_evidence=evidence,
    )


def _pattern_to_json(pattern: PacketPattern) -> list[int | None]:
    return list(pattern.bytes_)


def _pattern_from_json(data: Sequence[Any]) -> PacketPattern:
    values: list[int | None] = []
    try:
        for value in data:
            values.append(None if value is None else int(value))
    except (TypeError, ValueError) as exc:
        raise LearnedPollingOperationError(f"invalid packet pattern: {exc}") from exc
    if any(value is not None and not 0 <= value <= 0xFF for value in values):
        raise LearnedPollingOperationError("packet pattern bytes must fit in one byte")
    return PacketPattern(tuple(values))


def _step_to_json(step: ReplayStep) -> dict[str, Any]:
    return {
        "request": _pattern_to_json(step.request),
        "response": _pattern_to_json(step.response),
        "request_semantic_offset": step.request_semantic_offset,
        "response_semantic_offset": step.response_semantic_offset,
    }


def _step_from_json(data: Mapping[str, Any]) -> ReplayStep:
    try:
        request_offset = data.get("request_semantic_offset")
        response_offset = data.get("response_semantic_offset")
        return ReplayStep(
            request=_pattern_from_json(data["request"]),
            response=_pattern_from_json(data["response"]),
            request_semantic_offset=(
                None if request_offset is None else int(request_offset)
            ),
            response_semantic_offset=(
                None if response_offset is None else int(response_offset)
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise LearnedPollingOperationError(f"invalid replay step: {exc}") from exc


def polling_operation_to_profile(operation: LearnedPollingOperation) -> dict[str, Any]:
    return {
        "schema_version": LEARNED_POLLING_SCHEMA_VERSION,
        "profile_kind": "learned-polling-state-machine",
        "behavior": operation.behavior.value,
        "status": operation.state.value,
        "write_authorized": operation.write_authorized,
        "safety": operation.safety.value,
        "write_scope": operation.write_scope.value,
        "identity": {
            "bus": operation.identity.bus,
            "vendor_id": operation.identity.vendor_id,
            "product_id": operation.identity.product_id,
        },
        "fingerprints": {
            "model": operation.identity.model_fingerprint,
            "instance": operation.identity.instance_fingerprint,
        },
        "interface": {
            "bus": operation.interface.bus,
            "vendor_id": operation.interface.vendor_id,
            "product_id": operation.interface.product_id,
            "interface_number": operation.interface.interface_number,
            "descriptor_sha256": operation.interface.descriptor_sha256,
        },
        "demonstrated_rates": list(operation.demonstrated_rates),
        "raw_to_hz": {
            str(int(raw)): int(rate)
            for raw, rate in operation.raw_to_hz.items()
        },
        "control_query": {
            "request": _pattern_to_json(operation.control_query_request),
            "response": _pattern_to_json(operation.control_query_response),
            "state_offset": operation.control_state_offset,
            "states": {
                PollingControlState.ONBOARD.value: operation.onboard_state_raw,
                PollingControlState.HOST.value: operation.host_state_raw,
            },
        },
        "branches": {
            PollingControlState.ONBOARD.value: [
                _step_to_json(step) for step in operation.onboard_steps
            ],
            PollingControlState.HOST.value: [
                _step_to_json(step) for step in operation.host_steps
            ],
        },
        "promotion_evidence": (
            None
            if operation.promotion_evidence is None
            else dict(operation.promotion_evidence)
        ),
    }


def _maybe_int(value: Any) -> int | None:
    return None if value is None else int(value)


def polling_operation_from_profile(profile: Mapping[str, Any]) -> LearnedPollingOperation:
    validate_learned_polling_profile(profile)
    identity = profile["identity"]
    fingerprints = profile["fingerprints"]
    interface = profile["interface"]
    control = profile["control_query"]
    states = control["states"]
    branches = profile["branches"]
    return LearnedPollingOperation(
        behavior=SemanticBehavior(str(profile["behavior"])),
        state=LearnedOperationState(str(profile["status"])),
        identity=StableDeviceIdentity(
            bus=_maybe_int(identity.get("bus")),
            vendor_id=_maybe_int(identity.get("vendor_id")),
            product_id=_maybe_int(identity.get("product_id")),
            model_fingerprint=str(fingerprints["model"]),
            instance_fingerprint=(
                None
                if fingerprints.get("instance") is None
                else str(fingerprints["instance"])
            ),
        ),
        interface=StableInterfaceIdentity(
            bus=_maybe_int(interface.get("bus")),
            vendor_id=_maybe_int(interface.get("vendor_id")),
            product_id=_maybe_int(interface.get("product_id")),
            interface_number=_maybe_int(interface.get("interface_number")),
            descriptor_sha256=(
                None
                if interface.get("descriptor_sha256") is None
                else str(interface["descriptor_sha256"])
            ),
        ),
        demonstrated_rates=tuple(int(rate) for rate in profile["demonstrated_rates"]),
        raw_to_hz={
            int(raw): int(rate)
            for raw, rate in dict(profile["raw_to_hz"]).items()
        },
        control_query_request=_pattern_from_json(control["request"]),
        control_query_response=_pattern_from_json(control["response"]),
        control_state_offset=int(control["state_offset"]),
        onboard_state_raw=int(states[PollingControlState.ONBOARD.value]),
        host_state_raw=int(states[PollingControlState.HOST.value]),
        onboard_steps=tuple(
            _step_from_json(step)
            for step in branches[PollingControlState.ONBOARD.value]
        ),
        host_steps=tuple(
            _step_from_json(step)
            for step in branches[PollingControlState.HOST.value]
        ),
        safety=SafetyClass(str(profile["safety"])),
        write_scope=WriteScope(str(profile["write_scope"])),
        promotion_evidence=profile.get("promotion_evidence"),
    )


def validate_learned_polling_operation(operation: LearnedPollingOperation) -> None:
    if operation.behavior is not SemanticBehavior.REPORT_RATE_HZ:
        raise LearnedPollingOperationError("polling operation behavior must be REPORT_RATE_HZ")
    if operation.safety is not SafetyClass.REVERSIBLE:
        raise LearnedPollingOperationError("polling operation must be reversible")
    if operation.write_scope is not WriteScope.EXACT_MODEL:
        raise LearnedPollingOperationError("polling operation must be exact-model scoped")
    if not operation.identity.model_fingerprint:
        raise LearnedPollingOperationError("polling operation requires a model fingerprint")
    if not operation.interface.descriptor_sha256:
        raise LearnedPollingOperationError(
            "polling operation requires an exact descriptor fingerprint"
        )
    rates = tuple(int(rate) for rate in operation.demonstrated_rates)
    if len(rates) < 3 or len(set(rates)) != len(rates) or any(rate <= 0 for rate in rates):
        raise LearnedPollingOperationError(
            "polling operation requires at least three unique positive demonstrated rates"
        )
    mapping = {int(raw): int(rate) for raw, rate in operation.raw_to_hz.items()}
    if any(raw < 0 or raw > 0xFF for raw in mapping):
        raise LearnedPollingOperationError("polling raw values must fit in one byte")
    if len(mapping) != len(rates) or set(mapping.values()) != set(rates):
        raise LearnedPollingOperationError(
            "polling raw-value map must cover the demonstrated set one-to-one"
        )
    if any(value is None for value in operation.control_query_request.bytes_):
        raise LearnedPollingOperationError("control query request contains wildcards")
    response = operation.control_query_response.bytes_
    if (
        operation.control_state_offset < 0
        or operation.control_state_offset >= len(response)
    ):
        raise LearnedPollingOperationError("control-state offset is outside the response")
    wildcard_indexes = [
        index for index, value in enumerate(response) if value is None
    ]
    if wildcard_indexes != [operation.control_state_offset]:
        raise LearnedPollingOperationError(
            "control response must wildcard only the learned state byte"
        )
    if not 0 <= operation.onboard_state_raw <= 0xFF:
        raise LearnedPollingOperationError("Onboard raw state must fit in one byte")
    if not 0 <= operation.host_state_raw <= 0xFF:
        raise LearnedPollingOperationError("Host raw state must fit in one byte")
    if operation.onboard_state_raw == operation.host_state_raw:
        raise LearnedPollingOperationError("Onboard and Host raw states must differ")
    if not operation.onboard_steps or not operation.host_steps:
        raise LearnedPollingOperationError("both polling control branches are required")

    onboard = operation.replay_grammar(PollingControlState.ONBOARD)
    host = operation.replay_grammar(PollingControlState.HOST)
    if dict(onboard.raw_to_hz) != dict(host.raw_to_hz):
        raise LearnedPollingOperationError("polling branches disagree on raw-value mapping")
    if tuple(onboard.demonstrated_rates) != tuple(host.demonstrated_rates):
        raise LearnedPollingOperationError("polling branches disagree on demonstrated rates")

    # Onboard continuation must contain the Host-state verification observed in
    # the teaching experiment before its semantic polling write.
    host_query_reply = host.steps[0].response.bytes_
    if not any(step.response.bytes_ == host_query_reply for step in operation.onboard_steps):
        raise LearnedPollingOperationError(
            "Onboard branch does not verify that Host control state was reached"
        )

    if operation.state is LearnedOperationState.PROVEN:
        evidence = operation.promotion_evidence
        if not isinstance(evidence, Mapping):
            raise LearnedPollingOperationError(
                "PROVEN polling authority requires promotion evidence"
            )
        verified = evidence.get("verified_rates")
        rollback = evidence.get("rollback")
        state = evidence.get("state_evidence")
        if not isinstance(verified, list):
            raise LearnedPollingOperationError(
                "PROVEN polling authority requires per-rate physical evidence"
            )
        if not isinstance(rollback, Mapping) or rollback.get("success") is not True:
            raise LearnedPollingOperationError(
                "PROVEN polling authority requires successful rollback evidence"
            )
        if not isinstance(state, Mapping):
            raise LearnedPollingOperationError(
                "PROVEN polling authority requires state/session evidence"
            )
        # Re-run the promotion gate over persisted evidence. This makes flipping
        # the JSON status flag insufficient to manufacture write authority.
        demonstrated = replace(
            operation,
            state=LearnedOperationState.DEMONSTRATED,
            promotion_evidence=None,
        )
        promoted = promote_polling_operation(
            demonstrated,
            rate_evidence=verified,
            rollback_evidence=rollback,
            state_evidence=state,
        )
        if promoted.state is not LearnedOperationState.PROVEN:
            raise LearnedPollingOperationError("persisted polling promotion is invalid")


def validate_learned_polling_profile(profile: Mapping[str, Any]) -> None:
    if profile.get("schema_version") != LEARNED_POLLING_SCHEMA_VERSION:
        raise LearnedPollingOperationError("unsupported learned polling schema")
    if profile.get("profile_kind") != "learned-polling-state-machine":
        raise LearnedPollingOperationError("unexpected learned polling profile kind")
    if profile.get("behavior") != SemanticBehavior.REPORT_RATE_HZ.value:
        raise LearnedPollingOperationError("learned polling profile has wrong behavior")
    if profile.get("status") not in {state.value for state in LearnedOperationState}:
        raise LearnedPollingOperationError("invalid learned polling status")
    authorized = profile.get("write_authorized")
    if authorized is not (profile.get("status") == LearnedOperationState.PROVEN.value):
        raise LearnedPollingOperationError(
            "polling write authority does not match promotion status"
        )
    if profile.get("safety") != SafetyClass.REVERSIBLE.value:
        raise LearnedPollingOperationError("learned polling must be reversible")
    if profile.get("write_scope") != WriteScope.EXACT_MODEL.value:
        raise LearnedPollingOperationError("learned polling must be exact-model scoped")

    for key in ("identity", "fingerprints", "interface", "control_query", "branches"):
        if not isinstance(profile.get(key), Mapping):
            raise LearnedPollingOperationError(f"learned polling profile requires {key}")
    if not profile["fingerprints"].get("model"):
        raise LearnedPollingOperationError("learned polling requires model fingerprint")
    if not profile["interface"].get("descriptor_sha256"):
        raise LearnedPollingOperationError(
            "learned polling requires exact descriptor fingerprint"
        )
    rates = profile.get("demonstrated_rates")
    if not isinstance(rates, list):
        raise LearnedPollingOperationError("learned polling requires demonstrated rates")
    if not isinstance(profile.get("raw_to_hz"), Mapping):
        raise LearnedPollingOperationError("learned polling requires a raw-value map")

    serialized = json.dumps(profile, sort_keys=True)
    if "/dev/hidraw" in serialized or "/dev/input/event" in serialized:
        raise LearnedPollingOperationError(
            "volatile Linux device paths may not be persisted"
        )

    # Full object validation is the final structural and promotion-evidence pass.
    control = profile["control_query"]
    states = control.get("states")
    branches = profile["branches"]
    if not isinstance(states, Mapping):
        raise LearnedPollingOperationError("control query requires learned states")
    if not isinstance(branches.get(PollingControlState.ONBOARD.value), list):
        raise LearnedPollingOperationError("Onboard polling branch is missing")
    if not isinstance(branches.get(PollingControlState.HOST.value), list):
        raise LearnedPollingOperationError("Host polling branch is missing")

    operation = LearnedPollingOperation(
        behavior=SemanticBehavior(str(profile["behavior"])),
        state=LearnedOperationState(str(profile["status"])),
        identity=StableDeviceIdentity(
            bus=_maybe_int(profile["identity"].get("bus")),
            vendor_id=_maybe_int(profile["identity"].get("vendor_id")),
            product_id=_maybe_int(profile["identity"].get("product_id")),
            model_fingerprint=str(profile["fingerprints"]["model"]),
            instance_fingerprint=(
                None
                if profile["fingerprints"].get("instance") is None
                else str(profile["fingerprints"]["instance"])
            ),
        ),
        interface=StableInterfaceIdentity(
            bus=_maybe_int(profile["interface"].get("bus")),
            vendor_id=_maybe_int(profile["interface"].get("vendor_id")),
            product_id=_maybe_int(profile["interface"].get("product_id")),
            interface_number=_maybe_int(profile["interface"].get("interface_number")),
            descriptor_sha256=str(profile["interface"]["descriptor_sha256"]),
        ),
        demonstrated_rates=tuple(int(rate) for rate in rates),
        raw_to_hz={
            int(raw): int(rate)
            for raw, rate in dict(profile["raw_to_hz"]).items()
        },
        control_query_request=_pattern_from_json(control["request"]),
        control_query_response=_pattern_from_json(control["response"]),
        control_state_offset=int(control["state_offset"]),
        onboard_state_raw=int(states[PollingControlState.ONBOARD.value]),
        host_state_raw=int(states[PollingControlState.HOST.value]),
        onboard_steps=tuple(
            _step_from_json(step)
            for step in branches[PollingControlState.ONBOARD.value]
        ),
        host_steps=tuple(
            _step_from_json(step)
            for step in branches[PollingControlState.HOST.value]
        ),
        safety=SafetyClass(str(profile["safety"])),
        write_scope=WriteScope(str(profile["write_scope"])),
        promotion_evidence=profile.get("promotion_evidence"),
    )
    validate_learned_polling_operation(operation)


def _sudo_owner() -> tuple[int, int] | None:
    if os.geteuid() != 0:
        return None
    try:
        uid = int(os.environ["SUDO_UID"])
        gid = int(os.environ["SUDO_GID"])
    except (KeyError, ValueError):
        return None
    if uid == 0:
        return None
    try:
        pwd.getpwuid(uid)
    except KeyError:
        return None
    return uid, gid


def _filename(operation: LearnedPollingOperation) -> str:
    vendor = operation.identity.vendor_id
    product = operation.identity.product_id
    vendor_text = f"{vendor:04x}" if isinstance(vendor, int) else "unknown"
    product_text = f"{product:04x}" if isinstance(product, int) else "unknown"
    model = operation.identity.model_fingerprint[:16]
    return (
        f"{vendor_text}-{product_text}-{model}-"
        f"{SemanticBehavior.REPORT_RATE_HZ.value}.json"
    )


class LearnedPollingOperationStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or get_learned_operation_directory()

    def save(self, operation: LearnedPollingOperation) -> Path:
        validate_learned_polling_operation(operation)
        profile = polling_operation_to_profile(operation)
        validate_learned_polling_profile(profile)
        self.directory.mkdir(parents=True, exist_ok=True)
        owner = _sudo_owner()
        if owner is not None:
            for path in (self.directory.parent, self.directory):
                try:
                    if path.stat().st_uid == 0:
                        os.chown(path, *owner)
                except OSError:
                    pass
        destination = self.directory / _filename(operation)
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.directory,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp = Path(handle.name)
            json.dump(profile, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.replace(temp, destination)
            if owner is not None:
                os.chown(destination, *owner)
        except Exception:
            temp.unlink(missing_ok=True)
            raise
        return destination

    def load(self, path: Path) -> LearnedPollingOperation:
        try:
            profile = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LearnedPollingOperationError(
                f"could not load polling operation {path}: {exc}"
            ) from exc
        if not isinstance(profile, dict):
            raise LearnedPollingOperationError(
                "learned polling operation root must be an object"
            )
        return polling_operation_from_profile(profile)

    def operations(self) -> tuple[tuple[Path, LearnedPollingOperation], ...]:
        if not self.directory.is_dir():
            return ()
        result: list[tuple[Path, LearnedPollingOperation]] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                result.append((path, self.load(path)))
            except LearnedPollingOperationError:
                continue
        return tuple(result)

    def find_for_physical(
        self,
        physical,
        *,
        proven_only: bool = False,
    ) -> tuple[Path, LearnedPollingOperation] | None:
        matches: list[tuple[Path, LearnedPollingOperation]] = []
        for item in self.operations():
            _path, operation = item
            if proven_only and not operation.write_authorized:
                continue
            if not operation_matches_physical(operation, physical):
                continue
            matches.append(item)
        return matches[0] if len(matches) == 1 else None
