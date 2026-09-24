# SPDX-License-Identifier: AGPL-3.0-or-later
"""Interactive, bounded and read-only HID corpus capture command."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time

from .discovery import get_mouse_devices, select_mouse_device
from .generic_hid import capture_input_reports, discover_hid_devices
from .hid_corpus import (HidCaptureRecord, SCHEMA, descriptor_model, format_capture_explanation, format_semantic_inventory,
                         format_action_conditioned_candidates, load_hid_corpus_device,
                         physical_dpi_validations,
                         write_hid_corpus_capture)
from .hid_descriptor import parse_report_descriptor
from .hid_semantic_candidates import (SemanticEvidenceLevel,
                                      infer_action_conditioned_candidates)

CAPTURE_MODES = ("descriptor-only", "idle", "pointer-movement", "left-click", "right-click",
                 "middle-click", "wheel", "side-buttons", "dpi-button", "guided-action")


def capture_hid_corpus(destination: Path, mode: str, seconds: float) -> int:
    """Capture descriptors and one explicitly labelled Input-report experiment."""
    if mode not in CAPTURE_MODES:
        raise ValueError("unknown capture mode")
    if seconds <= 0:
        raise ValueError("capture duration must be greater than zero")
    mice = get_mouse_devices()
    selected = select_mouse_device(mice)
    if selected is None:
        return 0
    interfaces = discover_hid_devices(selected)
    if not interfaces:
        print("No matching hidraw interfaces were found.")
        return 1
    raw_descriptors: dict[str, bytes] = {}
    interface_rows = []
    for ordinal, interface in enumerate(interfaces):
        raw = interface.report_descriptor
        digest = hashlib.sha256(raw).hexdigest()
        identifier = f"interface-{ordinal:02d}-{digest[:12]}"
        raw_descriptors[identifier] = raw
        parsed = parse_report_descriptor(raw)
        interface_rows.append({"interface_id": identifier, "descriptor_file": f"{identifier}.bin",
                               "descriptor_sha256": digest, "interface_number": None,
                               "bus_type": selected.bustype, "parsed_descriptor": descriptor_model(parsed)})
    # The opaque fingerprint permits repeatability checks while stripping the
    # physical topology string that can identify a host or receiver port.
    physical_material = repr((selected.bustype, selected.vendor, selected.product, selected.phys,
                              tuple(row["descriptor_sha256"] for row in interface_rows))).encode()
    metadata = {"schema": SCHEMA, "capture_timestamp_ns": time.time_ns(),
                "capture_mode": mode, "experiment_label": mode,
                "mouse_control_commit": "unknown", "device": {"name": selected.name,
                "vendor_id": selected.vendor, "product_id": selected.product,
                "bus_type": selected.bustype,
                "stable_physical_fingerprint": hashlib.sha256(physical_material).hexdigest()},
                "interfaces": interface_rows,
                "sanitization": {"version": 1, "redacted_fields": ["device_path", "physical_path", "serial_number", "hostname"]}}
    records: list[HidCaptureRecord] = []
    if mode != "descriptor-only":
        print(f"Capturing {mode} for {seconds:g} seconds. Perform only that labelled action now.")
        start = time.monotonic_ns()
        for row, interface in zip(interface_rows, interfaces):
            def on_report(raw: bytes, *, interface_id: str = row["interface_id"], descriptor=interface.report_descriptor) -> None:
                numbered = any(item.report_id for item in parse_report_descriptor(descriptor).input_reports)
                records.append(HidCaptureRecord(time.monotonic_ns() - start, interface_id,
                                                raw[0] if numbered and raw else None, raw))
            capture_input_reports(interface, seconds, on_report)
    write_hid_corpus_capture(destination, metadata, raw_descriptors, mode, records)
    print(f"Sanitized corpus capture saved to {destination}")
    print("No Output, Feature, or other HID write was issued.")
    return 0


def _corpus_identity(device) -> tuple[object, tuple[str, ...]]:
    return (device.metadata.get("device", {}).get("stable_physical_fingerprint"),
            tuple(sorted(descriptor.fingerprint for descriptor in device.descriptors.values())))


def explain_hid_corpus(root: Path, negative_control_roots: tuple[Path, ...] = (),
                       calibrated_profile: Path | None = None,
                       persist_validated_binding: bool = False) -> int:
    device = load_hid_corpus_device(root)
    validations = None
    raw_profile = None
    if calibrated_profile is not None:
        raw_profile = json.loads(calibrated_profile.read_text(encoding="utf-8"))
        if not isinstance(raw_profile, dict):
            raise ValueError("calibrated profile must contain a JSON object")
        validations = physical_dpi_validations(device, raw_profile)
    print(f"Corpus: {root.name}")
    for identifier, descriptor in device.descriptors.items():
        print(f"\nInterface {identifier}")
        print(format_semantic_inventory(descriptor))
    for capture in sorted((root / "captures").glob("*.jsonl")):
        print()
        print(format_capture_explanation(device, capture.stem))
        if capture.stem == device.metadata.get("experiment_label") == "dpi-button":
            negative_controls = {}
            for control_root in negative_control_roots:
                control = load_hid_corpus_device(control_root)
                if _corpus_identity(control) != _corpus_identity(device):
                    raise ValueError(f"negative control is not from the same corpus device: {control_root}")
                label = control.metadata.get("experiment_label")
                mode = control.metadata.get("capture_mode")
                if not isinstance(label, str) or not isinstance(mode, str) or label == "dpi-button":
                    raise ValueError(f"invalid negative-control experiment: {control_root}")
                negative_controls[label] = control.decoded_capture(mode)
            print()
            print(format_action_conditioned_candidates(
                device, capture.stem, negative_controls, validations))
            if persist_validated_binding:
                if calibrated_profile is None or validations is None:
                    raise ValueError("persisting requires --calibrated-profile")
                candidates = infer_action_conditioned_candidates(
                    {"dpi-button": device.decoded_capture(capture.stem)},
                    negative_controls, physical_validations=validations)
                validated = [candidate for candidate in candidates
                             if candidate.evidence_level is SemanticEvidenceLevel.VALIDATED]
                if len(validated) != 1 or validated[0].source_field not in validations:
                    raise ValueError("exactly one clean physically validated member is required")
                from .calibrated_profiles import (promote_descriptor_member_binding,
                                                  save_calibrated_profile)
                promoted = promote_descriptor_member_binding(
                    raw_profile, validations[validated[0].source_field])
                destination = save_calibrated_profile(promoted)
                print(f"Persisted validated descriptor binding: {destination}")
    return 0
