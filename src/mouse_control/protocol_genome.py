"""Operation-specific, provenance-rich Protocol Genome records."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import json
from .evidence_graph import EvidenceGraph, EvidenceNode


class ProofState(str, Enum):
    UNKNOWN = "unknown"
    GRAMMAR_KNOWN = "grammar_known"
    READ_PROVEN = "read_proven"
    WRITE_CANDIDATE = "write_candidate"
    WRITE_VERIFIED = "write_verified"
    DISABLED = "disabled"


@dataclass(frozen=True)
class GenomeOperation:
    name: str
    grammar: str
    state: ProofState
    legal_values: tuple[int, ...]
    prerequisites: tuple[str, ...]
    integrity: str
    storage: str
    rollback: str
    hazards: tuple[str, ...]
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class GenomeDevice:
    family: str
    model: str
    transport_identity: str
    firmware_generation: str
    receiver_relationship: str
    operations: tuple[GenomeOperation, ...]


def ingest_genome_device(graph: EvidenceGraph, device: GenomeDevice) -> tuple[str, ...]:
    if (not device.family.strip() or not device.model.strip()
            or len(device.operations) > 4096):
        raise ValueError("malformed or excessive Genome device")
    for operation in device.operations:
        if (not operation.name.strip() or len(operation.legal_values) > 4096
                or len(operation.evidence) > 4096 or len(operation.hazards) > 4096):
            raise ValueError("malformed or excessive Genome operation")
    if any(ref not in graph.valid_ids for op in device.operations for ref in op.evidence):
        raise ValueError("genome references missing or invalidated evidence")
    identity = graph.add(EvidenceNode("hypothesis", json.dumps({
        "type": "protocol_genome_device", "family": device.family, "model": device.model,
        "transport": device.transport_identity, "firmware": device.firmware_generation,
        "receiver": device.receiver_relationship,
    }, sort_keys=True), f"protocol-genome:{device.family}"))
    result = [identity]
    for operation in device.operations:
        claim = json.dumps({
            "type": "protocol_genome_operation", "name": operation.name,
            "grammar": operation.grammar, "state": operation.state.value,
            "legal_values": operation.legal_values, "prerequisites": operation.prerequisites,
            "integrity": operation.integrity, "storage": operation.storage,
            "rollback": operation.rollback, "hazards": operation.hazards,
        }, sort_keys=True)
        result.append(graph.add(EvidenceNode("hypothesis", claim,
                                            f"protocol-genome:{device.family}:{operation.name}",
                                            (identity, *operation.evidence))))
    return tuple(result)
