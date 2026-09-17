"""Conservative dependent-field inference with retained alternatives."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from typing import Sequence


class DependencyKind(str, Enum):
    LITERAL = "literal"
    DUPLICATE = "duplicate"
    BYTE_SWAP = "byte_swap"
    SCALED = "scaled"
    AFFINE = "affine"
    RECIPROCAL = "reciprocal"
    LOOKUP = "lookup"
    ENUM = "enum"
    STAGE_INDEX = "stage_index"


@dataclass(frozen=True)
class DependencyCandidate:
    kind: DependencyKind
    offset: int
    width: int
    parameters: tuple[tuple[str, object], ...] = ()
    related_offset: int | None = None


@dataclass(frozen=True)
class DependencyInference:
    candidates: tuple[DependencyCandidate, ...]
    unexplained_offsets: tuple[int, ...]

    @property
    def promotion_safe(self) -> bool:
        return bool(self.candidates) and not self.unexplained_offsets


def infer_dependencies(frames: Sequence[bytes], semantic_values: Sequence[int]) -> DependencyInference:
    """Explain varying fields without choosing between equivalent candidates."""
    packets, values = tuple(frames), tuple(int(v) for v in semantic_values)
    if len(packets) < 3 or len(packets) != len(values) or len(set(values)) < 3:
        return DependencyInference((), ())
    widths = {len(frame) for frame in packets}
    if len(widths) != 1:
        raise ValueError("frames must have one stable width")
    width = next(iter(widths))
    changing = {i for i in range(width) if len({frame[i] for frame in packets}) > 1}
    candidates: list[DependencyCandidate] = []
    explained: set[int] = set()
    literal_spans: list[tuple[int, int]] = []
    for size in (1, 2):
        for offset in range(width - size + 1):
            for endian in (("big",) if size == 1 else ("little", "big")):
                raw = tuple(int.from_bytes(f[offset:offset + size], endian) for f in packets)
                if raw == values:
                    candidates.append(DependencyCandidate(DependencyKind.LITERAL, offset, size, (("endian", endian),)))
                    explained.update(range(offset, offset + size)); literal_spans.append((offset, size))
                if len(set(raw)) == len(raw):
                    mapping = tuple(sorted(zip(raw, values)))
                    candidates.append(DependencyCandidate(DependencyKind.LOOKUP, offset, size, (("mapping", mapping),)))
                    if raw == tuple(range(len(values))):
                        candidates.append(DependencyCandidate(DependencyKind.STAGE_INDEX, offset, size))
                    if len(raw) >= 2 and raw[1] != raw[0]:
                        scale = Fraction(values[1] - values[0], raw[1] - raw[0])
                        intercept = Fraction(values[0]) - scale * raw[0]
                        if all(scale * r + intercept == v for r, v in zip(raw, values)):
                            kind = DependencyKind.SCALED if intercept == 0 else DependencyKind.AFFINE
                            candidates.append(DependencyCandidate(kind, offset, size, (("scale", str(scale)), ("offset", str(intercept)))))
                            explained.update(range(offset, offset + size))
    for source, size in literal_spans:
        source_values = tuple(f[source:source + size] for f in packets)
        for offset in range(width - size + 1):
            if offset == source:
                continue
            if tuple(f[offset:offset + size] for f in packets) == source_values:
                candidates.append(DependencyCandidate(DependencyKind.DUPLICATE, offset, size, related_offset=source))
                explained.update(range(offset, offset + size))
            if size == 2 and tuple(f[offset:offset + size] for f in packets) == tuple(v[::-1] for v in source_values):
                candidates.append(DependencyCandidate(DependencyKind.BYTE_SWAP, offset, size, related_offset=source))
                explained.update(range(offset, offset + size))
    unique = tuple(dict.fromkeys(candidates))
    return DependencyInference(unique, tuple(sorted(changing - explained)))

