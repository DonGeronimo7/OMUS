from dataclasses import replace
import json

import pytest

from mouse_control.evidence_graph import EvidenceGraph, EvidenceNode
from mouse_control.experiment_authority import StorageEffect
from mouse_control.kernel_knowledge import mine_source
from mouse_control.peripheral_ir import (CapabilityIR, CapabilityKind, PhysicalIdentity,
    InterfaceIdentity, PeripheralIR, ValueDomain, compile_proof_plan, patch_candidate_state)
from mouse_control.protocol_grammar import (CodecKind, CodecSpec, FieldBinding,
    ProtocolFamily, ProtocolFrameGrammar, SafetyClass, SemanticBehavior,
    TransactionSpec, TransactionStep, TransportKind)


def candidate():
    field = FieldBinding(SemanticBehavior.DPI_VALUE, 'state', 2, 2, CodecSpec(CodecKind.U16_BE))
    query = TransactionSpec('query', (TransactionStep('read', 'state', TransportKind.HID_FEATURE_GET),), SafetyClass.READ_ONLY)
    setter = TransactionSpec('set', (TransactionStep('write', 'state', TransportKind.HID_FEATURE_SET),), SafetyClass.REVERSIBLE)
    family = ProtocolFamily('synthetic', '1', (), transactions=(query, setter),
                            frame_grammars=(ProtocolFrameGrammar('state', 'feature', 5, 8),))
    cap = CapabilityIR(CapabilityKind.DPI, 'query', 'set', field, ValueDomain((1500, 1600)),
                       StorageEffect.VOLATILE, 'snapshot restore', 'measured CPI', 'matched reply', ('source',))
    return PeripheralIR(PhysicalIdentity(3, 1, 2, 'model', 'unique', 'fw1'),
                        InterfaceIdentity(2, 'a'*64), family, (cap,))


def test_compiles_differential_plan_without_authority():
    plan = compile_proof_plan(candidate(), CapabilityKind.DPI, 1500, evidence_ids=frozenset({'source'}))
    assert not plan.blockers
    assert plan.target == 1600
    assert not plan.runtime_write_authorized
    assert plan.steps[-1] == 'verify restored state and behavior'


@pytest.mark.parametrize('change,blocker', [
    ({'storage': StorageEffect.UNKNOWN}, 'volatile'),
    ({'storage': StorageEffect.PERSISTENT}, 'volatile'),
    ({'rollback': ''}, 'rollback'), ({'verification': ''}, 'verification'),
    ({'correlation': ''}, 'correlation'), ({'setter': 'missing'}, 'setter'),
    ({'query': 'missing'}, 'query'), ({'evidence': ('missing',)}, 'source')])
def test_unresolved_candidates_have_precise_blockers(change, blocker):
    ir = candidate()
    ir = replace(ir, capabilities=(replace(ir.capabilities[0], **change),))
    plan = compile_proof_plan(ir, CapabilityKind.DPI, 1500, evidence_ids=frozenset({'source'}))
    assert any(blocker in item for item in plan.blockers)
    assert not plan.runtime_write_authorized


def test_dangerous_transaction_is_never_a_reversible_candidate():
    ir = candidate()
    family = replace(ir.family, transactions=(ir.family.transactions[0], replace(ir.family.transactions[1], safety=SafetyClass.DANGEROUS)))
    assert 'reversible setter unresolved' in compile_proof_plan(replace(ir, family=family), CapabilityKind.DPI, 1500, evidence_ids=frozenset({'source'})).blockers


def test_shared_blob_preserves_every_untargeted_byte():
    field = candidate().capabilities[0].field
    baseline = bytes.fromhex('059905dcff010203')
    patched = patch_candidate_state(baseline, field, 1600, ValueDomain((1500,1600)), report_size=8)
    assert patched == bytes.fromhex('05990640ff010203')
    assert baseline == bytes.fromhex('059905dcff010203')


def test_shared_bitfield_preserves_unrelated_bits():
    field = FieldBinding(SemanticBehavior.REPORT_RATE_HZ, 'state', 1, 1, CodecSpec(CodecKind.BITFIELD, mask=3, shift=2))
    assert patch_candidate_state(b'\x01\xf3', field, 2, ValueDomain((1,2,3)), report_size=2) == b'\x01\xfb'


def test_polling_enum_proposal_uses_sourced_encoding():
    field = FieldBinding(SemanticBehavior.REPORT_RATE_HZ, 'state', 1, 1,
                         CodecSpec(CodecKind.ENUM, values={1:1000,2:500,4:250,8:125}))
    assert patch_candidate_state(b'\xaa\x01\xff', field, 500, ValueDomain((125,250,500,1000)), report_size=3) == b'\xaa\x02\xff'


def test_ambiguous_inverse_refused():
    field = FieldBinding(SemanticBehavior.DPI_VALUE, 'state', 0, 1, CodecSpec(CodecKind.ENUM, values={1:100,2:100}))
    with pytest.raises(ValueError, match='non-injective'):
        patch_candidate_state(b'\x01', field, 100, ValueDomain((100,)), report_size=1)


@pytest.mark.parametrize('baseline,size,value', [(b'123',8,1500),(b'12345678',8,1700)])
def test_incomplete_snapshot_and_out_of_domain_refused(baseline,size,value):
    with pytest.raises(ValueError):
        patch_candidate_state(baseline,candidate().capabilities[0].field,value,ValueDomain((1500,1600)),report_size=size)


@pytest.mark.parametrize('kwargs', [{},{'values':(0,)},{'values':(True,)},{'values':(1,1)},
    {'minimum':1},{'minimum':1,'maximum':4,'step':2}, {'values':(1,), 'minimum':1,'maximum':2,'step':1}])
def test_invalid_domains_refused(kwargs):
    with pytest.raises(ValueError): ValueDomain(**kwargs)


def test_range_neighbor_is_bounded_without_enumerating_domain():
    domain = ValueDomain(minimum=100,maximum=10**12,step=100)
    assert domain.neighbor(100) == 200
    assert domain.neighbor(1000) == 900
    assert not domain.contains(True)


def test_graph_roundtrip_explanation_and_transitive_invalidation(tmp_path):
    graph = EvidenceGraph()
    source = graph.add(EvidenceNode('source','pinned revision','upstream'))
    read = graph.add(EvidenceNode('state','baseline read','capture',(source,)))
    write = graph.add(EvidenceNode('hypothesis','candidate setter','analysis',(read,)))
    polling = graph.add(EvidenceNode('state','independent polling','capture'))
    path=tmp_path/'proof.json'
    graph.save(path)
    with pytest.raises(FileExistsError): graph.save(path)
    restored = EvidenceGraph.loads(path.read_text())
    assert [r['id'] for r in restored.explain(write)] == [source,read,write]
    restored.invalidate(read,'readback disagreement')
    assert restored.valid_ids == {source,polling}
    assert EvidenceGraph.loads(restored.dumps()).valid_ids == {source,polling}
    new = restored.add(EvidenceNode('capability','later claim','analysis',(write,)))
    assert new not in restored.valid_ids


def test_failed_write_can_be_invalidated_without_erasing_read():
    graph = EvidenceGraph()
    read=graph.add(EvidenceNode('state','read established','capture'))
    write=graph.add(EvidenceNode('experiment','failed write','capture',(read,)))
    graph.invalidate(write,'verification failed')
    assert graph.valid_ids == {read}


@pytest.mark.parametrize('mutation',['claim','schema','parent','duplicate','type'])
def test_corrupt_graph_rejected(mutation):
    graph=EvidenceGraph();graph.add(EvidenceNode('source','a','b'))
    doc=json.loads(graph.dumps())
    if mutation=='claim': doc['nodes'][0]['claim']='tampered'
    if mutation=='schema': doc['schema']=True
    if mutation=='parent': doc['nodes'][0]['parents']=['missing']
    if mutation=='duplicate': doc['nodes'].append(doc['nodes'][0])
    if mutation=='type': doc['nodes'][0]['parents']='bad'
    with pytest.raises(ValueError): EvidenceGraph.loads(json.dumps(doc))


def test_graph_unresolved_dependency_refused():
    with pytest.raises(ValueError): EvidenceGraph().add(EvidenceNode('state','x','y',('missing',)))


def test_kernel_miner_masks_comments_and_strings_preserves_locations():
    graph=mine_source('/* HID_REQ_SET_REPORT */\n"HID_INPUT_REPORT";\nhid_hw_raw_request(dev, HID_REQ_GET_REPORT);\n',
                      path='drivers/hid/example.c',revision='a'*40)
    rows=json.loads(graph.dumps())['nodes']
    claims=[json.loads(r['claim']) for r in rows if r['kind']=='kernel_fact']
    assert claims == [{'line':3,'token':'HID_REQ_GET_REPORT'},{'line':3,'token':'hid_hw_raw_request'}]
    assert all('#L3' in r['source'] for r in rows if r['kind']=='kernel_fact')


@pytest.mark.parametrize('path,revision',[('../bad','a'*40),('/drivers/hid/a.c','a'*40),('drivers/hid/../../a','a'*40),('drivers/hid/a.c','main')])
def test_kernel_miner_requires_pinned_scoped_source(path,revision):
    with pytest.raises(ValueError): mine_source('',path=path,revision=revision)


def test_miner_extracts_enum_literals_without_guessing_expressions():
    graph=mine_source('enum numbers { A=0x06, B=A+1, C, D=43, E=010, F=1 << 3 };',
                      path='drivers/hid/example.h',revision='a'*40)
    rows=json.loads(graph.dumps())['nodes']
    facts=[json.loads(r['claim']) for r in rows if r['kind']=='kernel_fact']
    assert facts == [{'enum_member':'A','line':1,'value':6}, {'enum_member':'D','line':1,'value':43}]


def test_checked_in_kernel_corpus_has_intact_dependencies():
    from pathlib import Path
    for path in (Path(__file__).parents[1]/'docs/discovery-corpus').glob('*.evidence.json'):
        graph=EvidenceGraph.loads(path.read_text())
        assert len(graph.valid_ids)>1
        assert graph.dumps() == path.read_text().strip()
