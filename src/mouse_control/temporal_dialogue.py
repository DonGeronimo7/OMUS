"""Bounded temporal assembly of protocol messages into cautious dialogues."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Direction(str, Enum):
    IN = "in"
    OUT = "out"


class DialogueKind(str, Enum):
    REQUEST = "request"
    RESPONSE = "response"
    BUSY_PENDING = "busy_pending"
    RESPONSE_POLL = "response_poll"
    SELECTOR_WRITE = "selector_write"
    SETTER = "setter"
    COMMIT_APPLY = "commit_apply"
    ECHO = "echo"
    WRITE_ACKNOWLEDGEMENT = "write_acknowledgement"
    UNSOLICITED_EVENT = "unsolicited_event"
    PHYSICAL_ACTION_EVENT = "physical_action_event"
    RECONNECT_SNAPSHOT = "reconnect_snapshot"
    STALE_RESPONSE = "stale_response"
    UNRELATED = "unrelated"


@dataclass(frozen=True)
class DialogueObservation:
    source_id: str
    physical_id: str
    channel_id: str
    transport: str
    direction: Direction
    report_namespace: str
    report_id: int | None
    generation: int
    timestamp_ns: int
    sequence: int
    payload: bytes
    transaction_tag: int | str | None = None
    grammar: str | None = None
    status: str | None = None

    def __post_init__(self) -> None:
        if not self.source_id or not self.physical_id or not self.channel_id:
            raise ValueError("source, physical device, and channel identities are required")
        if self.generation < 0 or self.timestamp_ns < 0 or self.sequence < 0:
            raise ValueError("generation, timestamp, and sequence must be non-negative")


@dataclass(frozen=True)
class DialogueRecord:
    kind: DialogueKind
    observation: DialogueObservation
    request: DialogueObservation | None = None
    confidence: str = "structural"
    ambiguous: bool = False
    reason: str = ""


@dataclass
class _Pending:
    request: DialogueObservation
    busy: bool = False


class DialogueAssembler:
    """Correlate messages using identity, tags, grammar, status, and time.

    Timing only bounds candidates; it is never sufficient to select one when
    multiple structurally compatible requests remain.
    """

    def __init__(self, *, window_ms: int = 500) -> None:
        if window_ms <= 0:
            raise ValueError("window_ms must be positive")
        self.window_ns = window_ms * 1_000_000
        self._pending: list[_Pending] = []
        self._generation: dict[str, int] = {}

    @staticmethod
    def _same_channel(left: DialogueObservation, right: DialogueObservation) -> bool:
        return (
            left.source_id == right.source_id and left.physical_id == right.physical_id
            and left.channel_id == right.channel_id and left.transport == right.transport
            and left.report_namespace == right.report_namespace
            and left.report_id == right.report_id and left.generation == right.generation
        )

    def _candidates(self, item: DialogueObservation) -> list[_Pending]:
        candidates = [
            pending for pending in self._pending
            if self._same_channel(pending.request, item)
            and 0 <= item.timestamp_ns - pending.request.timestamp_ns <= self.window_ns
        ]
        if item.transaction_tag is not None:
            return [p for p in candidates if p.request.transaction_tag == item.transaction_tag]
        if item.grammar is not None:
            matched = [p for p in candidates if p.request.grammar == item.grammar]
            if matched:
                return matched
        return candidates

    def add(self, item: DialogueObservation) -> tuple[DialogueRecord, ...]:
        current = self._generation.get(item.physical_id, item.generation)
        self._generation[item.physical_id] = max(current, item.generation)
        if item.generation < self._generation[item.physical_id]:
            return (DialogueRecord(DialogueKind.STALE_RESPONSE, item, reason="older connection generation"),)
        if item.direction is Direction.OUT:
            candidates = self._candidates(item)
            if item.grammar in {"poll", "response_poll"} or (len(candidates) == 1 and candidates[0].busy):
                request = candidates[0].request if len(candidates) == 1 else None
                return (DialogueRecord(DialogueKind.RESPONSE_POLL, item, request, ambiguous=len(candidates) > 1),)
            self._pending.append(_Pending(item))
            kind = DialogueKind.SELECTOR_WRITE if item.grammar == "selector" else DialogueKind.SETTER if item.grammar == "setter" else DialogueKind.COMMIT_APPLY if item.grammar == "commit" else DialogueKind.REQUEST
            return () if kind is DialogueKind.REQUEST else (DialogueRecord(kind, item),)

        if item.grammar == "physical_action":
            return (DialogueRecord(DialogueKind.PHYSICAL_ACTION_EVENT, item),)
        if item.grammar == "event":
            return (DialogueRecord(DialogueKind.UNSOLICITED_EVENT, item),)
        candidates = self._candidates(item)
        if not candidates:
            kind = DialogueKind.UNSOLICITED_EVENT if item.grammar == "event" else DialogueKind.UNRELATED
            return (DialogueRecord(kind, item, reason="no compatible pending request"),)
        if len(candidates) != 1:
            return (DialogueRecord(DialogueKind.UNRELATED, item, ambiguous=True, reason="multiple compatible requests"),)
        pending = candidates[0]
        if item.status in {"busy", "pending"}:
            pending.busy = True
            return (DialogueRecord(DialogueKind.BUSY_PENDING, item, pending.request),)
        self._pending.remove(pending)
        if item.payload == pending.request.payload:
            kind = DialogueKind.ECHO
        elif item.status in {"ack", "acknowledged"}:
            kind = DialogueKind.WRITE_ACKNOWLEDGEMENT
        else:
            kind = DialogueKind.RESPONSE
        confidence = "identifier" if item.transaction_tag is not None else "grammar"
        return (DialogueRecord(kind, item, pending.request, confidence=confidence),)

    def advance_generation(self, physical_id: str, generation: int) -> tuple[DialogueRecord, ...]:
        if generation < self._generation.get(physical_id, -1):
            raise ValueError("connection generation cannot move backwards")
        self._generation[physical_id] = generation
        stale = [p for p in self._pending if p.request.physical_id == physical_id and p.request.generation < generation]
        self._pending = [p for p in self._pending if p not in stale]
        return tuple(DialogueRecord(DialogueKind.RECONNECT_SNAPSHOT, p.request, p.request, reason="pending request invalidated by reconnect") for p in stale)

    def finish(self) -> tuple[DialogueRecord, ...]:
        pending, self._pending = self._pending, []
        return tuple(DialogueRecord(DialogueKind.UNRELATED, p.request, p.request, reason="request timed out without response") for p in pending)
