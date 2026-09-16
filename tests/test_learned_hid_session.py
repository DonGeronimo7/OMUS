from __future__ import annotations

from pathlib import Path
import queue
import threading
import time
from types import SimpleNamespace

import pytest

from mouse_control.learned_hid_session import (
    LearnedHidSession,
    LearnedHidSessionError,
)
from mouse_control.learned_hid_transport import LearnedHidAdapter
from mouse_control.learned_operations import (
    StableDeviceIdentity,
    StableInterfaceIdentity,
    operation_from_grammar,
    promote_operation,
)
from mouse_control.transaction_engine import (
    TransactionAuthorization,
    TransactionContext,
    TransactionEngine,
)
from mouse_control.learned_hid_transport import learned_dpi_transaction_spec
from mouse_control.transaction_inference import (
    demonstration_from_trace,
    infer_transaction_grammar,
)


class Pattern:
    def __init__(self, expected: bytes) -> None:
        self.expected = bytes(expected)

    def matches(self, packet: bytes) -> bool:
        return bytes(packet) == self.expected


class ScriptedIo:
    def __init__(self, _path: Path) -> None:
        self.incoming: queue.Queue[bytes | None] = queue.Queue()
        self.writes: list[bytes] = []
        self.closed = False
        self.on_write = None
        self.reader_threads: set[int] = set()

    def write(self, data: bytes) -> None:
        self.writes.append(bytes(data))
        if self.on_write is not None:
            self.on_write(bytes(data), self)

    def read(self, timeout: float):
        self.reader_threads.add(threading.get_ident())
        try:
            item = self.incoming.get(timeout=timeout)
        except queue.Empty:
            return None
        if item is None:
            return b""
        return item

    def close(self) -> None:
        self.closed = True
        self.incoming.put(None)


def test_unmatched_packet_is_delivered_before_matching_reply():
    io = ScriptedIo(Path("/dev/null"))

    def on_write(_request, target):
        target.incoming.put(b"event")
        target.incoming.put(b"reply")

    io.on_write = on_write
    events: list[bytes] = []
    session = LearnedHidSession(
        "/dev/hidraw-test",
        io_factory=lambda _path: io,
        timeout=0.2,
    )
    try:
        session.subscribe(events.append)
        assert session.exchange(b"request", Pattern(b"reply")) == b"reply"
        assert events == [b"event"]
    finally:
        session.close()


def test_only_reader_thread_consumes_io():
    io = ScriptedIo(Path("/dev/null"))
    io.on_write = lambda _request, target: target.incoming.put(b"ok")
    session = LearnedHidSession(
        "/dev/hidraw-test",
        io_factory=lambda _path: io,
        timeout=0.2,
    )
    try:
        assert session.exchange(b"a", Pattern(b"ok")) == b"ok"
        assert session.exchange(b"b", Pattern(b"ok")) == b"ok"
    finally:
        session.close()

    assert len(io.reader_threads) == 1
    assert threading.get_ident() not in io.reader_threads


def test_concurrent_requests_are_serialized():
    io = ScriptedIo(Path("/dev/null"))
    first_written = threading.Event()
    release_first = threading.Event()

    def on_write(request, target):
        if request == b"first":
            first_written.set()

            def delayed():
                release_first.wait(1.0)
                target.incoming.put(b"r1")

            threading.Thread(target=delayed, daemon=True).start()
        elif request == b"second":
            target.incoming.put(b"r2")

    io.on_write = on_write
    session = LearnedHidSession(
        "/dev/hidraw-test",
        io_factory=lambda _path: io,
        timeout=0.5,
    )
    results: list[bytes] = []

    t1 = threading.Thread(
        target=lambda: results.append(session.exchange(b"first", Pattern(b"r1")))
    )
    t2 = threading.Thread(
        target=lambda: results.append(session.exchange(b"second", Pattern(b"r2")))
    )
    try:
        t1.start()
        assert first_written.wait(0.2)
        t2.start()
        time.sleep(0.03)
        assert io.writes == [b"first"]
        release_first.set()
        t1.join(0.5)
        t2.join(0.5)
        assert results == [b"r1", b"r2"]
        assert io.writes == [b"first", b"second"]
    finally:
        release_first.set()
        session.close()


def test_disconnect_fails_pending_request():
    io = ScriptedIo(Path("/dev/null"))
    io.on_write = lambda _request, target: target.incoming.put(None)
    session = LearnedHidSession(
        "/dev/hidraw-test",
        io_factory=lambda _path: io,
        timeout=0.5,
    )
    try:
        with pytest.raises(LearnedHidSessionError, match="disconnected"):
            session.exchange(b"request", Pattern(b"never"))
        assert session.closed
        assert session.disconnect_error is not None
    finally:
        session.close()


def test_timeout_clears_waiter_and_late_packet_becomes_unsolicited_event():
    io = ScriptedIo(Path("/dev/null"))
    session = LearnedHidSession(
        "/dev/hidraw-test",
        io_factory=lambda _path: io,
        timeout=0.03,
    )
    events: list[bytes] = []
    try:
        session.subscribe(events.append)
        with pytest.raises(LearnedHidSessionError, match="timed out"):
            session.exchange(b"request", Pattern(b"late"))
        io.incoming.put(b"late")
        deadline = time.monotonic() + 0.3
        while not events and time.monotonic() < deadline:
            time.sleep(0.005)
        assert events == [b"late"]
    finally:
        session.close()


def test_bad_subscriber_does_not_break_reader_or_other_subscribers():
    io = ScriptedIo(Path("/dev/null"))
    io.on_write = lambda _request, target: (
        target.incoming.put(b"event"),
        target.incoming.put(b"reply"),
    )
    good: list[bytes] = []

    def bad(_packet):
        raise RuntimeError("broken subscriber")

    session = LearnedHidSession(
        "/dev/hidraw-test",
        io_factory=lambda _path: io,
        timeout=0.2,
    )
    try:
        session.subscribe(bad)
        session.subscribe(good.append)
        assert session.exchange(b"request", Pattern(b"reply")) == b"reply"
        assert good == [b"event"]
        assert not session.closed
    finally:
        session.close()


def test_trace_records_raw_tx_and_rx_without_protocol_parsing():
    io = ScriptedIo(Path("/dev/null"))
    io.on_write = lambda _request, target: (
        target.incoming.put(b"\xff\x00\xfe"),
        target.incoming.put(b"\x91\x92"),
    )
    trace = []
    session = LearnedHidSession(
        "/dev/hidraw-test",
        io_factory=lambda _path: io,
        timeout=0.2,
        trace_callback=trace.append,
    )
    events: list[bytes] = []
    try:
        session.subscribe(events.append)
        assert session.exchange(b"\x80", Pattern(b"\x91\x92")) == b"\x91\x92"
    finally:
        session.close()

    assert [(event.direction, event.data) for event in trace] == [
        ("tx", b"\x80"),
        ("rx", b"\xff\x00\xfe"),
        ("rx", b"\x91\x92"),
    ]
    assert events == [b"\xff\x00\xfe"]


def _dpi_events(value: int):
    hi, lo = value.to_bytes(2, "big")
    return (
        SimpleNamespace(
            direction="tx",
            data=bytes.fromhex("11 01 1a 3a 00") + bytes((hi, lo)) + bytes(13),
        ),
        SimpleNamespace(
            direction="rx",
            data=bytes.fromhex("11 01 1a 3a") + bytes(16),
        ),
        SimpleNamespace(
            direction="tx",
            data=bytes.fromhex("11 01 1a 2a") + bytes(16),
        ),
        SimpleNamespace(
            direction="rx",
            data=bytes.fromhex("11 01 1a 2a 00")
            + bytes((hi, lo))
            + bytes.fromhex("03 20")
            + bytes(11),
        ),
    )


def _proven_dpi_operation():
    values = (800, 1500, 2000, 2500, 3000)
    grammar = infer_transaction_grammar(
        tuple(demonstration_from_trace(value, _dpi_events(value)) for value in values)
    )
    operation = operation_from_grammar(
        grammar,
        identity=StableDeviceIdentity(3, 0x046D, 0x4074, "modelhash"),
        interface=StableInterfaceIdentity(
            3, 0x046D, 0x4074, 2, "descriptorhash"
        ),
    )
    return promote_operation(
        operation,
        target_value=1500,
        measured_value=1500,
        deviation_fraction=0.0,
        calibration_confidence="high",
        raw_readback_value=1500,
    )


class DpiIo(ScriptedIo):
    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.current = 800

        def respond(data: bytes, target: ScriptedIo) -> None:
            if data[3] == 0x3A:
                self.current = int.from_bytes(data[5:7], "big")
                # Physical event arrives on the same stream before the ACK.
                target.incoming.put(
                    bytes((0x02, 0x00, 0x00, 0x00, 0x04))
                )
                target.incoming.put(bytes.fromhex("11 01 1a 3a") + bytes(16))
            elif data[3] == 0x2A:
                hi, lo = self.current.to_bytes(2, "big")
                target.incoming.put(
                    bytes.fromhex("11 01 1a 2a 00")
                    + bytes((hi, lo))
                    + bytes.fromhex("03 20")
                    + bytes(11)
                )

        self.on_write = respond


def test_learned_dpi_adapter_uses_shared_session_without_stealing_event():
    operation = _proven_dpi_operation()
    io = DpiIo(Path("/dev/null"))
    session = LearnedHidSession(
        "/dev/hidraw-test",
        io_factory=lambda _path: io,
        timeout=0.2,
    )
    events: list[bytes] = []
    session.subscribe(events.append)
    adapter = LearnedHidAdapter(
        "/dev/hidraw-test",
        operation,
        timeout=0.2,
        session=session,
    )
    try:
        context = TransactionEngine().run(
            learned_dpi_transaction_spec(),
            adapter,
            authorization=TransactionAuthorization(
                reversible_writes=True,
                reason="single-reader unit test",
            ),
            context=TransactionContext(values={"target": 1500}),
        )
        assert context.values["raw_readback"] == 1500
        assert events == [bytes((0x02, 0x00, 0x00, 0x00, 0x04))]
        adapter.close()
        assert not session.closed
    finally:
        session.close()


def test_adapter_rejects_shared_session_for_different_path():
    operation = _proven_dpi_operation()
    io = DpiIo(Path("/dev/null"))
    session = LearnedHidSession(
        "/dev/hidraw-a",
        io_factory=lambda _path: io,
        timeout=0.2,
    )
    try:
        with pytest.raises(Exception, match="different interface"):
            LearnedHidAdapter(
                "/dev/hidraw-b",
                operation,
                session=session,
            )
    finally:
        session.close()
