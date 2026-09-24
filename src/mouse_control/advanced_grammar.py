"""Bounded advanced grammar inference; hypotheses only, never authority."""
from __future__ import annotations
from dataclasses import dataclass
import binascii
from functools import reduce


@dataclass(frozen=True)
class IntegrityCandidate:
    name: str
    field_offset: int
    width: int
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class BitfieldCandidate:
    offset: int
    mask: int
    shift: int
    observed_values: tuple[int, ...]
    neighboring_constant_mask: int
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class RepeatedRecordCandidate:
    offset: int
    width: int
    count: int
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class CrossModelAlignment:
    prefix: int
    suffix: int
    left_middle: tuple[int, int]
    right_middle: tuple[int, int]
    equivalent: bool
    reasons: tuple[str, ...]


def _crc8(data: bytes, polynomial: int) -> int:
    value = 0
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = ((value << 1) ^ polynomial) & 0xff if value & 0x80 else (value << 1) & 0xff
    return value


def _crc16_modbus(data: bytes) -> int:
    value = 0xffff
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ 0xa001 if value & 1 else value >> 1
    return value


def infer_integrity(frames: tuple[tuple[bytes, str], ...], *, field_offset: int,
                    width: int = 1) -> tuple[IntegrityCandidate, ...]:
    """Test a finite reviewed family of integrity algorithms."""
    if len(frames) > 4096 or any(len(frame) > 4096 for frame, _ in frames):
        raise ValueError("integrity inference input exceeds deterministic bounds")
    if len(frames) < 2 or width not in (1, 2, 4):
        return ()
    evidence = tuple(dict.fromkeys(item[1] for item in frames))
    candidates: list[str] = []
    for name in ("sum8", "xor8", "crc8-07", "crc8-31", "crc16-modbus", "crc16-ccitt", "crc32"):
        good = True
        for frame, _ in frames:
            if field_offset < 0 or field_offset + width > len(frame):
                good = False
                break
            data = frame[:field_offset] + frame[field_offset + width:]
            actual = int.from_bytes(frame[field_offset:field_offset + width], "little")
            calculated = {
                "sum8": sum(data) & 0xff,
                "xor8": reduce(int.__xor__, data, 0),
                "crc8-07": _crc8(data, 0x07),
                "crc8-31": _crc8(data, 0x31),
                "crc16-modbus": _crc16_modbus(data),
                "crc16-ccitt": binascii.crc_hqx(data, 0),
                "crc32": binascii.crc32(data) & 0xffffffff,
            }[name]
            expected_width = (
                1 if name in {"sum8", "xor8", "crc8-07", "crc8-31"}
                else 2 if name.startswith("crc16") else 4
            )
            if width != expected_width or actual != calculated:
                good = False
                break
        if good:
            candidates.append(name)
    return tuple(IntegrityCandidate(name, field_offset, width, evidence) for name in candidates)


def infer_bitfield(samples: tuple[tuple[int, int, str], ...]) -> BitfieldCandidate | None:
    """Infer changed bits from controlled (raw, semantic, evidence) samples."""
    if len(samples) > 4096:
        raise ValueError("bitfield inference input exceeds deterministic bounds")
    if len(samples) < 2 or len({semantic for _, semantic, _ in samples}) < 2:
        return None
    changed = 0
    base = samples[0][0]
    for raw, _, _ in samples[1:]:
        changed |= base ^ raw
    if not changed:
        return None
    shift = (changed & -changed).bit_length() - 1
    evidence = tuple(dict.fromkeys(item[2] for item in samples))
    return BitfieldCandidate(0, changed, shift, tuple(sorted({item[1] for item in samples})),
                             (~changed) & 0xff, evidence)


def infer_repeated_records(payload: bytes, *, evidence: tuple[str, ...],
                           allowed_widths: tuple[int, ...] = (2, 4, 8, 16)) -> tuple[RepeatedRecordCandidate, ...]:
    if len(payload) > 65536 or len(allowed_widths) > 64:
        raise ValueError("record inference input exceeds deterministic bounds")
    result = []
    for width in allowed_widths:
        for offset in range(min(width, len(payload))):
            count = (len(payload) - offset) // width
            if count < 2 or offset + count * width != len(payload):
                continue
            records = [payload[offset + i * width:offset + (i + 1) * width] for i in range(count)]
            if len(set(records)) > 1 and len({record[0] for record in records}) == count:
                result.append(RepeatedRecordCandidate(offset, width, count, evidence))
    return tuple(result)


def align_models(left: bytes, right: bytes) -> CrossModelAlignment:
    if len(left) > 65536 or len(right) > 65536:
        raise ValueError("cross-model alignment input exceeds deterministic bounds")
    prefix = 0
    while prefix < min(len(left), len(right)) and left[prefix] == right[prefix]:
        prefix += 1
    suffix = 0
    while suffix < min(len(left), len(right)) - prefix and left[-1 - suffix] == right[-1 - suffix]:
        suffix += 1
    lm, rm = (prefix, len(left) - suffix), (prefix, len(right) - suffix)
    equivalent = left[lm[0]:lm[1]] == right[rm[0]:rm[1]]
    reasons = () if equivalent else ("generation-specific middle region differs",)
    return CrossModelAlignment(prefix, suffix, lm, rm, equivalent, reasons)
