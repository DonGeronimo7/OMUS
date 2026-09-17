import hashlib
import json

import pytest

from mouse_control.hid_behavior import HidBehaviorClass, profile_reports
from mouse_control.hid_corpus import (HidCaptureRecord, SCHEMA, descriptor_model, format_capture_explanation, format_semantic_inventory,
                                      load_hid_capture, load_hid_corpus_device,
                                      write_hid_corpus_capture)
from mouse_control.hid_semantics import HidSemanticClass, interpret_descriptor


MOUSE = bytes.fromhex(
    "05 01 09 02 A1 01 09 01 A1 00 05 09 19 01 29 05 15 00 25 01 "
    "95 05 75 01 81 02 95 01 75 03 81 01 05 01 09 30 09 31 09 38 "
    "15 81 25 7F 75 08 95 03 81 06 C0 C0")
VENDOR = bytes.fromhex("06 00 FF 09 23 A1 01 15 00 25 04 75 03 95 01 81 02 C0")
NUMBERED_MOUSE = bytes.fromhex(
    "05 01 09 02 A1 01 85 02 09 01 A1 00 05 09 19 01 29 05 15 00 25 01 "
    "95 05 75 01 81 02 95 01 75 03 81 01 95 01 75 08 81 01 05 01 09 30 09 31 15 81 25 7F "
    "75 08 95 02 81 06 09 38 95 01 81 06 05 0C 0A 38 02 95 01 81 06 06 00 FF "
    "09 01 15 00 25 FF 75 08 95 02 81 02 C0 C0")


def metadata():
    return {"schema": SCHEMA, "capture_mode": "dpi-button", "experiment_label": "dpi-button",
            "capture_timestamp_ns": 1, "mouse_control_commit": "test",
            "device": {"vendor_id": 0x046D, "product_id": 0x4074, "stable_physical_fingerprint": "opaque"},
            "interfaces": [{"interface_id": "pointer", "descriptor_file": "pointer.bin", "descriptor_sha256": hashlib.sha256(MOUSE).hexdigest()},
                           {"interface_id": "vendor", "descriptor_file": "vendor.bin", "descriptor_sha256": hashlib.sha256(VENDOR).hexdigest()}],
            "sanitization": {"version": 1, "redacted_fields": ["device_path", "serial_number"]}}


def test_corpus_replays_authoritative_raw_descriptor_and_reports(tmp_path):
    records = [HidCaptureRecord(index, "vendor", None, bytes([value]))
               for index, value in enumerate((0, 1, 2, 3, 4, 0))]
    write_hid_corpus_capture(tmp_path, metadata(), {"pointer": MOUSE, "vendor": VENDOR}, "dpi-button", records)
    corpus = load_hid_corpus_device(tmp_path)
    decoded = corpus.decoded_capture("dpi-button")
    behavior = next(iter(profile_reports(decoded).values()))
    assert behavior.classification is HidBehaviorClass.CYCLIC_STATE
    assert {semantic.semantic_class for field in interpret_descriptor(corpus.descriptors["pointer"])
            for semantic in field.semantics} >= {HidSemanticClass.BUTTON, HidSemanticClass.POINTER_AXIS, HidSemanticClass.WHEEL}
    assert "Descriptor SHA-256" in format_semantic_inventory(corpus.descriptors["vendor"])
    assert descriptor_model(corpus.descriptors["vendor"])["fields"][0]["field_id"].startswith("HID-F")


def test_corpus_refuses_tampered_descriptor_and_unsanitized_metadata(tmp_path):
    with pytest.raises(ValueError, match="unsanitized"):
        write_hid_corpus_capture(tmp_path, {**metadata(), "device_path": "/home/example"}, {"pointer": MOUSE, "vendor": VENDOR}, "idle", [])
    write_hid_corpus_capture(tmp_path, metadata(), {"pointer": MOUSE, "vendor": VENDOR}, "idle", [])
    (tmp_path / "descriptors" / "vendor.bin").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="SHA-256"):
        load_hid_corpus_device(tmp_path)


def test_corpus_rejects_unknown_interface_and_malformed_capture_records(tmp_path):
    write_hid_corpus_capture(tmp_path, metadata(), {"pointer": MOUSE, "vendor": VENDOR}, "idle", [HidCaptureRecord(1, "unknown", None, b"\0")])
    corpus = load_hid_corpus_device(tmp_path)
    with pytest.raises(ValueError, match="unknown interface"):
        corpus.decoded_capture("idle")
    (tmp_path / "captures" / "idle.jsonl").write_text(json.dumps({"timestamp_ns": "bad", "raw_hex": "00"}) + "\n")
    with pytest.raises(ValueError, match="invalid capture record"):
        load_hid_capture(corpus, "idle")


def test_one_way_sequence_counter_is_not_misclassified_as_cyclic_state():
    records = [HidCaptureRecord(index, "vendor", None, bytes([value]))
               for index, value in enumerate((0, 1, 2, 3, 4))]
    # This deliberately lacks the return-to-origin transition required for a
    # cyclic-state explanation.
    from mouse_control.hid_descriptor import parse_report_descriptor
    from mouse_control.hid_report import decode_input_report
    behavior = next(iter(profile_reports([decode_input_report(parse_report_descriptor(VENDOR), item.raw)
                                          for item in records]).values()))
    assert behavior.classification is HidBehaviorClass.COUNTER


def test_explain_replays_numbered_movement_and_distinguishes_empty_captures(tmp_path):
    meta = metadata()
    meta["interfaces"] = [{"interface_id": "pointer", "descriptor_file": "pointer.bin",
                           "descriptor_sha256": hashlib.sha256(NUMBERED_MOUSE).hexdigest()}]
    descriptors = {"pointer": NUMBERED_MOUSE}
    write_hid_corpus_capture(tmp_path, meta, descriptors, "descriptor-only", [])
    write_hid_corpus_capture(tmp_path, meta, descriptors, "idle", [
        HidCaptureRecord(1, "pointer", 2, bytes.fromhex("02 00 00 00 00 00 00 00 00"))])
    write_hid_corpus_capture(tmp_path, meta, descriptors, "pointer-movement", [
        HidCaptureRecord(1, "pointer", 2, bytes.fromhex("02 00 00 FF FF 00 00 00 00")),
        HidCaptureRecord(2, "pointer", 2, bytes.fromhex("02 00 00 FE FF 01 00 00 00"))])
    corpus = load_hid_corpus_device(tmp_path)
    descriptor_only = format_capture_explanation(corpus, "descriptor-only")
    idle = format_capture_explanation(corpus, "idle")
    movement = format_capture_explanation(corpus, "pointer-movement")
    assert "Observed Input reports: 0" in descriptor_only
    assert "Report 2: 1" in idle and "active 0/" in idle
    assert "Report 2: 2" in movement
    assert "X, Y" in movement and "values=(-2, -1)" in movement
    assert "Wheel" in movement and "AC Pan" in movement
    assert "Vendor-field activity:" in movement
    assert "Diagnostics: none" in movement
