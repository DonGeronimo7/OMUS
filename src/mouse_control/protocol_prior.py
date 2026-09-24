# SPDX-License-Identifier: AGPL-3.0-or-later
"""Import declarative protocol knowledge into the EvidenceGraph as hypotheses.

Protocol repertoire entries are useful priors, not proofs.  This importer keeps
that distinction structural: public/vendor sources become ``source`` nodes and
all derived family/operation knowledge becomes ``hypothesis`` nodes.  It never
creates a ``verification`` or ``capability`` node, and therefore cannot promote
runtime write authority by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Iterable

from .evidence_graph import EvidenceGraph, EvidenceNode
from .protocol_grammar import ProtocolFamily, ProtocolOperation, ProtocolSource


def _claim(kind: str, payload: dict[str, object]) -> str:
    return json.dumps({"type": kind, **payload}, sort_keys=True, separators=(",", ":"))


def _source_claim(source: ProtocolSource) -> str:
    return _claim("protocol_source", {
        "project": source.project,
        "reference": source.reference,
        "trust": source.trust.value,
        "verified_on": source.verified_on,
        "verified_date": source.verified_date,
        "notes": source.notes,
    })


def _operation_claim(operation: ProtocolOperation) -> str:
    return _claim("protocol_operation_prior", {
        "name": operation.name,
        "page": operation.page,
        "target": operation.target,
        "request_length": operation.request_length,
        "read_command": operation.read_command,
        "write_command": operation.write_command,
        "safety": operation.safety.value,
        "payload_fields": list(operation.payload_fields),
        "prerequisite": list(operation.prerequisite),
        "automatic_experiment_allowed": operation.automatic_experiment_allowed,
        "vendor_evidence": operation.vendor_evidence,
    })


@dataclass(frozen=True)
class ImportedProtocolPrior:
    family: str
    source_ids: tuple[str, ...]
    family_id: str
    operation_ids: tuple[str, ...]

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        return (*self.source_ids, self.family_id, *self.operation_ids)


def import_protocol_family_prior(
    graph: EvidenceGraph,
    family: ProtocolFamily,
) -> ImportedProtocolPrior:
    """Import one family without changing its epistemic status to proof."""

    source_ids = tuple(
        graph.add(EvidenceNode(
            "source",
            _source_claim(source),
            f"protocol-repertoire:{family.name}:{source.project}",
        ))
        for source in family.sources
    )
    family_id = graph.add(EvidenceNode(
        "hypothesis",
        _claim("protocol_family_prior", {
            "name": family.name,
            "revision": family.revision,
            "vendor_ids": list(family.vendor_ids),
            "product_ids": list(family.product_ids),
            "transports": [item.value for item in family.transports],
            "write_scope": family.write_scope.value,
            "identity_required": family.identity_required,
            "minimum_match_score": family.minimum_match_score,
            "signature_count": len(family.signatures),
            "operation_count": len(family.operations),
            "notes": family.notes,
        }),
        f"protocol-repertoire:{family.name}",
        source_ids,
    ))
    operation_ids = tuple(
        graph.add(EvidenceNode(
            "hypothesis",
            _operation_claim(operation),
            f"protocol-repertoire:{family.name}:{operation.name}",
            (family_id,),
        ))
        for operation in family.operations
    )
    return ImportedProtocolPrior(family.name, source_ids, family_id, operation_ids)


def import_repertoire_priors(
    graph: EvidenceGraph,
    families: Iterable[ProtocolFamily],
) -> tuple[ImportedProtocolPrior, ...]:
    """Import a deterministic set of family priors into an existing graph."""

    return tuple(import_protocol_family_prior(graph, family) for family in families)
