# SPDX-License-Identifier: AGPL-3.0-or-later
import json

import pytest

from mouse_control.trace.corpus import (
    TraceSessionManifest,
    observations_from_jsonl,
    observations_to_jsonl,
    sha256_file,
)
from mouse_control.trace.models import (
    CaptureQuality,
    CaptureSource,
    CompletenessStatus,
    UrbEventType,
    UsbDirection,
    UsbObservation,
    UsbTransferType,
)


def manifest() -> TraceSessionManifest:
    return TraceSessionManifest(
        session_id="session-1",
        mouse_control_commit="abc123",
        operating_system="Linux",
        kernel="6.x",
        capture_source=CaptureSource.USBMON_BINARY,
        device_fingerprint="device",
        descriptor_fingerprint="descriptor",
        experiment_definition=None,
        random_seed=42,
        started_ns=100,
        ended_ns=200,
    )


def test_manifest_serialization_is_deterministic_and_versioned() -> None:
    first = manifest().to_json()
    second = manifest().to_json()
    assert first == second
    assert TraceSessionManifest.from_json(first) == manifest()
    payload = json.loads(first)
    assert payload["schema_version"] == 1
    assert payload["trace_schema_version"] == 1


def test_manifest_refuses_unknown_schema() -> None:
    payload = json.loads(manifest().to_json())
    payload["schema_version"] = 99
    with pytest.raises(ValueError, match="unsupported"):
        TraceSessionManifest.from_json(json.dumps(payload))


def test_file_hash_is_streamed_and_reproducible(tmp_path) -> None:
    artifact = tmp_path / "capture.pcapng"
    artifact.write_bytes(b"evidence")
    assert sha256_file(artifact) == (
        "ee8250fb76e094b34b471f13a73dbbe51d1ae142e9df59d7c0d31ec20f0a0a8e"
    )


def test_canonical_observation_round_trip_retains_optional_usbmon_provenance() -> None:
    observation = UsbObservation(
        capture_id="capture", sequence=2, timestamp_ns=3,
        source=CaptureSource.USBMON_BINARY, bus_id=1, device_address=2,
        interface_number=3, endpoint=4, direction=UsbDirection.IN,
        transfer_type=UsbTransferType.INTERRUPT, event_type=UrbEventType.COMPLETE,
        urb_id=5, status=0, setup=None, declared_length=8, captured_length=2,
        payload=b"\xaa\xbb", physical_device_fingerprint="device",
        setup_flag=1, data_flag=2, interval=7, start_frame=101,
        transfer_flags=0x80000001, descriptor_count=6,
        capture_quality=CaptureQuality(
            source_representation="linux_usbmon_binary_extended",
            full_binary_header_available=True, dropped_record_count=None,
            clock_timebase="kernel_monotonic", completeness=CompletenessStatus.TRUNCATED,
        ),
    )

    replayed = tuple(observations_from_jsonl(observations_to_jsonl((observation,))))
    assert replayed == (observation,)
