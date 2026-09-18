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


class BurstCompletionReason(str, Enum):
    QUIET_INTERVAL = "quiet_interval"
    MAX_RESPONSES = "max_responses"
    DEADLINE = "deadline"
    EXPLICIT_END = "explicit_end"
    GENERATION_CHANGE = "generation_change"


@dataclass(frozen=True)
class BurstDialogueSpec:
    """Bounded correlation rules for one trigger followed by response records."""

    request_namespace: str
    response_namespace: str
    quiet_interval_ms: int
    absolute_deadline_ms: int
    max_responses: int
    request_report_id: int | None = None
    response_report_id: int | None = None
    response_channel_id: str | None = None
    response_grammar: str | None = None

    def __post_init__(self) -> None:
        if not self.request_namespace or not self.response_namespace:
            raise ValueError("burst namespaces are required")
        if self.quiet_interval_ms <= 0:
            raise ValueError("quiet_interval_ms must be positive")
        if self.absolute_deadline_ms <= self.quiet_interval_ms:
            raise ValueError("absolute_deadline_ms must exceed quiet_interval_ms")
        if self.max_responses <= 0:
            raise ValueError("max_responses must be positive")


@dataclass(frozen=True)
class BurstDialogueResult:
    request: DialogueObservation
    responses: tuple[DialogueObservation, ...]
    start_timestamp_ns: int
    last_response_timestamp_ns: int | None
    completion_reason: BurstCompletionReason
    confidence: str
    generation: int
    channel_id: str
    grammar: str | None

    @property
    def response_count(self) -> int:
        return len(self.responses)


@dataclass
class _Pending:
    request: DialogueObservation
    busy: bool = False


@dataclass
class _PendingBurst:
    request: DialogueObservation
    spec: BurstDialogueSpec
    responses: list[DialogueObservation]


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
        self._bursts: list[_PendingBurst] = []
        self._generation: dict[str, int] = {}

    @staticmethod
    def _burst_result(
        pending: _PendingBurst,
        reason: BurstCompletionReason,
    ) -> BurstDialogueResult:
        request = pending.request
        return BurstDialogueResult(
            request=request,
            responses=tuple(pending.responses),
            start_timestamp_ns=request.timestamp_ns,
            last_response_timestamp_ns=(
                pending.responses[-1].timestamp_ns if pending.responses else None
            ),
            completion_reason=reason,
            confidence="identifier" if request.transaction_tag is not None else "grammar",
            generation=request.generation,
            channel_id=pending.spec.response_channel_id or request.channel_id,
            grammar=pending.spec.response_grammar or request.grammar,
        )

    def begin_burst(
        self,
        request: DialogueObservation,
        spec: BurstDialogueSpec,
    ) -> tuple[BurstDialogueResult, ...]:
        """Begin one bounded burst without sending or executing the request."""

        if request.direction is not Direction.OUT:
            raise ValueError("burst request must be outgoing")
        if request.report_namespace != spec.request_namespace:
            raise ValueError("burst request namespace does not match specification")
        if spec.request_report_id is not None and request.report_id != spec.request_report_id:
            raise ValueError("burst request report ID does not match specification")
        current = self._generation.get(request.physical_id, request.generation)
        if request.generation < current:
            raise ValueError("cannot begin burst on an older connection generation")
        completed = (
            self._advance_burst_generation(request.physical_id, request.generation)
            if request.generation > current else ()
        )
        self._generation[request.physical_id] = request.generation
        self._bursts.append(_PendingBurst(request, spec, []))
        return completed

    @staticmethod
    def _burst_matches(pending: _PendingBurst, item: DialogueObservation) -> bool:
        request, spec = pending.request, pending.spec
        if item.direction is not Direction.IN:
            return False
        if item.grammar in {"event", "physical_action"}:
            return False
        if (
            item.source_id != request.source_id
            or item.physical_id != request.physical_id
            or item.transport != request.transport
            or item.generation != request.generation
            or item.channel_id != (spec.response_channel_id or request.channel_id)
            or item.report_namespace != spec.response_namespace
        ):
            return False
        if spec.response_report_id is not None and item.report_id != spec.response_report_id:
            return False
        expected_grammar = spec.response_grammar or request.grammar
        if expected_grammar is not None and item.grammar != expected_grammar:
            return False
        if request.transaction_tag is not None and item.transaction_tag != request.transaction_tag:
            return False
        last_timestamp = (
            pending.responses[-1].timestamp_ns
            if pending.responses else request.timestamp_ns
        )
        deadline = request.timestamp_ns + spec.absolute_deadline_ms * 1_000_000
        if not last_timestamp <= item.timestamp_ns < deadline:
            return False
        return True

    def advance_time(self, timestamp_ns: int) -> tuple[BurstDialogueResult, ...]:
        """Complete bursts whose replay timestamps crossed a quiet/deadline bound."""

        if timestamp_ns < 0:
            raise ValueError("timestamp_ns must be non-negative")
        completed: list[BurstDialogueResult] = []
        retained: list[_PendingBurst] = []
        for pending in self._bursts:
            request, spec = pending.request, pending.spec
            last = pending.responses[-1].timestamp_ns if pending.responses else request.timestamp_ns
            quiet_at = last + spec.quiet_interval_ms * 1_000_000
            deadline_at = request.timestamp_ns + spec.absolute_deadline_ms * 1_000_000
            reason: BurstCompletionReason | None = None
            if deadline_at <= quiet_at and timestamp_ns >= deadline_at:
                reason = BurstCompletionReason.DEADLINE
            elif timestamp_ns >= quiet_at:
                reason = BurstCompletionReason.QUIET_INTERVAL
            if reason is None:
                retained.append(pending)
            else:
                completed.append(self._burst_result(pending, reason))
        self._bursts = retained
        return tuple(completed)

    def observe_burst(
        self,
        item: DialogueObservation,
    ) -> tuple[BurstDialogueResult, ...]:
        """Observe one record and return any deterministically completed bursts."""

        completed = list(self.advance_time(item.timestamp_ns))
        current = self._generation.get(item.physical_id, item.generation)
        if item.generation < current:
            return tuple(completed)
        if item.generation > current:
            completed.extend(self._advance_burst_generation(item.physical_id, item.generation))
            self._generation[item.physical_id] = item.generation
        candidates = [pending for pending in self._bursts if self._burst_matches(pending, item)]
        if len(candidates) != 1:
            return tuple(completed)
        pending = candidates[0]
        pending.responses.append(item)
        if len(pending.responses) >= pending.spec.max_responses:
            self._bursts.remove(pending)
            completed.append(self._burst_result(pending, BurstCompletionReason.MAX_RESPONSES))
        return tuple(completed)

    def end_burst(
        self,
        request_sequence: int,
    ) -> BurstDialogueResult:
        """Complete one burst using a protocol-defined explicit terminator."""

        matches = [item for item in self._bursts if item.request.sequence == request_sequence]
        if len(matches) != 1:
            raise ValueError("request_sequence does not identify exactly one pending burst")
        pending = matches[0]
        self._bursts.remove(pending)
        return self._burst_result(pending, BurstCompletionReason.EXPLICIT_END)

    def _advance_burst_generation(
        self,
        physical_id: str,
        generation: int,
    ) -> tuple[BurstDialogueResult, ...]:
        stale = [
            item for item in self._bursts
            if item.request.physical_id == physical_id and item.request.generation < generation
        ]
        self._bursts = [item for item in self._bursts if item not in stale]
        return tuple(
            self._burst_result(item, BurstCompletionReason.GENERATION_CHANGE)
            for item in stale
        )

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

    def advance_generation(
        self,
        physical_id: str,
        generation: int,
    ) -> tuple[DialogueRecord | BurstDialogueResult, ...]:
        if generation < self._generation.get(physical_id, -1):
            raise ValueError("connection generation cannot move backwards")
        self._generation[physical_id] = generation
        stale = [p for p in self._pending if p.request.physical_id == physical_id and p.request.generation < generation]
        self._pending = [p for p in self._pending if p not in stale]
        records: list[DialogueRecord | BurstDialogueResult] = [
            DialogueRecord(
                DialogueKind.RECONNECT_SNAPSHOT, p.request, p.request,
                reason="pending request invalidated by reconnect",
            )
            for p in stale
        ]
        records.extend(self._advance_burst_generation(physical_id, generation))
        return tuple(records)

    def finish(self) -> tuple[DialogueRecord, ...]:
        pending, self._pending = self._pending, []
        return tuple(DialogueRecord(DialogueKind.UNRELATED, p.request, p.request, reason="request timed out without response") for p in pending)
