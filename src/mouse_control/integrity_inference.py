"""Bounded multi-frame checksum/integrity inference.

Structural matches are descriptive evidence only. They never authorize writes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class IntegrityHypothesis:
    algorithm: str
    offset: int
    width: int
    byte_order: str = "big"


def _xor8(data: bytes) -> int:
    result = 0
    for value in data:
        result ^= value
    return result


def _crc8(data: bytes, polynomial: int, initial: int) -> int:
    crc = initial
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = ((crc << 1) ^ polynomial) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def _crc16(data: bytes, polynomial: int, initial: int) -> int:
    crc = initial
    for value in data:
        crc ^= value << 8
        for _ in range(8):
            crc = ((crc << 1) ^ polynomial) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def infer_integrity(
    packets: Sequence[bytes],
    *,
    minimum_frames: int = 3,
    allow_crc16: bool = False,
) -> tuple[IntegrityHypothesis, ...]:
    """Return common integrity schemes that validate every aligned frame.

    Candidate checksum bytes are removed from the covered data. Algorithms and
    parameters are deliberately finite; this function does not brute-force.
    """
    frames = tuple(bytes(packet) for packet in packets)
    if len(frames) < minimum_frames or len({len(packet) for packet in frames}) != 1:
        return ()
    width = len(frames[0])
    if width < 2:
        return ()
    results: list[IntegrityHypothesis] = []
    checks8 = (
        ("xor8", _xor8),
        ("sum8", lambda data: sum(data) & 0xFF),
        ("ones-complement-sum8", lambda data: (~sum(data)) & 0xFF),
        ("crc8-07", lambda data: _crc8(data, 0x07, 0x00)),
        ("crc8-31", lambda data: _crc8(data, 0x31, 0x00)),
        ("crc8-9b", lambda data: _crc8(data, 0x9B, 0xFF)),
    )
    for offset in range(width):
        if len({packet[offset] for packet in frames}) < 2:
            continue
        payloads = tuple(packet[:offset] + packet[offset + 1:] for packet in frames)
        observed = tuple(packet[offset] for packet in frames)
        for name, calculate in checks8:
            if tuple(calculate(payload) for payload in payloads) == observed:
                results.append(IntegrityHypothesis(name, offset, 1))
    if allow_crc16 and len(frames) >= 4 and width >= 4:
        for offset in range(width - 1):
            if len({packet[offset:offset + 2] for packet in frames}) < 2:
                continue
            payloads = tuple(packet[:offset] + packet[offset + 2:] for packet in frames)
            for name, polynomial, initial in (
                ("crc16-ccitt-false", 0x1021, 0xFFFF),
                ("crc16-xmodem", 0x1021, 0x0000),
            ):
                expected = tuple(_crc16(payload, polynomial, initial) for payload in payloads)
                for byte_order in ("big", "little"):
                    observed = tuple(int.from_bytes(packet[offset:offset + 2], byte_order) for packet in frames)
                    if expected == observed:
                        results.append(IntegrityHypothesis(name, offset, 2, byte_order))
    return tuple(results)
