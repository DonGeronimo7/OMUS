from types import SimpleNamespace

from mouse_control.protocol_grammar import CodecKind
from mouse_control.transaction_inference import (
    demonstration_from_trace,
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
