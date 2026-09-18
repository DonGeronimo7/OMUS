import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from mouse_control.discovery_models import EvidenceLevel
from mouse_control.lamzu_aurora import (
    LAMZU_AURORA_LEGACY,
    LAMZU_AURORA_MODERN,
    build_read_request,
    legacy_checksum,
)
from mouse_control.proof_state import ProofState
from mouse_control.setup_tui import ActionKind, SECTIONS, SetupSection
from mouse_control.vendor_capture import (
    CAPTURE_SCHEMA,
    AmbiguousCaptureFormat,
    CaptureReviewStatus,
    ProvenanceCategory,
    UnsupportedCaptureFormat,
    VendorCaptureError,
    VendorCaptureStore,
    accepted_vendor_evidence,
    detect_capture_adapter,
    import_from_document,
    import_to_document,
    import_vendor_capture_bytes,
    review_vendor_capture,
)

from test_setup_tui import controller


def _response(command, payload=b"", *, alignment=0, status=0xA1, target=2, page=0):
    canonical = bytearray(64)
    canonical[0] = status
    canonical[2] = target
    canonical[3] = len(payload)
    canonical[4] = page
    canonical[5] = command
    canonical[6:6 + len(payload)] = payload
    return bytes(canonical) if alignment == 0 else b"\x00" + bytes(canonical[:-1])


def _record(frame, *, sequence, direction="host_to_device", role="request",
            report_type="feature", report_id=0, transaction_id=None, **extra):
    return {
        "sequence": sequence,
        "timestamp_ns": sequence * 1_000_000,
        "direction": direction,
        "role": role,
        "report_type": report_type,
        "report_id": report_id,
        "transaction_id": transaction_id,
        "frame_hex": frame.hex(),
        **extra,
    }


def _document(records, *, source=None):
    return {
        "schema": CAPTURE_SCHEMA,
        "source": source if source is not None else {
            "name": "Aurora public capture",
            "source_type": "official vendor web driver",
            "provenance_category": "official_vendor",
            "vendor": "LAMZU",
            "product_model": "THORN V2",
            "vid": "0x37b0",
            "pid": "0x0032",
            "receiver_vid": "0x37b0",
            "receiver_pid": "0x0032",
            "protocol_family": LAMZU_AURORA_MODERN.name,
            "source_version": "1.0.32",
            "capture_date": "2026-09-18",
            "source_reference": "public vendor package",
        },
        "records": records,
    }


def _encode(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode()


def _aurora_capture():
    battery = build_read_request("battery/charging")
    polling = build_read_request("polling")
    dpi = build_read_request("DPI stages")
    lod = build_read_request("LOD")
    routed = build_read_request("routed VID/PID", arguments=b"\x02")
    reset = bytearray(64)
    reset[2], reset[3], reset[5], reset[6] = 2, 1, 0, 0xC0
    unknown = bytearray(64)
    unknown[2], unknown[3], unknown[5] = 2, 1, 0xFE
    records = [
        _record(battery, sequence=1, transaction_id="battery"),
        _record(_response(0x83, b"\x01\x64", alignment=1), sequence=2,
                direction="device_to_host", role="response", transaction_id="battery"),
        _record(b"\x04\x03\x64\x01\x00\x00\x00", sequence=3, direction="device_to_host",
                role="push", report_type="input", report_id=4),
        _record(dpi, sequence=4, transaction_id="dpi"),
        _record(_response(0x81, b"\x01\x03\x20\x03\x20", page=1), sequence=5,
                direction="device_to_host", role="response", transaction_id="dpi"),
        _record(b"\x04\x01\x01\x03\x20\x03\x20", sequence=6,
                direction="device_to_host", role="push", report_type="input", report_id=4),
        _record(polling, sequence=7, transaction_id="poll"),
        _record(_response(0x80, b"\x01\x08", page=1), sequence=8,
                direction="device_to_host", role="response", transaction_id="poll"),
        _record(b"\x04\x08\x08\x00\x00\x00\x00", sequence=9, direction="device_to_host",
                role="push", report_type="input", report_id=4),
        _record(lod, sequence=10, transaction_id="lod"),
        _record(_response(0x88, b"\x01\x87", page=1), sequence=11,
                direction="device_to_host", role="response", transaction_id="lod"),
        _record(b"\x04\x07\x87\x00\x00\x00\x00", sequence=12, direction="device_to_host",
                role="push", report_type="input", report_id=4),
        _record(b"\x04\x02\x00\x00\x00\x00\x00", sequence=13, direction="device_to_host",
                role="push", report_type="input", report_id=4),
        _record(b"\x04\x06\x01\x00\x00\x00\x00", sequence=14, direction="device_to_host",
                role="push", report_type="input", report_id=4),
        _record(b"\x04\x0d\x01\x01\x00\x00\x00", sequence=15, direction="device_to_host",
                role="push", report_type="input", report_id=4),
        _record(routed, sequence=16, transaction_id="route"),
        _record(_response(0x8B, b"\x37\xb0\x00\x2e", target=1), sequence=17,
                direction="device_to_host", role="response", transaction_id="route"),
        _record(bytes(reset), sequence=18),
        _record(bytes(unknown), sequence=19),
    ]
    return _document(records)


def test_canonical_json_import_preserves_provenance_raw_frames_and_manifest():
    raw = _encode(_aurora_capture())
    imported = import_vendor_capture_bytes(
        raw, filename="aurora.json", import_date="2026-09-18",
    )
    assert imported.source.content_sha256 == sha256(raw).hexdigest()
    assert imported.source.original_filename == "aurora.json"
    assert imported.source.provenance_category is ProvenanceCategory.OFFICIAL_VENDOR
    assert imported.manifest.total_records == 19
    assert imported.manifest.accepted_records == 19
    assert imported.manifest.protocol_families_recognized == (LAMZU_AURORA_MODERN.name,)
    assert imported.manifest.identities_observed == ("37b0:0032", "receiver:37b0:0032")
    assert imported.manifest.conflicts == ()
    assert imported.records[0].physical_frame == build_read_request("battery/charging")
    assert imported.records[0].source_sequence == 1
    assert imported.records[0].original_length == 64
    assert imported.manifest.authority_notice.startswith("Imported evidence is not")


def test_aurora_fixture_projects_alignment_dialogues_pushes_power_and_routing():
    imported = import_vendor_capture_bytes(
        _encode(_aurora_capture()), filename="aurora.json", import_date="2026-09-18",
    )
    response = next(item for item in imported.records if item.transaction_id == "battery" and item.role.value == "response")
    assert dict(response.decoded_fields)["alignment"] == 1
    assert dict(response.decoded_fields)["payload_hex"] == "0164"
    experiment = imported.lab_experiment
    assert experiment is not None
    assert {item.semantic_state_id for item in experiment.pushed_states} >= {
        "lamzu.battery_percent", "lamzu.battery_charging",
        "lamzu.dpi.x_dpi", "lamzu.polling.raw_polling",
        "lamzu.lod.lod_tenths_mm", "lamzu.connection.connected",
        "lamzu.performance.tracking_20k",
    }
    assert experiment.timing_profile is not None
    assert experiment.power_analysis is not None
    assert any(item.decoded_value == 100 for item in experiment.power_evidence)
    assert experiment.routing_analysis is not None
    assert any("002e" in item.child_identity_candidate for item in experiment.routing_evidence)
    assert any(item.ambiguity for item in experiment.routing_evidence)


def test_dangerous_and_unknown_aurora_commands_are_suppressed():
    imported = import_vendor_capture_bytes(
        _encode(_aurora_capture()), filename="aurora.json", import_date="2026-09-18",
    )
    dangerous = [item for item in imported.records if item.dangerous]
    assert {item.semantic for item in dangerous} == {
        "factory/default reset", "unknown Aurora command",
    }
    assert imported.manifest.dangerous_suppressed_records == 2
    assert all(not item.experimentable for item in imported.records)
    assert all(not item.write_authorized for item in imported.evidence_records)
    assert all(item.evidence.level is EvidenceLevel.OBSERVED for item in imported.evidence_records)
    assert all(item.proof_state is not ProofState.PROVEN for item in imported.evidence_records)


def test_imported_known_setter_remains_decoded_but_unproven_and_non_experimentable():
    setter = bytearray(64)
    setter[2], setter[3], setter[4], setter[5] = 2, 3, 0, 0x1A
    setter[6:9] = b"\x01\x01\x00"
    imported = import_vendor_capture_bytes(
        _encode(_document([_record(bytes(setter), sequence=1)])),
        filename="setter.json", import_date="2026-09-18",
    )
    assert imported.records[0].semantic == "Rapid Trigger"
    assert imported.records[0].dangerous is False
    assert imported.records[0].experimentable is False
    assert imported.evidence_records[0].proof_state is ProofState.DECODED
    assert imported.evidence_records[0].write_authorized is False


def test_legacy_report8_remains_a_distinct_family():
    packet = bytearray(15)
    packet[0] = 0x04
    frame = bytes(packet) + bytes((legacy_checksum(bytes(packet)),))
    source = {
        "name": "Legacy public trace", "provenance_category": "other_public",
        "vid": "0x3554", "pid": "0x0001",
    }
    imported = import_vendor_capture_bytes(
        _encode(_document([_record(frame, sequence=1, report_id=8, report_type="output")], source=source)),
        filename="legacy.json", import_date="2026-09-18",
    )
    assert imported.records[0].protocol_family == LAMZU_AURORA_LEGACY.name
    assert imported.records[0].semantic == "legacy battery"
    assert LAMZU_AURORA_MODERN.name not in imported.manifest.protocol_families_recognized

    flash = bytearray(15)
    flash[0] = 0x08
    flash_frame = bytes(flash) + bytes((legacy_checksum(bytes(flash)),))
    flash_import = import_vendor_capture_bytes(
        _encode(_document([_record(flash_frame, sequence=1, report_id=8, report_type="output")], source=source)),
        filename="legacy-flash.json", import_date="2026-09-18",
    )
    assert flash_import.records[0].semantic == "legacy flash read"
    assert flash_import.records[0].dangerous is True


@pytest.mark.parametrize("provenance", [
    "official_vendor", "public_documentation", "open_source",
    "personal_capture", "other_public", "unknown",
])
def test_public_and_unknown_provenance_are_retained(provenance):
    document = _document([], source={"provenance_category": provenance})
    imported = import_vendor_capture_bytes(
        _encode(document), filename="source.json", import_date="2026-09-18",
    )
    assert imported.source.provenance_category.value == provenance


def test_prohibited_private_provenance_is_refused():
    document = _document([], source={"provenance_category": "prohibited_private"})
    with pytest.raises(VendorCaptureError, match="prohibited/private"):
        import_vendor_capture_bytes(_encode(document), filename="private.json")


def test_missing_optional_metadata_remains_unknown():
    imported = import_vendor_capture_bytes(
        _encode(_document([], source={})), filename="unknown.json", import_date="2026-09-18",
    )
    assert imported.source.source_name is None
    assert imported.source.vendor_id is None
    assert imported.source.protocol_family is None


def test_jsonl_adapter_round_trip_shape():
    lines = [
        json.dumps({
            "kind": "capture_header", "schema": CAPTURE_SCHEMA,
            "source": {"provenance_category": "open_source"},
        }),
        json.dumps({
            "kind": "record", "sequence": 0, "frame_hex": "0102",
            "direction": "unknown", "role": "unknown",
        }),
    ]
    imported = import_vendor_capture_bytes(
        ("\n".join(lines) + "\n").encode(), filename="capture.jsonl",
        import_date="2026-09-18",
    )
    assert imported.manifest.parser_selected.endswith("jsonl")
    assert imported.records[0].physical_frame == b"\x01\x02"
    assert imported.manifest.unknown_records == 1


def test_direction_and_report_metadata_safely_infer_known_aurora_roles():
    request = _record(
        build_read_request("battery/charging"), sequence=1,
        direction="host_to_device", role="unknown", transaction_id="battery",
        transfer_metadata={"control": {"request_type": 0x21}},
    )
    response = _record(
        _response(0x83, b"\x00\x32"), sequence=2,
        direction="device_to_host", role="unknown", transaction_id="battery",
    )
    imported = import_vendor_capture_bytes(
        _encode(_document([request, response])), filename="roles.json",
        import_date="2026-09-18",
    )
    assert [item.role.value for item in imported.records] == ["request", "response"]
    assert imported.records[0].transfer_metadata[0][0] == "control"
    assert dict(imported.records[1].decoded_fields)["payload_hex"] == "0032"


def test_malformed_invalid_and_truncated_records_are_bounded_warnings():
    records = [
        "not-an-object",
        {"frame_hex": "zz"},
        {"bytes": [0, 256]},
        {"frame_hex": "0102", "original_length": 8, "mystery": True},
    ]
    imported = import_vendor_capture_bytes(
        _encode(_document(records, source={"provenance_category": "unknown"})),
        filename="mixed.json", import_date="2026-09-18",
    )
    assert imported.manifest.malformed_records == 3
    assert imported.manifest.accepted_records == 1
    assert any("truncated" in item for item in imported.manifest.warnings)
    assert any("unknown record field" in item for item in imported.manifest.warnings)


def test_malformed_document_and_unsupported_format_are_distinct():
    with pytest.raises(VendorCaptureError):
        import_vendor_capture_bytes(b'{"schema":', filename="bad.json")
    with pytest.raises(UnsupportedCaptureFormat):
        import_vendor_capture_bytes(b"not a capture", filename="capture.bin")


def test_detection_ambiguity_abstains():
    class Adapter:
        def __init__(self, name):
            self.name = name
        def detect(self, raw, filename):
            return 50
        def parse(self, raw):
            return {}
    with pytest.raises(AmbiguousCaptureFormat):
        detect_capture_adapter(b"x", "x", adapters=(Adapter("a"), Adapter("b")))


def test_exact_duplicates_collapse_but_temporal_repetition_is_retained():
    frame = b"\x01\x02"
    first = _record(frame, sequence=1, semantic="state")
    duplicate = dict(first)
    repeated = _record(frame, sequence=2, semantic="state")
    imported = import_vendor_capture_bytes(
        _encode(_document([first, duplicate, repeated], source={
            "provenance_category": "public_documentation", "protocol_family": "generic",
        })), filename="repeat.json", import_date="2026-09-18",
    )
    assert imported.manifest.duplicate_records == 1
    assert imported.manifest.accepted_records == 2


def test_independent_source_corroboration_is_not_deduplicated():
    record = _record(b"\x01\x02", sequence=1, semantic="state")
    first = import_vendor_capture_bytes(
        _encode(_document([record], source={
            "name": "source one", "provenance_category": "open_source",
            "protocol_family": "generic",
        })), filename="one.json", import_date="2026-09-18",
    )
    second = import_vendor_capture_bytes(
        _encode(_document([record], source={
            "name": "source two", "provenance_category": "public_documentation",
            "protocol_family": "generic",
        })), filename="two.json", import_date="2026-09-18", existing=(first,),
    )
    assert second.manifest.accepted_records == 1
    assert second.manifest.duplicate_records == 0
    assert second.manifest.corroborating_records == 1
    assert first.evidence_records[0].evidence_id != second.evidence_records[0].evidence_id


def test_conflicting_interpretations_are_preserved_and_conflicted():
    base = {
        "name": "conflict source", "provenance_category": "public_documentation",
        "protocol_family": "generic-family",
    }
    records = [
        _record(b"\xaa", sequence=1, semantic="battery"),
        _record(b"\xaa", sequence=1, semantic="polling"),
    ]
    imported = import_vendor_capture_bytes(
        _encode(_document(records, source=base)), filename="conflict.json",
        import_date="2026-09-18",
    )
    assert imported.manifest.accepted_records == 2
    assert any("conflicting interpretations" in item for item in imported.manifest.conflicts)
    assert {item.proof_state for item in imported.evidence_records} == {ProofState.CONFLICTED}


def test_manifest_and_staged_import_round_trip_is_deterministic():
    imported = import_vendor_capture_bytes(
        _encode(_aurora_capture()), filename="aurora.json", import_date="2026-09-18",
    )
    document = import_to_document(imported)
    restored = import_from_document(json.loads(json.dumps(document)))
    assert restored.source == imported.source
    assert restored.records == imported.records
    assert restored.manifest == imported.manifest
    assert import_to_document(restored) == document


def test_review_status_distinguishes_staged_and_accepted_without_promotion():
    record = _record(b"\x01", sequence=7, semantic="state")
    record["sequence"] = "vendor-7"
    imported = import_vendor_capture_bytes(
        _encode(_document([record], source={
            "provenance_category": "public_documentation", "protocol_family": "generic",
        })), filename="review.json", import_date="2026-09-18",
    )
    assert accepted_vendor_evidence((imported,)) == ()
    accepted = review_vendor_capture(imported, CaptureReviewStatus.ACCEPTED)
    assert accepted.records[0].source_sequence == "vendor-7"
    assert len(accepted_vendor_evidence((accepted,))) == 1
    assert accepted.write_authorized is False
    assert accepted.evidence_records[0].proof_state is ProofState.DECODED
    assert accepted.evidence_records[0].evidence.level is EvidenceLevel.OBSERVED
    restored = import_from_document(import_to_document(accepted))
    assert restored.evidence_records[0].review_status is CaptureReviewStatus.ACCEPTED
    assert len(accepted_vendor_evidence((restored,))) == 1
    rejected = review_vendor_capture(imported, CaptureReviewStatus.REJECTED)
    assert accepted_vendor_evidence((rejected,)) == ()


def test_cross_source_identity_family_conflict_is_not_last_writer_wins():
    first = import_vendor_capture_bytes(
        _encode(_document([_record(b"\x01", sequence=1, semantic="state")], source={
            "provenance_category": "open_source", "vid": "0x1234", "pid": "0x5678",
            "protocol_family": "family-a",
        })), filename="a.json", import_date="2026-09-18",
    )
    second = import_vendor_capture_bytes(
        _encode(_document([_record(b"\x02", sequence=1, semantic="state")], source={
            "provenance_category": "public_documentation", "vid": "0x1234", "pid": "0x5678",
            "protocol_family": "family-b",
        })), filename="b.json", import_date="2026-09-18", existing=(first,),
    )
    assert any("conflicting protocol families" in item for item in second.manifest.conflicts)
    assert second.evidence_records[0].proof_state is ProofState.CONFLICTED


def test_conflicting_report_lengths_are_retained():
    source = {
        "provenance_category": "public_documentation",
        "protocol_family": "variable-but-unproven",
    }
    records = [
        _record(b"\x01", sequence=1, report_type="feature", report_id=2),
        _record(b"\x01\x02", sequence=2, report_type="feature", report_id=2),
    ]
    imported = import_vendor_capture_bytes(
        _encode(_document(records, source=source)), filename="lengths.json",
        import_date="2026-09-18",
    )
    assert any("conflicting report lengths" in item for item in imported.manifest.conflicts)


def test_resource_bounds_and_content_addressed_paths(monkeypatch, tmp_path):
    import mouse_control.vendor_capture as module

    monkeypatch.setattr(module, "MAX_RECORDS", 1)
    with pytest.raises(VendorCaptureError, match="record count"):
        import_vendor_capture_bytes(
            _encode(_document([{"frame_hex": "00"}, {"frame_hex": "01"}])),
            filename="too-many.json",
        )
    store = VendorCaptureStore(tmp_path)
    with pytest.raises(VendorCaptureError, match="unsafe source digest"):
        store.path_for_digest("../escape")


def test_content_addressed_store_save_load_duplicate_and_corruption(tmp_path):
    raw = _encode(_aurora_capture())
    capture = tmp_path / "aurora.json"
    capture.write_bytes(raw)
    store = VendorCaptureStore(tmp_path / "store")
    preview = store.preview_file(capture, import_date="2026-09-18")
    assert not store.path_for_digest(preview.source.content_sha256).exists()
    imported = store.import_file(capture, import_date="2026-09-18")
    path = store.path_for_digest(imported.source.content_sha256)
    assert path.exists()
    assert store.load(path).manifest == imported.manifest
    duplicate = store.import_file(capture, import_date="2026-09-19")
    assert duplicate.manifest.duplicate_import is True
    corrupt = store.directory / ("0" * 64 + ".json")
    corrupt.write_text("{bad", encoding="utf-8")
    loaded, warnings = store.load_all_safe()
    assert len(loaded) == 1
    assert len(warnings) == 1


def test_old_schema_compatibility_defaults_to_unreviewed():
    imported = import_vendor_capture_bytes(
        _encode(_document([_record(b"\x01", sequence=1)], source={
            "provenance_category": "unknown",
        })), filename="old.json", import_date="2026-09-18",
    )
    document = import_to_document(imported)
    document.pop("schema_version")
    document["manifest"].pop("review_status")
    restored = import_from_document(document)
    assert restored.manifest.review_status is CaptureReviewStatus.IMPORTED_UNREVIEWED


def test_digest_and_evidence_identity_do_not_depend_on_import_date():
    raw = _encode(_document([_record(b"\x01", sequence=1)]))
    first = import_vendor_capture_bytes(raw, filename="a.json", import_date="2026-09-18")
    second = import_vendor_capture_bytes(raw, filename="a.json", import_date="2026-09-19")
    assert first.source.content_sha256 == second.source.content_sha256
    assert [item.observation_id for item in first.records] == [item.observation_id for item in second.records]
    assert [item.evidence_id for item in first.evidence_records] == [item.evidence_id for item in second.evidence_records]


def test_bootloader_capture_never_becomes_experimentable():
    document = _document([_record(build_read_request("battery/charging"), sequence=1)], source={
        "provenance_category": "official_vendor", "vid": "0x37b0", "pid": "0x0041",
        "protocol_family": LAMZU_AURORA_MODERN.name,
    })
    imported = import_vendor_capture_bytes(_encode(document), filename="dfu.json")
    assert imported.records[0].dangerous is True
    assert any("bootloader/DFU" in item for item in imported.records[0].parser_warnings)
    assert imported.write_authorized is False


def test_tui_exposes_import_summary_and_cancellation_without_changing_lab_flow(tmp_path):
    app, _backend = controller()
    app.section_index = SECTIONS.index(SetupSection.LAB)
    app.discovery_complete = True
    app.discovery_result = type("Result", (), {"device": object()})()
    rows = app.detail_rows()
    assert any(row.text == "Run Full Automatic Lab" for row in rows)
    assert any(row.text == "Import Vendor Capture" for row in rows)
    app.row_cursor = 1
    assert app.handle_key("ENTER").kind is ActionKind.IMPORT_VENDOR_CAPTURE

    imported = import_vendor_capture_bytes(
        _encode(_aurora_capture()), filename="aurora.json", import_date="2026-09-18",
    )
    app.apply_vendor_capture_import(imported)
    text = "\n".join(row.text for row in app.detail_rows())
    assert "Vendor capture import" in text
    assert "dangerous/suppressed: 2" in text
    assert "Imported evidence does not enable writes" in text
    retained = app.vendor_capture_import
    app.cancel_vendor_capture_import()
    assert app.vendor_capture_import is retained
    app.row_cursor = 0
    assert app.handle_key("ENTER").kind is ActionKind.RUN_DISCOVERY_LAB


def test_importer_module_has_no_hardware_transport_or_network_client():
    source = Path(__file__).parents[1] / "src" / "mouse_control" / "vendor_capture.py"
    text = source.read_text(encoding="utf-8")
    assert "hidraw" not in text.lower()
    assert "HIDIOCS" not in text
    assert "urllib" not in text and "requests" not in text and "socket" not in text
    assert "eval(" not in text and "exec(" not in text
