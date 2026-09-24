# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from mouse_control.polling_replay import (
    GenericPollingReplayAdapter,
    PollingReplayError,
    infer_polling_replay_grammar,
)


RATES = (1000, 500, 250, 125)
RAW = {1000: 1, 500: 2, 250: 4, 125: 8}


def event(direction, data):
    return {"direction": direction, "data_hex": bytes(data).hex(), "relative_us": 0.0}


def profile():
    demonstrations = []
    for rate in RATES:
        raw = RAW[rate]
        events = [
            event("tx", b"\x10\x01"),
            event("rx", b"\x99\x77\x01"),  # unrelated async
            event("rx", b"\x20\x01"),
            event("tx", b"\x10\x02"),
            event("rx", b"\x20\x02"),
            event("tx", b"\x10\x03"),
            event("rx", b"\x20\x03"),
            event("tx", bytes((0x10, 0x04, raw))),
            event("rx", b"\x20\x04"),
            event("tx", b"\x10\x05"),
            event("rx", bytes((0x20, 0x05, raw))),
        ]
        demonstrations.append(
            {
                "target_hz": rate,
                "events": events,
            }
        )
    return {
        "schema_version": 1,
        "profile_kind": "polling-demonstrations",
        "write_authorized": False,
        "demonstrations": demonstrations,
    }


def test_infers_multistep_polling_write_and_readback():
    grammar = infer_polling_replay_grammar(profile())
    assert len(grammar.steps) == 5
    assert grammar.write_step_index == 3
    assert grammar.read_step_index == 4
    assert grammar.raw_to_hz == {1: 1000, 2: 500, 4: 250, 8: 125}
    assert grammar.raw_for_rate(500) == 2


def test_replay_rejects_rate_not_in_teacher_corpus():
    grammar = infer_polling_replay_grammar(profile())
    with pytest.raises(PollingReplayError):
        grammar.raw_for_rate(333)


def test_inference_rejects_authorized_teacher_corpus():
    data = profile()
    data["write_authorized"] = True
    with pytest.raises(PollingReplayError):
        infer_polling_replay_grammar(data)


class FakeIo:
    def __init__(self, _path, replies):
        self.replies = list(replies)
        self.writes = []
        self.closed = False

    def write(self, packet):
        self.writes.append(bytes(packet))

    def read(self, _timeout):
        if not self.replies:
            return None
        return self.replies.pop(0)

    def close(self):
        self.closed = True


def test_generic_adapter_renders_target_and_ignores_unrelated_packets():
    grammar = infer_polling_replay_grammar(profile())
    fake = FakeIo(
        Path("/dev/null"),
        replies=[
            b"\xff", b"\x20\x01",
            b"\x20\x02",
            b"\x20\x03",
            b"\x20\x04",
            b"\x20\x05\x02",
        ],
    )
    adapter = GenericPollingReplayAdapter(
        Path("/dev/null"),
        grammar,
        io_factory=lambda _path: fake,
        timeout=0.01,
    )
    try:
        assert adapter.execute(500) == 500
    finally:
        adapter.close()

    assert fake.writes == [
        b"\x10\x01",
        b"\x10\x02",
        b"\x10\x03",
        b"\x10\x04\x02",
        b"\x10\x05",
    ]
    assert fake.closed


def test_inference_rejects_ambiguous_second_semantic_write_step():
    data = profile()
    for demo in data["demonstrations"]:
        rate = demo["target_hz"]
        raw = RAW[rate]
        # Make the otherwise constant third request also encode polling rate.
        tx_seen = 0
        for item in demo["events"]:
            if item["direction"] == "tx":
                tx_seen += 1
                if tx_seen == 3:
                    item["data_hex"] = bytes((0x10, 0x03, raw)).hex()
                    break
    with pytest.raises(PollingReplayError):
        infer_polling_replay_grammar(data)
