import json

import pytest

from mouse_control.trace.corpus import TraceSessionManifest, sha256_file
from mouse_control.trace.models import CaptureSource


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
