from mouse_control.temporal_dialogue import (
    DialogueAssembler, DialogueKind, DialogueObservation, Direction,
)


def obs(seq, ms, direction, payload, *, generation=1, tag=None, grammar="rpc", status=None):
    return DialogueObservation(
        source_id="device-a", physical_id="physical-a", channel_id="hidraw-if2",
        transport="hid", direction=direction, report_namespace="feature",
        report_id=7, generation=generation, timestamp_ns=ms * 1_000_000,
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

