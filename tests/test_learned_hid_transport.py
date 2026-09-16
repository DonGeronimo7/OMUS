from pathlib import Path
from types import SimpleNamespace

import pytest

from mouse_control.learned_hid_transport import (
    LearnedHidTransportError,
    execute_learned_dpi,
    read_learned_dpi,
)
from mouse_control.learned_operations import (
    StableDeviceIdentity,
    StableInterfaceIdentity,
    operation_from_grammar,
    promote_operation,
)
from mouse_control.transaction_engine import TransactionAuthorization
from mouse_control.transaction_inference import (
    demonstration_from_trace,
    infer_transaction_grammar,
)


def _events(value: int):
    hi, lo = value.to_bytes(2, "big")
    return (
        SimpleNamespace(direction="tx", data=bytes.fromhex("11 01 1a 3a 00") + bytes((hi, lo)) + bytes(13)),
        SimpleNamespace(direction="rx", data=bytes.fromhex("11 01 1a 3a") + bytes(16)),
        SimpleNamespace(direction="tx", data=bytes.fromhex("11 01 1a 2a") + bytes(16)),
        SimpleNamespace(direction="rx", data=bytes.fromhex("11 01 1a 2a 00") + bytes((hi, lo)) + bytes.fromhex("03 20") + bytes(11)),
    )


def _operation():
    values = (800, 1500, 2000, 2500, 3000)
    grammar = infer_transaction_grammar(tuple(
        demonstration_from_trace(value, _events(value)) for value in values
    ))
    return operation_from_grammar(
        grammar,
        identity=StableDeviceIdentity(3, 0x046D, 0x4074, "modelhash"),
        interface=StableInterfaceIdentity(3, 0x046D, 0x4074, 2, "descriptorhash"),
    )


class FakeIo:
    def __init__(self, _path: Path):
        self.pending = []
        self.current = 800
        self.closed = False

    def write(self, data: bytes):
        if data[3] == 0x3A:
            self.current = int.from_bytes(data[5:7], "big")
            self.pending.append(bytes.fromhex("11 01 1a 3a") + bytes(16))
        elif data[3] == 0x2A:
            hi, lo = self.current.to_bytes(2, "big")
            self.pending.append(
                bytes.fromhex("11 01 1a 2a 00")
                + bytes((hi, lo))
                + bytes.fromhex("03 20")
                + bytes(11)
            )

    def read(self, _timeout: float):
        return self.pending.pop(0) if self.pending else None

    def close(self):
        self.closed = True


def test_demonstrated_write_is_blocked_without_promotion():
    operation = _operation()
    with pytest.raises(LearnedHidTransportError):
        execute_learned_dpi(
            operation,
            "/dev/hidraw-test",
            1500,
            authorization=TransactionAuthorization(reversible_writes=True),
            io_factory=FakeIo,
        )


def test_explicit_promotion_replays_only_demonstrated_value_and_reads_back():
    operation = _operation()
    context = execute_learned_dpi(
        operation,
        "/dev/hidraw-test",
        1500,
        promotion=True,
        authorization=TransactionAuthorization(
            reversible_writes=True,
            reason="unit-test promotion",
        ),
        io_factory=FakeIo,
    )
    assert context.values["raw_readback"] == 1500


def test_proven_operation_can_write_and_use_active_read_query():
    operation = promote_operation(
        _operation(),
        target_value=1500,
        measured_value=1500,
        deviation_fraction=0.0,
        calibration_confidence="high",
        raw_readback_value=1500,
    )
    context = execute_learned_dpi(
        operation,
        "/dev/hidraw-test",
        2000,
        authorization=TransactionAuthorization(
            reversible_writes=True,
            reason="proven learned runtime",
        ),
        io_factory=FakeIo,
    )
    assert context.values["raw_readback"] == 2000

    # A fresh fake device starts at 800; the read grammar is independently usable.
    assert read_learned_dpi(
        operation,
        "/dev/hidraw-test",
        authorization=TransactionAuthorization(
            active_queries=True,
            reason="proven learned read",
        ),
        io_factory=FakeIo,
    ) == 800
