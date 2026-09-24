# SPDX-License-Identifier: AGPL-3.0-or-later
import hashlib
import json
from copy import deepcopy

import pytest

from mouse_control.hid_behavior import HidBehaviorClass, profile_reports
from mouse_control.calibrated_profiles import (promote_descriptor_member_binding,
                                               validate_calibrated_profile)
from mouse_control.hid_corpus import (HidCaptureRecord, SCHEMA, descriptor_model, format_capture_explanation, format_semantic_inventory,
                                      format_action_conditioned_candidates,
                                      load_hid_capture, load_hid_corpus_device,
                                      physical_dpi_validations,
                                      write_hid_corpus_capture)
from mouse_control.hid_semantics import HidSemanticClass, interpret_descriptor
from mouse_control.hid_semantic_candidates import (SemanticBehavior,
                                                    infer_action_conditioned_candidates)


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
            "device": {"bus_type": 3, "vendor_id": 0x046D, "product_id": 0x4074,
                       "stable_physical_fingerprint": "opaque"},
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
    assert "X [" in movement and "values=(-2, -1); behavior=relative_activity" in movement
    assert "Y [" in movement and "values=(-1,); behavior=relative_activity" in movement
    assert "Wheel" in movement and "AC Pan" in movement
    assert "Vendor-field activity:" in movement
    assert "Diagnostics: none" in movement


def test_variable_members_profile_independently_and_promote_clean_dpi_cycle():
    # A 19-byte vendor report: three static header members, one state member,
    # and fifteen static padding members.  These are generic fixture bytes,
    # not a production device layout.
    descriptor = bytes.fromhex("06 00 FF 09 23 A1 01 85 11 15 00 25 FF 75 08 95 13 81 02 C0")
    from mouse_control.hid_descriptor import parse_report_descriptor
    from mouse_control.hid_report import decode_input_report
    parsed = parse_report_descriptor(descriptor)
    def packet(value): return bytes([0x11, 1, 7, 16, value] + [0] * 15)
    positive = tuple(decode_input_report(parsed, packet(value)) for value in (0, 1, 2, 3, 4, 0))
    controls = tuple(decode_input_report(parsed, packet(0)) for _ in range(3))
    profiles = profile_reports(positive)
    cycling = [item for item in profiles.values() if item.classification is HidBehaviorClass.CYCLIC_STATE]
    assert len(cycling) == 1
    assert cycling[0].field_id.endswith("/member-3")
    assert all(item.classification is HidBehaviorClass.STATIC for key, item in profiles.items()
               if key != cycling[0].field_id)
    candidate, = infer_action_conditioned_candidates({"dpi-button": positive}, {"movement": controls, "left-click": controls})
    assert candidate.behavior is SemanticBehavior.DPI_STAGE_INDEX
    assert candidate.source_field == cycling[0].field_id
    assert candidate.observed_values == (0, 1, 2, 3, 4)
    assert candidate.negative_controls == {"movement": 0, "left-click": 0}
    assert infer_action_conditioned_candidates({"dpi-button": positive}, {}) == ()


def test_g305_report_17_vendor_array_gets_positional_observation_members(tmp_path):
    # Sanitized from the real G305 descriptor's Report-17 collection.  The
    # Main flags are deliberately 0x00 (Data, Array, Absolute); positional
    # observation must not rewrite that descriptor fact to Variable.
    descriptor = bytes.fromhex(
        "06 00 FF 09 02 A1 01 85 11 75 08 95 13 15 00 26 FF 00 "
        "09 02 81 00 09 02 91 00 C0")
    reports = tuple(bytes([0x11, 1, 7, 16, value] + [0] * 15)
                    for value in (0, 1, 2, 3, 4, 0))
    meta = metadata()
    meta["interfaces"] = [{"interface_id": "vendor", "descriptor_file": "vendor.bin",
                           "descriptor_sha256": hashlib.sha256(descriptor).hexdigest()}]
    write_hid_corpus_capture(
        tmp_path, meta, {"vendor": descriptor}, "dpi-button",
        [HidCaptureRecord(index, "vendor", 17, report) for index, report in enumerate(reports)])
    corpus = load_hid_corpus_device(tmp_path)
    field = corpus.descriptors["vendor"].fields[0]
    assert not field.is_variable
    decoded = corpus.decoded_capture("dpi-button")
    assert decoded[0].values[3].parent_field_id == field.stable_id(corpus.descriptors["vendor"].fingerprint)
    assert decoded[0].values[3].field_id.endswith("/member-3")
    assert decoded[0].values[3].array_index == decoded[0].values[3].member_index == 3
    profiles = profile_reports(decoded)
    assert profiles[decoded[0].values[3].field_id].classification is HidBehaviorClass.CYCLIC_STATE
    assert all(profile.classification is HidBehaviorClass.STATIC
               for field_id, profile in profiles.items() if field_id != decoded[0].values[3].field_id)
    explanation = format_capture_explanation(corpus, "dpi-button")
    assert "Vendor member 3" in explanation
    assert "values=(0, 1, 2, 3, 4); behavior=cyclic_state" in explanation
    assert "sequence=0→1→2→3→4→0" in explanation
    candidates = format_action_conditioned_candidates(
        corpus, "dpi-button", {"idle": (), "pointer-movement": ()})
    assert "DPI_STAGE_INDEX" in candidates
    assert "evidence: CORRELATED" in candidates
    assert "idle=clean, pointer-movement=clean" in candidates

    report_identity = {
        "report_type": "input", "bus": 3, "vendor_id": 0x046D,
        "product_id": 0x4074, "interface_number": 2,
        "descriptor_sha256": hashlib.sha256(descriptor).hexdigest(),
        "report_length": 20, "report_id": 17,
    }
    configured = {str(raw): dpi for raw, dpi in enumerate((800, 1500, 2000, 2500, 3000))}
    measured = {str(raw): cpi for raw, cpi in enumerate((820, 1540, 2050, 2570, 3070))}
    states = [
        {"configured_dpi": dpi, "measured_cpi": cpi, "polling_hz": 1000,
         "confidence": "high"}
        for dpi, cpi in zip((800, 1500, 2000, 2500, 3000, 800),
                            (818, 1543, 2048, 2567, 3067, 823))
    ]
    calibrated = {
        "schema_version": 1, "profile_kind": "calibrated-read-only",
        "identity": {"bus": 3, "vendor_id": 0x046D, "product_id": 0x4074},
        "fingerprints": {"model": "model", "instance": "instance"},
        "dpi_cycle": {
            "configured_order": [800, 1500, 2000, 2500, 3000],
            "states": states, "wrap_confirmed": True,
            "semantic_evidence": "physically-calibrated",
        },
        "action_reports": [{"identity": report_identity, "role": "state-bearing"}],
        "raw_mappings": [{
            "report": report_identity, "offset": 4, "descriptor_roles": ["vendor"],
            "raw_to_configured_dpi": configured, "raw_to_measured_cpi": measured,
            "observations": 5, "confidence": "correlated", "write_authorized": False,
        }],
        "write_authorized": False,
    }
    validations = physical_dpi_validations(corpus, calibrated)
    assert tuple(validations) == (decoded[0].values[3].field_id,)
    validated = format_action_conditioned_candidates(
        corpus, "dpi-button", {"idle": (), "pointer-movement": ()}, validations)
    assert "evidence: VALIDATED" in validated
    assert "configured labels: {0: 800, 1: 1500, 2: 2000, 3: 2500, 4: 3000}" in validated
    assert "measured CPI: {0: 820, 1: 1540, 2: 2050, 3: 2570, 4: 3070}" in validated
    assert "write authority: false" in validated

    promoted = promote_descriptor_member_binding(
        calibrated, validations[decoded[0].values[3].field_id])
    validate_calibrated_profile(promoted)
    source = promoted["transition_sources"][0]
    assert promoted["schema_version"] == 2
    assert source["field_id"] == decoded[0].values[3].field_id
    assert source["parent_field_id"] == decoded[0].values[3].parent_field_id
    assert source["member_index"] == 3
    assert source["semantic_evidence"] == "validated"
    assert source["raw_to_measured_cpi"] == measured
    assert source["write_authorized"] is promoted["write_authorized"] is False
    assert promoted["raw_mappings"][0]["confidence"] == "correlated"

    incomplete = deepcopy(calibrated)
    incomplete["dpi_cycle"]["wrap_confirmed"] = False
    with pytest.raises(ValueError, match="complete physical DPI cycle"):
        physical_dpi_validations(corpus, incomplete)


def test_relative_fields_cannot_be_promoted_to_persistent_state():
    from mouse_control.hid_descriptor import parse_report_descriptor
    from mouse_control.hid_report import decode_input_report
    reports = tuple(decode_input_report(parse_report_descriptor(MOUSE), bytes([0, value, 0, 0]))
                    for value in (0, 1, 2, 0, 1, 2))
    relative = [item for item in profile_reports(reports).values() if item.relative]
    assert relative and {item.classification for item in relative} == {HidBehaviorClass.RELATIVE_ACTIVITY}
