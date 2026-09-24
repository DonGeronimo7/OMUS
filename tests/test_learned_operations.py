# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
from types import SimpleNamespace

import pytest

from mouse_control.learned_operations import (
    LearnedOperationError,
    LearnedOperationState,
    LearnedOperationStore,
    StableDeviceIdentity,
    StableInterfaceIdentity,
    operation_from_grammar,
    promote_operation,
)
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
        identity=StableDeviceIdentity(3, 0x046D, 0x4074, "modelhash", "instancehash"),
        interface=StableInterfaceIdentity(3, 0x046D, 0x4074, 2, "descriptorhash"),
    )


def test_demonstrated_profile_round_trips_without_write_authority(tmp_path: Path):
    operation = _operation()
    store = LearnedOperationStore(tmp_path)
    path = store.save(operation)
    loaded = store.load(path)

    assert loaded.state is LearnedOperationState.DEMONSTRATED
    assert loaded.write_authorized is False
    assert loaded.render_write(1500)[5:7] == bytes.fromhex("05 dc")


def test_promotion_requires_physical_agreement():
    operation = _operation()

    with pytest.raises(LearnedOperationError):
        promote_operation(
            operation,
            target_value=1500,
            measured_value=1900,
            deviation_fraction=(1900 - 1500) / 1500,
            calibration_confidence="high",
            raw_readback_value=1500,
        )

    promoted = promote_operation(
        operation,
        target_value=1500,
        measured_value=1540,
        deviation_fraction=(1540 - 1500) / 1500,
        calibration_confidence="high",
        raw_readback_value=1500,
    )
    assert promoted.state is LearnedOperationState.PROVEN
    assert promoted.write_authorized is True


def test_unseen_value_cannot_be_synthesized():
    operation = _operation()
    with pytest.raises(LearnedOperationError):
        operation.render_write(1750)
