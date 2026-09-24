# SPDX-License-Identifier: AGPL-3.0-or-later
"""Capability IR and offline proof-plan compiler. No transport or write authority.

Existing protocol_grammar objects remain the vocabulary for frames, records,
transactions, codecs, ownership and integrity. This layer links them to exact
bindings and evidence instead of implementing a second protocol interpreter.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .experiment_authority import StorageEffect
from .protocol_codec import decode_value, encode_value
from .protocol_grammar import CodecKind, FieldBinding, ProtocolFamily, SafetyClass, SemanticBehavior


class CapabilityKind(str, Enum):
    DPI = "dpi"
    POLLING_RATE = "report_rate"


@dataclass(frozen=True)
class PhysicalIdentity:
    transport: int
    vendor_id: int
    product_id: int
    model: str
    instance: str
    firmware: str

    def __post_init__(self):
        if self.transport not in (3, 5) or not all((self.model, self.instance, self.firmware)):
            raise ValueError("exact USB/Bluetooth identity and firmware evidence required")
        if any(type(v) is not int or not 0 <= v <= 65535 for v in (self.vendor_id, self.product_id)):
            raise ValueError("invalid VID/PID")
        if any('/' in v for v in (self.model, self.instance, self.firmware)):
            raise ValueError("live paths cannot be physical identity")


@dataclass(frozen=True)
class InterfaceIdentity:
    number: int
    descriptor_sha256: str

    def __post_init__(self):
        if type(self.number) is not int or self.number < 0:
            raise ValueError("exact interface number required")
        if len(self.descriptor_sha256) != 64 or any(c not in '0123456789abcdef' for c in self.descriptor_sha256):
            raise ValueError("exact descriptor SHA-256 required")


@dataclass(frozen=True)
class ValueDomain:
    values: tuple[int, ...] = ()
    minimum: int | None = None
    maximum: int | None = None
    step: int | None = None

    def __post_init__(self):
        ranged = any(v is not None for v in (self.minimum, self.maximum, self.step))
        if bool(self.values) == ranged:
            raise ValueError("supply one explicit domain or complete range")
        if self.values:
            if any(type(v) is not int or v <= 0 for v in self.values) or len(set(self.values)) != len(self.values):
                raise ValueError("domain must contain unique positive integers")
        elif (any(type(v) is not int for v in (self.minimum, self.maximum, self.step))
              or self.minimum <= 0 or self.maximum < self.minimum or self.step <= 0
              or (self.maximum - self.minimum) % self.step):
            raise ValueError("invalid aligned range")

    def contains(self, value: int) -> bool:
        if type(value) is not int:
            return False
        if self.values:
            return value in self.values
        return self.minimum <= value <= self.maximum and (value - self.minimum) % self.step == 0

    def neighbor(self, baseline: int) -> int | None:
        if not self.contains(baseline):
            raise ValueError("baseline outside legal domain")
        choices = self.values or (baseline - self.step, baseline + self.step)
        others = [v for v in choices if v != baseline and self.contains(v)]
        return min(others, key=lambda v: (abs(v - baseline), v)) if others else None


@dataclass(frozen=True)
class CapabilityIR:
    kind: CapabilityKind
    query: str
    setter: str
    field: FieldBinding
    domain: ValueDomain
    storage: StorageEffect = StorageEffect.UNKNOWN
    rollback: str = ""
    verification: str = ""
    correlation: str = ""
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class PeripheralIR:
    identity: PhysicalIdentity
    interface: InterfaceIdentity
    family: ProtocolFamily
    capabilities: tuple[CapabilityIR, ...]

    def __post_init__(self):
        if len({c.kind for c in self.capabilities}) != len(self.capabilities):
            raise ValueError("duplicate capability")


@dataclass(frozen=True)
class ProofPlan:
    capability: CapabilityKind
    baseline: int
    target: int | None
    steps: tuple[str, ...]
    blockers: tuple[str, ...]
    evidence: tuple[str, ...]

    @property
    def runtime_write_authorized(self) -> bool:
        return False


def compile_proof_plan(ir: PeripheralIR, capability: CapabilityKind, baseline: int,
                       *, evidence_ids: frozenset[str]) -> ProofPlan:
    """Compile reviewable research steps; never promote or execute a candidate.

    References must resolve, but resolving a reference does not establish truth.
    A transport owner still must capture baseline, bind generation, authorize,
    correlate, verify, and restore before any result can be promoted.
    """
    cap = next(c for c in ir.capabilities if c.kind is capability)
    blockers: list[str] = []
    transactions = {t.name: t for t in ir.family.transactions}
    frames = {f.name: f for f in ir.family.frame_grammars}
    if len(transactions) != len(ir.family.transactions) or len(frames) != len(ir.family.frame_grammars):
        blockers.append("ambiguous grammar names")
    query, setter = transactions.get(cap.query), transactions.get(cap.setter)
    if query is None or query.safety is not SafetyClass.READ_ONLY:
        blockers.append("read-only canonical query unresolved")
    if setter is None or setter.safety is not SafetyClass.REVERSIBLE:
        blockers.append("reversible setter unresolved")
    for transaction in (query, setter):
        if transaction is not None and (not transaction.steps or any(
            s.frame not in frames or s.transport is None for s in transaction.steps
        )):
            blockers.append(f"incomplete transaction: {transaction.name}")
    frame = frames.get(cap.field.frame)
    if frame is None or cap.field.offset + cap.field.width > frame.size:
        blockers.append("exact field/report shape unresolved")
    behaviors = ({SemanticBehavior.DPI_VALUE, SemanticBehavior.DPI_X, SemanticBehavior.DPI_Y,
                  SemanticBehavior.DPI_STAGE_INDEX} if capability is CapabilityKind.DPI
                 else {SemanticBehavior.REPORT_RATE_HZ})
    if cap.field.behavior not in behaviors:
        blockers.append("capability semantic mismatch")
    if cap.storage is not StorageEffect.VOLATILE:
        blockers.append("volatile storage behavior unresolved")
    for name in ("rollback", "verification", "correlation"):
        if not getattr(cap, name).strip():
            blockers.append(f"{name} unresolved")
    if not cap.evidence or any(ref not in evidence_ids for ref in cap.evidence):
        blockers.append("source evidence unresolved")
    target = cap.domain.neighbor(baseline)
    if target is None:
        blockers.append("no differential control value")
    return ProofPlan(capability, baseline, target,
                     ("bind exact identity and generation", "capture complete baseline",
                      "verify baseline behavior", "authorize bounded experiment",
                      "write one field", "correlate canonical readback",
                      "independently verify behavior", "restore complete baseline",
                      "verify restored state and behavior"), tuple(blockers), cap.evidence)


def patch_candidate_state(baseline: bytes, field: FieldBinding, value: int,
                          domain: ValueDomain, *, report_size: int,
                          mutation_policy=None) -> bytes:
    """Offline RMW proposal. Unknown bytes and untargeted bits remain intact.

    Does not synthesize commands/checksums or send reports. An executable driver
    must separately implement sourced integrity and transaction rules.
    """
    if len(baseline) != report_size or not 0 <= field.offset < report_size or field.offset + field.width > report_size:
        raise ValueError("complete exact-sized state required")
    if not domain.contains(value):
        raise ValueError("value outside legal domain")
    codec = field.codec
    if codec.kind in (CodecKind.ENUM, CodecKind.LOOKUP) and len(set(codec.values.values())) != len(codec.values):
        raise ValueError("non-injective codec cannot safely choose an encoding")
    encoded = encode_value(value, codec, width=field.width)
    if len(encoded) != field.width:
        raise ValueError("codec width disagrees with field")
    result = bytearray(baseline)
    if codec.kind is CodecKind.BITFIELD:
        mask = codec.mask << codec.shift
        if mask >= 1 << (8 * field.width):
            raise ValueError("bitfield mask exceeds field")
        original = int.from_bytes(baseline[field.offset:field.offset + field.width], 'little')
        raw = int.from_bytes(encoded, 'little')
        encoded = ((original & ~mask) | (raw & mask)).to_bytes(field.width, 'little')
    result[field.offset:field.offset + field.width] = encoded
    if decode_value(encoded, codec, width=field.width) != value:
        raise ValueError("codec does not roundtrip")
    candidate = bytes(result)
    if mutation_policy is not None:
        mutation_policy.require_candidate(baseline, candidate)
    return candidate
