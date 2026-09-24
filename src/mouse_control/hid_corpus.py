# SPDX-License-Identifier: AGPL-3.0-or-later
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
from .hid_semantic_candidates import (PhysicalDpiValidation,
                                      infer_action_conditioned_candidates)
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
    def member_sort_key(field_id: str) -> tuple[str, int]:
        if "/member-" not in field_id:
            return field_id, -1
        parent_id, member = field_id.rsplit("/member-", 1)
        return parent_id, int(member)

    for field_id in sorted(values, key=member_sort_key):
        parent_id = field_id.split("/member-", 1)[0]
        semantics = semantic_index.get(parent_id, ())
        member_index = (int(field_id.rsplit("/member-", 1)[1])
                        if "/member-" in field_id else None)
        selected_semantics = (semantics[min(member_index, len(semantics) - 1):
                                        min(member_index, len(semantics) - 1) + 1]
                              if member_index is not None and semantics else semantics)
        is_vendor = any(item.semantic_class is HidSemanticClass.VENDOR_DEFINED
                        for item in selected_semantics)
        names = (f"Vendor member {member_index}" if is_vendor and member_index is not None
                 else ", ".join(item.name for item in selected_semantics) or "Undeclared field")
        observed = values[field_id]
        behavior = profiles[field_id]
        activity = sum(value != 0 for value in observed)
        text = (f"{names} [{field_id}]: active {activity}/{len(observed)}; "
                f"values={tuple(sorted(set(observed)))}; behavior={behavior.classification.value}")
        if behavior.classification.value == "cyclic_state":
            sequence = [value for left, value in zip([None, *observed[:-1]], observed)
                        if left != value]
            text += "; sequence=" + "→".join(str(value) for value in sequence)
        if is_vendor:
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


def format_action_conditioned_candidates(
    positive_device: HidCorpusDevice,
    positive_mode: str,
    negative_controls: Mapping[str, tuple[DecodedHidReport, ...]],
    physical_validations: Mapping[str, PhysicalDpiValidation] | None = None,
) -> str:
    """Render read-only semantic candidates from labelled corpus evidence."""
    label = positive_device.metadata.get("experiment_label", positive_mode)
    if not isinstance(label, str):
        raise ValueError("corpus experiment_label must be a string")
    candidates = infer_action_conditioned_candidates(
        {label: positive_device.decoded_capture(positive_mode)}, negative_controls,
        physical_validations=physical_validations)
    lines = ["Semantic candidates:"]
    if not candidates:
        lines.append("  none")
        return "\n".join(lines)
    for candidate in candidates:
        lines.extend((
            f"  {candidate.behavior.value.upper()}",
            f"    source: {candidate.source_field}",
            f"    evidence: {candidate.evidence_level.value.upper()}",
            f"    values: {candidate.observed_values}",
            "    sequence: " + "→".join(
                str(value) for transition in candidate.transition_sequence
                for value in transition[:1]) +
                (f"→{candidate.transition_sequence[-1][1]}"
                 if candidate.transition_sequence else ""),
            "    negative controls: " +
                (", ".join(f"{name}=clean" for name in candidate.negative_controls)
                 if candidate.negative_controls else "none supplied"),
        ))
        if candidate.evidence_level.value == "validated":
            lines.extend((
                f"    configured labels: {dict(candidate.configured_dpi_mapping)}",
                f"    measured CPI: {dict(candidate.measured_cpi_mapping)}",
                "    write authority: false",
            ))
    return "\n".join(lines)


def physical_dpi_validations(
    device: HidCorpusDevice,
    profile: Mapping[str, object],
) -> Mapping[str, PhysicalDpiValidation]:
    """Join exact report members to independent physical CPI evidence.

    The calibrated profile's raw mapping remains correlated and read-only.  A
    complete high-confidence physical cycle with wrap can validate only the
    semantic meaning of the exact matching observation member.
    """
    from .calibrated_profiles import validate_calibrated_profile

    validate_calibrated_profile(profile)
    identity = profile.get("identity")
    capture_identity = device.metadata.get("device")
    if not isinstance(identity, Mapping) or not isinstance(capture_identity, Mapping):
        raise ValueError("calibrated profile and corpus require device identity")
    expected_identity = (
        capture_identity.get("bus_type"), capture_identity.get("vendor_id"),
        capture_identity.get("product_id"),
    )
    actual_identity = (
        identity.get("bus"), identity.get("vendor_id"), identity.get("product_id"),
    )
    if actual_identity != expected_identity:
        raise ValueError("calibrated profile does not match corpus device identity")

    cycle = profile.get("dpi_cycle")
    if not isinstance(cycle, Mapping):
        raise ValueError("calibrated profile requires physical DPI-cycle evidence")
    order = cycle.get("configured_order")
    states = cycle.get("states")
    if (cycle.get("semantic_evidence") != "physically-calibrated" or
            cycle.get("wrap_confirmed") is not True or
            not isinstance(order, list) or not isinstance(states, list) or
            len(order) < 2 or len(states) != len(order) + 1 or
            len(set(order)) != len(order) or
            any(not isinstance(value, int) or isinstance(value, bool) or value <= 0
                for value in order)):
        raise ValueError("calibrated profile does not prove a complete physical DPI cycle")
    configured_states = []
    for state in states:
        if not isinstance(state, Mapping):
            raise ValueError("calibrated profile has a malformed physical state")
        configured = state.get("configured_dpi")
        measured = state.get("measured_cpi")
        if (state.get("confidence") != "high" or not isinstance(configured, int) or
                configured <= 0 or
                not isinstance(measured, (int, float)) or
                abs(float(measured) - configured) / configured > 0.15):
            raise ValueError("calibrated profile lacks high-confidence physical CPI agreement")
        configured_states.append(configured)
    if configured_states[:-1] != order or configured_states[-1] != order[0]:
        raise ValueError("calibrated profile physical states do not prove cycle wrap")

    result: dict[str, PhysicalDpiValidation] = {}
    mappings = profile.get("raw_mappings")
    assert isinstance(mappings, list)  # checked by validate_calibrated_profile
    action_reports = profile.get("action_reports")
    if not isinstance(action_reports, list):
        raise ValueError("calibrated profile requires action-specific report evidence")
    for mapping in mappings:
        if not isinstance(mapping, Mapping):
            continue
        report = mapping.get("report")
        configured_raw = mapping.get("raw_to_configured_dpi")
        measured_raw = mapping.get("raw_to_measured_cpi")
        offset = mapping.get("offset")
        if (mapping.get("write_authorized") is not False or
                mapping.get("confidence") != "correlated" or
                not isinstance(report, Mapping) or not isinstance(offset, int) or
                not isinstance(configured_raw, Mapping) or
                not isinstance(measured_raw, Mapping) or
                not isinstance(mapping.get("observations"), int) or
                mapping["observations"] < len(order)):
            continue
        report_identity = (
            report.get("bus"), report.get("vendor_id"), report.get("product_id"),
        )
        if (report_identity != expected_identity or report.get("report_type") != "input" or
                not isinstance(report.get("interface_number"), int) or
                not any(isinstance(item, Mapping) and item.get("role") == "state-bearing" and
                        item.get("identity") == report for item in action_reports)):
            continue
        descriptor_hash = report.get("descriptor_sha256")
        descriptors = [item for item in device.descriptors.values()
                       if item.fingerprint == descriptor_hash]
        if len(descriptors) != 1:
            continue
        descriptor = descriptors[0]
        report_id = report.get("report_id")
        definitions = [item for item in descriptor.input_reports
                       if item.report_id == report_id and
                       item.byte_length == report.get("report_length")]
        if len(definitions) != 1:
            continue
        fields = [item for item in descriptor.fields
                  if item.report_type == "input" and item.report_id == report_id and
                  item.has_positional_members and item.report_size == 8 and
                  item.wire_bit_offset // 8 <= offset <
                  (item.wire_bit_offset + item.bit_length) // 8]
        if len(fields) != 1:
            continue
        member = offset - fields[0].wire_bit_offset // 8
        source_field = fields[0].member_stable_id(descriptor.fingerprint, member)
        try:
            configured_mapping = {int(raw): int(dpi) for raw, dpi in configured_raw.items()}
            measured_mapping = {int(raw): int(cpi) for raw, cpi in measured_raw.items()}
        except (TypeError, ValueError):
            continue
        if (set(configured_mapping.values()) != set(order) or
                set(configured_mapping) != set(measured_mapping)):
            continue
        validation = PhysicalDpiValidation(
            source_field, configured_mapping, measured_mapping,
            fields[0].stable_id(descriptor.fingerprint), member,
            dict(report), offset, int(mapping["observations"]))
        previous = result.get(source_field)
        if previous is not None and previous != validation:
            raise ValueError("calibrated profile has ambiguous physical mappings for one member")
        result[source_field] = validation
    return result


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
