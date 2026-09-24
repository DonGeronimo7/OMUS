from __future__ import annotations
import binascii
import json
import pytest
from mouse_control.advanced_grammar import (align_models, infer_bitfield, infer_integrity,
                                            infer_repeated_records)
from mouse_control.active_fingerprint import FingerprintHypothesis, FingerprintProbe, ProbeRisk
from mouse_control.community_evidence import CommunityReport, ReportCategory, ingest_report
from mouse_control.discovery_pipeline import run_discovery_pipeline
from mouse_control.discovery_view import build_discovery_view
from mouse_control.evidence_graph import EvidenceGraph, EvidenceNode
from mouse_control.fast_recipe import FastRecipe
from mouse_control.grammar_inference import TraceExample
from mouse_control.interface_quarantine import InterfacePolicy, InterfaceRole, ResearchInterface
from mouse_control.protocol_prior import import_protocol_family_prior
from mouse_control.protocol_repertoire import DEFAULT_REPERTOIRE
from mouse_control.genome_catalog import compile_family_genome
from mouse_control.protocol_genome import ProofState, ingest_genome_device


def interface():
    return ResearchInterface("usb:1234:5678:serial", 2, "a" * 64, 7, 0xff00, 1, (5,),
                             frozenset({"input", "feature"}), "hid-generic",
                             InterfaceRole.CONFIGURATION, "session")


def policy(i): return InterfacePolicy(i.physical_identity, i.number, i.descriptor_sha256, i.role)
def family(name): return next(item for item in DEFAULT_REPERTOIRE if item.name == name)


def test_integrity_inference_is_bounded_and_retains_ambiguity() -> None:
    frames = []
    for body, eid in ((b"\x01\x02", "e1"), (b"\x10\x20", "e2")):
        frames.append((body + bytes((sum(body) & 0xff,)), eid))
    result = infer_integrity(tuple(frames), field_offset=2)
    # These examples intentionally fit both rules; ambiguity must be retained.
    assert {item.name for item in result} == {"sum8", "xor8"}
    crc_body = b"\x10\x20\x30"
    crc = binascii.crc32(crc_body).to_bytes(4, "little")
    assert [item.name for item in infer_integrity(((crc_body + crc, "e1"),
                                                   (b"abc" + binascii.crc32(b"abc").to_bytes(4, "little"), "e2")),
                                                  field_offset=3, width=4)] == ["crc32"]


def test_bitfield_nested_records_and_cross_model_alignment() -> None:
    field = infer_bitfield(((0b10100000, 0, "e1"), (0b10100100, 1, "e2"), (0b10101100, 3, "e3")))
    assert field is not None and field.mask == 0b00001100 and field.neighboring_constant_mask == 0b11110011
    records = infer_repeated_records(b"\x01a\x02b\x03c", evidence=("e",), allowed_widths=(2,))
    assert records[0].width == 2 and records[0].count == 3
    aligned = align_models(b"HEADaaTAIL", b"HEADbbbbTAIL")
    assert aligned.prefix == 4 and aligned.suffix == 4 and not aligned.equivalent


@pytest.mark.parametrize("name", ["hidpp2", "razer-rpc90", "lamzu-aurora-feature64",
                                   "darmoshark-dms", "rawm-variable-logical-records",
                                   "wlmouse-beastx-pages"])
def test_existing_repertoire_compiles_to_operation_specific_genome(name) -> None:
    graph = EvidenceGraph(); item = family(name)
    prior = import_protocol_family_prior(graph, item)
    device = compile_family_genome(item, evidence=prior.evidence_ids)
    ids = ingest_genome_device(graph, device)
    assert ids and all(identifier in graph.valid_ids for identifier in ids)
    assert all(op.state is not ProofState.WRITE_VERIFIED for op in device.operations)


def test_pipeline_runs_quarantine_genome_fingerprint_advice_and_grammar() -> None:
    graph = EvidenceGraph(); i = interface(); f = family("hidpp2")
    source = graph.add(EvidenceNode("source", "capture", "test"))
    result = run_discovery_pipeline(
        graph, interface=i, current_generation=7, policies=(policy(i),), families=(f,),
        hypotheses=(FingerprintHypothesis("hidpp", {"feature-11": True}, (source,)),
                    FingerprintHypothesis("other", {"feature-11": False}, (source,))),
        probes=(FingerprintProbe("feature-11", ProbeRisk.SAFE_READ, 1, (source,)),),
        examples=(TraceExample(b"\x05\x20\x03", b"\x05", 800, source),
                  TraceExample(b"\x05\x40\x06", b"\x05", 1600, source)))
    assert result.admission.admitted and result.fingerprint is not None
    assert result.advice and result.grammars and result.genome_ids
    assert [step.phase for step in result.trace][:4] == ["interface_quarantine", "protocol_genome", "active_fingerprint", "advice"]
    view = build_discovery_view(result)
    assert "Interface 2: admitted" in view.overview
    assert any("mutation: none" in row for row in view.decisions)


def test_pipeline_fails_closed_on_descriptor_change_before_corpus_work() -> None:
    graph = EvidenceGraph(); i = interface()
    changed = ResearchInterface(i.physical_identity, i.number, "b" * 64, i.generation,
                                i.usage_page, i.usage, i.report_ids, i.directions,
                                i.kernel_driver, i.role, i.endpoint_owner)
    result = run_discovery_pipeline(graph, interface=changed, current_generation=7,
                                    policies=(policy(i),), families=(family("hidpp2"),),
                                    hypotheses=(), probes=(), examples=())
    assert not result.admission.admitted and result.genome_ids == ()
    assert result.trace[0].decision == "refused"


def test_fast_recipe_is_small_and_invalidates_identity_firmware_descriptor_or_evidence() -> None:
    graph = EvidenceGraph(); eid = graph.add(EvidenceNode("verification", "readback", "test"))
    recipe = FastRecipe("device", 2, "a" * 64, "1.0", "query/set/readback", "u16le",
                        (800, 1600), "host-mode", "canonical-readback", "generation", (eid,))
    encoded = recipe.dumps(); assert len(encoded) < 1024 and FastRecipe.loads(encoded) == recipe
    assert recipe.validate(identity_fingerprint="device", descriptor_sha256="a" * 64,
                           firmware="1.0", valid_evidence=graph.valid_ids)[0]
    graph.invalidate(eid, "contradiction")
    ok, reasons = recipe.validate(identity_fingerprint="other", descriptor_sha256="b" * 64,
                                  firmware="2.0", valid_evidence=graph.valid_ids)
    assert not ok and len(reasons) == 4
    with pytest.raises((ValueError, TypeError, json.JSONDecodeError)):
        FastRecipe.loads('{"schema":99}')


def test_community_success_is_attributed_but_never_write_authority() -> None:
    graph = EvidenceGraph()
    report = CommunityReport(ReportCategory.COMMUNITY_OMUS_SUCCESS, "G502 X", 0x046d, 0xc099,
                             "1.0.4", "wireless", "dpi read", "unknown", "issue-123")
    identifier = ingest_report(graph, report)
    assert identifier in graph.valid_ids and not report.grants_write_authority
