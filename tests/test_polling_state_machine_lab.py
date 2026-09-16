from __future__ import annotations

from pathlib import Path

from mouse_control.polling_replay import (
    GenericPollingReplayAdapter,
    infer_polling_replay_grammar,
)


RATES = (1000, 500, 250, 125)
RAW = {1000: 1, 500: 2, 250: 4, 125: 8}


def event(direction, data):
    return {
        "direction": direction,
        "data_hex": bytes(data).hex(),
        "relative_us": 0.0,
    }


def host_profile():
    demonstrations = []
    for rate in RATES:
        raw = RAW[rate]
        demonstrations.append(
            {
                "target_hz": rate,
                "anchor_hz": 500 if rate == 1000 else 1000,
                "start_control": "host",
                "end_control": "host",
                "events": [
                    event("tx", b"\x11\x01"),
                    event("rx", b"\x21\x02"),
                    event("tx", bytes((0x12, raw))),
                    event("rx", b"\x22\x00"),
                    event("tx", b"\x13\x00"),
                    event("rx", bytes((0x23, raw))),
                ],
            }
        )
    return {
        "schema_version": 1,
        "profile_kind": "polling-host-demonstrations",
        "write_authorized": False,
        "prerequisite_control": "host",
        "resulting_control": "host",
        "demonstrations": demonstrations,
    }


def onboard_profile():
    demonstrations = []
    for rate in RATES:
        raw = RAW[rate]
        demonstrations.append(
            {
                "target_hz": rate,
                "events": [
                    event("tx", b"\x10\x01"),
                    event("rx", b"\x20\x01"),
                    event("tx", b"\x10\x02"),
                    event("rx", b"\x20\x02"),
                    event("tx", b"\x10\x03"),
                    event("rx", b"\x20\x03"),
                    event("tx", bytes((0x10, 0x04, raw))),
                    event("rx", b"\x20\x04"),
                    event("tx", b"\x10\x05"),
                    event("rx", bytes((0x20, 0x05, raw))),
                ],
            }
        )
    return {
        "schema_version": 1,
        "profile_kind": "polling-demonstrations",
        "write_authorized": False,
        "demonstrations": demonstrations,
    }


class FakeIo:
    def __init__(self, _path):
        self.replies = []
        self.writes = []
        self.closed = False

    def queue(self, *packets):
        self.replies.extend(packets)

    def write(self, packet):
        self.writes.append(bytes(packet))

    def read(self, _timeout):
        if not self.replies:
            return None
        return self.replies.pop(0)

    def close(self):
        self.closed = True


def test_host_corpus_infers_three_step_branch():
    grammar = infer_polling_replay_grammar(host_profile())
    assert len(grammar.steps) == 3
    assert grammar.write_step_index == 1
    assert grammar.read_step_index == 2
    assert grammar.raw_for_rate(250) == 4


def test_one_adapter_can_execute_onboard_then_host_grammar_on_same_io():
    onboard = infer_polling_replay_grammar(onboard_profile())
    host = infer_polling_replay_grammar(host_profile())
    fake = FakeIo(Path("/dev/null"))

    adapter = GenericPollingReplayAdapter(
        Path("/dev/null"),
        onboard,
        io_factory=lambda _path: fake,
        timeout=0.01,
    )
    try:
        fake.queue(
            b"\x20\x01",
            b"\x20\x02",
            b"\x20\x03",
            b"\x20\x04",
            b"\x20\x05\x02",
        )
        assert adapter.execute(500) == 500

        fake.queue(
            b"\x21\x02",
            b"\x22\x00",
            b"\x23\x04",
        )
        assert adapter.execute_with_grammar(host, 250) == 250
    finally:
        adapter.close()

    assert fake.closed
    assert fake.writes == [
        b"\x10\x01",
        b"\x10\x02",
        b"\x10\x03",
        b"\x10\x04\x02",
        b"\x10\x05",
        b"\x11\x01",
        b"\x12\x04",
        b"\x13\x00",
    ]


def test_execute_with_grammar_restores_default_grammar_after_call():
    onboard = infer_polling_replay_grammar(onboard_profile())
    host = infer_polling_replay_grammar(host_profile())
    fake = FakeIo(Path("/dev/null"))
    adapter = GenericPollingReplayAdapter(
        Path("/dev/null"),
        onboard,
        io_factory=lambda _path: fake,
        timeout=0.01,
    )
    try:
        fake.queue(b"\x21\x02", b"\x22\x00", b"\x23\x04")
        assert adapter.execute_with_grammar(host, 250) == 250
        assert adapter.grammar is onboard
    finally:
        adapter.close()
