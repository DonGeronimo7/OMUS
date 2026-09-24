# SPDX-License-Identifier: AGPL-3.0-or-later
"""Persistent read-only profiles learned by physically calibrated discovery.

These profiles are deliberately separate from runtime/write-capability profiles.
They cache only path-independent observations learned from physical calibration
plus passive Linux input/HID capture. Nothing saved here can authorize a write.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import pwd
from copy import deepcopy
from tempfile import NamedTemporaryFile
from typing import Any, Iterable, Mapping, Sequence

from .calibrated_discovery import CalibratedDpiState, CalibratedRawMapping
from .device_profiles import get_profile_directory
from .transition_sources import CalibratedTransitionSource, SUPPORTED_SOURCE_KINDS


CALIBRATED_PROFILE_SCHEMA_VERSION = 2
SUPPORTED_CALIBRATED_PROFILE_SCHEMAS = frozenset({1, 2})


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
        "bus": int(bus) if bus is not None else None,
        "vendor_id": int(vendor_id) if vendor_id is not None else None,
        "product_id": int(product_id) if product_id is not None else None,
        "interface_number": None if interface_number is None else int(interface_number),
        "descriptor_sha256": None if descriptor_sha256 is None else str(descriptor_sha256),
        "report_length": int(report_length),
        "report_id": int(report_id),
    }


def _transition_source_to_json(source: CalibratedTransitionSource) -> dict[str, Any]:
    if source.kind not in SUPPORTED_SOURCE_KINDS:
        raise CalibratedProfileError(f"unsupported calibrated transition source {source.kind!r}")
    item: dict[str, Any] = {
        "kind": source.kind,
        "cycle_order": [int(value) for value in source.cycle_order],
        "observations": int(source.observations),
        "confidence": str(source.confidence),
        "write_authorized": False,
    }
    if source.report_key is not None and source.kind in {"hid_state", "hid_cycle_trigger"}:
        item["report"] = _report_key_to_json(source.report_key)
    if source.interface:
        item["interface"] = dict(source.interface)
    if source.offset is not None:
        item["offset"] = int(source.offset)
    if source.raw_to_dpi:
        item["raw_to_configured_dpi"] = {
            str(int(raw)): int(dpi) for raw, dpi in source.raw_to_dpi.items()
        }
    if source.measured_cpi_mapping:
        item["raw_to_measured_cpi"] = {
            str(int(raw)): int(cpi)
            for raw, cpi in source.measured_cpi_mapping.items()
        }
    if source.field_id is not None:
        item["field_id"] = source.field_id
    if source.parent_field_id is not None:
        item["parent_field_id"] = source.parent_field_id
    if source.member_index is not None:
        item["member_index"] = int(source.member_index)
    if source.semantic_evidence is not None:
        item["semantic_evidence"] = source.semantic_evidence
    if source.event_type is not None:
        item["event_type"] = int(source.event_type)
    if source.code is not None:
        item["code"] = int(source.code)
    if source.press_value is not None:
        item["press_value"] = int(source.press_value)
    if source.release_value is not None:
        item["release_value"] = int(source.release_value)
    if source.press_pattern is not None:
        item["press_pattern_hex"] = bytes(source.press_pattern).hex()
    if source.release_pattern is not None:
        item["release_pattern_hex"] = bytes(source.release_pattern).hex()
    return item


def calibrated_profile_data(
    *,
    device,
    configured_cycle: Sequence[int],
    measured_cycle: Sequence[CalibratedDpiState],
    mappings: Sequence[CalibratedRawMapping],
    action_report_keys: Iterable[object] = (),
    transition_sources: Sequence[CalibratedTransitionSource] = (),
    calibration_confidence: str = "validated",
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
            "confidence": str(calibration_confidence),
            "semantic_evidence": "physically-calibrated",
        },
        "action_reports": reports,
        "raw_mappings": raw_mappings,
        "transition_sources": [
            _transition_source_to_json(source) for source in transition_sources
        ],
        "write_authorized": False,
    }


def physical_calibration_is_reusable(profile: Mapping[str, Any]) -> bool:
    """Return whether schema-v2 data proves a complete reusable physical cycle.

    Runtime transition-source discovery is intentionally not part of this test.
    A physically measured cycle remains valuable even when the only unresolved
    question is how to observe future presses at runtime.
    """

    if profile.get("schema_version") != 2 or profile.get("write_authorized") is not False:
        return False
    cycle = profile.get("dpi_cycle")
    if not isinstance(cycle, Mapping):
        return False
    order = cycle.get("configured_order")
    states = cycle.get("states")
    if (
        not isinstance(order, list)
        or len(order) < 2
        or len(set(order)) < 2
        or any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
            for value in order
        )
    ):
        return False
    if (
        cycle.get("wrap_confirmed") is not True
        or cycle.get("confidence") != "validated"
        or cycle.get("semantic_evidence") != "physically-calibrated"
        or not isinstance(states, list)
        or len(states) != len(order) + 1
    ):
        return False

    observed: list[int] = []
    for state in states:
        if not isinstance(state, Mapping):
            return False
        configured = state.get("configured_dpi")
        measured = state.get("measured_cpi")
        confidence = state.get("confidence")
        polling = state.get("polling_hz")
        if (
            not isinstance(configured, int)
            or isinstance(configured, bool)
            or configured <= 0
            or not isinstance(measured, (int, float))
            or isinstance(measured, bool)
            or float(measured) <= 0
            or not isinstance(confidence, str)
            or not confidence
            or (
                polling is not None
                and (
                    not isinstance(polling, int)
                    or isinstance(polling, bool)
                    or polling <= 0
                )
            )
        ):
            return False
        observed.append(configured)
    return observed[:-1] == order and observed[-1] == order[0]


def validate_calibrated_profile(profile: Mapping[str, Any]) -> None:
    schema_version = profile.get("schema_version")
    if schema_version not in SUPPORTED_CALIBRATED_PROFILE_SCHEMAS:
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

    if schema_version >= 2:
        sources = profile.get("transition_sources")
        if not isinstance(sources, list):
            raise CalibratedProfileError("schema v2 calibrated profiles require transition_sources")
        for source in sources:
            if not isinstance(source, Mapping):
                raise CalibratedProfileError("calibrated transition source must be an object")
            kind = source.get("kind")
            if kind not in SUPPORTED_SOURCE_KINDS:
                raise CalibratedProfileError("unsupported calibrated transition source kind")
            if source.get("write_authorized") is not False:
                raise CalibratedProfileError("calibrated transition sources can never authorize writes")
            order = source.get("cycle_order")
            if not isinstance(order, list) or len(order) < 2 or any(
                not isinstance(value, int) or isinstance(value, bool) or value <= 0
                for value in order
            ):
                raise CalibratedProfileError("calibrated transition source requires a DPI cycle")
            if kind in {"hid_state", "feature_state", "evdev_absolute_stage"} and not isinstance(
                source.get("raw_to_configured_dpi"), Mapping
            ):
                raise CalibratedProfileError("absolute calibrated source requires a DPI lookup")
            if kind in {"hid_state", "hid_cycle_trigger"} and not isinstance(
                source.get("report"), Mapping
            ):
                raise CalibratedProfileError("HID calibrated source requires a report identity")
            if source.get("field_id") is not None:
                if (
                    kind != "hid_state"
                    or source.get("confidence") != "validated"
                    or source.get("semantic_evidence") != "validated"
                    or not isinstance(source.get("field_id"), str)
                    or not isinstance(source.get("parent_field_id"), str)
                    or not isinstance(source.get("member_index"), int)
                    or not isinstance(source.get("offset"), int)
                    or not isinstance(source.get("raw_to_measured_cpi"), Mapping)
                ):
                    raise CalibratedProfileError(
                        "descriptor-backed HID state requires validated member evidence"
                    )
            if kind in {"feature_state", "evdev_absolute_stage", "evdev_cycle_trigger"} and not isinstance(
                source.get("interface"), Mapping
            ):
                raise CalibratedProfileError("calibrated source requires a stable interface identity")

    serialized = json.dumps(profile, sort_keys=True)
    if "/dev/hidraw" in serialized or "/dev/input/event" in serialized:
        raise CalibratedProfileError("volatile Linux device paths may not be persisted")


def promote_descriptor_member_binding(
    profile: Mapping[str, Any],
    validation: Any,
) -> dict[str, Any]:
    """Persist one physically validated descriptor member as a read-only source."""

    validate_calibrated_profile(profile)
    if (
        not isinstance(validation.source_field, str)
        or not isinstance(validation.parent_field, str)
        or not isinstance(validation.member_index, int)
        or not isinstance(validation.offset, int)
        or not isinstance(validation.report_identity, Mapping)
        or validation.observations <= 0
    ):
        raise CalibratedProfileError("validated descriptor member evidence is incomplete")
    matching = [
        mapping for mapping in profile.get("raw_mappings", ())
        if isinstance(mapping, Mapping)
        and mapping.get("report") == validation.report_identity
        and mapping.get("offset") == validation.offset
        and mapping.get("confidence") == "correlated"
        and mapping.get("write_authorized") is False
    ]
    if len(matching) != 1:
        raise CalibratedProfileError("validated member must match one correlated raw mapping")

    promoted = deepcopy(dict(profile))
    cycle = promoted.get("dpi_cycle")
    if not isinstance(cycle, dict):
        raise CalibratedProfileError("validated member requires a physical DPI cycle")
    cycle["confidence"] = "validated"
    promoted["schema_version"] = CALIBRATED_PROFILE_SCHEMA_VERSION
    source = {
        "kind": "hid_state",
        "cycle_order": list(cycle["configured_order"]),
        "observations": int(validation.observations),
        "confidence": "validated",
        "report": dict(validation.report_identity),
        "offset": int(validation.offset),
        "raw_to_configured_dpi": {
            str(int(raw)): int(dpi)
            for raw, dpi in validation.configured_dpi_mapping.items()
        },
        "raw_to_measured_cpi": {
            str(int(raw)): int(cpi)
            for raw, cpi in validation.measured_cpi_mapping.items()
        },
        "field_id": validation.source_field,
        "parent_field_id": validation.parent_field,
        "member_index": int(validation.member_index),
        "semantic_behavior": "dpi_stage_index",
        "semantic_evidence": "validated",
        "write_authorized": False,
    }
    existing = promoted.get("transition_sources")
    if existing not in (None, [], [source]):
        raise CalibratedProfileError("refusing to replace existing calibrated transition sources")
    promoted["transition_sources"] = [source]
    promoted["write_authorized"] = False
    validate_calibrated_profile(promoted)
    return promoted


def _filename(profile: Mapping[str, Any]) -> str:
    identity = profile["identity"]
    model = str(profile["fingerprints"]["model"])
    vendor = identity.get("vendor_id")
    product = identity.get("product_id")
    vendor_text = f"{vendor:04x}" if isinstance(vendor, int) else "unknown"
    product_text = f"{product:04x}" if isinstance(product, int) else "unknown"
    return f"{vendor_text}-{product_text}-{model[:16]}.json"


def profile_matches_device(profile: Mapping[str, Any], device) -> bool:
    """Match a calibrated profile to an unambiguous physical device identity."""

    if getattr(device, "ambiguous", False):
        return False
    identity = profile.get("identity")
    fingerprints = profile.get("fingerprints")
    if not isinstance(identity, Mapping) or not isinstance(fingerprints, Mapping):
        return False
    if fingerprints.get("model") != getattr(device, "model_fingerprint", None):
        return False
    for key, value in (
        ("vendor_id", getattr(device, "vendor_id", None)),
        ("product_id", getattr(device, "product_id", None)),
        ("bus", getattr(device, "bus", None)),
    ):
        expected = identity.get(key)
        if expected is not None and value is not None and expected != value:
            return False
    instance = fingerprints.get("instance")
    current_instance = getattr(device, "instance_fingerprint", None)
    if instance and current_instance and instance != current_instance:
        return False
    return True


def find_calibrated_profile(device) -> tuple[Path, dict[str, Any]] | None:
    """Return one exact validated learned calibration, refusing ambiguity."""

    directory = get_calibrated_profile_directory()
    if not directory.is_dir():
        return None
    matches: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                continue
            validate_calibrated_profile(raw)
        except (OSError, json.JSONDecodeError, CalibratedProfileError):
            continue
        if not profile_matches_device(raw, device):
            continue
        if raw.get("schema_version") == 1 and not raw.get("raw_mappings"):
            continue
        if (
            raw.get("schema_version") == 2
            and not raw.get("transition_sources")
            and not physical_calibration_is_reusable(raw)
        ):
            continue
        matches.append((path, raw))
    return matches[0] if len(matches) == 1 else None


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
