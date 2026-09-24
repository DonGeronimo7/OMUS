# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations
import pytest
import hashlib
from mouse_control.discovery_orchestrator import analyze_unknown_interface
from mouse_control.evidence_graph import EvidenceGraph, EvidenceNode
from mouse_control.grammar_inference import FieldKind, TraceExample, infer_grammars
from mouse_control.interface_quarantine import (
    InterfaceAccess, InterfacePolicy, InterfaceRole, ResearchInterface, admit_interface,
)
from mouse_control.protocol_genome import (
    GenomeDevice, GenomeOperation, ProofState, ingest_genome_device,
)
from mouse_control.hid_bpf_adapter import HidBpfAdapter
from mouse_control.hid_bpf_observation import HidBpfHook, HidBpfObservation, HidBpfStage
from mouse_control.oracle_transport import OracleTeachingAdapter, TeachingTransfer
from mouse_control.virtual_oracle import (
    OracleTransferKind, VirtualPeripheralOracle, VirtualReportDefinition, VirtualReportKey,
)
from mouse_control.firmware_proof import FirmwareRecipe, dry_run_firmware, inspect_firmware


def iface(*, number=2, descriptor="a" * 64, generation=7,
          role=InterfaceRole.CONFIGURATION, directions=frozenset({"input", "feature"}),
          physical="usb:1234:5678:serial"):
    return ResearchInterface(physical, number, descriptor, generation, 0xff00, 1, (5,),
                             directions, "hid-generic", role, "discovery-session")


def policy(interface, *, mutate=False):
    return InterfacePolicy(interface.physical_identity, interface.number,
                           interface.descriptor_sha256, interface.role, True, mutate)


def test_multi_interface_mouse_admits_only_exact_configuration_surface() -> None:
    config, normal = iface(), iface(number=0, role=InterfaceRole.NORMAL_INPUT)
    policies = (policy(config, mutate=True),)
    assert admit_interface(config, InterfaceAccess.MUTATE, current_generation=7,
                           policies=policies).admitted
    denied = admit_interface(normal, InterfaceAccess.MUTATE, current_generation=7,
                             policies=policies)
    assert not denied.admitted
    assert "normal-input or unknown interfaces are observation-only" in denied.reasons


def test_receiver_layout_descriptor_staleness_and_reenumeration_are_refused() -> None:
    original = iface(role=InterfaceRole.RECEIVER)
    admitted = policy(original, mutate=True)
    changed = iface(descriptor="b" * 64, role=InterfaceRole.RECEIVER)
    assert "descriptor or role differs from admitted interface" in admit_interface(
        changed, InterfaceAccess.READ, current_generation=7, policies=(admitted,)).reasons
    assert "stale interface generation" in admit_interface(
        original, InterfaceAccess.READ, current_generation=8, policies=(admitted,)).reasons


def test_unknown_and_bootloader_interfaces_never_receive_generic_mutation_admission() -> None:
    unknown = iface(role=InterfaceRole.UNKNOWN, directions=frozenset({"output"}))
    assert not admit_interface(unknown, InterfaceAccess.MUTATE, current_generation=7,
                               policies=(policy(unknown, mutate=True),)).admitted
    boot = iface(role=InterfaceRole.BOOTLOADER, directions=frozenset({"feature"}))
    denied = admit_interface(boot, InterfaceAccess.MUTATE, current_generation=7,
                             policies=(policy(boot, mutate=True),))
    assert not denied.admitted and "separate trust domain" in " ".join(denied.reasons)


def test_parser_finds_constant_and_u16_little_endian_value() -> None:
    examples = (
        TraceExample(b"\x05\x20\x03\xaa", b"\x05\x00", 800, "e1"),
        TraceExample(b"\x05\x40\x06\xaa", b"\x05\x00", 1600, "e2"),
    )
    grammars = infer_grammars(examples)
    assert len(grammars) == 1
    fields = grammars[0].fields
    assert any(item.kind is FieldKind.VALUE and item.encoding == "u16-little" for item in fields)
    assert {item.offset for item in fields if item.kind is FieldKind.CONSTANT} == {0, 3}


def test_parser_retains_endian_alternatives_when_bytes_are_symmetric() -> None:
    examples = (
        TraceExample(b"\x09\x01\x01", b"\x00", 257, "e1"),
        TraceExample(b"\x09\x02\x02", b"\x00", 514, "e2"),
    )
    grammars = infer_grammars(examples)
    assert {field.encoding for grammar in grammars for field in grammar.fields
            if field.kind is FieldKind.VALUE} == {"u16-little", "u16-big"}


def test_parser_detects_sum8_and_variable_length_and_rejects_insufficient_evidence() -> None:
    examples = (
        TraceExample(b"\x04\x10\x20\x34", b"\x00", None, "e1"),
        TraceExample(b"\x05\x10\x20\x30\x65", b"\x00", None, "e2"),
    )
    grammar = infer_grammars(examples)[0]
    assert grammar.request_size is None
    assert "packet sizes vary" in grammar.contradictions
    assert infer_grammars((examples[0],)) == ()


def test_protocol_genome_keeps_operation_proof_independent_and_invalidatable() -> None:
    graph = EvidenceGraph()
    source = graph.add(EvidenceNode("source", "reviewed public source", "fixture"))
    device = GenomeDevice("fixture-family", "fixture-model", "usb:1234:5678", "v1", "direct", (
        GenomeOperation("dpi", "page-1", ProofState.WRITE_CANDIDATE, (800, 1600),
                        ("host-mode",), "sum8", "volatile", "restore baseline",
                        ("not physically verified",), (source,)),
        GenomeOperation("polling", "page-2", ProofState.READ_PROVEN, (125, 500, 1000),
                        (), "none", "unknown", "", (), (source,)),
        GenomeOperation("firmware", "container-v1", ProofState.DISABLED, (), (), "sha256",
                        "persistent", "", ("writing disabled",), (source,)),
    ))
    ids = ingest_genome_device(graph, device)
    assert len(ids) == 4 and all(item in graph.valid_ids for item in ids)
    graph.invalidate(source, "source retracted")
    assert all(item not in graph.valid_ids for item in ids[1:])


def test_genome_refuses_missing_evidence() -> None:
    graph = EvidenceGraph()
    device = GenomeDevice("f", "m", "usb", "v1", "direct", (
        GenomeOperation("dpi", "g", ProofState.GRAMMAR_KNOWN, (), (), "", "", "", (), ("missing",)),
    ))
    with pytest.raises(ValueError):
        ingest_genome_device(graph, device)


def test_orchestrator_escalates_only_for_exact_missing_evidence() -> None:
    interface = iface()
    analysis = analyze_unknown_interface(interface, current_generation=7,
                                         policies=(policy(interface),), examples=())
    assert analysis.admission.admitted
    assert analysis.escalation is not None
    assert analysis.escalation.stage == "grammar_inference"
    stale = analyze_unknown_interface(interface, current_generation=8,
                                      policies=(policy(interface),), examples=())
    assert stale.escalation is not None and stale.escalation.stage == "interface_quarantine"


class FakeLoader:
    def __init__(self, rows=(), self_test=(True, True, True)):
        self.rows, self.result, self.detached = list(rows), self_test, False
    def attach(self, binding): return True
    def self_test(self): return self.result
    def drain(self):
        rows, self.rows = tuple(self.rows), []
        return rows
    def detach(self): self.detached = True


def observation(generation=7):
    return HidBpfObservation(1, generation, 3, 0x1234, 0x5678, 2, "a" * 64,
                             HidBpfHook.HW_REQUEST, HidBpfStage.BEFORE, 0, 3, 5, b"\x05")


def test_hid_bpf_adapter_falls_back_and_rejects_stale_generation() -> None:
    assert HidBpfAdapter(None, known_safe_kernel=True).attach(observation().binding_key).blockers
    loader = FakeLoader()
    adapter = HidBpfAdapter(loader, known_safe_kernel=True)
    assert adapter.attach(observation().binding_key).attached
    loader.rows = [observation(6), observation(7)]
    assert adapter.observations(current_generation=7) == (observation(7),)
    adapter.detach()
    assert loader.detached


def test_hid_bpf_adapter_requires_clean_buffer_and_self_test() -> None:
    assert "stale-buffer-not-empty" in HidBpfAdapter(
        FakeLoader((observation(),)), known_safe_kernel=True
    ).attach(observation().binding_key).blockers
    assert "request-source-unavailable" in HidBpfAdapter(
        FakeLoader(self_test=(True, False, True)), known_safe_kernel=True
    ).attach(observation().binding_key).blockers


def test_oracle_teaching_adapter_preserves_order_and_action_bracket() -> None:
    key = VirtualReportKey(2, "feature", 5)
    oracle = VirtualPeripheralOracle((VirtualReportDefinition(key, 3, True, True, True),))
    adapter = OracleTeachingAdapter(oracle)
    action_id = adapter.replay((
        TeachingTransfer(1, OracleTransferKind.GET_REPORT, key),
        TeachingTransfer(2, OracleTransferKind.SET_REPORT, key, b"\x05\x20\x03"),
    ), action="set DPI 800")
    assert len(oracle.action_transactions(action_id)) == 2
    assert oracle.get_state(key) == b"\x05\x20\x03"


def test_firmware_inspection_and_dry_run_accept_exact_artifact_but_never_enable_writes(tmp_path) -> None:
    image = b"RDFU" + bytes(range(32))
    path = tmp_path / "firmware.bin"
    path.write_bytes(image)
    graph = EvidenceGraph()
    eid = graph.add(EvidenceNode("source", "reviewed artifact", "fixture"))
    recipe = FirmwareRecipe("logitech-rdfu", "usb:046d:c539", "usb:046d:aaaa",
                            len(image), b"RDFU", hashlib.sha256(image).hexdigest(),
                            "hid-feature", "vendor release", (eid,))
    result = dry_run_firmware(inspect_firmware(path), recipe,
                              connected_runtime_identity="usb:046d:c539",
                              valid_evidence=graph.valid_ids)
    assert result.compatible and not result.writes_enabled and result.reasons == ()


def test_firmware_dry_run_explains_identity_hash_and_evidence_mismatch(tmp_path) -> None:
    path = tmp_path / "wrong.bin"
    path.write_bytes(b"NOPE")
    recipe = FirmwareRecipe("fixture", "usb:a", "", 8, b"GOOD", "0" * 64,
                            "hid", "", ("missing",))
    result = dry_run_firmware(inspect_firmware(path), recipe,
                              connected_runtime_identity="usb:b", valid_evidence=frozenset())
    assert not result.compatible and not result.writes_enabled
    assert len(result.reasons) == 7
