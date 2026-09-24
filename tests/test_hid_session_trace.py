# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
import queue

from mouse_control.hid_session import HidSession, RawHidTraceEvent


class ScriptedIo:
    def __init__(self, _path: Path) -> None:
        self.pending: queue.Queue[bytes] = queue.Queue()
        self.closed = False

    def write(self, data: bytes) -> None:
        self.pending.put(bytes(data))

    def read(self, timeout: float) -> bytes | None:
        try:
            return self.pending.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self) -> None:
        self.closed = True


def test_trace_callback_records_exact_tx_and_rx_bytes() -> None:
    events: list[RawHidTraceEvent] = []
    session = HidSession(
        Path("/dev/hidraw-test"),
        io_factory=ScriptedIo,
        trace_callback=events.append,
        timeout=0.25,
    )
    try:
        response = session.request(1, 2, 3, b"\xaa\xbb")
        assert response.device_index == 1
    finally:
        session.close()

    assert [event.direction for event in events] == ["tx", "rx"]
    assert events[0].data == events[1].data
    assert events[0].data.startswith(bytes((0x11, 1, 2)))
    assert all(event.path == "/dev/hidraw-test" for event in events)


def test_trace_callback_failure_does_not_break_transport() -> None:
    calls = 0

    def broken_trace(_event: RawHidTraceEvent) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("diagnostic sink failed")

    session = HidSession(
        Path("/dev/hidraw-test"),
        io_factory=ScriptedIo,
        trace_callback=broken_trace,
        timeout=0.25,
    )
    try:
        response = session.request(1, 2, 3)
        assert response.device_index == 1
    finally:
        session.close()

    assert calls == 2
