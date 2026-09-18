import json
from pathlib import Path

from mouse_control.community_report import build_community_report, render_community_report
from mouse_control.discovery_models import (
    DeviceNode, DiscoveryEvidence, DiscoveryResult, EvidenceLevel, PhysicalDevice,
)


def test_report_is_deterministic_redacted_and_exposes_missing_evidence() -> None:
    node = DeviceNode(Path("/dev/hidraw9"), Path("/sys/private/user/device"), "hidraw", "hidraw", 3, 0x1234, 0x5678, 2, uniq="serial-secret", descriptor_sha256="abc")
    device = PhysicalDevice("Unknown Mouse", 0x1234, 0x5678, 3, Path("/sys/private"), hidraw_nodes=[node], model_fingerprint="model", instance_fingerprint="secret")
    result = DiscoveryResult(device, None, {}, observations=[DiscoveryEvidence(EvidenceLevel.OBSERVED, "vendor-defined-reports", "failed at /home/alice/private/device", details={"path": "/dev/hidraw9", "serial": "secret"})])
    model = build_community_report(result, version="0.9.4")
    text = render_community_report(model)
    assert text == render_community_report(model)
    assert "/dev/" not in text and "/sys/" not in text and "/home/" not in text
    assert "serial-secret" not in text and '"serial"' not in text
    parsed = json.loads(text)
    assert parsed["device"]["vid_pid"] == "1234:5678"
    assert parsed["operations"]["dpi"]["proof_state"] == "unknown"
    assert parsed["next_evidence"]
    assert parsed["safety"]["active_writes_authorized"] is False


def test_integrated_evidence_is_recursively_privacy_filtered() -> None:
    device = PhysicalDevice("Unknown", 1, 2, 3, None, model_fingerprint="model")
    report = build_community_report(
        DiscoveryResult(device, None, {}), version="0.9.4",
        integrated_evidence={
            "dialogues": [{"kind": "response", "note": "read /home/alice/capture.bin"}],
            "serial_number": "secret",
            "nested": {"device_path": "/dev/hidraw7", "safe": "retained"},
        },
    )
    text = render_community_report(report)
    assert "/home/alice" not in text and "/dev/hidraw7" not in text
    assert "serial_number" not in text and "device_path" not in text
    assert report["integrated_evidence"]["nested"]["safe"] == "retained"
