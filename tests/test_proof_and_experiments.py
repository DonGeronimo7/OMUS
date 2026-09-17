import pytest

from mouse_control.experiment_authority import (
    ExperimentAuthority, ExperimentEligibility, ExperimentSpec, StorageEffect,
)
from mouse_control.proof_state import OperationProof, ProofState, ProofTransitionError


def test_proof_is_operation_specific_and_cannot_skip_verification() -> None:
    proof = OperationProof("dpi.write")
    for state in (
        ProofState.OBSERVED, ProofState.RECOGNIZED, ProofState.DECODED,
        ProofState.HYPOTHESIZED, ProofState.EXPERIMENT_ELIGIBLE,
        ProofState.EXPERIMENTED, ProofState.VERIFIED, ProofState.PROVEN,
    ):
        proof = proof.transition(state, evidence=f"evidence-{state.value}")
    assert proof.state is ProofState.PROVEN
    with pytest.raises(ProofTransitionError):
        OperationProof("polling.write").transition(ProofState.PROVEN, evidence="guess")


def test_conflicted_and_revoked_proof_never_authorizes_write() -> None:
    proof = OperationProof("dpi.write", ProofState.PROVEN, ("readback",))
    assert proof.write_authorized
    assert not proof.transition(ProofState.CONFLICTED, evidence="source mismatch").write_authorized
    assert not proof.transition(ProofState.REVOKED, evidence="unsafe").write_authorized


def test_experiment_authority_is_separate_from_runtime_proof() -> None:
    spec = ExperimentSpec(
        physical_identity="model:x/instance:y", channel_identity="if2/hash:abc",
        protocol_context="compx/config-v1", operation="dpi.write",
        legal_values=(800, 1200, 1600), expected_effect="absolute DPI changes",
        restore_plan="restore baseline with verified recipe", storage=StorageEffect.VOLATILE,
        idempotent=True, timeout_ms=500, retries=0, verification="canonical readback",
        abort_conditions=("disconnect", "ambiguous response"), source_recipe="source:rev1",
    )
    authority = ExperimentAuthority.evaluate(
        spec, lab_mode=True, exact_physical_match=True, exact_channel_match=True,
        constrained_grammar=True, baseline_captured=True,
    )
    assert authority.eligibility is ExperimentEligibility.ELIGIBLE
    assert authority.runtime_write_authorized is False


def test_unknown_or_persistent_experiment_remains_blocked() -> None:
    spec = ExperimentSpec(
        physical_identity="x", channel_identity="y", protocol_context="unknown",
        operation="raw.write", legal_values=(), expected_effect="unknown",
        restore_plan="none", storage=StorageEffect.PERSISTENT, idempotent=False,
        timeout_ms=100, retries=0, verification="none", abort_conditions=(),
    )
    result = ExperimentAuthority.evaluate(
        spec, lab_mode=True, exact_physical_match=True, exact_channel_match=True,
        constrained_grammar=False, baseline_captured=False,
    )
    assert result.eligibility is ExperimentEligibility.BLOCKED

