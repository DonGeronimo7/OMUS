# SPDX-License-Identifier: AGPL-3.0-or-later
"""Safe bridge from learned Discovery knowledge to bounded executable experiments.

This module deliberately does *not* create runtime write authority.  It compiles
one exact-device learned DPI operation into the new Peripheral IR, binds that IR
to one current hidraw interface and connection generation, and can execute an
operator-authorized reversible research experiment through the existing
single-reader learned-HID transaction owner.

The bridge exists to keep three concerns separate:

* persisted/research knowledge (LearnedOperation + EvidenceGraph),
* current live binding/generation facts, and
* explicit transaction authorization for one bounded experiment.

A successful experiment remains research evidence.  Promotion to PROVEN/runtime
write authority is still handled by the existing learned-operation promotion
path and requires independent physical verification.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Callable

from .evidence_graph import EvidenceGraph, EvidenceNode
from .experiment_authority import (
    ExperimentAuthority,
    ExperimentEligibility,
    ExperimentSpec,
    StorageEffect,
)
from .learned_hid_session import LearnedHidSession
from .learned_hid_transport import (
    LearnedHidAdapter,
    LearnedHidTransportError,
    execute_learned_dpi,
    learned_dpi_read_spec,
    learned_dpi_transaction_spec,
)
from .learned_operations import (
    LearnedOperation,
    LearnedOperationError,
    LearnedOperationState,
    matching_interface_node,
    operation_matches_physical,
)
from .peripheral_ir import (
    CapabilityIR,
    CapabilityKind,
    InterfaceIdentity,
    PeripheralIR,
    PhysicalIdentity,
    ProofPlan,
    ValueDomain,
    compile_proof_plan,
)
from .protocol_grammar import (
    FieldBinding,
    ProtocolFamily,
    ProtocolFrameGrammar,
    ProtocolSource,
    SemanticBehavior,
    SourceTrust,
    WriteScope,
)
from .transaction_engine import (
    TransactionAuthorization,
    TransactionContext,
    TransactionEngine,
)


class DiscoveryExecutionError(RuntimeError):
    """A compiled experiment could not proceed or complete safely."""

    def __init__(
        self,
        message: str,
        *,
        write_attempted: bool = False,
        restored: bool = False,
        recovery_required: bool = False,
    ) -> None:
        super().__init__(message)
        self.write_attempted = bool(write_attempted)
        self.restored = bool(restored)
        self.recovery_required = bool(recovery_required)


@dataclass(frozen=True)
class ExecutableDpiExperiment:
    """Generation-bound receipt for one operator-supervised research experiment.

    The receipt is intentionally non-serializable authority: a caller must still
    provide an explicit operator authorization flag at execution time, and the
    current generation is checked immediately before every hardware write.
    """

    ir: PeripheralIR
    proof_plan: ProofPlan
    authority: ExperimentAuthority
    operation: LearnedOperation
    node_path: Path
    generation: int
    baseline: int
    target: int
    stable_channel_identity: str

    @property
    def runtime_write_authorized(self) -> bool:
        return False


@dataclass(frozen=True)
class ExperimentExecutionResult:
    baseline: int
    target: int
    target_readback: int
    restored_readback: int
    restored: bool
    generation: int

    @property
    def runtime_write_authorized(self) -> bool:
        return False


def _exact_physical_identity(physical, *, firmware: str) -> PhysicalIdentity:
    if getattr(physical, "ambiguous", False):
        raise DiscoveryExecutionError("ambiguous physical device cannot compile an executable experiment")
    required = {
        "bus": getattr(physical, "bus", None),
        "vendor_id": getattr(physical, "vendor_id", None),
        "product_id": getattr(physical, "product_id", None),
        "model_fingerprint": getattr(physical, "model_fingerprint", ""),
        "instance_fingerprint": getattr(physical, "instance_fingerprint", None),
    }
    missing = [name for name, value in required.items() if value is None or value == ""]
    if missing:
        raise DiscoveryExecutionError(
            "exact physical identity is incomplete: " + ", ".join(missing)
        )
    return PhysicalIdentity(
        int(required["bus"]),
        int(required["vendor_id"]),
        int(required["product_id"]),
        str(required["model_fingerprint"]),
        str(required["instance_fingerprint"]),
        firmware,
    )


def _validate_learned_dpi_operation(operation: LearnedOperation) -> None:
    if operation.behavior is not SemanticBehavior.DPI_VALUE:
        raise DiscoveryExecutionError("only learned scalar DPI operations are compiled by this bridge")
    if operation.write_scope is not WriteScope.EXACT_MODEL:
        raise DiscoveryExecutionError("learned operation is not exact-model scoped")
    if operation.state not in {LearnedOperationState.DEMONSTRATED, LearnedOperationState.PROVEN}:
        raise DiscoveryExecutionError("learned operation is not in an executable research state")
    if not operation.demonstrated_values or len(set(operation.demonstrated_values)) != len(operation.demonstrated_values):
        raise DiscoveryExecutionError("learned operation has no unique demonstrated value domain")
    if operation.write_field.width != operation.read_field.width:
        raise DiscoveryExecutionError("learned write/readback widths disagree")
    if operation.write_field.codec != operation.read_field.codec:
        raise DiscoveryExecutionError("learned write/readback codecs disagree")
    # Rendering one known value proves there are no unresolved wildcard bytes
    # outside the semantic span. The active read request must be fully resolved.
    try:
        operation.render_write(operation.demonstrated_values[0])
        operation.render_read()
    except LearnedOperationError as exc:
        raise DiscoveryExecutionError(str(exc)) from exc


def _stable_channel_identity(node) -> str:
    fields = (
        getattr(node, "bus", None),
        getattr(node, "vendor_id", None),
        getattr(node, "product_id", None),
        getattr(node, "interface_number", None),
        getattr(node, "descriptor_sha256", None),
    )
    if any(value is None or value == "" for value in fields):
        raise DiscoveryExecutionError("current HID interface lacks exact stable binding facts")
    return (
        f"bus={fields[0]};vid={int(fields[1]):04x};pid={int(fields[2]):04x};"
        f"if={fields[3]};desc={fields[4]}"
    )


def compile_learned_dpi_ir(
    operation: LearnedOperation,
    physical,
    *,
    firmware: str,
    evidence_graph: EvidenceGraph,
    evidence_ids: tuple[str, ...],
    storage: StorageEffect = StorageEffect.UNKNOWN,
) -> tuple[PeripheralIR, Path, str]:
    """Compile an exact live learned-DPI binding into Peripheral IR.

    This validates current identity/interface facts and evidence references, but
    it does not capture a baseline, authorize a write, or execute any I/O.
    """

    _validate_learned_dpi_operation(operation)
    if not operation_matches_physical(operation, physical):
        raise DiscoveryExecutionError("learned operation does not match the current physical device")
    identity = _exact_physical_identity(physical, firmware=firmware)
    try:
        node = matching_interface_node(operation, physical)
    except LearnedOperationError as exc:
        raise DiscoveryExecutionError(str(exc)) from exc

    stable_channel = _stable_channel_identity(node)
    if operation.interface.bus is None or operation.interface.vendor_id is None or operation.interface.product_id is None:
        raise DiscoveryExecutionError("learned operation lacks exact bus/VID/PID interface identity")
    if operation.interface.interface_number is None or not operation.interface.descriptor_sha256:
        raise DiscoveryExecutionError("learned operation lacks exact interface number/descriptor identity")

    # Re-check the persisted interface against the live node with no wildcard
    # semantics.  matching_interface_node intentionally supports older partial
    # profiles; executable compilation does not.
    expected_interface = (
        operation.interface.bus,
        operation.interface.vendor_id,
        operation.interface.product_id,
        operation.interface.interface_number,
        operation.interface.descriptor_sha256,
    )
    live_interface = (
        node.bus,
        node.vendor_id,
        node.product_id,
        node.interface_number,
        node.descriptor_sha256,
    )
    if expected_interface != live_interface:
        raise DiscoveryExecutionError("persisted learned interface does not exactly equal the live binding")

    if not evidence_ids:
        raise DiscoveryExecutionError("source-backed executable compilation requires evidence IDs")
    invalid = tuple(identifier for identifier in evidence_ids if identifier not in evidence_graph.valid_ids)
    if invalid:
        raise DiscoveryExecutionError("evidence is missing or invalidated: " + ", ".join(invalid))

    write_report_id = operation.write_request.bytes_[0]
    read_report_id = operation.read_request.bytes_[0]
    if write_report_id is None or read_report_id is None:
        raise DiscoveryExecutionError("learned request report IDs must be invariant")

    query = learned_dpi_read_spec()
    setter = learned_dpi_transaction_spec()
    frames = (
        ProtocolFrameGrammar("write", "output", int(write_report_id), operation.write_request.length),
        ProtocolFrameGrammar("readback", "output", int(read_report_id), operation.read_request.length),
    )
    binding = FieldBinding(
        SemanticBehavior.DPI_VALUE,
        "write",
        operation.write_field.offset,
        operation.write_field.width,
        operation.write_field.codec,
        evidence_note="exact-model learned write field; execution remains promotion/lab-gated",
    )
    trust = (
        SourceTrust.LOCAL_PROVEN
        if operation.state is LearnedOperationState.PROVEN
        else SourceTrust.REFERENCE
    )
    family = ProtocolFamily(
        name="learned-exact-dpi",
        revision="learned-operation-v1",
        sources=(
            ProtocolSource(
                project="OMUS Automatic Discovery",
                reference="content-addressed EvidenceGraph + learned-operation profile",
                trust=trust,
                verified_on=getattr(physical, "name", None) if trust is SourceTrust.LOCAL_PROVEN else None,
                notes="Compilation receipt only; family resemblance never grants authority.",
            ),
        ),
        vendor_ids=(identity.vendor_id,),
        product_ids=(identity.product_id,),
        bindings=(binding,),
        transactions=(query, setter),
        frame_grammars=frames,
        write_scope=WriteScope.EXACT_MODEL,
        identity_required=True,
        notes="Generated from one exact learned operation and one current stable interface binding.",
    )
    capability = CapabilityIR(
        CapabilityKind.DPI,
        query.name,
        setter.name,
        binding,
        ValueDomain(tuple(int(value) for value in operation.demonstrated_values)),
        storage=storage,
        rollback="restore the complete captured baseline with the same demonstrated setter",
        verification="canonical learned readback plus independent physical verification",
        correlation="single-reader learned HID session with exact response-pattern correlation",
        evidence=tuple(evidence_ids),
    )
    return (
        PeripheralIR(
            identity,
            InterfaceIdentity(int(node.interface_number), str(node.descriptor_sha256)),
            family,
            (capability,),
        ),
        Path(node.path),
        stable_channel,
    )


def prepare_learned_dpi_experiment(
    operation: LearnedOperation,
    physical,
    *,
    firmware: str,
    evidence_graph: EvidenceGraph,
    evidence_ids: tuple[str, ...],
    baseline: int,
    generation: int,
    storage: StorageEffect,
    idempotent: bool,
) -> ExecutableDpiExperiment:
    """Create a generation-bound, still-non-authoritative experiment receipt."""

    if type(generation) is not int or generation < 0:
        raise DiscoveryExecutionError("connection generation must be a non-negative integer")
    ir, node_path, stable_channel = compile_learned_dpi_ir(
        operation,
        physical,
        firmware=firmware,
        evidence_graph=evidence_graph,
        evidence_ids=evidence_ids,
        storage=storage,
    )
    proof = compile_proof_plan(
        ir,
        CapabilityKind.DPI,
        baseline,
        evidence_ids=evidence_graph.valid_ids,
    )
    if proof.blockers or proof.target is None:
        raise DiscoveryExecutionError(
            "proof plan is not executable: " + "; ".join(proof.blockers or ("no target",))
        )
    cap = ir.capabilities[0]
    spec = ExperimentSpec(
        physical_identity=(
            f"bus={ir.identity.transport};vid={ir.identity.vendor_id:04x};"
            f"pid={ir.identity.product_id:04x};model={ir.identity.model};"
            f"instance={ir.identity.instance};firmware={ir.identity.firmware}"
        ),
        channel_identity=stable_channel,
        protocol_context=f"{ir.family.name}:{ir.family.revision}",
        operation="set-dpi",
        legal_values=tuple(operation.demonstrated_values),
        expected_effect=f"DPI changes from {baseline} to {proof.target}",
        restore_plan=cap.rollback,
        storage=cap.storage,
        idempotent=bool(idempotent),
        timeout_ms=1000,
        retries=0,
        verification=cap.verification,
        abort_conditions=(
            "connection generation changed",
            "baseline readback disagreed",
            "target readback disagreed",
            "independent physical verification disagreed",
            "rollback readback disagreed",
        ),
        source_recipe=",".join(evidence_ids),
    )
    authority = ExperimentAuthority.evaluate(
        spec,
        lab_mode=True,
        exact_physical_match=True,
        exact_channel_match=True,
        constrained_grammar=True,
        baseline_captured=True,
    )
    if authority.eligibility is not ExperimentEligibility.ELIGIBLE:
        raise DiscoveryExecutionError(
            "experiment is not eligible: " + "; ".join(authority.reasons)
        )
    return ExecutableDpiExperiment(
        ir=ir,
        proof_plan=proof,
        authority=authority,
        operation=operation,
        node_path=node_path,
        generation=generation,
        baseline=int(baseline),
        target=int(proof.target),
        stable_channel_identity=stable_channel,
    )


def _query_dpi(operation: LearnedOperation, session: LearnedHidSession, node_path: Path) -> int:
    context = TransactionContext()
    adapter = LearnedHidAdapter(node_path, operation, session=session)
    try:
        TransactionEngine().run(
            learned_dpi_read_spec(),
            adapter,
            authorization=TransactionAuthorization(
                active_queries=True,
                reason="generation-bound compiled Discovery baseline/readback",
            ),
            context=context,
        )
        return int(context.values["raw_readback"])
    finally:
        adapter.close()


def execute_learned_dpi_experiment(
    plan: ExecutableDpiExperiment,
    *,
    session: LearnedHidSession,
    current_generation: Callable[[], int],
    verify_physical: Callable[[int, str], bool],
    operator_authorized: bool,
) -> ExperimentExecutionResult:
    """Execute one bounded reversible experiment through existing transaction code.

    The caller owns ``session`` and must keep it bound to the same interface.
    ``verify_physical`` is deliberately external: the executor cannot manufacture
    physical evidence.  Any failure after a write attempts rollback only while
    the original connection generation is still current.
    """

    if plan.authority.eligibility is not ExperimentEligibility.ELIGIBLE:
        raise DiscoveryExecutionError("compiled experiment is no longer eligible")
    if plan.runtime_write_authorized or plan.authority.runtime_write_authorized:
        raise DiscoveryExecutionError("research receipt must never carry runtime write authority")
    if not operator_authorized:
        raise DiscoveryExecutionError("explicit operator authorization is required")
    if Path(session.path) != plan.node_path:
        raise DiscoveryExecutionError("single-reader session is bound to a different live interface")

    def require_generation() -> None:
        observed = current_generation()
        if observed != plan.generation:
            raise DiscoveryExecutionError(
                f"connection generation changed ({plan.generation} -> {observed})",
                recovery_required=True,
            )

    require_generation()
    try:
        actual_baseline = _query_dpi(plan.operation, session, plan.node_path)
    except Exception as exc:
        raise DiscoveryExecutionError(f"baseline query failed: {exc}") from exc
    if actual_baseline != plan.baseline:
        raise DiscoveryExecutionError(
            f"baseline changed since compilation: expected {plan.baseline}, read {actual_baseline}"
        )
    if not verify_physical(plan.baseline, "baseline"):
        raise DiscoveryExecutionError("independent baseline verification failed")

    require_generation()
    write_attempted = False
    target_readback: int | None = None
    restored_readback: int | None = None
    restored = False
    failure: BaseException | None = None

    try:
        # Mark attempt before the call: a transport/readback failure can occur
        # after the target packet reached the device.
        write_attempted = True
        target_context = execute_learned_dpi(
            plan.operation,
            plan.node_path,
            plan.target,
            promotion=not plan.operation.write_authorized,
            authorization=TransactionAuthorization(
                reversible_writes=True,
                reason="operator-authorized generation-bound Discovery experiment",
            ),
            session=session,
        )
        target_readback = int(target_context.values["raw_readback"])
        require_generation()
        if target_readback != plan.target:
            raise DiscoveryExecutionError("target readback disagreed after transaction", write_attempted=True)
        if not verify_physical(plan.target, "target"):
            raise DiscoveryExecutionError("independent target verification failed", write_attempted=True)
        require_generation()

        rollback = execute_learned_dpi(
            plan.operation,
            plan.node_path,
            plan.baseline,
            promotion=not plan.operation.write_authorized,
            authorization=TransactionAuthorization(
                reversible_writes=True,
                reason="mandatory rollback for compiled Discovery experiment",
            ),
            session=session,
        )
        restored_readback = int(rollback.values["raw_readback"])
        if restored_readback != plan.baseline:
            raise DiscoveryExecutionError("rollback readback disagreed", write_attempted=True)
        restored = True
        require_generation()
        if not verify_physical(plan.baseline, "restored"):
            raise DiscoveryExecutionError(
                "independent rollback verification failed",
                write_attempted=True,
                restored=True,
            )
        return ExperimentExecutionResult(
            baseline=plan.baseline,
            target=plan.target,
            target_readback=target_readback,
            restored_readback=restored_readback,
            restored=True,
            generation=plan.generation,
        )
    except BaseException as exc:  # rollback must also cover transport/readback failures
        failure = exc

    # No additional write is safe after a generation change: the hidraw path may
    # now refer to another lifetime/device.  Surface recovery_required instead.
    if current_generation() != plan.generation:
        raise DiscoveryExecutionError(
            f"experiment failed after a write and connection generation changed: {failure}",
            write_attempted=write_attempted,
            restored=restored,
            recovery_required=True,
        ) from failure

    if write_attempted and not restored:
        try:
            rollback = execute_learned_dpi(
                plan.operation,
                plan.node_path,
                plan.baseline,
                promotion=not plan.operation.write_authorized,
                authorization=TransactionAuthorization(
                    reversible_writes=True,
                    reason="emergency rollback for failed compiled Discovery experiment",
                ),
                session=session,
            )
            restored_readback = int(rollback.values["raw_readback"])
            restored = restored_readback == plan.baseline
        except Exception as rollback_exc:
            raise DiscoveryExecutionError(
                f"experiment failed ({failure}); emergency rollback failed ({rollback_exc})",
                write_attempted=True,
                restored=False,
                recovery_required=True,
            ) from rollback_exc

    if isinstance(failure, DiscoveryExecutionError):
        raise DiscoveryExecutionError(
            str(failure),
            write_attempted=write_attempted or failure.write_attempted,
            restored=restored or failure.restored,
            recovery_required=failure.recovery_required or not restored,
        ) from failure
    if isinstance(failure, LearnedHidTransportError):
        raise DiscoveryExecutionError(
            f"transaction failed: {failure}",
            write_attempted=write_attempted,
            restored=restored,
            recovery_required=not restored,
        ) from failure
    raise DiscoveryExecutionError(
        f"experiment failed: {failure}",
        write_attempted=write_attempted,
        restored=restored,
        recovery_required=write_attempted and not restored,
    ) from failure



def record_dpi_experiment_evidence(
    graph: EvidenceGraph,
    plan: ExecutableDpiExperiment,
    result: ExperimentExecutionResult,
    *,
    source: str = "omus-bounded-discovery-experiment",
) -> tuple[str, str]:
    """Persist one completed reversible experiment as research evidence.

    This function is intentionally separate from execution so callers cannot
    mistake a transaction return value for persisted proof.  It records the
    exact generation/binding, target/readback and rollback outcome as an
    ``experiment`` followed by a ``verification`` node.  It never emits a
    ``capability`` node and therefore does not promote runtime write authority.
    """

    if not result.restored or result.generation != plan.generation:
        raise DiscoveryExecutionError(
            "only a fully restored same-generation experiment can be recorded as verification"
        )
    if result.baseline != plan.baseline or result.target != plan.target:
        raise DiscoveryExecutionError("experiment result does not belong to the compiled plan")
    if result.target_readback != plan.target or result.restored_readback != plan.baseline:
        raise DiscoveryExecutionError("experiment readbacks are not canonical")

    evidence = tuple(plan.ir.capabilities[0].evidence)
    invalid = tuple(identifier for identifier in evidence if identifier not in graph.valid_ids)
    if invalid:
        raise DiscoveryExecutionError(
            "cannot persist verification from invalidated evidence: " + ", ".join(invalid)
        )
    experiment_claim = json.dumps({
        "operation": "set-dpi",
        "generation": plan.generation,
        "channel_identity": plan.stable_channel_identity,
        "baseline": plan.baseline,
        "target": plan.target,
        "node_path": str(plan.node_path),
        "runtime_write_authorized": False,
    }, sort_keys=True, separators=(",", ":"))
    experiment_id = graph.add(EvidenceNode(
        "experiment", experiment_claim, source, evidence
    ))
    verification_claim = json.dumps({
        "target_readback": result.target_readback,
        "restored_readback": result.restored_readback,
        "restored": result.restored,
        "physical_verification": "external-callback-confirmed-all-phases",
        "runtime_write_authorized": False,
    }, sort_keys=True, separators=(",", ":"))
    verification_id = graph.add(EvidenceNode(
        "verification", verification_claim, source, (experiment_id,)
    ))
    return experiment_id, verification_id
