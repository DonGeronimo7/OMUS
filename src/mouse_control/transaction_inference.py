"""Protocol-neutral inference of reversible write/readback transaction grammar.

This module consumes successful semantic demonstrations as opaque raw packets.
It does not know vendor names, HID++ feature indexes, Razer commands, or device
families.  Its job is to explain which bytes are invariant and which contiguous
field encodes the demonstrated semantic value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .protocol_grammar import CodecKind, CodecSpec


class TransactionInferenceError(ValueError):
    """Successful demonstrations do not support one safe explainable grammar."""


@dataclass(frozen=True)
class DemonstratedTransaction:
    semantic_value: int
    tx_packets: tuple[bytes, ...]
    rx_packets: tuple[bytes, ...]

    def __post_init__(self) -> None:
        if self.semantic_value <= 0:
            raise ValueError("semantic_value must be positive")
        if not self.tx_packets or not self.rx_packets:
            raise ValueError("demonstration requires both TX and RX packets")
        if any(not packet for packet in (*self.tx_packets, *self.rx_packets)):
            raise ValueError("demonstration packets may not be empty")


@dataclass(frozen=True)
class SemanticField:
    offset: int
    width: int
    codec: CodecSpec

    def __post_init__(self) -> None:
        if self.offset < 0 or self.width <= 0:
            raise ValueError("semantic field offset/width are invalid")


@dataclass(frozen=True)
class FramePattern:
    """Aligned packet template.

    ``None`` marks bytes occupied by a semantic field or another deliberately
    wildcarded response byte. For writable request frames this module only
    permits the semantic span to vary.
    """

    bytes_: tuple[int | None, ...]

    def __post_init__(self) -> None:
        if not self.bytes_:
            raise ValueError("frame pattern may not be empty")
        for value in self.bytes_:
            if value is not None and not 0 <= value <= 0xFF:
                raise ValueError("frame pattern values must fit in one byte")

    @property
    def length(self) -> int:
        return len(self.bytes_)

    @property
    def constant_count(self) -> int:
        return sum(value is not None for value in self.bytes_)

    def matches(self, packet: bytes) -> bool:
        if len(packet) != len(self.bytes_):
            return False
        return all(expected is None or packet[index] == expected
                   for index, expected in enumerate(self.bytes_))


@dataclass(frozen=True)
class InferredTransactionGrammar:
    write_request: FramePattern
    write_field: SemanticField
    write_reply: FramePattern
    read_request: FramePattern
    read_reply: FramePattern
    read_field: SemanticField
    demonstrated_values: tuple[int, ...]
    demonstration_count: int

    @property
    def codec_agrees(self) -> bool:
        return (
            self.write_field.width == self.read_field.width
            and self.write_field.codec.kind is self.read_field.codec.kind
        )


def _directions(events) -> tuple[tuple[bytes, ...], tuple[bytes, ...]]:
    tx = tuple(bytes(event.data) for event in events if event.direction == "tx")
    rx = tuple(bytes(event.data) for event in events if event.direction == "rx")
    return tx, rx


def demonstration_from_trace(semantic_value: int, events) -> DemonstratedTransaction:
    tx, rx = _directions(tuple(events))
    return DemonstratedTransaction(int(semantic_value), tx, rx)


def _aligned(samples: Sequence[bytes], label: str) -> int:
    if not samples:
        raise TransactionInferenceError(f"{label}: no packets")
    lengths = {len(sample) for sample in samples}
    if len(lengths) != 1:
        raise TransactionInferenceError(f"{label}: packet lengths are not stable")
    return next(iter(lengths))


def _codec_for(width: int, endian: str) -> CodecSpec:
    if width == 1:
        return CodecSpec(CodecKind.U8)
    if width == 2 and endian == "big":
        return CodecSpec(CodecKind.U16_BE)
    if width == 2 and endian == "little":
        return CodecSpec(CodecKind.U16_LE)
    # The current declarative codec vocabulary intentionally stops at U16.
    # Wider exact integer matches are rejected rather than inventing a codec.
    raise TransactionInferenceError("semantic integer field wider than two bytes is unsupported")


def _decode(packet: bytes, offset: int, width: int, endian: str) -> int:
    return int.from_bytes(packet[offset:offset + width], endian)


def _find_semantic_field(
    packets: Sequence[bytes],
    semantic_values: Sequence[int],
    *,
    label: str,
) -> SemanticField:
    width_total = _aligned(packets, label)
    candidates: list[SemanticField] = []
    for field_width in (1, 2):
        if field_width > width_total:
            continue
        endians = ("big",) if field_width == 1 else ("big", "little")
        for offset in range(0, width_total - field_width + 1):
            for endian in endians:
                decoded = tuple(
                    _decode(packet, offset, field_width, endian)
                    for packet in packets
                )
                if decoded == tuple(semantic_values):
                    candidates.append(
                        SemanticField(offset, field_width, _codec_for(field_width, endian))
                    )
    if not candidates:
        raise TransactionInferenceError(
            f"{label}: no U8/U16 field exactly encodes every demonstrated semantic value"
        )

    # Prefer the narrowest exact representation, then the earliest offset.
    candidates.sort(key=lambda field: (field.width, field.offset, field.codec.kind.value))
    best = candidates[0]
    same_rank = [
        item for item in candidates
        if (item.width, item.offset) == (best.width, best.offset)
    ]
    kinds = {item.codec.kind for item in same_rank}
    if len(kinds) > 1:
        raise TransactionInferenceError(f"{label}: semantic field endianness is ambiguous")
    return best


def _pattern(
    packets: Sequence[bytes],
    *,
    wildcard_span: tuple[int, int] | None = None,
    require_constant_elsewhere: bool,
    label: str,
) -> FramePattern:
    width = _aligned(packets, label)
    start = end = -1
    if wildcard_span is not None:
        start, span_width = wildcard_span
        end = start + span_width
    result: list[int | None] = []
    for offset in range(width):
        values = {packet[offset] for packet in packets}
        if start <= offset < end:
            result.append(None)
            continue
        if len(values) == 1:
            result.append(next(iter(values)))
            continue
        if require_constant_elsewhere:
            raise TransactionInferenceError(
                f"{label}: byte {offset} varies outside the semantic field"
            )
        result.append(None)
    return FramePattern(tuple(result))


def infer_transaction_grammar(
    demonstrations: Sequence[DemonstratedTransaction],
) -> InferredTransactionGrammar:
    """Infer one simple reversible write + readback grammar.

    The accepted training shape is intentionally strict: every successful
    demonstration must contain two TX packets and two RX packets in order:
    write request/reply followed by read request/reply.  This is the first
    safely writable grammar class. More complex selectors/checksums can be added
    without weakening this gate.
    """

    samples = tuple(demonstrations)
    if len(samples) < 3:
        raise TransactionInferenceError("at least three successful demonstrations are required")
    semantic_values = tuple(sample.semantic_value for sample in samples)
    if len(set(semantic_values)) != len(semantic_values):
        raise TransactionInferenceError("demonstrated semantic values must be distinct")
    if any(len(sample.tx_packets) != 2 or len(sample.rx_packets) != 2 for sample in samples):
        raise TransactionInferenceError(
            "simple transaction inference requires exactly two TX and two RX packets per demonstration"
        )

    write_requests = tuple(sample.tx_packets[0] for sample in samples)
    write_replies = tuple(sample.rx_packets[0] for sample in samples)
    read_requests = tuple(sample.tx_packets[1] for sample in samples)
    read_replies = tuple(sample.rx_packets[1] for sample in samples)

    write_field = _find_semantic_field(
        write_requests, semantic_values, label="write request"
    )
    read_field = _find_semantic_field(
        read_replies, semantic_values, label="read reply"
    )

    write_request = _pattern(
        write_requests,
        wildcard_span=(write_field.offset, write_field.width),
        require_constant_elsewhere=True,
        label="write request",
    )
    write_reply = _pattern(
        write_replies,
        require_constant_elsewhere=True,
        label="write reply",
    )
    read_request = _pattern(
        read_requests,
        require_constant_elsewhere=True,
        label="read request",
    )
    read_reply = _pattern(
        read_replies,
        wildcard_span=(read_field.offset, read_field.width),
        require_constant_elsewhere=True,
        label="read reply",
    )

    grammar = InferredTransactionGrammar(
        write_request=write_request,
        write_field=write_field,
        write_reply=write_reply,
        read_request=read_request,
        read_reply=read_reply,
        read_field=read_field,
        demonstrated_values=tuple(sorted(semantic_values)),
        demonstration_count=len(samples),
    )
    if not grammar.codec_agrees:
        raise TransactionInferenceError(
            "write field and readback field do not use the same proven codec"
        )
    return grammar
