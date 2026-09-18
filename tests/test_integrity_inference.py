from mouse_control.integrity_inference import infer_integrity
from mouse_control.transaction_inference import DemonstratedTransaction, infer_transaction_grammar


def _xor_frame(value: int) -> bytes:
    frame = bytearray((0xA5, value, 0x10, 0))
    frame[-1] = frame[0] ^ frame[1] ^ frame[2]
    return bytes(frame)


def test_multiple_frames_identify_bounded_xor_and_reject_single_frame():
    frames = tuple(_xor_frame(value) for value in (10, 20, 30))
    hypotheses = infer_integrity(frames)
    # XOR is symmetric, so inference retains both varying candidate locations;
    # transaction semantics separately exclude the demonstrated value field.
    assert {(item.algorithm, item.offset) for item in hypotheses} == {
        ("xor8", 1), ("xor8", 3)
    }
    hypothesis = next(item for item in hypotheses if item.offset == 3)
    assert (hypothesis.algorithm, hypothesis.offset, hypothesis.width) == ("xor8", 3, 1)
    assert infer_integrity(frames[:1]) == ()


def test_transaction_inference_allows_only_proven_checksum_variation():
    demonstrations = []
    for value in (10, 20, 30):
        write = _xor_frame(value)
        demonstrations.append(DemonstratedTransaction(
            value,
            (write, b"\xB0"),
            (b"\xA0", bytes((0xB1, value))),
        ))
    grammar = infer_transaction_grammar(demonstrations)
    assert grammar.write_integrity is not None
    assert grammar.write_integrity.algorithm == "xor8"
    assert grammar.write_request.bytes_ == (0xA5, None, 0x10, None)


def test_sum_complement_and_crc8_hypotheses_are_finite():
    payloads = (b"\x01\x02", b"\x04\x08", b"\x10\x20")
    sum_frames = tuple(payload + bytes((sum(payload) & 0xFF,)) for payload in payloads)
    complement_frames = tuple(payload + bytes(((~sum(payload)) & 0xFF,)) for payload in payloads)
    assert any(item.algorithm == "sum8" for item in infer_integrity(sum_frames))
    assert any(item.algorithm == "ones-complement-sum8" for item in infer_integrity(complement_frames))
    assert {item.algorithm for item in infer_integrity(sum_frames)} <= {
        "xor8", "sum8", "ones-complement-sum8", "crc8-07", "crc8-31", "crc8-9b"
    }
