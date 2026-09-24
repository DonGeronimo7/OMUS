# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from mouse_control.experiment_authority import StorageEffect
from mouse_control.mutation_policy import (
    MutationClassification,
    MutationOutcome,
    MutationTrial,
    changed_bits,
    infer_mutation_safety,
)
from mouse_control.peripheral_ir import patch_candidate_state, ValueDomain
from mouse_control.protocol_grammar import CodecKind, CodecSpec, FieldBinding, SemanticBehavior


def flip(frame: bytes, *bits: int) -> bytes:
    result = bytearray(frame)
    for bit in bits:
        result[bit // 8] ^= 1 << (bit % 8)
    return bytes(result)


def test_changed_bits_uses_stable_byte_bit_coordinates():
    assert changed_bits(b"\x00\x00", b"\x01\x80") == frozenset({0, 15})
    with pytest.raises(ValueError):
        changed_bits(b"\x00", b"\x00\x00")


def test_singleton_success_is_independently_mutable_but_absence_is_unknown():
    base = b"\x00\x00"
    policy = infer_mutation_safety((
        MutationTrial(base, flip(base, 3), MutationOutcome.ACCEPTED_VERIFIED),
        MutationTrial(base, flip(base, 7), MutationOutcome.TRANSPORT_FAILURE),
    ))
    assert policy.classification(3) is MutationClassification.INDEPENDENT
    assert policy.classification(7) is MutationClassification.UNKNOWN
    assert policy.allows(base, flip(base, 3))
    assert not policy.allows(base, flip(base, 7))


def test_rejected_singleton_is_restricted_not_immutable():
    base = b"\x00"
    policy = infer_mutation_safety((
        MutationTrial(base, flip(base, 2), MutationOutcome.REJECTED),
    ))
    assert policy.classification(2) is MutationClassification.RESTRICTED
    assert policy.classification(2) is not MutationClassification.IMMUTABLE


def test_coupling_requires_failed_singletons_and_verified_group_success():
    base = b"\x00"
    policy = infer_mutation_safety((
        MutationTrial(base, flip(base, 1), MutationOutcome.NO_EFFECT),
        MutationTrial(base, flip(base, 2), MutationOutcome.REJECTED),
        MutationTrial(base, flip(base, 1, 2), MutationOutcome.ACCEPTED_VERIFIED),
    ))
    assert policy.coupled_groups == ((1, 2),)
    assert policy.classification(1) is MutationClassification.COUPLED
    assert not policy.allows(base, flip(base, 1))
    assert policy.allows(base, flip(base, 1, 2))


def test_declared_immutable_overrides_experimental_success():
    base = b"\x00"
    policy = infer_mutation_safety((
        MutationTrial(base, flip(base, 4), MutationOutcome.ACCEPTED_VERIFIED),
    ), declared_immutable_bits=(4,))
    assert policy.classification(4) is MutationClassification.IMMUTABLE
    assert not policy.allows(base, flip(base, 4))


def test_patch_candidate_state_can_be_guarded_by_mutation_map():
    base = b"\x00"
    field = FieldBinding(
        SemanticBehavior.REPORT_RATE_HZ, "state", 0, 1,
        CodecSpec(CodecKind.BITFIELD, mask=0b11, shift=0),
    )
    # Value 1 -> 2 flips both low bits, so only the proven coupled group permits it.
    coupled = infer_mutation_safety((
        MutationTrial(base, flip(base, 0), MutationOutcome.REJECTED),
        MutationTrial(base, flip(base, 1), MutationOutcome.REJECTED),
        MutationTrial(base, flip(base, 0, 1), MutationOutcome.ACCEPTED_VERIFIED),
    ))
    assert patch_candidate_state(
        b"\x01", field, 2, ValueDomain((1, 2)), report_size=1,
        mutation_policy=coupled,
    ) == b"\x02"

    restricted = infer_mutation_safety((
        MutationTrial(b"\x01", b"\x00", MutationOutcome.REJECTED),
        MutationTrial(b"\x01", b"\x03", MutationOutcome.REJECTED),
    ))
    with pytest.raises(ValueError, match="mutation-safe"):
        patch_candidate_state(
            b"\x01", field, 2, ValueDomain((1, 2)), report_size=1,
            mutation_policy=restricted,
        )


def test_regions_coalesce_for_explainable_reporting():
    base = b"\x00"
    policy = infer_mutation_safety((
        MutationTrial(base, flip(base, 0), MutationOutcome.ACCEPTED_VERIFIED),
        MutationTrial(base, flip(base, 1), MutationOutcome.ACCEPTED_VERIFIED),
        MutationTrial(base, flip(base, 3), MutationOutcome.REJECTED),
    ))
    assert [(r.start_bit, r.end_bit, r.classification.value) for r in policy.regions] == [
        (0, 1, "independently_mutable"),
        (2, 2, "unknown"),
        (3, 3, "restricted"),
        (4, 7, "unknown"),
    ]
