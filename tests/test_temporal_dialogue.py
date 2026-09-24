# SPDX-License-Identifier: AGPL-3.0-or-later
from mouse_control.temporal_dialogue import (
    BurstCompletionReason, BurstDialogueSpec, DialogueAssembler, DialogueKind,
    DialogueObservation, Direction, PushedStateAssociation, PushedStateSpec,
    StateFreshness,
)


def obs(
    seq, ms, direction, payload, *, generation=1, tag=None, grammar="rpc",
    status=None, namespace="feature", report_id=7, channel="hidraw-if2",
):
    return DialogueObservation(
        source_id="device-a", physical_id="physical-a", channel_id=channel,
        transport="hid", direction=direction, report_namespace=namespace,
        report_id=report_id, generation=generation, timestamp_ns=ms * 1_000_000,
        sequence=seq, payload=payload, transaction_tag=tag, grammar=grammar,
        status=status,
    )


def test_request_unrelated_event_delayed_reply() -> None:
    assembler = DialogueAssembler(window_ms=100)
    assert assembler.add(obs(1, 0, Direction.OUT, b"query", tag=4)) == ()
    event = assembler.add(obs(2, 10, Direction.IN, b"button", grammar="event"))
    reply = assembler.add(obs(3, 70, Direction.IN, b"reply", tag=4))
    assert event[0].kind is DialogueKind.UNSOLICITED_EVENT
    assert reply[0].kind is DialogueKind.RESPONSE
    assert reply[0].request.sequence == 1


def test_selector_busy_poll_reply_forms_one_dialogue() -> None:
    assembler = DialogueAssembler(window_ms=200)
    assembler.add(obs(1, 0, Direction.OUT, b"selector", tag=9))
    busy = assembler.add(obs(2, 10, Direction.IN, b"busy", tag=9, status="busy"))
    poll = assembler.add(obs(3, 20, Direction.OUT, b"poll", tag=9))
    reply = assembler.add(obs(4, 30, Direction.IN, b"reply", tag=9, status="ok"))
    assert busy[0].kind is DialogueKind.BUSY_PENDING
    assert poll[0].kind is DialogueKind.RESPONSE_POLL
    assert reply[0].kind is DialogueKind.RESPONSE
    assert reply[0].request.sequence == 1


def test_overlapping_transactions_use_tags() -> None:
    assembler = DialogueAssembler()
    assembler.add(obs(1, 0, Direction.OUT, b"a", tag=1))
    assembler.add(obs(2, 1, Direction.OUT, b"b", tag=2))
    second = assembler.add(obs(3, 2, Direction.IN, b"B", tag=2))
    first = assembler.add(obs(4, 3, Direction.IN, b"A", tag=1))
    assert second[0].request.sequence == 2
    assert first[0].request.sequence == 1


def test_without_tags_grammar_can_separate_but_ambiguity_is_retained() -> None:
    assembler = DialogueAssembler()
    assembler.add(obs(1, 0, Direction.OUT, b"a", grammar="dpi"))
    assembler.add(obs(2, 1, Direction.OUT, b"b", grammar="rate"))
    match = assembler.add(obs(3, 2, Direction.IN, b"ok", grammar="rate"))
    assert match[0].request.sequence == 2

    ambiguous = DialogueAssembler()
    ambiguous.add(obs(1, 0, Direction.OUT, b"a"))
    ambiguous.add(obs(2, 1, Direction.OUT, b"b"))
    result = ambiguous.add(obs(3, 2, Direction.IN, b"ok"))
    assert result[0].kind is DialogueKind.UNRELATED
    assert result[0].ambiguous


def test_reconnect_rejects_stale_reply_and_flushes_pending() -> None:
    assembler = DialogueAssembler()
    assembler.add(obs(1, 0, Direction.OUT, b"query", tag=1))
    stale = assembler.add(obs(2, 5, Direction.IN, b"old", generation=0, tag=1))
    flushed = assembler.advance_generation("physical-a", 2)
    assert stale[0].kind is DialogueKind.STALE_RESPONSE
    assert flushed[0].kind is DialogueKind.RECONNECT_SNAPSHOT


def test_write_echo_and_physical_event_are_not_query_replies() -> None:
    assembler = DialogueAssembler()
    assembler.add(obs(1, 0, Direction.OUT, b"set", tag=8))
    echo = assembler.add(obs(2, 1, Direction.IN, b"set", tag=8))
    event = assembler.add(obs(3, 2, Direction.IN, b"dpi", grammar="physical_action"))
    assert echo[0].kind is DialogueKind.ECHO
    assert event[0].kind is DialogueKind.PHYSICAL_ACTION_EVENT


def burst_spec(*, quiet=10, deadline=50, maximum=8):
    return BurstDialogueSpec(
        request_namespace="mouse-command", response_namespace="mouse-telemetry",
        request_report_id=0x20, response_report_id=0x21,
        quiet_interval_ms=quiet, absolute_deadline_ms=deadline,
        max_responses=maximum, response_grammar="telemetry-burst",
    )


def burst_request(*, generation=1):
    return obs(
        10, 0, Direction.OUT, b"query", generation=generation, tag=3,
        grammar="telemetry-burst", namespace="mouse-command", report_id=0x20,
    )


def burst_response(
    seq, ms, payload=b"record", *, generation=1,
    namespace="mouse-telemetry", report_id=0x21,
    grammar="telemetry-burst", channel="hidraw-if2",
):
    return obs(
        seq, ms, Direction.IN, payload, generation=generation, tag=3,
        grammar=grammar, namespace=namespace, report_id=report_id, channel=channel,
    )


def test_single_and_multi_response_bursts_complete_after_quiet_interval() -> None:
    single = DialogueAssembler()
    single.begin_burst(burst_request(), burst_spec())
    assert single.observe_burst(burst_response(11, 5)) == ()
    completed = single.advance_time(15_000_000)
    assert completed[0].completion_reason is BurstCompletionReason.QUIET_INTERVAL
    assert [item.sequence for item in completed[0].responses] == [11]

    multi = DialogueAssembler()
    multi.begin_burst(burst_request(), burst_spec())
    for sequence, timestamp in ((11, 5), (12, 8), (13, 12)):
        assert multi.observe_burst(burst_response(sequence, timestamp)) == ()
    completed = multi.advance_time(22_000_000)
    assert [item.sequence for item in completed[0].responses] == [11, 12, 13]
    assert completed[0].last_response_timestamp_ns == 12_000_000


def test_burst_deadline_and_maximum_count_are_hard_bounds() -> None:
    deadline = DialogueAssembler()
    deadline.begin_burst(burst_request(), burst_spec(quiet=10, deadline=25, maximum=20))
    for sequence, timestamp in ((11, 8), (12, 16), (13, 24)):
        assert deadline.observe_burst(burst_response(sequence, timestamp)) == ()
    completed = deadline.advance_time(25_000_000)
    assert completed[0].completion_reason is BurstCompletionReason.DEADLINE
    assert completed[0].response_count == 3

    maximum = DialogueAssembler()
    maximum.begin_burst(burst_request(), burst_spec(maximum=2))
    assert maximum.observe_burst(burst_response(11, 1)) == ()
    completed = maximum.observe_burst(burst_response(12, 2))
    assert completed[0].completion_reason is BurstCompletionReason.MAX_RESPONSES
    assert completed[0].response_count == 2


def test_wrong_namespace_unrelated_input_and_late_response_are_excluded() -> None:
    assembler = DialogueAssembler()
    assembler.begin_burst(burst_request(), burst_spec(quiet=10, deadline=30))
    wrong = burst_response(11, 2, namespace="dongle-telemetry")
    event = obs(
        12, 4, Direction.IN, b"movement", grammar="event",
        namespace="mouse-telemetry", report_id=0x21,
    )
    assert assembler.observe_burst(wrong) == ()
    assert assembler.observe_burst(event) == ()
    assert assembler.observe_burst(burst_response(13, 5, channel="hidraw-if3")) == ()
    empty = assembler.advance_time(10_000_000)
    assert empty[0].response_count == 0

    late = DialogueAssembler()
    late.begin_burst(burst_request(), burst_spec(quiet=10, deadline=25, maximum=20))
    for sequence, timestamp in ((11, 8), (12, 16), (13, 24)):
        late.observe_burst(burst_response(sequence, timestamp))
    completed = late.observe_burst(burst_response(14, 26))
    assert completed[0].completion_reason is BurstCompletionReason.DEADLINE
    assert [item.sequence for item in completed[0].responses] == [11, 12, 13]


def test_reconnect_invalidates_burst_and_new_generation_reply_cannot_join() -> None:
    assembler = DialogueAssembler()
    assembler.begin_burst(burst_request(), burst_spec())
    assembler.observe_burst(burst_response(11, 2))
    completed = assembler.observe_burst(burst_response(12, 5, generation=2))
    assert completed[0].completion_reason is BurstCompletionReason.GENERATION_CHANGE
    assert [item.sequence for item in completed[0].responses] == [11]


def test_zero_response_burst_and_invalid_limits_are_explicit() -> None:
    assembler = DialogueAssembler()
    assembler.begin_burst(burst_request(), burst_spec())
    completed = assembler.advance_time(10_000_000)
    assert completed[0].completion_reason is BurstCompletionReason.QUIET_INTERVAL
    assert completed[0].responses == ()

    explicit = DialogueAssembler()
    explicit.begin_burst(burst_request(), burst_spec())
    ended = explicit.end_burst(10)
    assert ended.completion_reason is BurstCompletionReason.EXPLICIT_END
    assert ended.responses == ()

    for kwargs in (
        {"quiet_interval_ms": 0, "absolute_deadline_ms": 50, "max_responses": 1},
        {"quiet_interval_ms": 10, "absolute_deadline_ms": 10, "max_responses": 1},
        {"quiet_interval_ms": 10, "absolute_deadline_ms": 50, "max_responses": 0},
    ):
        try:
            BurstDialogueSpec("request", "response", **kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid burst bounds must fail")


def pushed_spec():
    return PushedStateSpec(
        namespace="state-input", report_id=0x13, grammar="pushed-state",
        channel_id="hidraw-if2", periodic_max_gap_ms=100,
        nudge_window_ms=50, nudge_namespace="feature-nudge",
        nudge_report_id=0x05, nudge_channel_id="hidraw-if2",
    )


def pushed_obs(seq, ms, state, *, generation=1, subtype=0x1D):
    raw = bytes((subtype, state ^ 0xFF))
    return obs(
        seq, ms, Direction.IN, raw, generation=generation,
        grammar="pushed-state", namespace="state-input", report_id=0x13,
    )


def test_unsolicited_periodic_state_is_grouped_with_explicit_freshness() -> None:
    assembler = DialogueAssembler()
    first = assembler.observe_pushed_state(
        pushed_obs(20, 0, 1), pushed_spec(), semantic_state_id="dpi-stage",
        decoded_state=1, subtype=0x1D, transform="xor_ff",
    )
    second = assembler.observe_pushed_state(
        pushed_obs(21, 40, 1), pushed_spec(), semantic_state_id="dpi-stage",
        decoded_state=1, subtype=0x1D, transform="xor_ff",
    )
    assert first is not None and second is not None
    assert first.association is PushedStateAssociation.UNSOLICITED
    assert first.freshness is StateFreshness.UNKNOWN
    assert second.periodic_index == 2
    assert second.freshness is StateFreshness.FRESH
    assert "known-periodic-push-cadence" in second.freshness_reasons


def test_nudge_association_is_not_request_response_ownership() -> None:
    assembler = DialogueAssembler()
    nudge = obs(
        30, 0, Direction.OUT, b"read-side-nudge", grammar="state-nudge",
        namespace="feature-nudge", report_id=0x05,
    )
    assembler.begin_state_nudge(nudge, pushed_spec())
    pushed = assembler.observe_pushed_state(
        pushed_obs(31, 20, 2), pushed_spec(), semantic_state_id="dpi-stage",
        decoded_state=2, subtype=0x1D, transform="xor_ff",
    )
    assert pushed is not None
    assert pushed.association is PushedStateAssociation.NUDGED
    assert pushed.nudge is nudge
    assert pushed.freshness is StateFreshness.FRESH
    assert "nudge-precedes-asynchronous-push" in pushed.freshness_reasons


def test_stale_immediate_read_loses_to_fresh_delayed_push() -> None:
    assembler = DialogueAssembler()
    immediate_observation = obs(
        40, 1, Direction.IN, b"old", grammar="feature-read",
        namespace="feature", report_id=0x05,
    )
    immediate = assembler.state_read_evidence(
        immediate_observation, semantic_state_id="dpi-stage", decoded_state=1,
    )
    nudge = obs(
        39, 0, Direction.OUT, b"nudge", grammar="state-nudge",
        namespace="feature-nudge", report_id=0x05,
    )
    assembler.begin_state_nudge(nudge, pushed_spec())
    pushed = assembler.observe_pushed_state(
        pushed_obs(41, 20, 2), pushed_spec(), semantic_state_id="dpi-stage",
        decoded_state=2, subtype=0x1D, transform="xor_ff",
    )
    assert pushed is not None
    stale, fresh = assembler.prefer_later_pushed_state(immediate, pushed)
    assert stale.freshness is StateFreshness.STALE
    assert fresh.freshness is StateFreshness.FRESH
    assert stale.decoded_state == 1
    assert fresh.decoded_state == 2


def test_old_generation_push_is_rejected_and_unrelated_input_is_ignored() -> None:
    assembler = DialogueAssembler()
    accepted = assembler.observe_pushed_state(
        pushed_obs(50, 0, 1), pushed_spec(), semantic_state_id="dpi-stage",
        decoded_state=1,
    )
    assert accepted is not None and accepted.accepted
    assembler.advance_generation("physical-a", 2)
    stale = assembler.observe_pushed_state(
        pushed_obs(51, 5, 2, generation=1), pushed_spec(),
        semantic_state_id="dpi-stage", decoded_state=2,
    )
    assert stale is not None
    assert not stale.accepted
    assert stale.freshness is StateFreshness.STALE

    unrelated = obs(
        52, 6, Direction.IN, b"movement", generation=2, grammar="event",
        namespace="mouse-input", report_id=1,
    )
    assert assembler.observe_pushed_state(
        unrelated, pushed_spec(), semantic_state_id="dpi-stage", decoded_state=9,
    ) is None


def test_controlled_action_correlates_transition_without_write_authority() -> None:
    assembler = DialogueAssembler()
    assembler.observe_pushed_state(
        pushed_obs(60, 0, 1), pushed_spec(), semantic_state_id="dpi-stage",
        decoded_state=1,
    )
    action = obs(
        61, 10, Direction.IN, b"dpi-button", grammar="physical_action",
        namespace="mouse-input", report_id=1,
    )
    changed = assembler.observe_pushed_state(
        pushed_obs(62, 20, 2), pushed_spec(), semantic_state_id="dpi-stage",
        decoded_state=2, controlled_action=action,
    )
    assert changed is not None
    assert "state-changed-after-controlled-action" in changed.freshness_reasons
    assert changed.freshness is StateFreshness.FRESH
