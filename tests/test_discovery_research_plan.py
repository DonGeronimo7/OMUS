from types import SimpleNamespace
from unittest.mock import Mock

from mouse_control.discovery_models import DiscoveredCapability, DiscoveryEvidence, DiscoveryResult, EvidenceLevel
from mouse_control.discovery_research import ResearchStatus, build_discovery_research_plan
from mouse_control.learned_operations import LearnedOperationState
from mouse_control.protocol_grammar import TransportKind, WriteScope


def _result(*, protocol=None, capabilities=None):
    device = SimpleNamespace(ambiguous=False)
    return DiscoveryResult(device=device, protocol=protocol, capabilities=capabilities or {})


def test_known_protocol_read_only_does_not_trigger_generic_deeper_learning():
    plan = build_discovery_research_plan(
        _result(protocol=SimpleNamespace(name="known")),
        (),
        learned_operation_store=Mock(),
        learned_polling_store=Mock(),
    )
    assert plan.dpi.status is ResearchStatus.KNOWN_READ_ONLY
    assert plan.polling.status is ResearchStatus.KNOWN_READ_ONLY
    assert plan.deeper_learning_recommended is False


def test_unknown_without_executable_probe_routes_to_deeper_learning():
    dpi_store = Mock()
    dpi_store.find_for_physical.return_value = None
    polling_store = Mock()
    polling_store.find_for_physical.return_value = None
    plan = build_discovery_research_plan(
        _result(), (),
        learned_operation_store=dpi_store,
        learned_polling_store=polling_store,
    )
    assert plan.dpi.status is ResearchStatus.NO_EVIDENCE
    assert plan.polling.status is ResearchStatus.NO_EVIDENCE
    assert plan.deeper_learning_recommended is True


def test_demonstrated_dpi_grammar_is_probe_ready_not_runtime_writable():
    op = SimpleNamespace(state=LearnedOperationState.DEMONSTRATED)
    dpi_store = Mock()
    dpi_store.find_for_physical.return_value = ("path", op)
    polling_store = Mock()
    polling_store.find_for_physical.return_value = None
    plan = build_discovery_research_plan(
        _result(), (),
        learned_operation_store=dpi_store,
        learned_polling_store=polling_store,
    )
    assert plan.dpi.status is ResearchStatus.REVERSIBLE_PROBE_READY
    assert plan.reversible_probe_available is True
    assert plan.deeper_learning_recommended is False


def test_structural_write_transport_is_candidate_not_authority():
    family = SimpleNamespace(
        write_scope=WriteScope.EXACT_MODEL,
        transports=(TransportKind.HID_FEATURE_SET,),
    )
    candidate = SimpleNamespace(family=family)
    dpi_store = Mock(); dpi_store.find_for_physical.return_value = None
    polling_store = Mock(); polling_store.find_for_physical.return_value = None
    plan = build_discovery_research_plan(
        _result(), (candidate,),
        learned_operation_store=dpi_store,
        learned_polling_store=polling_store,
    )
    assert plan.dpi.status is ResearchStatus.STRUCTURAL_CANDIDATE
    assert plan.polling.status is ResearchStatus.STRUCTURAL_CANDIDATE
    assert plan.deeper_learning_recommended is True
    assert plan.dpi.writable is False


def test_proven_capability_remains_runtime_authority():
    proof = DiscoveryEvidence(EvidenceLevel.PROVEN, "learned-operation-proven", "ok")
    cap = DiscoveredCapability("dpi", readable=True, writable=True, evidence=[proof]).normalized()
    dpi_store = Mock(); dpi_store.find_for_physical.return_value = None
    polling_store = Mock(); polling_store.find_for_physical.return_value = None
    plan = build_discovery_research_plan(
        _result(capabilities={"dpi": cap}), (),
        learned_operation_store=dpi_store,
        learned_polling_store=polling_store,
    )
    assert plan.dpi.status is ResearchStatus.PROVEN
    assert plan.deeper_learning_recommended is False
