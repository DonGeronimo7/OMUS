# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bounded temporal assembly of protocol messages into cautious dialogues."""

from __future__ import annotations

from dataclasses import dataclass, replace
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
    completion_timestamp_ns: int | None = None
    quiet_interval_ns: int | None = None

    @property
    def response_count(self) -> int:
        return len(self.responses)


class StateFreshness(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown_freshness"


class PushedStateAssociation(str, Enum):
    UNSOLICITED = "unsolicited_state"
    NUDGED = "nudged_state"


@dataclass(frozen=True)
class PushedStateSpec:
    """Identity and timing rules for one asynchronous state stream."""

    namespace: str
    report_id: int | None
    grammar: str
    channel_id: str | None = None
    periodic_max_gap_ms: int | None = None
    nudge_window_ms: int = 250
    nudge_namespace: str | None = None
    nudge_report_id: int | None = None
    nudge_channel_id: str | None = None

    def __post_init__(self) -> None:
        if not self.namespace or not self.grammar:
            raise ValueError("pushed-state namespace and grammar are required")
        if self.periodic_max_gap_ms is not None and self.periodic_max_gap_ms <= 0:
            raise ValueError("periodic_max_gap_ms must be positive")
        if self.nudge_window_ms <= 0:
            raise ValueError("nudge_window_ms must be positive")


@dataclass(frozen=True)
class StateEvidence:
    observation: DialogueObservation
    semantic_state_id: str
    decoded_state: bytes | int | str
    freshness: StateFreshness
    freshness_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class PushedStateRecord(StateEvidence):
    association: PushedStateAssociation = PushedStateAssociation.UNSOLICITED
    nudge: DialogueObservation | None = None
    accepted: bool = True
    periodic_index: int = 1
    state_counter: int | None = None
    subtype: int | None = None
    transform: str | None = None
    transform_source: bytes = b""
    transformed_payload: bytes = b""
    controlled_action: DialogueObservation | None = None


@dataclass
class _Pending:
    request: DialogueObservation
    busy: bool = False


@dataclass
class _PendingBurst:
    request: DialogueObservation
    spec: BurstDialogueSpec
    responses: list[DialogueObservation]


@dataclass
class _PendingNudge:
    observation: DialogueObservation
    spec: PushedStateSpec


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
        self._nudges: list[_PendingNudge] = []
        self._state_history: dict[tuple[object, ...], PushedStateRecord] = {}
        self._generation: dict[str, int] = {}

    @staticmethod
    def state_read_evidence(
        observation: DialogueObservation,
        *,
        semantic_state_id: str,
        decoded_state: bytes | int | str,
    ) -> StateEvidence:
        """Record a successful read without pretending it proves freshness."""

        if not semantic_state_id:
            raise ValueError("semantic_state_id is required")
        return StateEvidence(
            observation, semantic_state_id, decoded_state, StateFreshness.UNKNOWN,
            ("successful-read-does-not-prove-freshness",),
        )

    @staticmethod
    def prefer_later_pushed_state(
        immediate: StateEvidence,
        pushed: PushedStateRecord,
    ) -> tuple[StateEvidence, PushedStateRecord]:
        """Resolve stale immediate state when a later accepted push disagrees."""

        same_context = (
            immediate.semantic_state_id == pushed.semantic_state_id
            and immediate.observation.physical_id == pushed.observation.physical_id
            and immediate.observation.generation == pushed.observation.generation
            and immediate.observation.timestamp_ns <= pushed.observation.timestamp_ns
        )
        if not same_context or not pushed.accepted or immediate.decoded_state == pushed.decoded_state:
            return immediate, pushed
        stale = replace(
            immediate,
            freshness=StateFreshness.STALE,
            freshness_reasons=immediate.freshness_reasons + (
                "superseded-by-later-pushed-state",
            ),
        )
        fresh = replace(
            pushed,
            freshness=StateFreshness.FRESH,
            freshness_reasons=pushed.freshness_reasons + (
                "newer-pushed-state-disagrees-with-immediate-read",
            ),
        )
        return stale, fresh

    def begin_state_nudge(
        self,
        observation: DialogueObservation,
        spec: PushedStateSpec,
    ) -> None:
        """Observe an eligible read-side nudge; this method never executes it."""

        if observation.direction is not Direction.OUT:
            raise ValueError("state nudge must be outgoing")
        if spec.nudge_namespace is not None and observation.report_namespace != spec.nudge_namespace:
            raise ValueError("state nudge namespace does not match specification")
        if spec.nudge_report_id is not None and observation.report_id != spec.nudge_report_id:
            raise ValueError("state nudge report ID does not match specification")
        if spec.nudge_channel_id is not None and observation.channel_id != spec.nudge_channel_id:
            raise ValueError("state nudge channel does not match specification")
        current = self._generation.get(observation.physical_id, observation.generation)
        if observation.generation < current:
            raise ValueError("cannot associate a nudge from an older generation")
        self._generation[observation.physical_id] = observation.generation
        self._nudges.append(_PendingNudge(observation, spec))

    @staticmethod
    def _state_matches(item: DialogueObservation, spec: PushedStateSpec) -> bool:
        return (
            item.direction is Direction.IN
            and item.report_namespace == spec.namespace
            and (spec.report_id is None or item.report_id == spec.report_id)
            and item.grammar == spec.grammar
            and (spec.channel_id is None or item.channel_id == spec.channel_id)
        )

    @staticmethod
    def _nudge_matches(
        pending: _PendingNudge,
        item: DialogueObservation,
    ) -> bool:
        nudge, spec = pending.observation, pending.spec
        return (
            nudge.source_id == item.source_id
            and nudge.physical_id == item.physical_id
            and nudge.transport == item.transport
            and nudge.generation == item.generation
            and 0 <= item.timestamp_ns - nudge.timestamp_ns
            <= spec.nudge_window_ms * 1_000_000
        )

    def observe_pushed_state(
        self,
        item: DialogueObservation,
        spec: PushedStateSpec,
        *,
        semantic_state_id: str,
        decoded_state: bytes | int | str,
        state_counter: int | None = None,
        controlled_action: DialogueObservation | None = None,
        subtype: int | None = None,
        transform: str | None = None,
        transform_source: bytes = b"",
        transformed_payload: bytes = b"",
    ) -> PushedStateRecord | None:
        """Classify one asynchronous state observation without request ownership."""

        if not semantic_state_id:
            raise ValueError("semantic_state_id is required")
        known_generation = self._generation.get(item.physical_id)
        if known_generation is None:
            self._generation[item.physical_id] = item.generation
            current = item.generation
        else:
            current = known_generation
        if item.generation < current:
            return PushedStateRecord(
                observation=item,
                semantic_state_id=semantic_state_id,
                decoded_state=decoded_state,
                freshness=StateFreshness.STALE,
                freshness_reasons=("older-connection-generation",),
                accepted=False,
                state_counter=state_counter,
                subtype=subtype, transform=transform,
                transform_source=transform_source,
                transformed_payload=transformed_payload,
            )
        if item.generation > current:
            self._generation[item.physical_id] = item.generation
            self._nudges = [
                pending for pending in self._nudges
                if pending.observation.physical_id != item.physical_id
                or pending.observation.generation >= item.generation
            ]
            self._state_history = {
                key: value for key, value in self._state_history.items()
                if value.observation.physical_id != item.physical_id
                or value.observation.generation >= item.generation
            }
        if not self._state_matches(item, spec):
            return None

        key = (
            item.source_id, item.physical_id, item.transport, item.channel_id,
            item.report_namespace, item.report_id, item.grammar,
            item.generation, semantic_state_id,
        )
        previous = self._state_history.get(key)
        nudges = [
            pending for pending in self._nudges
            if pending.spec == spec and self._nudge_matches(pending, item)
        ]
        nudge = nudges[0].observation if len(nudges) == 1 else None
        if len(nudges) == 1:
            self._nudges.remove(nudges[0])

        periodic_index = 1
        periodic = False
        if previous is not None and spec.periodic_max_gap_ms is not None:
            gap = item.timestamp_ns - previous.observation.timestamp_ns
            periodic = 0 <= gap <= spec.periodic_max_gap_ms * 1_000_000
            if periodic:
                periodic_index = previous.periodic_index + 1

        reasons: list[str] = []
        association = PushedStateAssociation.UNSOLICITED
        if nudge is not None:
            association = PushedStateAssociation.NUDGED
            reasons.append("nudge-precedes-asynchronous-push")
        if periodic:
            reasons.append("known-periodic-push-cadence")
        if previous is not None and state_counter is not None:
            previous_counter = previous.state_counter
            if previous_counter is not None and state_counter > previous_counter:
                reasons.append("monotonic-state-counter")
        if (
            controlled_action is not None
            and previous is not None
            and controlled_action.physical_id == item.physical_id
            and controlled_action.generation == item.generation
            and previous.observation.timestamp_ns <= controlled_action.timestamp_ns <= item.timestamp_ns
            and previous.decoded_state != decoded_state
        ):
            reasons.append("state-changed-after-controlled-action")

        freshness = StateFreshness.FRESH if reasons else StateFreshness.UNKNOWN
        record = PushedStateRecord(
            observation=item,
            semantic_state_id=semantic_state_id,
            decoded_state=decoded_state,
            freshness=freshness,
            freshness_reasons=tuple(reasons),
            association=association,
            nudge=nudge,
            accepted=True,
            periodic_index=periodic_index,
            state_counter=state_counter,
            subtype=subtype,
            transform=transform,
            transform_source=transform_source,
            transformed_payload=transformed_payload,
            controlled_action=controlled_action,
        )
        self._state_history[key] = record
        return record

    @staticmethod
    def _burst_result(
        pending: _PendingBurst,
        reason: BurstCompletionReason,
        *,
        completion_timestamp_ns: int | None = None,
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
            completion_timestamp_ns=completion_timestamp_ns,
            quiet_interval_ns=(
                pending.spec.quiet_interval_ms * 1_000_000
                if reason is BurstCompletionReason.QUIET_INTERVAL else None
            ),
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
                completed.append(self._burst_result(
                    pending,
                    reason,
                    completion_timestamp_ns=(
                        deadline_at if reason is BurstCompletionReason.DEADLINE else quiet_at
                    ),
                ))
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
            completed.append(self._burst_result(
                pending,
                BurstCompletionReason.MAX_RESPONSES,
                completion_timestamp_ns=item.timestamp_ns,
            ))
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
        self._nudges = [
            pending for pending in self._nudges
            if pending.observation.physical_id != physical_id
            or pending.observation.generation >= generation
        ]
        self._state_history = {
            key: value for key, value in self._state_history.items()
            if value.observation.physical_id != physical_id
            or value.observation.generation >= generation
        }
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
