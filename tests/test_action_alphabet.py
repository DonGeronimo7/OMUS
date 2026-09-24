from __future__ import annotations

from dataclasses import replace

import pytest

from mouse_control.action_alphabet import (
    SymbolicAction, SymbolicActionKind, extend_action_alphabet, synthesize_action_alphabet,
)
from mouse_control.experiment_authority import StorageEffect
from mouse_control.peripheral_ir import (
    CapabilityIR, CapabilityKind, InterfaceIdentity, PeripheralIR, PhysicalIdentity, ValueDomain,
)
from mouse_control.protocol_grammar import (
    CodecKind, CodecSpec, FieldBinding, ProtocolFamily, ProtocolSource, SemanticBehavior,
    SourceTrust, WriteScope,
)


def ir_for(capability: CapabilityIR) -> PeripheralIR:
    return PeripheralIR(
        PhysicalIdentity(3, 0x1234, 0x5678, "model", "instance", "1.0"),
        InterfaceIdentity(2, "a" * 64),
        ProtocolFamily(
            "fixture", "v1",
            (ProtocolSource("fixture", "local", SourceTrust.REFERENCE),),
            write_scope=WriteScope.NEVER,
        ),
        (capability,),
    )


def dpi_capability(**changes) -> CapabilityIR:
    base = CapabilityIR(
        CapabilityKind.DPI,
        "query-dpi",
        "set-dpi",
        FieldBinding(SemanticBehavior.DPI_VALUE, "dpi", 0, width=2,
                     codec=CodecSpec(CodecKind.U16_LE)),
        ValueDomain(values=(800, 1500, 2000)),
        storage=StorageEffect.VOLATILE,
        rollback="restore-baseline",
        verification="canonical-readback",
        evidence=("e1",),
    )
    return replace(base, **changes)


def test_alphabet_contains_query_and_only_nearest_reversible_neighbor() -> None:
    actions = synthesize_action_alphabet(ir_for(dpi_capability()), {CapabilityKind.DPI: 1500})
    assert [(item.kind, item.value) for item in actions] == [
        (SymbolicActionKind.QUERY, None),
        (SymbolicActionKind.SET_NEIGHBOR, 2000),
    ]
    assert all(not item.runtime_write_authorized for item in actions)


def test_unknown_or_persistent_storage_never_generates_write_symbol() -> None:
    for storage in (StorageEffect.UNKNOWN, StorageEffect.PERSISTENT):
        actions = synthesize_action_alphabet(
            ir_for(dpi_capability(storage=storage)), {CapabilityKind.DPI: 800}
        )
        assert [item.kind for item in actions] == [SymbolicActionKind.QUERY]


def test_missing_rollback_or_verification_keeps_alphabet_read_only() -> None:
    for changes in ({"rollback": ""}, {"verification": ""}):
        actions = synthesize_action_alphabet(
            ir_for(dpi_capability(**changes)), {CapabilityKind.DPI: 800}
        )
        assert len(actions) == 1 and actions[0].kind is SymbolicActionKind.QUERY


def test_illegal_baseline_is_refused_instead_of_projected_to_domain() -> None:
    with pytest.raises(ValueError):
        synthesize_action_alphabet(ir_for(dpi_capability()), {CapabilityKind.DPI: 1000})


def test_incremental_extension_preserves_existing_order_and_adds_new_symbols_once() -> None:
    query = SymbolicAction("QUERY_DPI", SymbolicActionKind.QUERY, CapabilityKind.DPI)
    set_1500 = SymbolicAction("SET_DPI_1500", SymbolicActionKind.SET_NEIGHBOR, CapabilityKind.DPI, 1500)
    result = extend_action_alphabet((query,), (query, set_1500, set_1500))
    assert result == (query, set_1500)
