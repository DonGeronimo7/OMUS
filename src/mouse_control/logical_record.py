"""Read-only logical-record reassembly across fixed HID transport frames."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .integrity_inference import IntegrityHypothesis, validate_integrity
from .temporal_dialogue import Direction


class RecordCompleteness(str, Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    INVALID = "invalid"


class RecordIntegrity(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TransportFrame:
    """One fixed-width report with persistent stream identity metadata."""

    source_id: str
    physical_id: str
    channel_id: str
    transport: str
    direction: Direction
    report_namespace: str
    report_id: int | None
    fixed_wire_length: int
    generation: int
    timestamp_ns: int
    sequence: int
    payload: bytes

    def __post_init__(self) -> None:
        if not self.source_id or not self.physical_id or not self.channel_id:
            raise ValueError("transport frame identities are required")
        if not self.report_namespace or not self.transport:
            raise ValueError("transport and report namespace are required")
        if self.fixed_wire_length <= 0 or len(self.payload) != self.fixed_wire_length:
            raise ValueError("payload must equal the fixed HID wire length")
        if self.generation < 0 or self.timestamp_ns < 0 or self.sequence < 0:
            raise ValueError("generation, timestamp, and sequence must be non-negative")


@dataclass(frozen=True)
class RecordFieldSpec:
    name: str
    offset: int
    width: int = 1

    def __post_init__(self) -> None:
        if not self.name or self.offset < 0 or self.width <= 0:
            raise ValueError("record field name, offset, and width are required")


@dataclass(frozen=True)
class IntegritySelector:
    """Select an integrity wrapper from bytes in the assembled record."""

    offset: int
    value: int
    hypothesis: IntegrityHypothesis

    def __post_init__(self) -> None:
        if self.offset < 0 or not 0 <= self.value <= 0xFF:
            raise ValueError("integrity selector must address one byte")


@dataclass(frozen=True)
class LogicalRecordGrammar:
    """Declarative boundaries for records carried in fixed transport frames.

    ``length_adjustment`` converts the declared integer to total record bytes.
    This represents both total-length fields (adjustment zero) and payload-
    length fields (adjustment equal to the header/trailer size).
    """

    name: str
    report_namespace: str
    report_id: int | None
    fixed_wire_length: int
    start_markers: tuple[bytes, ...]
    length_offset: int
    length_width: int = 1
    length_byte_order: str = "little"
    length_adjustment: int = 0
    minimum_record_length: int = 1
    maximum_record_length: int = 4096
    type_offset: int | None = None
    sequence_offset: int | None = None
    known_fields: tuple[RecordFieldSpec, ...] = ()
    integrity_selectors: tuple[IntegritySelector, ...] = ()
    padding_bytes: tuple[int, ...] = (0x00,)

    def __post_init__(self) -> None:
        if not self.name or not self.report_namespace:
            raise ValueError("logical-record grammar name and namespace are required")
        if self.fixed_wire_length <= 0 or self.length_offset < 0 or self.length_width <= 0:
            raise ValueError("logical-record framing dimensions are invalid")
        if self.length_byte_order not in {"little", "big"}:
            raise ValueError("logical record length byte order must be little or big")
        if self.minimum_record_length <= 0 or self.maximum_record_length < self.minimum_record_length:
            raise ValueError("logical-record length bounds are invalid")
        if not self.start_markers or any(not marker for marker in self.start_markers):
            raise ValueError("at least one non-empty record marker is required")
        if len(set(self.start_markers)) != len(self.start_markers):
            raise ValueError("record start markers must be unique")
        if any(not 0 <= value <= 0xFF for value in self.padding_bytes):
            raise ValueError("padding values must fit in one byte")

    @property
    def header_length(self) -> int:
        return max(
            max(map(len, self.start_markers)),
            self.length_offset + self.length_width,
            0 if self.type_offset is None else self.type_offset + 1,
            0 if self.sequence_offset is None else self.sequence_offset + 1,
        )


@dataclass(frozen=True)
class OpaqueRegion:
    offset: int
    data: bytes


@dataclass(frozen=True)
class LogicalRecord:
    grammar: str
    completeness: RecordCompleteness
    integrity: RecordIntegrity
    integrity_protected: bool
    data: bytes
    source_frames: tuple[TransportFrame, ...]
    start_timestamp_ns: int
    end_timestamp_ns: int
    generation: int
    channel_id: str
    report_namespace: str
    report_id: int | None
    declared_length: int | None
    captured_logical_length: int
    record_type: int | None
    record_sequence: int | None
    fields: dict[str, bytes] = field(default_factory=dict)
    opaque_regions: tuple[OpaqueRegion, ...] = ()
    reason: str = ""

    @property
    def transport_wire_lengths(self) -> tuple[int, ...]:
        return tuple(frame.fixed_wire_length for frame in self.source_frames)


@dataclass
class _PendingRecord:
    frames: list[TransportFrame]
    data: bytearray
    declared_length: int | None = None


class LogicalRecordReassembler:
    """Assemble independent record streams without crossing identity domains."""

    def __init__(self, grammar: LogicalRecordGrammar) -> None:
        self.grammar = grammar
        self._pending: dict[tuple[object, ...], _PendingRecord] = {}
        self._generation: dict[tuple[object, ...], int] = {}

    def _base_key(self, frame: TransportFrame) -> tuple[object, ...]:
        return (
            frame.source_id, frame.physical_id, frame.channel_id,
            frame.transport, frame.direction, frame.report_namespace,
            frame.report_id, self.grammar.name,
        )

    def _key(self, frame: TransportFrame) -> tuple[object, ...]:
        return self._base_key(frame) + (frame.generation,)

    def _matches(self, frame: TransportFrame) -> bool:
        return (
            frame.report_namespace == self.grammar.report_namespace
            and frame.report_id == self.grammar.report_id
            and frame.fixed_wire_length == self.grammar.fixed_wire_length
        )

    def _marker_length(self, data: bytes | bytearray) -> int | None:
        for marker in sorted(self.grammar.start_markers, key=len, reverse=True):
            if bytes(data[:len(marker)]) == marker:
                return len(marker)
        return None

    def _declared_total(self, data: bytes | bytearray) -> int | None:
        end = self.grammar.length_offset + self.grammar.length_width
        if len(data) < end:
            return None
        declared = int.from_bytes(
            data[self.grammar.length_offset:end], self.grammar.length_byte_order,
        )
        return declared + self.grammar.length_adjustment

    def _opaque_regions(self, data: bytes) -> tuple[OpaqueRegion, ...]:
        known = [False] * len(data)
        marker_length = self._marker_length(data) or 0
        spans = [(0, marker_length), (
            self.grammar.length_offset,
            self.grammar.length_offset + self.grammar.length_width,
        )]
        for offset in (self.grammar.type_offset, self.grammar.sequence_offset):
            if offset is not None:
                spans.append((offset, offset + 1))
        spans.extend((item.offset, item.offset + item.width) for item in self.grammar.known_fields)
        for start, end in spans:
            for index in range(max(0, start), min(len(data), end)):
                known[index] = True
        regions: list[OpaqueRegion] = []
        start: int | None = None
        for index, is_known in enumerate((*known, True)):
            if not is_known and start is None:
                start = index
            elif is_known and start is not None:
                regions.append(OpaqueRegion(start, data[start:index]))
                start = None
        return tuple(regions)

    def _record(
        self,
        pending: _PendingRecord,
        completeness: RecordCompleteness,
        *,
        reason: str,
    ) -> LogicalRecord:
        data = bytes(pending.data)
        integrity = RecordIntegrity.UNKNOWN
        integrity_protected = False
        for selector in self.grammar.integrity_selectors:
            if len(data) > selector.offset and data[selector.offset] == selector.value:
                integrity_protected = True
                result = (
                    validate_integrity(data, selector.hypothesis)
                    if completeness is RecordCompleteness.COMPLETE
                    else None
                )
                integrity = (
                    RecordIntegrity.UNKNOWN if result is None
                    else RecordIntegrity.VALID if result
                    else RecordIntegrity.INVALID
                )
                if integrity is RecordIntegrity.INVALID:
                    completeness = RecordCompleteness.INVALID
                    reason = "integrity validation failed"
                break
        fields = {
            spec.name: data[spec.offset:spec.offset + spec.width]
            for spec in self.grammar.known_fields
            if spec.offset + spec.width <= len(data)
        }
        frames = tuple(pending.frames)
        first, last = frames[0], frames[-1]
        return LogicalRecord(
            self.grammar.name, completeness, integrity, integrity_protected,
            data, frames,
            first.timestamp_ns, last.timestamp_ns, first.generation,
            first.channel_id, first.report_namespace, first.report_id,
            pending.declared_length, len(data),
            data[self.grammar.type_offset]
            if self.grammar.type_offset is not None and len(data) > self.grammar.type_offset
            else None,
            data[self.grammar.sequence_offset]
            if self.grammar.sequence_offset is not None and len(data) > self.grammar.sequence_offset
            else None,
            fields, self._opaque_regions(data), reason,
        )

    def _invalidate_old_generation(
        self, frame: TransportFrame,
    ) -> list[LogicalRecord]:
        base = self._base_key(frame)
        previous = self._generation.get(base)
        if previous is None or frame.generation <= previous:
            self._generation[base] = max(frame.generation, previous or 0)
            return []
        self._generation[base] = frame.generation
        old_key = base + (previous,)
        pending = self._pending.pop(old_key, None)
        if pending is None:
            return []
        return [self._record(
            pending, RecordCompleteness.INCOMPLETE,
            reason="connection generation changed before record completion",
        )]

    def add(self, frame: TransportFrame) -> tuple[LogicalRecord, ...]:
        if not self._matches(frame):
            return ()
        completed = self._invalidate_old_generation(frame)
        base = self._base_key(frame)
        current = self._generation.get(base, frame.generation)
        if frame.generation < current:
            return tuple(completed)
        key = self._key(frame)
        pending = self._pending.get(key)
        remaining = bytearray(frame.payload)
        while remaining:
            if pending is None:
                if (
                    not remaining
                    or remaining[0] in self.grammar.padding_bytes
                    or self._marker_length(remaining) is None
                ):
                    break
                pending = _PendingRecord([frame], bytearray())
                self._pending[key] = pending
            elif pending.frames[-1] is not frame:
                pending.frames.append(frame)

            if pending.declared_length is None:
                need = self.grammar.header_length - len(pending.data)
                take = min(max(need, 1), len(remaining))
                pending.data.extend(remaining[:take])
                del remaining[:take]
                pending.declared_length = self._declared_total(pending.data)
                if pending.declared_length is None:
                    continue
                if not (
                    self.grammar.minimum_record_length
                    <= pending.declared_length
                    <= self.grammar.maximum_record_length
                ) or pending.declared_length < self.grammar.header_length:
                    completed.append(self._record(
                        pending, RecordCompleteness.INVALID,
                        reason="declared logical length is outside grammar bounds",
                    ))
                    self._pending.pop(key, None)
                    pending = None
                    continue

            needed = pending.declared_length - len(pending.data)
            take = min(needed, len(remaining))
            pending.data.extend(remaining[:take])
            del remaining[:take]
            if len(pending.data) < pending.declared_length:
                continue
            completed.append(self._record(
                pending, RecordCompleteness.COMPLETE,
                reason="declared logical length captured",
            ))
            self._pending.pop(key, None)
            pending = None
        return tuple(completed)

    def finish(self) -> tuple[LogicalRecord, ...]:
        records = tuple(
            self._record(
                pending, RecordCompleteness.INCOMPLETE,
                reason="capture ended before declared logical length",
            )
            for pending in self._pending.values()
        )
        self._pending.clear()
        return records
