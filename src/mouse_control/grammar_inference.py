# SPDX-License-Identifier: AGPL-3.0-or-later
"""Conservative byte-structure inference from aligned, attributed examples."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class FieldKind(str, Enum):
    CONSTANT = "constant"
    VALUE = "value"
    LENGTH = "length"
    CHECKSUM_SUM8 = "checksum_sum8"
    STATUS = "status"
    VARIABLE = "variable"


@dataclass(frozen=True)
class TraceExample:
    request: bytes
    response: bytes
    semantic_value: int | None
    evidence: str
    pre_state: str = ""


@dataclass(frozen=True)
class InferredField:
    kind: FieldKind
    offset: int
    width: int
    encoding: str
    examples: tuple[str, ...]
    contradictions: tuple[str, ...] = ()


@dataclass(frozen=True)
class GrammarAlternative:
    request_size: int | None
    response_size: int | None
    fields: tuple[InferredField, ...]
    scope: str
    evidence: tuple[str, ...]
    contradictions: tuple[str, ...]

    @property
    def runtime_write_authorized(self) -> bool:
        return False


def infer_grammars(examples: tuple[TraceExample, ...], *, scope: str = "exact_model") -> tuple[GrammarAlternative, ...]:
    if len(examples) > 4096 or any(len(item.request) > 4096 or len(item.response) > 4096
                                   for item in examples):
        raise ValueError("grammar inference input exceeds deterministic bounds")
    if len(examples) < 2 or any(not item.evidence for item in examples):
        return ()
    evidence = tuple(dict.fromkeys(item.evidence for item in examples))
    req_sizes, resp_sizes = {len(item.request) for item in examples}, {len(item.response) for item in examples}
    min_req = min(req_sizes)
    constants = tuple(InferredField(FieldKind.CONSTANT, offset, 1, f"0x{examples[0].request[offset]:02x}", evidence)
                      for offset in range(min_req)
                      if len({item.request[offset] for item in examples}) == 1)
    fields = list(constants)
    if len(req_sizes) > 1:
        for offset in range(min_req):
            if all(item.request[offset] == len(item.request) for item in examples):
                fields.append(InferredField(FieldKind.LENGTH, offset, 1, "u8", evidence))
    for offset in range(min_req):
        if all(sum(item.request[:offset] + item.request[offset + 1:]) & 0xff == item.request[offset]
               for item in examples):
            fields.append(InferredField(FieldKind.CHECKSUM_SUM8, offset, 1, "sum8-excluding-field", evidence))
    values = tuple(item.semantic_value for item in examples)
    alternatives: list[GrammarAlternative] = []
    if all(value is not None and 0 <= value <= 65535 for value in values):
        for endian in ("little", "big"):
            matches = []
            for offset in range(max(0, min_req - 1)):
                if all(int.from_bytes(item.request[offset:offset + 2], endian) == item.semantic_value
                       for item in examples):
                    matches.append(offset)
            for offset in matches:
                alternatives.append(GrammarAlternative(
                    next(iter(req_sizes)) if len(req_sizes) == 1 else None,
                    next(iter(resp_sizes)) if len(resp_sizes) == 1 else None,
                    tuple(fields + [InferredField(FieldKind.VALUE, offset, 2, f"u16-{endian}", evidence)]),
                    scope, evidence, (),
                ))
    if not alternatives:
        contradictions = ("packet sizes vary",) if len(req_sizes) > 1 else ()
        alternatives.append(GrammarAlternative(
            next(iter(req_sizes)) if len(req_sizes) == 1 else None,
            next(iter(resp_sizes)) if len(resp_sizes) == 1 else None,
            tuple(fields), scope, evidence, contradictions,
        ))
    return tuple(alternatives)
