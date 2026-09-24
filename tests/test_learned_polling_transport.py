# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
import queue

import pytest

from mouse_control.learned_hid_session import LearnedHidSession
from mouse_control.learned_operations import (
    LearnedOperationState,
    StableDeviceIdentity,
    StableInterfaceIdentity,
)
from mouse_control.learned_polling import (
    LearnedPollingOperation,
    PollingControlState,
)
from mouse_control.learned_polling_transport import (
    LearnedPollingTransportError,
    execute_learned_polling,
    learned_polling_write_without_takeover,
    query_learned_polling_control_state,
    read_learned_polling_rate,
)
from mouse_control.polling_replay import PacketPattern, ReplayStep
from mouse_control.protocol_grammar import SemanticBehavior


RAW = {1000: 1, 500: 2, 250: 4, 125: 8}


def pattern(data):
    return PacketPattern(
        tuple(None if value is None else int(value) for value in data)
    )


def operation():
    write = ReplayStep(
        request=pattern((0x10, 0x03, None)),
        response=pattern((0x20, 0x03)),
        request_semantic_offset=2,
    )
    read = ReplayStep(
        request=pattern((0x10, 0x04)),
        response=pattern((0x20, 0x04, None)),
        response_semantic_offset=2,
    )
    return LearnedPollingOperation(
        behavior=SemanticBehavior.REPORT_RATE_HZ,
        state=LearnedOperationState.PROVEN,
        identity=StableDeviceIdentity(
            3, 0x046D, 0x4074, "model", "instance"
        ),
        interface=StableInterfaceIdentity(
            3, 0x046D, 0x4074, 2, "descriptor"
        ),
        demonstrated_rates=(125, 250, 500, 1000),
        raw_to_hz={1: 1000, 2: 500, 4: 250, 8: 125},
        control_query_request=pattern((0x10, 0x01)),
        control_query_response=pattern((0x20, None)),
        control_state_offset=1,
        onboard_state_raw=1,
        host_state_raw=2,
        onboard_steps=(
            ReplayStep(
                request=pattern((0x10, 0x02)),
                response=pattern((0x20, 0x02)),
            ),
            ReplayStep(
                request=pattern((0x10, 0x01)),
                response=pattern((0x20, 0x02)),
            ),
            write,
            read,
        ),
        host_steps=(write, read),
        promotion_evidence={"unit": True},
    )


class PollingIo:
    def __init__(self, _path: Path):
        self.pending = queue.Queue()
        self.closed = False
        self.mode = 1
        self.rate_raw = 1
        self.writes = []

    def write(self, data: bytes):
        packet = bytes(data)
        self.writes.append(packet)
        if packet == b"\x10\x01":
            self.pending.put(bytes((0x20, self.mode)))
        elif packet == b"\x10\x02":
            self.mode = 2
            self.pending.put(b"\x20\x02")
        elif packet[:2] == b"\x10\x03":
            self.rate_raw = packet[2]
            self.pending.put(b"\x20\x03")
        elif packet == b"\x10\x04":
            self.pending.put(bytes((0x20, 0x04, self.rate_raw)))
        else:
            raise AssertionError(f"unexpected request {packet!r}")

    def read(self, timeout: float):
        try:
            return self.pending.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self):
        self.closed = True


def make_session(io):
    return LearnedHidSession(
        "/dev/hidraw-test",
        io_factory=lambda _path: io,
        timeout=0.2,
    )


def test_onboard_write_uses_takeover_branch_then_reads_back():
    io = PollingIo(Path("/dev/null"))
    session = make_session(io)
    try:
        assert query_learned_polling_control_state(
            operation(), session
        ) is PollingControlState.ONBOARD
        assert execute_learned_polling(operation(), session, 500) == 500
        assert io.mode == 2
        assert io.rate_raw == 2
    finally:
        session.close()


def test_host_write_skips_takeover_steps():
    io = PollingIo(Path("/dev/null"))
    io.mode = 2
    session = make_session(io)
    try:
        assert execute_learned_polling(operation(), session, 250) == 250
        assert b"\x10\x02" not in io.writes
        assert io.rate_raw == 4
    finally:
        session.close()


def test_read_does_not_take_over_onboard_mode():
    io = PollingIo(Path("/dev/null"))
    session = make_session(io)
    try:
        assert read_learned_polling_rate(operation(), session) is None
        assert io.mode == 1
        assert b"\x10\x02" not in io.writes
    finally:
        session.close()


def test_host_read_and_without_takeover_policy():
    io = PollingIo(Path("/dev/null"))
    io.mode = 2
    io.rate_raw = 8
    session = make_session(io)
    try:
        assert learned_polling_write_without_takeover(
            operation(), session
        ) is True
        assert read_learned_polling_rate(operation(), session) == 125
    finally:
        session.close()


def test_undemonstrated_rate_is_rejected_before_write():
    io = PollingIo(Path("/dev/null"))
    session = make_session(io)
    try:
        with pytest.raises(
            LearnedPollingTransportError, match="physically promoted"
        ):
            execute_learned_polling(operation(), session, 333)
        assert io.writes == []
    finally:
        session.close()
