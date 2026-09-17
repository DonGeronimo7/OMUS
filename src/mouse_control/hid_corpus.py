"""Portable, read-only HID semantic corpus records.

Raw descriptors and Input reports remain the source of truth.  This module
does not contain a HID transport and intentionally cannot issue a write.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping

from .hid_descriptor import ParsedHidDescriptor, parse_report_descriptor
from .hid_report import DecodedHidReport, decode_input_report
from .hid_behavior import profile_reports
from .hid_semantics import HidSemanticClass, interpret_descriptor

SCHEMA = "mouse-control-hid-corpus-schema: 1"


@dataclass(frozen=True)
class HidCaptureRecord:
    timestamp_ns: int
    interface_id: str
    report_id: int | None
    raw: bytes

    @classmethod
    def from_json(cls, value: Mapping[str, object]) -> "HidCaptureRecord":
        raw_hex = value.get("raw_hex")
        if not isinstance(raw_hex, str) or not isinstance(value.get("timestamp_ns"), int):
            raise ValueError("capture record requires integer timestamp_ns and raw_hex")
        interface_id = value.get("interface_id", "interface-00")
        if not isinstance(interface_id, str):
            raise ValueError("capture interface_id must be a string")
        report_id = value.get("report_id")
        if report_id is not None and (not isinstance(report_id, int) or not 0 <= report_id <= 255):
            raise ValueError("capture report_id must be null or an unsigned byte")
        try:
            raw = bytes.fromhex(raw_hex)
        except ValueError as exc:
            raise ValueError("capture raw_hex is not hexadecimal") from exc
        return cls(value["timestamp_ns"], interface_id, report_id, raw)

    def to_json(self) -> dict[str, object]:
        return {"timestamp_ns": self.timestamp_ns, "interface_id": self.interface_id,
                "report_id": self.report_id, "raw_hex": self.raw.hex()}


@dataclass(frozen=True)
class HidCorpusDevice:
    root: Path
    metadata: Mapping[str, object]
    descriptors: Mapping[str, ParsedHidDescriptor]

    def capture(self, mode: str) -> tuple[HidCaptureRecord, ...]:
        return load_hid_capture(self, mode)

    def decoded_capture(self, mode: str) -> tuple[DecodedHidReport, ...]:
        previous: dict[str, DecodedHidReport] = {}
        decoded = []
        for item in self.capture(mode):
            descriptor = self.descriptors.get(item.interface_id)
            if descriptor is None:
                raise ValueError(f"capture references unknown interface {item.interface_id!r}")
            report = decode_input_report(descriptor, item.raw, previous=previous.get(item.interface_id))
            previous[item.interface_id] = report
            decoded.append(report)
        return tuple(decoded)


def _read_json(path: Path) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid corpus JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"corpus JSON object required: {path}")
    return value


def load_hid_corpus_device(root: str | Path) -> HidCorpusDevice:
    """Load a version-1 corpus device and parse its authoritative bytes."""
    root = Path(root)
    metadata = _read_json(root / "device.json")
    if metadata.get("schema") != SCHEMA:
        raise ValueError("unsupported HID corpus schema")
    interfaces = metadata.get("interfaces")
    if not isinstance(interfaces, list) or not interfaces:
        raise ValueError("corpus device requires a non-empty interfaces list")
    descriptors: dict[str, ParsedHidDescriptor] = {}
    for interface in interfaces:
        if not isinstance(interface, dict):
            raise ValueError("corpus interface must be an object")
        identifier, filename, expected = interface.get("interface_id"), interface.get("descriptor_file"), interface.get("descriptor_sha256")
        if not all(isinstance(item, str) for item in (identifier, filename, expected)):
            raise ValueError("corpus interface identity, descriptor file, and hash are required")
        raw = (root / "descriptors" / filename).read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        if actual != expected:
            raise ValueError(f"descriptor SHA-256 mismatch for {identifier}")
        descriptors[identifier] = parse_report_descriptor(raw)
    return HidCorpusDevice(root, metadata, descriptors)


def load_hid_capture(device: HidCorpusDevice, mode: str) -> tuple[HidCaptureRecord, ...]:
    """Load a bounded labelled capture; never silently accepts malformed lines."""
    if not mode or "/" in mode or "\\" in mode:
        raise ValueError("invalid capture mode")
    path = device.root / "captures" / f"{mode}.jsonl"
    records = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError("object required")
            records.append(HidCaptureRecord.from_json(value))
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid capture record at {path}:{line_number}") from exc
    return tuple(records)


def format_semantic_inventory(descriptor: ParsedHidDescriptor) -> str:
    """Render descriptor-declared facts without behavior or vendor claims."""
    lines = [f"Descriptor SHA-256: {descriptor.fingerprint}", "Collections:"]
    for collection in descriptor.collections:
        usage = "undeclared" if collection.usage_page is None else f"{collection.usage_page:04X}:{collection.usage or 0:04X}"
        lines.append(f"  {collection.index}: {collection.known_type or collection.collection_type} {usage}")
    lines.append("Input fields:")
    for field in interpret_descriptor(descriptor):
        names = ", ".join(item.name for item in field.semantics)
        lines.append(f"  Report {field.report_id} {field.field_id}: bits {field.bit_offset}+{field.bit_width}; {names}")
    if descriptor.diagnostics:
        lines.append("Diagnostics:")
        lines.extend(f"  {item.severity.value}: {item.code}: {item.message}" for item in descriptor.diagnostics)
    return "\n".join(lines)


def format_capture_explanation(device: HidCorpusDevice, mode: str) -> str:
    """Render decoded Input evidence for one labelled capture.

    This is deliberately derived at display time from immutable raw records,
    rather than serializing an interpretation beside them.
    """
    records = device.capture(mode)
    decoded = device.decoded_capture(mode)
    semantic_index = {}
    for descriptor in device.descriptors.values():
        for field in interpret_descriptor(descriptor):
            semantic_index[field.field_id] = field.semantics
    by_report: dict[int, int] = {}
    values: dict[str, list[int]] = {}
    diagnostics = []
    for report in decoded:
        by_report[report.report_id] = by_report.get(report.report_id, 0) + 1
        diagnostics.extend(report.diagnostics)
        for value in report.values:
            if value.logical_value is not None:
                values.setdefault(value.field_id, []).append(value.logical_value)
    lines = [f"Capture: {mode}", f"Observed Input reports: {len(records)}"]
    if by_report:
        lines.append("Report counts: " + ", ".join(
            f"Report {report_id}: {count}" for report_id, count in sorted(by_report.items())))
    else:
        lines.append("Report counts: none")
    standard, vendor = [], []
    profiles = profile_reports(decoded)
    for field_id in sorted(values):
        semantics = semantic_index.get(field_id, ())
        names = ", ".join(item.name for item in semantics) or "Undeclared field"
        observed = values[field_id]
        behavior = profiles[field_id]
        activity = sum(value != 0 for value in observed)
        text = (f"{names} [{field_id}]: active {activity}/{len(observed)}; "
                f"values={tuple(sorted(set(observed)))}; behavior={behavior.classification.value}")
        if any(item.semantic_class is HidSemanticClass.VENDOR_DEFINED for item in semantics):
            vendor.append(text)
        else:
            standard.append(text)
    lines.append("Decoded standard-field activity:")
    lines.extend(f"  {item}" for item in standard) if standard else lines.append("  none")
    lines.append("Vendor-field activity:")
    lines.extend(f"  {item}" for item in vendor) if vendor else lines.append("  none")
    if diagnostics:
        lines.append("Diagnostics:")
        lines.extend(f"  {item.severity.value}: {item.code}: {item.message}" for item in diagnostics)
    else:
        lines.append("Diagnostics: none")
    return "\n".join(lines)


def descriptor_model(descriptor: ParsedHidDescriptor) -> dict[str, object]:
    """JSON-safe descriptor-declared model stored beside raw descriptor bytes."""
    return {
        "fingerprint": descriptor.fingerprint,
        "reports": [{"report_id": item.report_id, "report_type": item.report_type,
                     "byte_length": item.byte_length, "usage_pages": list(item.usage_pages)}
                    for item in descriptor.reports],
        "collections": [{"index": item.index, "type": item.collection_type,
                         "usage_page": item.usage_page, "usage": item.usage,
                         "parent_index": item.parent_index} for item in descriptor.collections],
        "fields": [{"field_id": item.stable_id(descriptor.fingerprint), "report_id": item.report_id,
                    "report_type": item.report_type, "bit_offset": item.bit_offset,
                    "bit_width": item.bit_length, "logical_minimum": item.logical_minimum,
                    "logical_maximum": item.logical_maximum, "relative": item.is_relative,
                    "variable": item.is_variable, "usages": [list(value) for value in item.usages],
                    "collection_path": list(item.collection_path)} for item in descriptor.fields],
        "diagnostics": [{"severity": item.severity.value, "code": item.code,
                         "message": item.message, "offset": item.offset} for item in descriptor.diagnostics],
    }


def write_hid_corpus_capture(root: str | Path, metadata: Mapping[str, object],
                             descriptors: Mapping[str, bytes], mode: str,
                             records: Iterable[HidCaptureRecord]) -> Path:
    """Write one sanitized capture.  Callers must supply no raw host paths."""
    root = Path(root)
    if metadata.get("schema") != SCHEMA:
        raise ValueError("corpus metadata must declare schema version 1")
    serialized = json.dumps(metadata, sort_keys=True)
    # Names in ``redacted_fields`` are intentionally retained as an audit trail;
    # reject only actual sensitive values or accidentally persisted raw keys.
    forbidden = ("/dev/", "/home/")
    if any(value in serialized.lower() for value in forbidden) or any(
            key in {"device_path", "physical_path", "serial_number", "hostname"}
            for key in metadata if key != "sanitization"):
        raise ValueError("corpus metadata contains unsanitized host identity")
    (root / "descriptors").mkdir(parents=True, exist_ok=True)
    (root / "captures").mkdir(parents=True, exist_ok=True)
    (root / "device.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for identifier, raw in descriptors.items():
        filename = next((item["descriptor_file"] for item in metadata["interfaces"] if item["interface_id"] == identifier), None)
        if not isinstance(filename, str):
            raise ValueError(f"metadata has no descriptor file for {identifier}")
        (root / "descriptors" / filename).write_bytes(raw)
    destination = root / "captures" / f"{mode}.jsonl"
    destination.write_text("".join(json.dumps(item.to_json(), sort_keys=True) + "\n" for item in records), encoding="utf-8")
    return destination
