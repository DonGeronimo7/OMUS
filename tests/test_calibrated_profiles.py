from __future__ import annotations

from mouse_control.calibrated_discovery import CalibratedDpiState, CalibratedRawMapping
from mouse_control.calibrated_profiles import calibrated_profile_data, validate_calibrated_profile
from mouse_control.discovery_models import PhysicalDevice


def _device() -> PhysicalDevice:
    return PhysicalDevice(
        "Unknown Mouse",
        0x1234,
        0x5678,
        3,
        None,
        model_fingerprint="model-fingerprint",
        instance_fingerprint="instance-fingerprint",
    )


def _report_key(product: int = 0x5678):
    return ("input", 3, 0x1234, product, 2, "descriptor-sha", 20, 17)


def test_calibrated_profile_is_path_independent_and_read_only():
    states = (
        CalibratedDpiState(800, 818.0, 1000, "high"),
        CalibratedDpiState(1500, 1535.0, 1000, "high"),
        CalibratedDpiState(800, 816.0, 1000, "high"),
    )
    mapping = CalibratedRawMapping(
        report_key=_report_key(),
        offset=4,
        configured_mapping={0: 800, 1: 1500},
        measured_cpi_mapping={0: 816, 1: 1535},
        observations=2,
        descriptor_roles=("vendor",),
    )
    transition_only = _report_key(0x9999)

    profile = calibrated_profile_data(
        device=_device(),
        configured_cycle=(800, 1500),
        measured_cycle=states,
        mappings=(mapping,),
        action_report_keys=(_report_key(), transition_only),
    )
    validate_calibrated_profile(profile)

    assert profile["write_authorized"] is False
    assert profile["dpi_cycle"]["wrap_confirmed"] is True
    assert profile["raw_mappings"][0]["raw_to_configured_dpi"] == {"0": 800, "1": 1500}
    assert profile["raw_mappings"][0]["write_authorized"] is False
    roles = {item["identity"]["product_id"]: item["role"] for item in profile["action_reports"]}
    assert roles[0x5678] == "state-bearing"
    assert roles[0x9999] == "transition-only"
    assert "/dev/hidraw" not in str(profile)
    assert "/dev/input/event" not in str(profile)
