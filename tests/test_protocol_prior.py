from __future__ import annotations

import json

from mouse_control.evidence_graph import EvidenceGraph
from mouse_control.protocol_prior import import_protocol_family_prior, import_repertoire_priors
from mouse_control.protocol_repertoire import DEFAULT_REPERTOIRE


def family(name: str):
    return next(item for item in DEFAULT_REPERTOIRE if item.name == name)


def test_public_family_import_stays_hypothesis_only() -> None:
    graph = EvidenceGraph()
    imported = import_protocol_family_prior(graph, family("wlmouse-beastx-pages"))
    explanation = graph.explain(imported.operation_ids[0])
    assert [row["kind"] for row in explanation][-2:] == ["hypothesis", "hypothesis"]
    assert all(row["kind"] not in {"verification", "capability"} for row in explanation)
    operation = json.loads(explanation[-1]["claim"])
    assert operation["page"] == 0x18
    assert operation["write_command"] == 0x06
    assert operation["safety"] == "reversible"


def test_prior_import_is_content_addressed_and_idempotent() -> None:
    graph = EvidenceGraph()
    first = import_protocol_family_prior(graph, family("darmoshark-dms"))
    second = import_protocol_family_prior(graph, family("darmoshark-dms"))
    assert first == second
    assert set(first.evidence_ids).issubset(graph.valid_ids)


def test_source_invalidation_revokes_all_derived_prior_nodes() -> None:
    graph = EvidenceGraph()
    imported = import_protocol_family_prior(graph, family("darmoshark-dms"))
    graph.invalidate(imported.source_ids[0], "upstream evidence withdrawn")
    assert imported.family_id not in graph.valid_ids
    assert all(identifier not in graph.valid_ids for identifier in imported.operation_ids)


def test_repertoire_import_keeps_hidpp_public_extended_features_as_hypotheses() -> None:
    graph = EvidenceGraph()
    imported = import_repertoire_priors(graph, (family("hidpp2"),))
    assert len(imported) == 1
    claims = [json.loads(row["claim"]) for identifier in imported[0].operation_ids
              for row in graph.explain(identifier) if row["id"] == identifier]
    pages = {claim["page"] for claim in claims}
    assert {0x2201, 0x2202, 0x8060, 0x8061}.issubset(pages)
