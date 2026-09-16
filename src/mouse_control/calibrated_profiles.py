"""Persistent read-only profiles learned by physically calibrated discovery.

These profiles are deliberately separate from runtime/write-capability profiles.
They cache only path-independent observations that were learned from physical
calibration plus passive HID capture.  Nothing saved here can authorize a HID
write.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import pwd
from tempfile import NamedTemporaryFile
from typing import Any, Iterable, Mapping, Sequence

from .calibrated_discovery import CalibratedDpiState, CalibratedRawMapping
from .device_profiles import get_profile_directory


CALIBRATED_PROFILE_SCHEMA_VERSION = 1


class CalibratedProfileError(RuntimeError):
    """A calibrated read-side profile is malformed or unsafe."""


def get_calibrated_profile_directory() -> Path:
    return get_profile_directory() / "calibrated-read"


def _sudo_identity() -> tuple[int, int] | None:
    if os.geteuid() != 0:
        return None
    try:
        uid = int(os.environ["SUDO_UID"])
        gid = int(os.environ["SUDO_GID"])
    except (KeyError, TypeError, ValueError):
        return None
    if uid == 0:
        return None
    try:
        pwd.getpwuid(uid)
    except KeyError:
        return None
    return uid, gid


def _report_key_to_json(report_key: object) -> dict[str, Any]:
    if not isinstance(report_key, tuple) or len(report_key) < 8:
        raise CalibratedProfileError("calibrated mapping has an unsupported report identity")
    report_type, bus, vendor_id, product_id, interface_number, descriptor_sha256 = report_key[:6]
    report_length, report_id = report_key[-2:]
    if report_type not in {"input", "output", "feature"}:
        raise CalibratedProfileError("unsupported calibrated report type")
    return {
        "report_type": str(report_type),
        "bus": int(bus),
        "vendor_id": int(vendor_id),
        "product_id": int(product_id),
        "interface_number": None if interface_number is None else int(interface_number),
        "descriptor_sha256": None if descriptor_sha256 is None else str(descriptor_sha256),
        "report_length": int(report_length),
        "report_id": int(report_id),
    }


def calibrated_profile_data(
    *,
    device,
    configured_cycle: Sequence[int],
    measured_cycle: Sequence[CalibratedDpiState],
    mappings: Sequence[CalibratedRawMapping],
    action_report_keys: Iterable[object] = (),
) -> dict[str, Any]:
    """Build path-independent read-side learning data from one accepted run."""

    action_keys = tuple(action_report_keys)
    state_keys = {mapping.report_key for mapping in mappings}
    reports = []
    for key in action_keys:
        reports.append(
            {
                "identity": _report_key_to_json(key),
                "role": "state-bearing" if key in state_keys else "transition-only",
            }
        )

    raw_mappings = []
    for mapping in mappings:
        raw_mappings.append(
            {
                "report": _report_key_to_json(mapping.report_key),
                "offset": int(mapping.offset),
                "descriptor_roles": list(mapping.descriptor_roles),
                "raw_to_configured_dpi": {
                    str(int(raw)): int(dpi) for raw, dpi in mapping.configured_mapping.items()
                },
                "raw_to_measured_cpi": {
                    str(int(raw)): int(cpi) for raw, cpi in mapping.measured_cpi_mapping.items()
                },
                "observations": int(mapping.observations),
                "confidence": "correlated",
                "write_authorized": False,
            }
        )

    states = [
        {
            "configured_dpi": int(state.configured_dpi),
            "measured_cpi": float(state.measured_cpi),
            "polling_hz": None if state.polling_hz is None else int(state.polling_hz),
            "confidence": str(state.confidence),
        }
        for state in measured_cycle
    ]

    return {
        "schema_version": CALIBRATED_PROFILE_SCHEMA_VERSION,
        "profile_kind": "calibrated-read-only",
        "identity": {
            "vendor_id": device.vendor_id,
            "product_id": device.product_id,
            "bus": device.bus,
        },
        "fingerprints": {
            "model": device.model_fingerprint,
            "instance": device.instance_fingerprint,
        },
        "dpi_cycle": {
            "configured_order": [int(value) for value in configured_cycle],
            "states": states,
            "wrap_confirmed": bool(
                len(states) >= 2
                and states[0]["configured_dpi"] == states[-1]["configured_dpi"]
            ),
            "semantic_evidence": "physically-calibrated",
        },
        "action_reports": reports,
        "raw_mappings": raw_mappings,
        "write_authorized": False,
    }


def validate_calibrated_profile(profile: Mapping[str, Any]) -> None:
    if profile.get("schema_version") != CALIBRATED_PROFILE_SCHEMA_VERSION:
        raise CalibratedProfileError("unsupported calibrated profile schema")
    if profile.get("profile_kind") != "calibrated-read-only":
        raise CalibratedProfileError("unexpected calibrated profile kind")
    fingerprints = profile.get("fingerprints")
    if not isinstance(fingerprints, Mapping) or not fingerprints.get("model"):
        raise CalibratedProfileError("calibrated profile requires a model fingerprint")
    if profile.get("write_authorized") is not False:
        raise CalibratedProfileError("calibrated read-side profiles can never authorize writes")
    mappings = profile.get("raw_mappings")
    if not isinstance(mappings, list):
        raise CalibratedProfileError("calibrated profile raw_mappings must be a list")
    for mapping in mappings:
        if not isinstance(mapping, Mapping):
            raise CalibratedProfileError("calibrated raw mapping must be an object")
        if mapping.get("write_authorized") is not False:
            raise CalibratedProfileError("calibrated raw mappings can never authorize writes")
        if not isinstance(mapping.get("raw_to_configured_dpi"), Mapping):
            raise CalibratedProfileError("calibrated raw mapping requires a DPI lookup")
    serialized = json.dumps(profile, sort_keys=True)
    if "/dev/hidraw" in serialized or "/dev/input/event" in serialized:
        raise CalibratedProfileError("volatile Linux device paths may not be persisted")


def _filename(profile: Mapping[str, Any]) -> str:
    identity = profile["identity"]
    model = str(profile["fingerprints"]["model"])
    vendor = identity.get("vendor_id")
    product = identity.get("product_id")
    vendor_text = f"{vendor:04x}" if isinstance(vendor, int) else "unknown"
    product_text = f"{product:04x}" if isinstance(product, int) else "unknown"
    return f"{vendor_text}-{product_text}-{model[:16]}.json"


def save_calibrated_profile(profile: Mapping[str, Any]) -> Path:
    validate_calibrated_profile(profile)
    directory = get_calibrated_profile_directory()
    directory.mkdir(parents=True, exist_ok=True)
    identity = _sudo_identity()
    if identity is not None:
        uid, gid = identity
        for path in (directory.parent, directory):
            try:
                if path.stat().st_uid == 0:
                    os.chown(path, uid, gid)
            except OSError:
                pass

    destination = directory / _filename(profile)
    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=directory,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        json.dump(profile, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temp_path, destination)
        if identity is not None:
            os.chown(destination, *identity)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return destination
