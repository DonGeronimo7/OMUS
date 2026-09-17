"""Interactive, bounded and read-only HID corpus capture command."""
from __future__ import annotations

import hashlib
from pathlib import Path
import time

from .discovery import get_mouse_devices, select_mouse_device
from .generic_hid import capture_input_reports, discover_hid_devices
from .hid_corpus import (HidCaptureRecord, SCHEMA, descriptor_model, format_semantic_inventory,
                         write_hid_corpus_capture)
from .hid_descriptor import parse_report_descriptor

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


def explain_hid_corpus(root: Path) -> int:
    from .hid_corpus import load_hid_corpus_device
    device = load_hid_corpus_device(root)
    print(f"Corpus: {root.name}")
    for identifier, descriptor in device.descriptors.items():
        print(f"\nInterface {identifier}")
        print(format_semantic_inventory(descriptor))
    return 0
