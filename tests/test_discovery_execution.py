# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
from types import SimpleNamespace

import pytest

from mouse_control.discovery_execution import (
    DiscoveryExecutionError,
    ExperimentExecutionResult,
    compile_learned_dpi_ir,
    execute_learned_dpi_experiment,
    prepare_learned_dpi_experiment,
)
from mouse_control.discovery_models import DeviceNode, PhysicalDevice
from mouse_control.evidence_graph import EvidenceGraph, EvidenceNode
from mouse_control.experiment_authority import StorageEffect
from mouse_control.learned_operations import (
    StableDeviceIdentity,
    StableInterfaceIdentity,
    operation_from_grammar,
)
from mouse_control.protocol_grammar import SemanticBehavior
from mouse_control.transaction_inference import demonstration_from_trace, infer_transaction_grammar


DESCRIPTOR = "d" * 64


def _events(value: int):
    hi, lo = value.to_bytes(2, "big")
    return (
        SimpleNamespace(direction="tx", data=bytes.fromhex("11 01 1a 3a 00") + bytes((hi, lo)) + bytes(13)),
        SimpleNamespace(direction="rx", data=bytes.fromhex("11 01 1a 3a") + bytes(16)),
        SimpleNamespace(direction="tx", data=bytes.fromhex("11 01 1a 2a") + bytes(16)),
        SimpleNamespace(direction="rx", data=bytes.fromhex("11 01 1a 2a 00") + bytes((hi, lo)) + bytes.fromhex("03 20") + bytes(11)),
    )


def _operation(*, instance="instancehash"):
    values = (800, 1500, 2000, 2500, 3000)
    grammar = infer_transaction_grammar(tuple(
        demonstration_from_trace(value, _events(value)) for value in values
    ))
    return operation_from_grammar(
        grammar,
        identity=StableDeviceIdentity(3, 0x046D, 0x4074, "modelhash", instance),
        interface=StableInterfaceIdentity(3, 0x046D, 0x4074, 2, DESCRIPTOR),
    )


def _physical(*, instance="instancehash", ambiguous=False):
    node = DeviceNode(
        path=Path("/dev/hidraw-test"),
        sysfs_path=Path("/sys/test"),
        subsystem="hidraw",
        node_type="hidraw",
        bus=3,
        vendor_id=0x046D,
        product_id=0x4074,
        interface_number=2,
        descriptor_sha256=DESCRIPTOR,
    )
    return PhysicalDevice(
        "Test Mouse", 0x046D, 0x4074, 3, Path("/sys/test-parent"),
        hidraw_nodes=[node], model_fingerprint="modelhash",
        instance_fingerprint=instance, ambiguous=ambiguous,
    )


def _graph():
    graph = EvidenceGraph()
    source = graph.add(EvidenceNode("source", "learned trace corpus", "unit-test"))
    transaction = graph.add(EvidenceNode("transaction", "exact learned dpi transaction", "unit-test", (source,)))
    return graph, (source, transaction)


class FakeSession:
    def __init__(self, *, generation=None, fail_target_read=False, fail_rollback=False):
        self.path = Path("/dev/hidraw-test")
        self.current = 800
        self.requests = []
        self.generation = generation
        self.fail_target_read = fail_target_read
        self.fail_rollback = fail_rollback
        self._set_count = 0

    def exchange(self, request, pattern, *, timeout=None):
        self.requests.append(bytes(request))
        if request[3] == 0x3A:
            self._set_count += 1
            target = int.from_bytes(request[5:7], "big")
            self.current = target
            if self.generation is not None and self._set_count == 1:
                self.generation[0] += 1
            return bytes.fromhex("11 01 1a 3a") + bytes(16)
        if request[3] == 0x2A:
            value = self.current
            if self.fail_target_read and self._set_count == 1:
                value = 999
                self.fail_target_read = False
            if self.fail_rollback and self._set_count >= 2:
                value = 999
            hi, lo = int(value).to_bytes(2, "big")
            reply = bytes.fromhex("11 01 1a 2a 00") + bytes((hi, lo)) + bytes.fromhex("03 20") + bytes(11)
            if not pattern.matches(reply):
                # The actual session would simply keep waiting. The fake makes
                # mismatch explicit so the executor's rollback path is tested.
                raise RuntimeError("synthetic readback mismatch")
            return reply
        raise AssertionError(request.hex())


def _plan(*, baseline=800, generation=7, idempotent=True):
    graph, evidence = _graph()
    return prepare_learned_dpi_experiment(
        _operation(), _physical(), firmware="fw-test",
        evidence_graph=graph, evidence_ids=evidence,
        baseline=baseline, generation=generation,
        storage=StorageEffect.VOLATILE, idempotent=idempotent,
    )


def test_exact_learned_operation_compiles_to_ir_without_authority():
    graph, evidence = _graph()
    ir, path, channel = compile_learned_dpi_ir(
        _operation(), _physical(), firmware="fw-test",
        evidence_graph=graph, evidence_ids=evidence,
        storage=StorageEffect.VOLATILE,
    )
    cap = ir.capabilities[0]
    assert ir.identity.instance == "instancehash"
    assert ir.interface.descriptor_sha256 == DESCRIPTOR
    assert cap.kind.value == "dpi"
    assert cap.domain.values == (800, 1500, 2000, 2500, 3000)
    assert path == Path("/dev/hidraw-test")
    assert "if=2" in channel and DESCRIPTOR in channel
    assert not ir.family.can_authorize_write(exact_model=True)


def test_executable_compilation_refuses_partial_identity_invalid_evidence_and_unknown_storage():
    graph, evidence = _graph()
    with pytest.raises(DiscoveryExecutionError, match="exact physical identity"):
        compile_learned_dpi_ir(
            _operation(instance=None), _physical(instance=None), firmware="fw-test",
            evidence_graph=graph, evidence_ids=evidence,
            storage=StorageEffect.VOLATILE,
        )
    graph.invalidate(evidence[-1], "conflict")
    with pytest.raises(DiscoveryExecutionError, match="invalidated"):
        compile_learned_dpi_ir(
            _operation(), _physical(), firmware="fw-test",
            evidence_graph=graph, evidence_ids=evidence,
            storage=StorageEffect.VOLATILE,
        )
    fresh, fresh_ids = _graph()
    with pytest.raises(DiscoveryExecutionError, match="volatile"):
        prepare_learned_dpi_experiment(
            _operation(), _physical(), firmware="fw-test",
            evidence_graph=fresh, evidence_ids=fresh_ids, baseline=800, generation=1,
            storage=StorageEffect.UNKNOWN, idempotent=True,
        )


def test_plan_is_generation_bound_eligible_but_never_runtime_authority():
    plan = _plan()
    assert plan.target == 1500
    assert plan.generation == 7
    assert plan.authority.eligibility.value == "eligible"
    assert not plan.runtime_write_authorized
    assert not plan.authority.runtime_write_authorized


def test_non_idempotent_operation_remains_ineligible():
    graph, evidence = _graph()
    with pytest.raises(DiscoveryExecutionError, match="idempotent"):
        prepare_learned_dpi_experiment(
            _operation(), _physical(), firmware="fw-test",
            evidence_graph=graph, evidence_ids=evidence,
            baseline=800, generation=1,
            storage=StorageEffect.VOLATILE, idempotent=False,
        )


def test_stale_generation_and_baseline_mismatch_never_write():
    plan = _plan()
    session = FakeSession()
    with pytest.raises(DiscoveryExecutionError, match="generation changed"):
        execute_learned_dpi_experiment(
            plan, session=session, current_generation=lambda: 8,
            verify_physical=lambda *_: True, operator_authorized=True,
        )
    assert session.requests == []

    session = FakeSession()
    session.current = 1500
    with pytest.raises(DiscoveryExecutionError, match="baseline changed"):
        execute_learned_dpi_experiment(
            plan, session=session, current_generation=lambda: 7,
            verify_physical=lambda *_: True, operator_authorized=True,
        )
    assert all(request[3] != 0x3A for request in session.requests)


def test_successful_experiment_verifies_target_and_restores_baseline():
    plan = _plan()
    session = FakeSession()
    observations = []
    result = execute_learned_dpi_experiment(
        plan,
        session=session,
        current_generation=lambda: 7,
        verify_physical=lambda value, phase: observations.append((phase, value)) or True,
        operator_authorized=True,
    )
    assert result.target_readback == 1500
    assert result.restored_readback == 800
    assert result.restored
    assert session.current == 800
    assert observations == [("baseline", 800), ("target", 1500), ("restored", 800)]
    assert not result.runtime_write_authorized


def test_failed_physical_target_verification_rolls_back_and_reports_restored():
    plan = _plan()
    session = FakeSession()
    def verifier(value, phase):
        return phase != "target"
    with pytest.raises(DiscoveryExecutionError) as caught:
        execute_learned_dpi_experiment(
            plan, session=session, current_generation=lambda: 7,
            verify_physical=verifier, operator_authorized=True,
        )
    assert caught.value.write_attempted
    assert caught.value.restored
    assert not caught.value.recovery_required
    assert session.current == 800


def test_target_readback_failure_still_attempts_emergency_rollback():
    plan = _plan()
    session = FakeSession(fail_target_read=True)
    with pytest.raises(DiscoveryExecutionError) as caught:
        execute_learned_dpi_experiment(
            plan, session=session, current_generation=lambda: 7,
            verify_physical=lambda *_: True, operator_authorized=True,
        )
    assert caught.value.write_attempted
    assert caught.value.restored
    assert session.current == 800


def test_generation_change_after_write_refuses_to_touch_new_lifetime():
    generation = [7]
    plan = _plan(generation=7)
    session = FakeSession(generation=generation)
    with pytest.raises(DiscoveryExecutionError) as caught:
        execute_learned_dpi_experiment(
            plan, session=session, current_generation=lambda: generation[0],
            verify_physical=lambda *_: True, operator_authorized=True,
        )
    assert caught.value.write_attempted
    assert caught.value.recovery_required
    assert not caught.value.restored
    assert session.current == 1500
    # One set only: no rollback packet may cross the generation boundary.
    assert sum(request[3] == 0x3A for request in session.requests) == 1


def test_rollback_transport_failure_requires_recovery():
    plan = _plan()
    session = FakeSession(fail_rollback=True)
    # Force failure after the target so the emergency rollback is also attempted.
    with pytest.raises(DiscoveryExecutionError) as caught:
        execute_learned_dpi_experiment(
            plan, session=session, current_generation=lambda: 7,
            verify_physical=lambda value, phase: phase != "target",
            operator_authorized=True,
        )
    assert caught.value.write_attempted
    assert caught.value.recovery_required


def test_completed_experiment_can_be_persisted_as_verification_without_capability(tmp_path):
    from mouse_control.discovery_execution import record_dpi_experiment_evidence

    graph, evidence_ids = _graph()
    operation, physical = _operation(), _physical()
    plan = prepare_learned_dpi_experiment(
        operation, physical, firmware="fw-test", evidence_graph=graph,
        evidence_ids=evidence_ids, baseline=800, generation=3,
        storage=StorageEffect.VOLATILE, idempotent=True,
    )
    result = ExperimentExecutionResult(
        baseline=800, target=1500, target_readback=1500,
        restored_readback=800, restored=True, generation=3,
    )
    experiment_id, verification_id = record_dpi_experiment_evidence(graph, plan, result)
    explanation = graph.explain(verification_id)
    assert explanation[-1]["kind"] == "verification"
    assert experiment_id in graph.valid_ids and verification_id in graph.valid_ids
    assert all(item["kind"] != "capability" for item in explanation)

    graph.invalidate(evidence_ids[0], "source withdrawn")
    assert experiment_id not in graph.valid_ids
    assert verification_id not in graph.valid_ids


def test_failed_or_cross_generation_result_cannot_be_recorded_as_verification(tmp_path):
    from mouse_control.discovery_execution import record_dpi_experiment_evidence

    graph, evidence_ids = _graph()
    operation, physical = _operation(), _physical()
    plan = prepare_learned_dpi_experiment(
        operation, physical, firmware="fw-test", evidence_graph=graph,
        evidence_ids=evidence_ids, baseline=800, generation=3,
        storage=StorageEffect.VOLATILE, idempotent=True,
    )
    with pytest.raises(DiscoveryExecutionError, match="fully restored"):
        record_dpi_experiment_evidence(graph, plan, ExperimentExecutionResult(
            baseline=800, target=1500, target_readback=1500,
            restored_readback=800, restored=False, generation=3,
        ))
    with pytest.raises(DiscoveryExecutionError, match="fully restored"):
        record_dpi_experiment_evidence(graph, plan, ExperimentExecutionResult(
            baseline=800, target=1500, target_readback=1500,
            restored_readback=800, restored=True, generation=4,
        ))
