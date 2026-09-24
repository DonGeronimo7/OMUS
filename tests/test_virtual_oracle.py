from __future__ import annotations

import json

import pytest

from mouse_control.evidence_graph import EvidenceGraph
from mouse_control.virtual_oracle import (
    OracleTransferKind, VirtualOracleError, VirtualPeripheralOracle,
    VirtualReportDefinition, VirtualReportKey,
)


FEATURE = VirtualReportKey(2, "feature", 0x05)
OUTPUT = VirtualReportKey(2, "output", 0x06)


def oracle() -> VirtualPeripheralOracle:
    return VirtualPeripheralOracle((
        VirtualReportDefinition(FEATURE, 8, readable=True, writable=True, write_updates_state=True),
        VirtualReportDefinition(OUTPUT, 4, readable=False, writable=True),
    ), initial_state={FEATURE: bytes.fromhex("01 00 00 00 00 00 00 00")})


def test_oracle_enforces_exact_reports_and_research_state_override_is_not_traffic() -> None:
    item = oracle()
    item.set_state(FEATURE, bytes.fromhex("02 00 00 00 00 00 00 00"))
    assert item.transactions == ()
    assert item.get_report(FEATURE)[0] == 2
    assert item.transactions[-1].kind is OracleTransferKind.GET_REPORT
    with pytest.raises(VirtualOracleError):
        item.set_report(FEATURE, b"short")
    with pytest.raises(VirtualOracleError):
        item.get_report(VirtualReportKey(9, "feature", 1))


def test_vendor_action_window_records_writes_and_can_mirror_known_virtual_state() -> None:
    item = oracle()
    with item.action("set_dpi", dpi=1600) as action_id:
        item.set_report(FEATURE, bytes.fromhex("01 40 06 00 00 00 00 00"))
        assert item.get_report(FEATURE)[1:3] == bytes.fromhex("40 06")
    records = item.action_transactions(action_id)
    assert [row.kind for row in records] == [OracleTransferKind.SET_REPORT, OracleTransferKind.GET_REPORT]
    assert all(row.action_id == action_id for row in records)


def test_differential_vendor_actions_identify_only_changed_write_bytes() -> None:
    item = oracle()
    with item.action("set_dpi", dpi=800) as first:
        item.set_report(FEATURE, bytes.fromhex("01 20 03 aa 00 00 00 00"))
        item.output_report(OUTPUT, bytes.fromhex("10 20 30 40"))
    with item.action("set_dpi", dpi=1600) as second:
        item.set_report(FEATURE, bytes.fromhex("01 40 06 aa 00 00 00 00"))
        item.output_report(OUTPUT, bytes.fromhex("10 20 30 40"))
    changes = item.differential_write_bytes((first, second))
    assert [(row.key, row.offset, row.values) for row in changes] == [
        (FEATURE, 1, (0x20, 0x40)),
        (FEATURE, 2, (0x03, 0x06)),
    ]


def test_unaligned_extra_write_is_not_compared_to_unrelated_packet() -> None:
    item = oracle()
    with item.action("a") as first:
        item.set_report(FEATURE, b"\x01" * 8)
        item.set_report(FEATURE, b"\x02" * 8)
    with item.action("b") as second:
        item.set_report(FEATURE, b"\x03" * 8)
    changes = item.differential_write_bytes((first, second))
    assert all(row.transfer_ordinal == 0 for row in changes)


def test_oracle_evidence_is_experiment_and_frame_only_and_invalidation_propagates() -> None:
    item = oracle()
    graph = EvidenceGraph()
    with item.action("set_dpi", dpi=1600) as action_id:
        item.set_report(FEATURE, bytes.fromhex("01 40 06 00 00 00 00 00"))
    evidence = item.emit_action_evidence(graph, action_id)
    rows = graph.explain(evidence[-1])
    assert [row["kind"] for row in rows] == ["experiment", "frame"]
    assert all(row["kind"] not in {"verification", "capability"} for row in rows)
    payload = json.loads(rows[-1]["claim"])
    assert payload["direction"] == "host_to_device"
    graph.invalidate(evidence[0], "counterfactual model was wrong")
    assert evidence[-1] not in graph.valid_ids


def test_actions_cannot_be_nested() -> None:
    item = oracle()
    with item.action("outer"):
        with pytest.raises(VirtualOracleError):
            with item.action("inner"):
                pass
