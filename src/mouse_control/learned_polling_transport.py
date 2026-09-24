# SPDX-License-Identifier: AGPL-3.0-or-later
"""Runtime execution for PROVEN learned polling state machines.

The executor is protocol-neutral: persisted packet patterns decide how requests
are rendered and correlated.  It shares LearnedHidSession with DPI/event users,
so polling transactions never create a competing hidraw reader.
"""

from __future__ import annotations

from .learned_hid_session import LearnedHidSession, LearnedHidSessionError
from .learned_polling import (
    LearnedPollingOperation,
    PollingControlState,
)
from .polling_replay import ReplayStep


class LearnedPollingTransportError(RuntimeError):
    """A PROVEN learned polling transaction could not execute safely."""


def _resolved_request(
    step: ReplayStep,
    operation: LearnedPollingOperation,
    target_hz: int | None = None,
) -> bytes:
    values = list(step.request.bytes_)
    offset = step.request_semantic_offset
    if offset is not None:
        if target_hz is None:
            raise LearnedPollingTransportError(
                "polling write step requires a semantic target"
            )
        if offset < 0 or offset >= len(values):
            raise LearnedPollingTransportError(
                "polling semantic request offset is outside the packet"
            )
        values[offset] = operation.raw_for_rate(int(target_hz))
    if any(value is None for value in values):
        raise LearnedPollingTransportError(
            "learned polling request contains unresolved wildcard bytes"
        )
    return bytes(int(value) for value in values)


def _decode_rate(
    operation: LearnedPollingOperation,
    packet: bytes,
    offset: int,
) -> int:
    if offset < 0 or offset >= len(packet):
        raise LearnedPollingTransportError(
            "polling semantic response offset is outside the packet"
        )
    raw = int(packet[offset])
    try:
        rate = int(operation.raw_to_hz[raw])
    except KeyError as exc:
        raise LearnedPollingTransportError(
            f"polling readback raw value 0x{raw:02x} was never demonstrated"
        ) from exc
    if rate not in operation.demonstrated_rates:
        raise LearnedPollingTransportError(
            f"decoded polling rate {rate} Hz is outside the promoted set"
        )
    return rate


def query_learned_polling_control_state(
    operation: LearnedPollingOperation,
    session: LearnedHidSession,
) -> PollingControlState:
    """Read the learned control state without changing ownership."""

    if not operation.write_authorized:
        raise LearnedPollingTransportError(
            "learned polling operation is not PROVEN"
        )
    request_values = operation.control_query_request.bytes_
    if any(value is None for value in request_values):
        raise LearnedPollingTransportError(
            "learned polling control query contains unresolved bytes"
        )
    request = bytes(int(value) for value in request_values)
    try:
        reply = session.exchange(
            request,
            operation.control_query_response,
        )
    except LearnedHidSessionError as exc:
        raise LearnedPollingTransportError(str(exc)) from exc

    offset = operation.control_state_offset
    if offset < 0 or offset >= len(reply):
        raise LearnedPollingTransportError(
            "polling control-state byte is outside the reply"
        )
    raw = int(reply[offset])
    if raw == operation.onboard_state_raw:
        return PollingControlState.ONBOARD
    if raw == operation.host_state_raw:
        return PollingControlState.HOST
    raise LearnedPollingTransportError(
        f"polling control query returned unknown state 0x{raw:02x}"
    )


def learned_polling_write_without_takeover(
    operation: LearnedPollingOperation,
    session: LearnedHidSession,
) -> bool:
    """Whether a write can occur without changing firmware control ownership."""

    return (
        query_learned_polling_control_state(operation, session)
        is PollingControlState.HOST
    )


def read_learned_polling_rate(
    operation: LearnedPollingOperation,
    session: LearnedHidSession,
) -> int | None:
    """Read polling rate when the learned non-mutating Host read is applicable.

    The promotion corpus did not independently prove an Onboard-mode standalone
    polling read.  Returning None there is intentional: ordinary monitoring must
    never take Host ownership merely to obtain a value.
    """

    state = query_learned_polling_control_state(operation, session)
    if state is not PollingControlState.HOST:
        return None

    read_steps = [
        step
        for step in operation.host_steps
        if step.response_semantic_offset is not None
    ]
    if len(read_steps) != 1:
        raise LearnedPollingTransportError(
            f"expected one Host polling read step, found {len(read_steps)}"
        )
    step = read_steps[0]
    request = _resolved_request(step, operation)
    try:
        reply = session.exchange(request, step.response)
    except LearnedHidSessionError as exc:
        raise LearnedPollingTransportError(str(exc)) from exc
    assert step.response_semantic_offset is not None
    return _decode_rate(operation, reply, step.response_semantic_offset)


def execute_learned_polling(
    operation: LearnedPollingOperation,
    session: LearnedHidSession,
    target_hz: int,
) -> int:
    """Execute the correct PROVEN branch and require semantic readback."""

    target = int(target_hz)
    if not operation.write_authorized:
        raise LearnedPollingTransportError(
            "learned polling operation is not PROVEN"
        )
    if not operation.accepts(target):
        raise LearnedPollingTransportError(
            f"{target} Hz is outside the physically promoted polling set"
        )

    state = query_learned_polling_control_state(operation, session)
    steps = (
        operation.onboard_steps
        if state is PollingControlState.ONBOARD
        else operation.host_steps
    )
    readback: int | None = None

    for step in steps:
        request = _resolved_request(step, operation, target)
        try:
            reply = session.exchange(request, step.response)
        except LearnedHidSessionError as exc:
            raise LearnedPollingTransportError(str(exc)) from exc
        if step.response_semantic_offset is not None:
            readback = _decode_rate(
                operation,
                reply,
                step.response_semantic_offset,
            )

    if readback is None:
        raise LearnedPollingTransportError(
            "learned polling branch completed without semantic readback"
        )
    if readback != target:
        raise LearnedPollingTransportError(
            f"learned polling requested {target} Hz, read back {readback} Hz"
        )
    return readback
