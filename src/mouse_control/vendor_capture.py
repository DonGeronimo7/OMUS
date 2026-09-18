"""Offline, provenance-preserving vendor capture ingestion for Discovery Lab.

The importer accepts bounded data files and projects observations into existing
Discovery/Lab evidence types.  It has no HID transport, replay primitive,
network client, dynamic-code path, or authority-promotion path.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import date
from enum import Enum
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Iterable, Mapping, Protocol, Sequence

from .device_profiles import get_profile_directory
from .discovery_lab import (
    LabExperiment,
    LabInterval,
    LabIntervalRecord,
    ProtocolObservation,
    RouteEndpoint,
)
from .discovery_models import DiscoveryEvidence, EvidenceLevel
from .lamzu_aurora import (
    AuroraKnowledgeError,
    LAMZU_AURORA_LEGACY,
    LAMZU_AURORA_MODERN,
    decode_event,
    decode_routed_identity,
    event_to_pushed_states,
    is_lamzu_bootloader_identity,
    normalize_response,
    status_dialogue_kind,
)
from .power_investigator import analyze_power_state
from .proof_state import ProofState
from .protocol_timing import profile_experiment_timing
from .routing_mapper import aurora_routed_identity_evidence, analyze_receiver_child_routing
from .temporal_dialogue import (
    DialogueKind,
    DialogueObservation,
    DialogueRecord,
    Direction,
)


CAPTURE_SCHEMA = "mouse-control-vendor-capture:1"
IMPORT_SCHEMA_VERSION = 1
IMPORTER_VERSION = "vendor-capture-v1"
MAX_CAPTURE_BYTES = 8 * 1024 * 1024
MAX_PERSISTED_BYTES = 32 * 1024 * 1024
MAX_RECORDS = 100_000
MAX_FRAME_BYTES = 4096
MAX_TREE_DEPTH = 24
MAX_TREE_NODES = 500_000


class VendorCaptureError(ValueError):
    """Capture input cannot be safely imported."""


class UnsupportedCaptureFormat(VendorCaptureError):
    pass


class AmbiguousCaptureFormat(VendorCaptureError):
    pass


class ProvenanceCategory(str, Enum):
    OFFICIAL_VENDOR = "official_vendor"
    PUBLIC_DOCUMENTATION = "public_documentation"
    OPEN_SOURCE = "open_source"
    PERSONAL_CAPTURE = "personal_capture"
    OTHER_PUBLIC = "other_public"
    UNKNOWN = "unknown"
    PROHIBITED_PRIVATE = "prohibited_private"


class CaptureReviewStatus(str, Enum):
    IMPORTED_UNREVIEWED = "imported_unreviewed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class CaptureDirection(str, Enum):
    HOST_TO_DEVICE = "host_to_device"
    DEVICE_TO_HOST = "device_to_host"
    UNKNOWN = "unknown"


class CaptureRole(str, Enum):
    REQUEST = "request"
    RESPONSE = "response"
    PUSH = "push"
    STATUS = "status"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class VendorCaptureSource:
    source_name: str | None
    original_filename: str
    source_type: str | None
    provenance_category: ProvenanceCategory
    vendor: str | None = None
    product_model: str | None = None
    vendor_id: int | None = None
    product_id: int | None = None
    receiver_vendor_id: int | None = None
    receiver_product_id: int | None = None
    protocol_family: str | None = None
    source_version: str | None = None
    capture_date: str | None = None
    import_date: str | None = None
    source_reference: str | None = None
    notes: str | None = None
    importer_version: str = IMPORTER_VERSION
    content_sha256: str = ""

    def __post_init__(self) -> None:
        if Path(self.original_filename).name != self.original_filename:
            raise VendorCaptureError("original filename must not contain a path")
        for name in (
            "vendor_id", "product_id", "receiver_vendor_id", "receiver_product_id",
        ):
            value = getattr(self, name)
            if value is not None and not 0 <= value <= 0xFFFF:
                raise VendorCaptureError(f"{name} must fit in 16 bits")
        if self.provenance_category is ProvenanceCategory.PROHIBITED_PRIVATE:
            raise VendorCaptureError("prohibited/private provenance cannot be imported")
        if self.content_sha256 and (
            len(self.content_sha256) != 64
            or any(char not in "0123456789abcdef" for char in self.content_sha256)
        ):
            raise VendorCaptureError("source digest must be lowercase SHA-256")


@dataclass(frozen=True)
class NormalizedCaptureRecord:
    observation_id: str
    source_digest: str
    order: int
    source_sequence: int | str | None
    physical_frame: bytes
    original_length: int
    logical_payload: bytes
    direction: CaptureDirection = CaptureDirection.UNKNOWN
    timestamp_ns: int | None = None
    report_id: int | None = None
    report_type: str | None = None
    transport: str | None = None
    interface_number: int | None = None
    endpoint: int | None = None
    channel: str | None = None
    transfer_metadata: tuple[tuple[str, object], ...] = ()
    transaction_id: str | None = None
    role: CaptureRole = CaptureRole.UNKNOWN
    protocol_family: str | None = None
    semantic: str | None = None
    decoded_fields: tuple[tuple[str, object], ...] = ()
    parser_warnings: tuple[str, ...] = ()
    source_reference: str | None = None
    dangerous: bool = False
    experimentable: bool = False
    review_status: CaptureReviewStatus = CaptureReviewStatus.IMPORTED_UNREVIEWED

    def __post_init__(self) -> None:
        if self.order < 0 or self.original_length < 0:
            raise VendorCaptureError("record order and original length must be non-negative")
        if len(self.physical_frame) > MAX_FRAME_BYTES:
            raise VendorCaptureError("capture frame exceeds bounded maximum")
        if self.timestamp_ns is not None and self.timestamp_ns < 0:
            raise VendorCaptureError("capture timestamp must be non-negative")
        if isinstance(self.source_sequence, int) and self.source_sequence < 0:
            raise VendorCaptureError("source sequence must be non-negative")
        if self.source_sequence is not None and not isinstance(self.source_sequence, (int, str)):
            raise VendorCaptureError("source sequence must be an integer, string, or unknown")
        if self.report_id is not None and not 0 <= self.report_id <= 0xFF:
            raise VendorCaptureError("report ID must fit in one byte")
        if self.experimentable:
            raise VendorCaptureError("imported observations cannot be experimentable")


@dataclass(frozen=True)
class StagedEvidenceRecord:
    """Review envelope around the existing shared ``DiscoveryEvidence`` type."""

    evidence_id: str
    observation_id: str
    evidence: DiscoveryEvidence
    proof_state: ProofState
    provenance_category: ProvenanceCategory
    review_status: CaptureReviewStatus = CaptureReviewStatus.IMPORTED_UNREVIEWED
    dangerous: bool = False
    experimentable: bool = False
    contradictions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.proof_state not in {ProofState.OBSERVED, ProofState.DECODED, ProofState.CONFLICTED}:
            raise VendorCaptureError("imports may only create observed, decoded, or conflicted evidence")
        if self.evidence.level is not EvidenceLevel.OBSERVED:
            raise VendorCaptureError("imported DiscoveryEvidence must remain OBSERVED")
        if self.experimentable:
            raise VendorCaptureError("staged imported evidence cannot be experimentable")

    @property
    def write_authorized(self) -> bool:
        return False


@dataclass(frozen=True)
class VendorImportManifest:
    source_digest: str
    parser_selected: str
    total_records: int
    accepted_records: int
    malformed_records: int
    unknown_records: int
    duplicate_records: int
    request_records: int
    response_records: int
    pushed_records: int
    dangerous_suppressed_records: int
    protocol_families_recognized: tuple[str, ...]
    identities_observed: tuple[str, ...]
    warnings: tuple[str, ...]
    conflicts: tuple[str, ...]
    corroborating_records: int = 0
    duplicate_import: bool = False
    review_status: CaptureReviewStatus = CaptureReviewStatus.IMPORTED_UNREVIEWED
    importer_version: str = IMPORTER_VERSION
    schema_version: int = IMPORT_SCHEMA_VERSION
    authority_notice: str = "Imported evidence is not a physically verified capability."

    @property
    def write_authorized(self) -> bool:
        return False


@dataclass(frozen=True)
class VendorCaptureImport:
    source: VendorCaptureSource
    records: tuple[NormalizedCaptureRecord, ...]
    evidence_records: tuple[StagedEvidenceRecord, ...]
    manifest: VendorImportManifest
    lab_experiment: LabExperiment | None = None

    @property
    def write_authorized(self) -> bool:
        return False


class CaptureFormatAdapter(Protocol):
    name: str

    def detect(self, raw: bytes, filename: str) -> int: ...

    def parse(self, raw: bytes) -> Mapping[str, object]: ...


def _bounded_json(value: object, *, depth: int = 0, counter: list[int] | None = None) -> None:
    if depth > MAX_TREE_DEPTH:
        raise VendorCaptureError("capture JSON nesting exceeds bounded maximum")
    if counter is None:
        counter = [0]
    counter[0] += 1
    if counter[0] > MAX_TREE_NODES:
        raise VendorCaptureError("capture JSON structure exceeds bounded maximum")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise VendorCaptureError("capture JSON object keys must be strings")
            _bounded_json(item, depth=depth + 1, counter=counter)
    elif isinstance(value, list):
        for item in value:
            _bounded_json(item, depth=depth + 1, counter=counter)
    elif isinstance(value, str) and len(value) > MAX_CAPTURE_BYTES:
        raise VendorCaptureError("capture JSON string exceeds bounded maximum")


class CanonicalJsonAdapter:
    name = "mouse-control-canonical-json"

    def detect(self, raw: bytes, filename: str) -> int:
        stripped = raw.lstrip()
        if not stripped.startswith(b"{"):
            return 0
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return 0
        return 100 if isinstance(value, dict) and value.get("schema") == CAPTURE_SCHEMA else 0

    def parse(self, raw: bytes) -> Mapping[str, object]:
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VendorCaptureError(f"malformed canonical JSON: {exc}") from exc
        _bounded_json(value)
        if not isinstance(value, dict) or value.get("schema") != CAPTURE_SCHEMA:
            raise VendorCaptureError("canonical capture schema is missing or unsupported")
        return value


class CanonicalJsonlAdapter:
    name = "mouse-control-canonical-jsonl"

    def detect(self, raw: bytes, filename: str) -> int:
        try:
            lines = [line for line in raw.decode("utf-8").splitlines() if line.strip()]
            first = json.loads(lines[0]) if lines else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            return 0
        return 100 if isinstance(first, dict) and first.get("kind") == "capture_header" and first.get("schema") == CAPTURE_SCHEMA else 0

    def parse(self, raw: bytes) -> Mapping[str, object]:
        try:
            lines = [line for line in raw.decode("utf-8").splitlines() if line.strip()]
        except UnicodeDecodeError as exc:
            raise VendorCaptureError("canonical JSONL must be UTF-8") from exc
        if not lines:
            raise VendorCaptureError("canonical JSONL capture is empty")
        parsed: list[object] = []
        for number, line in enumerate(lines, 1):
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise VendorCaptureError(f"malformed JSONL record at line {number}") from exc
            _bounded_json(item)
            parsed.append(item)
        header = parsed[0]
        if not isinstance(header, dict) or header.get("kind") != "capture_header" or header.get("schema") != CAPTURE_SCHEMA:
            raise VendorCaptureError("canonical JSONL header is missing or unsupported")
        source = header.get("source", {})
        records = []
        for number, item in enumerate(parsed[1:], 2):
            if not isinstance(item, dict) or item.get("kind") != "record":
                records.append({"_parse_error": f"JSONL line {number} is not a record"})
                continue
            records.append({key: value for key, value in item.items() if key != "kind"})
        return {"schema": CAPTURE_SCHEMA, "source": source, "records": records}


DEFAULT_ADAPTERS: tuple[CaptureFormatAdapter, ...] = (
    CanonicalJsonAdapter(), CanonicalJsonlAdapter(),
)


def detect_capture_adapter(
    raw: bytes,
    filename: str,
    *,
    adapters: Sequence[CaptureFormatAdapter] = DEFAULT_ADAPTERS,
) -> CaptureFormatAdapter:
    matches = sorted(
        ((adapter.detect(raw, filename), adapter) for adapter in adapters),
        key=lambda item: (-item[0], item[1].name),
    )
    matches = [item for item in matches if item[0] > 0]
    if not matches:
        raise UnsupportedCaptureFormat("unsupported vendor capture format")
    if len(matches) > 1 and matches[0][0] == matches[1][0]:
        raise AmbiguousCaptureFormat(
            "capture format detection is ambiguous between "
            + ", ".join(item[1].name for item in matches if item[0] == matches[0][0])
        )
    return matches[0][1]


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise VendorCaptureError("optional metadata text must be a string")
    return value


def _optional_u16(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = int(value, 0)
        except ValueError as exc:
            raise VendorCaptureError("identity value is not an integer") from exc
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 0xFFFF:
        raise VendorCaptureError("identity value must fit in 16 bits")
    return value


def _source_from_raw(
    raw: Mapping[str, object], *, filename: str, digest: str, import_date: str,
) -> tuple[VendorCaptureSource, tuple[str, ...]]:
    known = {
        "name", "source_type", "provenance_category", "vendor", "product_model",
        "vid", "pid", "receiver_vid", "receiver_pid", "protocol_family",
        "source_version", "capture_date", "source_reference", "notes",
    }
    warnings = tuple(f"unknown source field preserved only as a warning: {key}" for key in sorted(set(raw) - known))
    provenance_raw = raw.get("provenance_category", ProvenanceCategory.UNKNOWN.value)
    try:
        provenance = ProvenanceCategory(str(provenance_raw))
    except ValueError as exc:
        raise VendorCaptureError("unknown provenance category") from exc
    family = _optional_text(raw.get("protocol_family"))
    if family in {"lamzu-aurora", "aurora"}:
        family = LAMZU_AURORA_MODERN.name
    elif family == "lamzu-legacy":
        family = LAMZU_AURORA_LEGACY.name
    return VendorCaptureSource(
        source_name=_optional_text(raw.get("name")),
        original_filename=Path(filename).name,
        source_type=_optional_text(raw.get("source_type")),
        provenance_category=provenance,
        vendor=_optional_text(raw.get("vendor")),
        product_model=_optional_text(raw.get("product_model")),
        vendor_id=_optional_u16(raw.get("vid")),
        product_id=_optional_u16(raw.get("pid")),
        receiver_vendor_id=_optional_u16(raw.get("receiver_vid")),
        receiver_product_id=_optional_u16(raw.get("receiver_pid")),
        protocol_family=family,
        source_version=_optional_text(raw.get("source_version")),
        capture_date=_optional_text(raw.get("capture_date")),
        import_date=import_date,
        source_reference=_optional_text(raw.get("source_reference")),
        notes=_optional_text(raw.get("notes")),
        content_sha256=digest,
    ), warnings


def _bytes_from_record(raw: Mapping[str, object]) -> bytes:
    if "frame_hex" in raw:
        value = raw["frame_hex"]
        if not isinstance(value, str):
            raise VendorCaptureError("frame_hex must be a string")
        if len(value) > MAX_FRAME_BYTES * 2:
            raise VendorCaptureError("capture frame exceeds bounded maximum")
        try:
            return bytes.fromhex(value)
        except ValueError as exc:
            raise VendorCaptureError("capture frame contains invalid hexadecimal") from exc
    values = raw.get("bytes")
    if not isinstance(values, list):
        raise VendorCaptureError("capture record requires frame_hex or bytes")
    if len(values) > MAX_FRAME_BYTES:
        raise VendorCaptureError("capture frame exceeds bounded maximum")
    if any(not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 0xFF for value in values):
        raise VendorCaptureError("capture byte values must be integers from 0 to 255")
    return bytes(values)


def _enum_value(enum_type, value: object, *, default):
    if value is None:
        return default
    try:
        return enum_type(str(value))
    except ValueError as exc:
        raise VendorCaptureError(f"invalid {enum_type.__name__} value") from exc


def _stable_id(prefix: str, value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return prefix + "-" + sha256(encoded).hexdigest()[:24]


def _record_fingerprint(record: NormalizedCaptureRecord, *, include_source: bool = True) -> tuple[object, ...]:
    return (
        record.source_digest if include_source else None,
        record.source_sequence,
        record.timestamp_ns, record.direction.value, record.report_id, record.report_type,
        record.transport, record.interface_number, record.endpoint, record.channel,
        json.dumps(record.transfer_metadata, sort_keys=True, separators=(",", ":"), default=str),
        record.transaction_id, record.role.value, record.semantic, record.physical_frame,
    )


def _raw_record(
    raw: Mapping[str, object], *, order: int, source: VendorCaptureSource,
) -> NormalizedCaptureRecord:
    known = {
        "sequence", "timestamp_ns", "direction", "report_id", "report_type",
        "transport", "interface_number", "endpoint", "channel", "transfer_metadata",
        "transaction_id", "role", "protocol_family", "semantic", "frame_hex",
        "bytes", "original_length", "source_reference",
    }
    frame = _bytes_from_record(raw)
    source_sequence = raw.get("sequence")
    if source_sequence is not None and (
        not isinstance(source_sequence, (int, str)) or isinstance(source_sequence, bool)
        or isinstance(source_sequence, int) and source_sequence < 0
    ):
        raise VendorCaptureError("sequence must be a non-negative integer, string, or null")
    original_length = raw.get("original_length", len(frame))
    if not isinstance(original_length, int) or isinstance(original_length, bool) or original_length < 0:
        raise VendorCaptureError("original_length must be a non-negative integer")
    warnings = [f"unknown record field ignored: {key}" for key in sorted(set(raw) - known)]
    if original_length > len(frame):
        warnings.append("record is truncated relative to original_length")
    timestamp = raw.get("timestamp_ns")
    if timestamp is not None and (not isinstance(timestamp, int) or isinstance(timestamp, bool) or timestamp < 0):
        raise VendorCaptureError("timestamp_ns must be a non-negative integer")
    report_id = raw.get("report_id")
    if report_id is not None and (not isinstance(report_id, int) or isinstance(report_id, bool) or not 0 <= report_id <= 0xFF):
        raise VendorCaptureError("report_id must fit in one byte")
    for name in ("interface_number", "endpoint"):
        value = raw.get(name)
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
            raise VendorCaptureError(f"{name} must be a non-negative integer")
    metadata = raw.get("transfer_metadata", {})
    if not isinstance(metadata, dict):
        raise VendorCaptureError("transfer_metadata must be an object")
    _bounded_json(metadata)
    values = {
        "source": source.content_sha256,
        "timestamp": timestamp,
        "direction": raw.get("direction", "unknown"),
        "report_id": report_id,
        "report_type": raw.get("report_type"),
        "transport": raw.get("transport"),
        "interface": raw.get("interface_number"),
        "endpoint": raw.get("endpoint"),
        "channel": raw.get("channel"),
        "transaction": raw.get("transaction_id"),
        "role": raw.get("role", "unknown"),
        "frame": frame.hex(),
    }
    return NormalizedCaptureRecord(
        observation_id=_stable_id("import-observation", values),
        source_digest=source.content_sha256,
        order=order,
        source_sequence=source_sequence,
        physical_frame=frame,
        original_length=original_length,
        logical_payload=frame,
        direction=_enum_value(CaptureDirection, raw.get("direction"), default=CaptureDirection.UNKNOWN),
        timestamp_ns=timestamp,
        report_id=report_id,
        report_type=_optional_text(raw.get("report_type")),
        transport=_optional_text(raw.get("transport")),
        interface_number=raw.get("interface_number"),
        endpoint=raw.get("endpoint"),
        channel=_optional_text(raw.get("channel")),
        transfer_metadata=tuple(sorted(metadata.items())),
        transaction_id=(str(raw["transaction_id"]) if raw.get("transaction_id") is not None else None),
        role=_enum_value(CaptureRole, raw.get("role"), default=CaptureRole.UNKNOWN),
        protocol_family=_optional_text(raw.get("protocol_family")) or source.protocol_family,
        semantic=_optional_text(raw.get("semantic")),
        parser_warnings=tuple(warnings),
        source_reference=_optional_text(raw.get("source_reference")) or source.source_reference,
    )


def _aurora_family(source: VendorCaptureSource, record: NormalizedCaptureRecord) -> str | None:
    family = record.protocol_family
    if family in {LAMZU_AURORA_MODERN.name, "lamzu-aurora", "aurora"}:
        return LAMZU_AURORA_MODERN.name
    if family in {LAMZU_AURORA_LEGACY.name, "lamzu-legacy"}:
        return LAMZU_AURORA_LEGACY.name
    if source.vendor_id == 0x3554:
        return LAMZU_AURORA_LEGACY.name
    if source.vendor_id in {0x37B0, 0x373E}:
        return LAMZU_AURORA_MODERN.name
    return None


def _modern_operation(frame: bytes):
    if len(frame) != 64:
        return None, None
    target, page, command = frame[2], frame[4], frame[5]
    for item in LAMZU_AURORA_MODERN.operations:
        if item.target == target and item.page == page:
            if command == item.read_command:
                return item, "read"
            if command == item.write_command:
                return item, "write"
    return None, None


def _dangerous_modern(frame: bytes) -> str | None:
    if len(frame) != 64:
        return None
    target, page, command = frame[2], frame[4], frame[5]
    for item in LAMZU_AURORA_MODERN.dangerous_operations:
        if item.command is None:
            continue
        if command == item.command and (item.page is None or page == item.page) and (item.target is None or target == item.target):
            return item.name
    return None


def _enrich_aurora(
    records: Sequence[NormalizedCaptureRecord], source: VendorCaptureSource,
) -> tuple[NormalizedCaptureRecord, ...]:
    prepared: list[NormalizedCaptureRecord] = []
    for record in records:
        family = _aurora_family(source, record)
        role = record.role
        if family == LAMZU_AURORA_MODERN.name and role is CaptureRole.UNKNOWN:
            if record.direction is CaptureDirection.HOST_TO_DEVICE and record.report_type == "feature":
                role = CaptureRole.REQUEST
            elif record.direction is CaptureDirection.DEVICE_TO_HOST and record.report_type == "input" and record.report_id == 4:
                role = CaptureRole.PUSH
            elif record.direction is CaptureDirection.DEVICE_TO_HOST and record.report_type == "feature":
                role = CaptureRole.RESPONSE
        prepared.append(replace(record, role=role))
    request_by_transaction = {
        item.transaction_id: item for item in prepared
        if item.transaction_id is not None and item.role is CaptureRole.REQUEST
    }
    dangerous_transactions = {
        item.transaction_id for item in prepared
        if item.transaction_id is not None
        and item.role is CaptureRole.REQUEST
        and _aurora_family(source, item) == LAMZU_AURORA_MODERN.name
        and len(item.physical_frame) == 64
        and (
            _dangerous_modern(item.physical_frame) is not None
            or _modern_operation(item.physical_frame)[0] is None
        )
    }
    result: list[NormalizedCaptureRecord] = []
    bootloader = is_lamzu_bootloader_identity(source.vendor_id, source.product_id)
    for record in prepared:
        family = _aurora_family(source, record)
        if family is None:
            result.append(record)
            continue
        warnings = list(record.parser_warnings)
        semantic = record.semantic
        decoded: dict[str, object] = {}
        dangerous = (
            record.dangerous or bootloader
            or record.transaction_id in dangerous_transactions
        )
        logical = record.logical_payload
        role = record.role
        if bootloader:
            warnings.append("known bootloader/DFU identity is excluded from experiments")
        if family == LAMZU_AURORA_MODERN.name:
            if role is CaptureRole.REQUEST and len(record.physical_frame) == 64:
                operation, side = _modern_operation(record.physical_frame)
                denied = _dangerous_modern(record.physical_frame)
                if operation is not None:
                    semantic = operation.name
                    decoded.update({
                        "target": operation.target, "page": operation.page,
                        "command": record.physical_frame[5], "operation_side": side,
                    })
                elif denied is not None:
                    semantic, dangerous = denied, True
                else:
                    semantic = semantic or "unknown Aurora command"
                    dangerous = True
                    warnings.append("unknown command is suppressed and non-experimentable")
            elif role in {CaptureRole.RESPONSE, CaptureRole.STATUS}:
                request = request_by_transaction.get(record.transaction_id)
                expected = request.physical_frame[5] if request is not None and len(request.physical_frame) == 64 else None
                if expected is not None:
                    try:
                        normalized = normalize_response(record.physical_frame, expected_command=expected)
                        logical = normalized.canonical_frame
                        operation, _side = _modern_operation(request.physical_frame)
                        semantic = operation.name if operation is not None else semantic
                        decoded.update({
                            "alignment": normalized.alignment, "status": normalized.status,
                            "target": normalized.target, "page": normalized.page,
                            "command": normalized.command, "payload_hex": normalized.payload.hex(),
                        })
                    except AuroraKnowledgeError as exc:
                        warnings.append(str(exc))
            elif role is CaptureRole.PUSH or (record.report_id == 4 and record.report_type == "input"):
                try:
                    event = decode_event(record.physical_frame)
                    semantic = event.name
                    decoded.update(event.values)
                    role = CaptureRole.PUSH
                except AuroraKnowledgeError as exc:
                    warnings.append(str(exc))
        else:
            if len(record.physical_frame) != 16 or record.report_id != 8:
                warnings.append("legacy report-8 frame has an unexpected shape")
            command = record.physical_frame[0] if record.physical_frame else None
            operation = next((
                item for item in LAMZU_AURORA_LEGACY.operations
                if command in {item.read_command, item.write_command}
            ), None)
            if operation is not None:
                semantic = operation.name
                decoded["command"] = command
                if operation.name in {"legacy flash read", "legacy flash write"}:
                    dangerous = True
            elif command is not None:
                semantic = semantic or "unknown legacy command"
                dangerous = True
                warnings.append("unknown legacy command is suppressed and non-experimentable")
        result.append(replace(
            record, protocol_family=family, logical_payload=logical, role=role,
            semantic=semantic, decoded_fields=tuple(sorted(decoded.items())),
            parser_warnings=tuple(dict.fromkeys(warnings)), dangerous=dangerous,
            experimentable=False,
        ))
    return tuple(result)


def _evidence_record(
    record: NormalizedCaptureRecord, source: VendorCaptureSource,
    *, conflicts: tuple[str, ...] = (),
) -> StagedEvidenceRecord:
    decoded = bool(record.decoded_fields or record.semantic)
    proof = ProofState.CONFLICTED if conflicts else ProofState.DECODED if decoded else ProofState.OBSERVED
    details: dict[str, object] = {
        "observation_id": record.observation_id,
        "source_digest": source.content_sha256,
        "provenance_category": source.provenance_category.value,
        "review_status": record.review_status.value,
        "protocol_family": record.protocol_family,
        "semantic": record.semantic,
        "physical_frame_hex": record.physical_frame.hex(),
        "logical_payload_hex": record.logical_payload.hex(),
        "decoded_fields": dict(record.decoded_fields),
        "confidence": "imported-unreviewed",
        "dangerous": record.dangerous,
        "experimentable": False,
        "write_authorized": False,
    }
    evidence = DiscoveryEvidence(
        EvidenceLevel.OBSERVED,
        "vendor_capture_import",
        record.semantic or "Imported raw protocol observation",
        source=source.source_reference or source.source_name or source.original_filename,
        details=details,
    )
    return StagedEvidenceRecord(
        _stable_id("import-evidence", (record.observation_id, source.content_sha256)),
        record.observation_id, evidence, proof, source.provenance_category,
        review_status=record.review_status,
        dangerous=record.dangerous, contradictions=conflicts,
    )


def _conflicts(
    records: Sequence[NormalizedCaptureRecord], source: VendorCaptureSource,
    existing: Sequence[VendorCaptureImport],
) -> tuple[tuple[str, ...], int]:
    messages: set[str] = set()
    corroborating = 0
    all_records = [(record, None) for record in records]
    for imported in existing:
        all_records.extend((record, imported.source.content_sha256) for record in imported.records)
    by_command: dict[tuple[object, ...], set[str]] = {}
    by_report: dict[tuple[object, ...], set[int]] = {}
    by_identity: dict[tuple[int | None, int | None], set[str]] = {}
    by_raw: dict[tuple[str | None, bytes], set[str]] = {}
    for record, _other_source in all_records:
        decoded = dict(record.decoded_fields)
        command = decoded.get("command")
        if record.protocol_family and command is not None and record.semantic:
            key = (record.protocol_family, decoded.get("target"), decoded.get("page"), command)
            by_command.setdefault(key, set()).add(record.semantic)
        if record.protocol_family and record.report_id is not None:
            decoded = dict(record.decoded_fields)
            report_length = (
                len(record.logical_payload)
                if "alignment" in decoded else record.original_length
            )
            by_report.setdefault((record.protocol_family, record.report_type, record.report_id), set()).add(report_length)
        if record.semantic:
            by_raw.setdefault((record.protocol_family, record.physical_frame), set()).add(record.semantic)
    source_pairs = [(item.source, item.records) for item in existing]
    source_pairs.append((source, tuple(records)))
    for imported_source, imported_records in source_pairs:
        key = (imported_source.vendor_id, imported_source.product_id)
        families = {
            item.protocol_family for item in imported_records if item.protocol_family
        }
        if key != (None, None):
            if imported_source.protocol_family:
                families.add(imported_source.protocol_family)
            by_identity.setdefault(key, set()).update(families)
        if imported_source is source:
            continue
        for current in records:
            if any(_record_fingerprint(current, include_source=False) == _record_fingerprint(other, include_source=False) for other in imported_records):
                corroborating += 1
    for key, semantics in sorted(by_command.items(), key=lambda item: repr(item[0])):
        if len(semantics) > 1:
            messages.add(f"conflicting meanings for {key}: {', '.join(sorted(semantics))}")
    for key, semantics in sorted(by_raw.items(), key=lambda item: repr(item[0])):
        if len(semantics) > 1:
            messages.add(
                f"same raw frame has conflicting interpretations in {key[0] or 'unknown family'}: "
                + ", ".join(sorted(semantics))
            )
    for key, lengths in sorted(by_report.items(), key=lambda item: repr(item[0])):
        if len(lengths) > 1:
            messages.add(f"conflicting report lengths for {key}: {', '.join(map(str, sorted(lengths)))}")
    for key, families in sorted(by_identity.items(), key=lambda item: repr(item[0])):
        if len(families) > 1:
            messages.add(f"identity {key} has conflicting protocol families: {', '.join(sorted(families))}")
    return tuple(sorted(messages)), corroborating


def _dialogue_projection(
    records: Sequence[NormalizedCaptureRecord], source: VendorCaptureSource,
) -> LabExperiment | None:
    timed = [record for record in records if record.timestamp_ns is not None]
    if not timed:
        return None
    physical = {
        "source_digest": source.content_sha256,
        "vendor_id": source.vendor_id,
        "product_id": source.product_id,
        "model": source.product_model,
        "instance_fingerprint": f"import:{source.content_sha256}",
    }
    observations = tuple(ProtocolObservation(
        record.observation_id,
        record.channel or f"{record.transport or 'unknown'}:{record.report_type or 'unknown'}:{record.report_id}",
        int(record.timestamp_ns), record.order, record.physical_frame,
        LabInterval.BASELINE, direction=record.direction.value,
        report_id=record.report_id, connection_generation=0,
    ) for record in timed)
    minimum = min(item.timestamp_ns for item in observations)
    maximum = max(item.timestamp_ns for item in observations)
    interval = LabIntervalRecord(LabInterval.BASELINE, 0, minimum, maximum, len(observations))
    dialogue_observations: dict[str, DialogueObservation] = {}
    for record in timed:
        if record.direction is CaptureDirection.UNKNOWN:
            continue
        dialogue_observations[record.observation_id] = DialogueObservation(
            record.observation_id, f"import:{source.content_sha256}",
            record.channel or "capture", record.transport or "unknown",
            Direction.OUT if record.direction is CaptureDirection.HOST_TO_DEVICE else Direction.IN,
            record.report_type or "unknown", record.report_id, 0,
            int(record.timestamp_ns), record.order, record.logical_payload,
            transaction_tag=record.transaction_id,
            grammar=record.protocol_family,
            status=(str(dict(record.decoded_fields).get("status")) if "status" in dict(record.decoded_fields) else None),
        )
    request_by_transaction = {
        record.transaction_id: dialogue_observations.get(record.observation_id)
        for record in timed if record.role is CaptureRole.REQUEST and record.transaction_id is not None
    }
    dialogues: list[DialogueRecord] = []
    pushed = []
    for record in timed:
        observation = dialogue_observations.get(record.observation_id)
        if observation is None:
            continue
        request = request_by_transaction.get(record.transaction_id)
        if record.role is CaptureRole.REQUEST:
            dialogues.append(DialogueRecord(DialogueKind.REQUEST, observation, confidence="imported-structure"))
        elif record.role in {CaptureRole.RESPONSE, CaptureRole.STATUS}:
            kind = DialogueKind.RESPONSE
            status = dict(record.decoded_fields).get("status")
            if isinstance(status, int):
                try:
                    kind = status_dialogue_kind(status)
                except AuroraKnowledgeError:
                    pass
            dialogues.append(DialogueRecord(
                kind, observation, request=request,
                confidence="imported-transaction-id" if request else "imported-unpaired",
                ambiguous=request is None,
                reason="capture transaction relationship" if request else "no unambiguous imported request",
            ))
        elif record.role is CaptureRole.PUSH:
            dialogues.append(DialogueRecord(DialogueKind.UNSOLICITED_EVENT, observation, confidence="imported-structure"))
            if record.protocol_family == LAMZU_AURORA_MODERN.name:
                try:
                    pushed.extend(event_to_pushed_states(observation))
                except AuroraKnowledgeError:
                    pass
    experiment = LabExperiment(
        _stable_id("vendor-import", source.content_sha256), physical, 0,
        "offline vendor capture import", None, (interval,), observations,
        dialogues=tuple(dialogues), pushed_states=tuple(pushed),
        provenance=(source.provenance_category.value, source.content_sha256),
        proof_state=ProofState.DECODED if any(item.decoded_fields for item in records) else ProofState.OBSERVED,
        confidence="imported-unreviewed",
    )
    experiment = profile_experiment_timing(experiment)
    route_evidence = []
    for record in records:
        if record.semantic != "routed VID/PID" or record.role is not CaptureRole.RESPONSE:
            continue
        payload_hex = dict(record.decoded_fields).get("payload_hex")
        if not isinstance(payload_hex, str):
            continue
        try:
            identity = decode_routed_identity(bytes.fromhex(payload_hex))
        except (ValueError, AuroraKnowledgeError):
            continue
        route_evidence.append(aurora_routed_identity_evidence(
            experiment, identity,
            source_route=RouteEndpoint(
                transport=record.transport or "unknown",
                interface_number=record.interface_number,
                endpoint=record.endpoint,
                channel=record.channel,
                namespace=record.report_type,
                report_id=record.report_id,
                direction=record.direction.value,
            ),
            source_observation_ids=(record.observation_id,),
            receiver_usb_pid=source.receiver_product_id or source.product_id,
        ))
    if route_evidence:
        experiment = analyze_receiver_child_routing(
            experiment, supplied_evidence=route_evidence,
            receiver_identity=(
                f"usb:{source.receiver_vendor_id or source.vendor_id:04x}:"
                f"{source.receiver_product_id or source.product_id:04x}"
                if (source.receiver_vendor_id or source.vendor_id) is not None
                and (source.receiver_product_id or source.product_id) is not None else None
            ),
        )
    if pushed:
        experiment = analyze_power_state(
            experiment, session_id=f"import:{source.content_sha256}",
            charging_action_available=False,
        )
    return experiment


def import_vendor_capture_bytes(
    raw: bytes,
    *,
    filename: str,
    import_date: str | None = None,
    adapters: Sequence[CaptureFormatAdapter] = DEFAULT_ADAPTERS,
    existing: Sequence[VendorCaptureImport] = (),
) -> VendorCaptureImport:
    """Import one bounded capture without opening hardware or transmitting data."""

    if len(raw) > MAX_CAPTURE_BYTES:
        raise VendorCaptureError("capture file exceeds bounded maximum")
    digest = sha256(raw).hexdigest()
    adapter = detect_capture_adapter(raw, filename, adapters=adapters)
    document = adapter.parse(raw)
    source_raw = document.get("source", {})
    if not isinstance(source_raw, dict):
        raise VendorCaptureError("capture source metadata must be an object")
    source, source_warnings = _source_from_raw(
        source_raw, filename=filename, digest=digest,
        import_date=import_date or date.today().isoformat(),
    )
    duplicate = next((item for item in existing if item.source.content_sha256 == digest), None)
    if duplicate is not None:
        return replace(duplicate, manifest=replace(duplicate.manifest, duplicate_import=True))
    raw_records = document.get("records")
    if not isinstance(raw_records, list):
        raise VendorCaptureError("capture records must be an array")
    if len(raw_records) > MAX_RECORDS:
        raise VendorCaptureError("capture record count exceeds bounded maximum")
    records: list[NormalizedCaptureRecord] = []
    warnings = list(source_warnings)
    malformed = 0
    duplicates = 0
    seen: set[tuple[object, ...]] = set()
    for order, item in enumerate(raw_records):
        if not isinstance(item, dict) or "_parse_error" in item:
            malformed += 1
            warnings.append(str(item.get("_parse_error", f"record {order} is not an object")) if isinstance(item, dict) else f"record {order} is not an object")
            continue
        try:
            record = _raw_record(item, order=order, source=source)
        except VendorCaptureError as exc:
            malformed += 1
            warnings.append(f"record {order}: {exc}")
            continue
        fingerprint = _record_fingerprint(record)
        if fingerprint in seen:
            duplicates += 1
            continue
        seen.add(fingerprint)
        records.append(record)
        warnings.extend(f"record {order}: {warning}" for warning in record.parser_warnings)
    enriched = _enrich_aurora(records, source)
    conflicts, corroborating = _conflicts(enriched, source, existing)
    evidence = tuple(_evidence_record(item, source, conflicts=conflicts) for item in enriched)
    families = tuple(sorted({item.protocol_family for item in enriched if item.protocol_family}))
    identities = tuple(filter(None, (
        f"{source.vendor_id:04x}:{source.product_id:04x}"
        if source.vendor_id is not None and source.product_id is not None else None,
        f"receiver:{source.receiver_vendor_id:04x}:{source.receiver_product_id:04x}"
        if source.receiver_vendor_id is not None and source.receiver_product_id is not None else None,
    )))
    manifest = VendorImportManifest(
        digest, adapter.name, len(raw_records), len(enriched), malformed,
        sum(item.semantic is None for item in enriched), duplicates,
        sum(item.role is CaptureRole.REQUEST for item in enriched),
        sum(item.role in {CaptureRole.RESPONSE, CaptureRole.STATUS} for item in enriched),
        sum(item.role is CaptureRole.PUSH for item in enriched),
        sum(item.dangerous for item in enriched), families, identities,
        tuple(dict.fromkeys(warnings)), conflicts, corroborating_records=corroborating,
    )
    return VendorCaptureImport(
        source, enriched, evidence, manifest,
        _dialogue_projection(enriched, source),
    )


def import_vendor_capture(
    path: str | Path,
    *,
    import_date: str | None = None,
    adapters: Sequence[CaptureFormatAdapter] = DEFAULT_ADAPTERS,
    existing: Sequence[VendorCaptureImport] = (),
) -> VendorCaptureImport:
    path = Path(path)
    try:
        size = path.stat().st_size
        if size > MAX_CAPTURE_BYTES:
            raise VendorCaptureError("capture file exceeds bounded maximum")
        raw = path.read_bytes()
    except OSError as exc:
        raise VendorCaptureError(f"could not read capture: {exc}") from exc
    return import_vendor_capture_bytes(
        raw, filename=path.name, import_date=import_date,
        adapters=adapters, existing=existing,
    )


def review_vendor_capture(
    imported: VendorCaptureImport,
    status: CaptureReviewStatus,
) -> VendorCaptureImport:
    """Apply a human review disposition without promoting proof or authority."""

    records = tuple(replace(item, review_status=status) for item in imported.records)
    evidence = tuple(replace(
        item,
        review_status=status,
        evidence=replace(
            item.evidence,
            details={
                **dict(item.evidence.details),
                "review_status": status.value,
                "confidence": (
                    "accepted-prior-knowledge"
                    if status is CaptureReviewStatus.ACCEPTED else status.value
                ),
                "write_authorized": False,
                "experimentable": False,
            },
        ),
    ) for item in imported.evidence_records)
    manifest = replace(imported.manifest, review_status=status)
    return replace(imported, records=records, evidence_records=evidence, manifest=manifest)


def accepted_vendor_evidence(
    imports: Iterable[VendorCaptureImport],
) -> tuple[DiscoveryEvidence, ...]:
    """Return human-accepted prior knowledge, never runtime proof or authority."""

    return tuple(
        item.evidence
        for imported in sorted(imports, key=lambda value: value.source.content_sha256)
        for item in sorted(imported.evidence_records, key=lambda value: value.evidence_id)
        if item.review_status is CaptureReviewStatus.ACCEPTED
        and item.proof_state in {ProofState.OBSERVED, ProofState.DECODED}
        and not item.experimentable
    )


def _json_safe(value: object) -> object:
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return value


def import_to_document(imported: VendorCaptureImport) -> dict[str, object]:
    """Serialize the durable staging record; derived Lab analysis is rebuildable."""

    return {
        "schema_version": IMPORT_SCHEMA_VERSION,
        "source": _json_safe(asdict(imported.source)),
        "records": [_json_safe(asdict(item)) for item in imported.records],
        "manifest": _json_safe(asdict(imported.manifest)),
        "evidence": [{
            "evidence_id": item.evidence_id,
            "observation_id": item.observation_id,
            "proof_state": item.proof_state.value,
            "provenance_category": item.provenance_category.value,
            "review_status": item.review_status.value,
            "dangerous": item.dangerous,
            "experimentable": False,
            "contradictions": list(item.contradictions),
            "discovery_evidence": {
                "level": item.evidence.level.name,
                "code": item.evidence.code,
                "message": item.evidence.message,
                "source": item.evidence.source,
                "details": _json_safe(dict(item.evidence.details)),
            },
        } for item in imported.evidence_records],
    }


def _decode_bytes(value: object) -> bytes:
    if not isinstance(value, dict) or set(value) != {"bytes_hex"} or not isinstance(value["bytes_hex"], str):
        raise VendorCaptureError("persisted byte field is invalid")
    try:
        return bytes.fromhex(value["bytes_hex"])
    except ValueError as exc:
        raise VendorCaptureError("persisted byte field is not hexadecimal") from exc


def import_from_document(document: Mapping[str, object]) -> VendorCaptureImport:
    """Load schema 1 and the minimal pre-release schema 0 compatibility form."""

    schema = document.get("schema_version", 0)
    if schema not in {0, IMPORT_SCHEMA_VERSION}:
        raise VendorCaptureError("unsupported persisted vendor-import schema")
    source_raw = document.get("source")
    records_raw = document.get("records", [])
    manifest_raw = document.get("manifest")
    if not isinstance(source_raw, dict) or not isinstance(records_raw, list) or not isinstance(manifest_raw, dict):
        raise VendorCaptureError("persisted vendor import is incomplete")
    source_values = dict(source_raw)
    source_values["provenance_category"] = ProvenanceCategory(source_values.get("provenance_category", "unknown"))
    source = VendorCaptureSource(**source_values)
    records: list[NormalizedCaptureRecord] = []
    for raw in records_raw:
        if not isinstance(raw, dict):
            raise VendorCaptureError("persisted record must be an object")
        values = dict(raw)
        values.setdefault("source_sequence", None)
        for name in ("physical_frame", "logical_payload"):
            values[name] = _decode_bytes(values[name])
        values["direction"] = CaptureDirection(values.get("direction", "unknown"))
        values["role"] = CaptureRole(values.get("role", "unknown"))
        values["review_status"] = CaptureReviewStatus(values.get("review_status", "imported_unreviewed"))
        for name in ("transfer_metadata", "decoded_fields"):
            values[name] = tuple(tuple(item) for item in values.get(name, ()))
        values["parser_warnings"] = tuple(values.get("parser_warnings", ()))
        records.append(NormalizedCaptureRecord(**values))
    manifest_values = dict(manifest_raw)
    manifest_values["protocol_families_recognized"] = tuple(manifest_values.get("protocol_families_recognized", ()))
    manifest_values["identities_observed"] = tuple(manifest_values.get("identities_observed", ()))
    manifest_values["warnings"] = tuple(manifest_values.get("warnings", ()))
    manifest_values["conflicts"] = tuple(manifest_values.get("conflicts", ()))
    manifest_values["review_status"] = CaptureReviewStatus(manifest_values.get("review_status", "imported_unreviewed"))
    manifest = VendorImportManifest(**manifest_values)
    conflicts = manifest.conflicts
    evidence = tuple(_evidence_record(item, source, conflicts=conflicts) for item in records)
    return VendorCaptureImport(source, tuple(records), evidence, manifest, _dialogue_projection(records, source))


class VendorCaptureStore:
    """Content-addressed local staging store for auditable imports."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or (get_profile_directory().parent / "vendor-captures")

    def path_for_digest(self, digest: str) -> Path:
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise VendorCaptureError("unsafe source digest")
        return self.directory / f"{digest}.json"

    def save(self, imported: VendorCaptureImport) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        destination = self.path_for_digest(imported.source.content_sha256)
        payload = import_to_document(imported)
        with NamedTemporaryFile(
            "w", encoding="utf-8", dir=self.directory,
            prefix=f".{imported.source.content_sha256}.", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.replace(temporary, destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return destination

    def load(self, path: Path) -> VendorCaptureImport:
        try:
            raw = path.read_bytes()
            if len(raw) > MAX_PERSISTED_BYTES:
                raise VendorCaptureError("persisted import exceeds bounded maximum")
            document = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            raise VendorCaptureError(f"could not load persisted import: {exc}") from exc
        if not isinstance(document, dict):
            raise VendorCaptureError("persisted import root must be an object")
        _bounded_json(document)
        imported = import_from_document(document)
        if path.name != f"{imported.source.content_sha256}.json":
            raise VendorCaptureError("persisted import filename does not match source digest")
        return imported

    def load_all_safe(self) -> tuple[tuple[VendorCaptureImport, ...], tuple[str, ...]]:
        if not self.directory.exists():
            return (), ()
        imports: list[VendorCaptureImport] = []
        warnings: list[str] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                imports.append(self.load(path))
            except VendorCaptureError as exc:
                warnings.append(f"{path.name}: {exc}")
        return tuple(imports), tuple(warnings)

    def preview_file(self, path: str | Path, *, import_date: str | None = None) -> VendorCaptureImport:
        """Parse and normalize without persisting; used for explicit TUI review."""

        existing, _warnings = self.load_all_safe()
        return import_vendor_capture(path, import_date=import_date, existing=existing)

    def import_file(self, path: str | Path, *, import_date: str | None = None) -> VendorCaptureImport:
        imported = self.preview_file(path, import_date=import_date)
        if not imported.manifest.duplicate_import:
            self.save(imported)
        return imported
