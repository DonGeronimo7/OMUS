"""Compile the existing reviewed protocol repertoire into Genome records."""
from __future__ import annotations
from .protocol_genome import GenomeDevice, GenomeOperation, ProofState
from .protocol_grammar import ProtocolFamily, SafetyClass


def compile_family_genome(family: ProtocolFamily, *, evidence: tuple[str, ...]) -> GenomeDevice:
    operations = []
    for operation in family.operations:
        if operation.safety is SafetyClass.READ_ONLY:
            state = ProofState.GRAMMAR_KNOWN
        elif operation.safety is SafetyClass.REVERSIBLE:
            state = ProofState.WRITE_CANDIDATE
        else:
            state = ProofState.DISABLED
        operations.append(GenomeOperation(
            operation.name, f"page={operation.page:#x};target={operation.target:#x};length={operation.request_length}",
            state, (), tuple(operation.prerequisite), "family grammar", "unknown", "",
            ("repertoire knowledge is not runtime write authority",), evidence,
        ))
    if not operations:
        operations.append(GenomeOperation("identity", "family signatures", ProofState.GRAMMAR_KNOWN,
                                          (), (), "", "", "", ("no operation recipe",), evidence))
    return GenomeDevice(family.name, "family-scope", "repertoire identities",
                        family.revision, "family-specific", tuple(operations))
