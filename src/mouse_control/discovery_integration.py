"""Thin integration path joining existing discovery evidence layers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .dependency_inference import DependencyInference, infer_dependencies
from .discovery_models import DeviceNode, PhysicalDevice
from .hid_descriptor import ParsedHidDescriptor
from .logical_record import LogicalRecord
from .proof_state import OperationEvidence, OperationProof, ProofState
from .protocol_repertoire import (
    FamilyCandidate,
    OpenSetRecognition,
    RecognitionStatus,
    SemanticExchange,
    SemanticFamilyRecognition,
    match_repertoire,
    recognize_family_semantics,
    recognize_open_set,
)
from .temporal_dialogue import (
    DialogueAssembler, DialogueKind, DialogueObservation, DialogueRecord, Direction,
    PushedStateRecord,
)
from .trace.models import UsbDirection, UsbObservation


@dataclass(frozen=True)
class IntegratedDiscoveryResult:
    dialogues: tuple[DialogueRecord, ...]
    dependencies: DependencyInference
    recognition: SemanticFamilyRecognition
    proof: OperationProof
    descriptor_structure: tuple[dict[str, object], ...]
    evidence_source_ids: tuple[str, ...]
    connection_generation: int
    next_safe_observation_recipe_id: str

    @property
    def write_authorized(self) -> bool:
        return self.proof.write_authorized

    def community_evidence(self) -> dict[str, object]:
        return {
            "evidence_source_ids": list(self.evidence_source_ids),
            "dialogues": [
                {
                    "kind": item.kind.value,
                    "request_sequence": item.request.sequence if item.request else None,
                    "observation_sequence": item.observation.sequence,
                    "confidence": item.confidence,
                }
                for item in self.dialogues
            ],
            "dependencies": [
                {
                    "kind": item.kind.value,
                    "offset": item.offset,
                    "width": item.width,
                    "related_offset": item.related_offset,
                }
                for item in self.dependencies.candidates
            ],
            "unexplained_offsets": list(self.dependencies.unexplained_offsets),
            "recognition": {
                "family": self.recognition.candidate.family.name,
                "structural_matched": list(self.recognition.candidate.matched),
                "semantic_matched": list(self.recognition.matched),
                "semantic_missing": list(self.recognition.missing),
                "recognized": self.recognition.recognized,
            },
            "operation_proof": {
                "operation": self.proof.operation,
                "proof_state": self.proof.state.value,
                "write_authorized": self.proof.write_authorized,
            },
            "descriptor_structure": list(self.descriptor_structure),
            "connection_generation": self.connection_generation,
            "next_safe_observation_recipe_id": self.next_safe_observation_recipe_id,
        }


@dataclass(frozen=True)
class IntegratedPushedStateResult:
    records: tuple[PushedStateRecord, ...]
    recognition: OpenSetRecognition
    proof: OperationProof
    evidence_source_ids: tuple[str, ...]

    @property
    def write_authorized(self) -> bool:
        return False


@dataclass(frozen=True)
class IntegratedLogicalRecordResult:
    records: tuple[LogicalRecord, ...]
    recognition: OpenSetRecognition
    proof: OperationProof
    evidence_source_ids: tuple[str, ...]

    @property
    def write_authorized(self) -> bool:
        return False


def integrate_logical_records(
    records: Sequence[LogicalRecord],
    *,
    family_name: str,
    physical: PhysicalDevice,
    descriptors: Mapping[DeviceNode, ParsedHidDescriptor],
) -> IntegratedLogicalRecordResult:
    """Join read-only reconstructed records to open-set recognition and proof."""

    retained = tuple(records)
    recognition = recognize_open_set(
        physical,
        descriptors,
        logical_records={family_name: retained},
    )
    sources = tuple(
        f"{frame.source_id}:{frame.sequence}"
        for record in retained
        for frame in record.source_frames
    )
    proof = OperationProof(
        "read.logical_protocol_record",
        (
            ProofState.RECOGNIZED
            if recognition.status is RecognitionStatus.RECOGNIZED
            else ProofState.OBSERVED
        ),
        (
            ("passive logical-record discriminator",)
            if recognition.status is RecognitionStatus.RECOGNIZED
            else ("logical-record observation",)
        ),
        OperationEvidence(evidence_source_ids=sources),
    )
    return IntegratedLogicalRecordResult(retained, recognition, proof, sources)


def integrate_pushed_state_observations(
    records: Sequence[PushedStateRecord],
    *,
    family_name: str,
    physical: PhysicalDevice,
    descriptors: Mapping[DeviceNode, ParsedHidDescriptor],
) -> IntegratedPushedStateResult:
    """Join passive asynchronous state evidence to open-set recognition."""

    retained = tuple(records)
    recognition = recognize_open_set(
        physical,
        descriptors,
        pushed_states={family_name: retained},
    )
    sources = tuple(
        f"{record.observation.source_id}:{record.observation.sequence}"
        for record in retained
    )
    proof = OperationProof(
        "read.asynchronous_protocol_state",
        (
            ProofState.RECOGNIZED
            if recognition.status is RecognitionStatus.RECOGNIZED
            else ProofState.OBSERVED
        ),
        (
            ("passive pushed-state discriminator",)
            if recognition.status is RecognitionStatus.RECOGNIZED
            else ("asynchronous state observation",)
        ),
        OperationEvidence(evidence_source_ids=sources),
    )
    return IntegratedPushedStateResult(retained, recognition, proof, sources)


def _dialogue_observation(item: UsbObservation, *, generation: int) -> DialogueObservation:
    if not item.payload:
        raise ValueError("semantic recognition requires a non-empty HID frame")
    outgoing = item.direction is UsbDirection.OUT
    sequence_offset = 3 if outgoing else 2
    if len(item.payload) <= sequence_offset:
        raise ValueError("BITMOUSE frame is too short for sequence correlation")
    return DialogueObservation(
        source_id=item.capture_id,
        physical_id=item.physical_device_fingerprint,
        channel_id=f"interface:{item.interface_number}:endpoint:{item.endpoint}",
        transport="usb-hid",
        direction=Direction.OUT if outgoing else Direction.IN,
        report_namespace="bitmouse-72",
        report_id=0x72,
        generation=generation,
        timestamp_ns=item.timestamp_ns,
        sequence=item.sequence,
        payload=item.payload,
        transaction_tag=item.payload[sequence_offset],
        grammar="bitmouse-72",
    )


def _descriptor_structure(
    descriptors: Mapping[DeviceNode, ParsedHidDescriptor],
) -> tuple[dict[str, object], ...]:
    result: list[dict[str, object]] = []
    for node, descriptor in descriptors.items():
        applications = sorted({field.application_usage for field in descriptor.fields if field.application_usage})
        for report in descriptor.reports:
            result.append({
                "interface_number": node.interface_number,
                "report_namespace": report.report_type,
                "report_id": report.report_id,
                "report_size": report.byte_length,
                "usage_pages": list(report.usage_pages),
                "application_contexts": [list(item) for item in applications],
                "descriptor_fingerprint": descriptor.fingerprint,
            })
    return tuple(sorted(result, key=lambda item: (
        item["interface_number"] if item["interface_number"] is not None else -1,
        str(item["report_namespace"]), int(item["report_id"]),
    )))


def integrate_bitmouse_observations(
    observations: Sequence[UsbObservation],
    *,
    physical: PhysicalDevice,
    descriptors: Mapping[DeviceNode, ParsedHidDescriptor],
    semantic_values: Sequence[int],
    generation: int = 0,
) -> IntegratedDiscoveryResult:
    """Exercise canonical→temporal→dependency→semantic→proof/report evidence."""

    candidates = match_repertoire(physical, descriptors)
    structural: FamilyCandidate | None = next(
        (item for item in candidates if item.family.name == "bitmouse-72"), None
    )
    if structural is None:
        raise ValueError("observations lack the BITMOUSE structural descriptor grammar")
    assembler = DialogueAssembler()
    records: list[DialogueRecord] = []
    for item in observations:
        records.extend(assembler.add(_dialogue_observation(item, generation=generation)))
    records.extend(assembler.finish())
    exchanges = tuple(
        SemanticExchange(item.request.payload, item.observation.payload)
        for item in records
        if item.kind is DialogueKind.RESPONSE and item.request is not None
    )
    recognition = recognize_family_semantics(structural, exchanges)
    dependencies = infer_dependencies(recognition.semantic_records, semantic_values)
    sources = tuple(
        f"{item.capture_id}:{item.sequence}" for item in observations
    )
    proof = OperationProof(
        "read.protocol_state",
        ProofState.RECOGNIZED if recognition.recognized else ProofState.OBSERVED,
        ("passive semantic discriminator",) if recognition.recognized else ("structural match",),
        OperationEvidence(evidence_source_ids=sources),
    )
    return IntegratedDiscoveryResult(
        dialogues=tuple(records), dependencies=dependencies,
        recognition=recognition, proof=proof,
        descriptor_structure=_descriptor_structure(descriptors),
        evidence_source_ids=sources, connection_generation=generation,
        next_safe_observation_recipe_id="bitmouse-72-passive-query-replay-v1",
    )
