# SPDX-License-Identifier: AGPL-3.0-or-later
from types import SimpleNamespace

from mouse_control.protocol_grammar import CodecKind
from mouse_control.transaction_inference import (
    FieldRole,
    demonstration_from_trace,
    infer_field_roles,
    infer_transaction_grammar,
)


def events(value: int):
    hi, lo = value.to_bytes(2, "big")
    return (
        SimpleNamespace(direction="tx", data=bytes.fromhex("11 01 1a 3a 00") + bytes((hi, lo)) + bytes(13)),
        SimpleNamespace(direction="rx", data=bytes.fromhex("11 01 1a 3a") + bytes(16)),
        SimpleNamespace(direction="tx", data=bytes.fromhex("11 01 1a 2a") + bytes(16)),
        SimpleNamespace(direction="rx", data=bytes.fromhex("11 01 1a 2a 00") + bytes((hi, lo)) + bytes.fromhex("03 20") + bytes(11)),
    )


def test_infers_g305_write_and_readback_as_u16_be():
    demos = tuple(
        demonstration_from_trace(value, events(value))
        for value in (800, 1500, 2000, 2500, 3000)
    )
    grammar = infer_transaction_grammar(demos)

    assert grammar.write_field.offset == 5
    assert grammar.write_field.width == 2
    assert grammar.write_field.codec.kind is CodecKind.U16_BE
    assert grammar.read_field.offset == 5
    assert grammar.read_field.codec.kind is CodecKind.U16_BE
    assert grammar.write_request.constant_count == 18
    assert grammar.demonstrated_values == (800, 1500, 2000, 2500, 3000)


def test_write_variation_outside_semantic_field_is_rejected():
    demos = []
    for index, value in enumerate((800, 1500, 2000)):
        sample = list(events(value))
        changed = bytearray(sample[0].data)
        changed[10] = index
        sample[0] = SimpleNamespace(direction="tx", data=bytes(changed))
        demos.append(demonstration_from_trace(value, sample))

    import pytest
    from mouse_control.transaction_inference import TransactionInferenceError

    with pytest.raises(TransactionInferenceError):
        infer_transaction_grammar(tuple(demos))


def test_repeated_transactions_classify_counter_echo_length_and_status_candidates():
    requests = (
        bytes((0x10, 0x01, 0x04, 0xAA)),
        bytes((0x10, 0x02, 0x04, 0xAA)),
        bytes((0x10, 0x03, 0x04, 0xAA)),
    )
    replies = (
        bytes((0x00, 0x01, 0x55)),
        bytes((0x00, 0x02, 0x55)),
        bytes((0x00, 0x03, 0x55)),
    )
    roles = infer_field_roles(requests, replies)
    assert any(item.role is FieldRole.COUNTER and item.offset == 1 for item in roles)
    assert any(item.role is FieldRole.ECHO and item.offset == 1 and item.related_offset == 1 for item in roles)
    assert any(item.role is FieldRole.LENGTH and item.offset == 2 for item in roles)
    assert any(item.role is FieldRole.STATUS and item.offset == 0 for item in roles)


def test_field_role_inference_requires_three_aligned_pairs():
    assert infer_field_roles((b"\x01", b"\x02"), (b"\x01", b"\x02")) == ()
    assert infer_field_roles((b"\x01",) * 3, (b"\x00", b"\x00")) == ()
