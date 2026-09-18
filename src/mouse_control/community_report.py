"""Deterministic, privacy-conscious Automatic Discovery artifact."""

from __future__ import annotations

import json
import re
from typing import Any

from .discovery_models import DiscoveryResult
from .proof_state import proof_state_from_evidence


REPORT_SCHEMA = "mouse-control-community-discovery/v1"
_SAFE_DETAIL_KEYS = {
    "ambiguous", "behavior", "descriptor_sha256", "exact_identity", "family",
    "interface_number", "matched", "missing", "report_ids", "reports", "revision",
    "score", "semantic_fields", "strongest_source_trust", "write_authorized",
    "write_scope", "demonstrated_values", "demonstrated_rates", "diagnostics",
}


def _safe_text(value: str) -> str:
    """Remove path-shaped material that may have leaked into a diagnostic."""
    return re.sub(r"(?:/[A-Za-z0-9_.@:+-]+){2,}", "<redacted-path>", value)


def _safe_nested(value: Any) -> Any:
    """Recursively redact path text and reject identity-bearing key names."""

    if isinstance(value, str):
        return _safe_text(value)
    if isinstance(value, list):
        return [_safe_nested(item) for item in value]
    if isinstance(value, tuple):
        return [_safe_nested(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _safe_nested(item)
            for key, item in value.items()
            if not any(token in str(key).lower() for token in ("serial", "path", "username", "uniq"))
        }
    return value


def _operation(name: str, capability: Any | None) -> dict[str, Any]:
    levels = tuple(item.level.name for item in capability.evidence) if capability else ()
    state = proof_state_from_evidence(levels)
    return {
        "proof_state": state.value,
        "readable": bool(capability and capability.readable),
        "writable": bool(capability and capability.writable and state.value == "proven"),
        "values": list(capability.values or ()) if capability else [],
    }


def build_community_report(
    result: DiscoveryResult,
    *,
    version: str,
    integrated_evidence: dict[str, object] | None = None,
) -> dict[str, Any]:
    """Build an allowlisted report; paths, serials, and instance IDs never enter it."""
    device = result.device
    interfaces = [
        {
            "subsystem": node.subsystem,
            "type": node.node_type,
            "interface_number": node.interface_number,
            "descriptor_sha256": node.descriptor_sha256,
        }
        for node in sorted(device.all_nodes, key=lambda n: (n.subsystem, n.interface_number or -1, n.descriptor_sha256 or ""))
    ]
    candidates = []
    conflicts = []
    observations = []
    for evidence in sorted(result.observations, key=lambda e: (e.code, e.message)):
        safe_details = {
            key: value for key, value in sorted(evidence.details.items())
            if key in _SAFE_DETAIL_KEYS
        }
        entry = {"code": evidence.code, "level": evidence.level.name.lower(), "message": _safe_text(evidence.message), "details": safe_details}
        observations.append(entry)
        if evidence.code == "protocol-family-candidate":
            candidates.append(safe_details)
        if "conflict" in evidence.code:
            conflicts.append(entry)
    operations = {
        name: _operation(name, result.capabilities.get(name))
        for name in sorted(set(result.capabilities) | {"dpi", "report_rate", "battery", "remapping"})
    }
    if "remapping" not in result.capabilities:
        operations["remapping"] = {"proof_state": "proven", "readable": True, "writable": True, "values": []}
    next_evidence: list[str] = []
    if not candidates and result.protocol is None:
        next_evidence.append("capture repeated guided actions with quiet and normal-use negative controls")
    if operations["dpi"]["proof_state"] not in {"verified", "proven"}:
        next_evidence.append("repeat nonuniform DPI-stage observations and physically calibrate absolute CPI")
    if operations["report_rate"]["proof_state"] not in {"verified", "proven"}:
        next_evidence.append("collect read-only polling observations for each hardware rate setting")
    report = {
        "schema": REPORT_SCHEMA,
        "mouse_control_version": version,
        "device": {
            "name": device.name,
            "vid_pid": (f"{device.vendor_id:04x}:{device.product_id:04x}" if device.vendor_id is not None and device.product_id is not None else "unknown"),
            "transport": device.bus,
            "model_fingerprint": device.model_fingerprint,
            "ambiguous": device.ambiguous,
        },
        "interfaces": interfaces,
        "protocol": {"known": result.protocol.name if result.protocol else None, "candidates": candidates},
        "operations": operations,
        "observations": observations,
        "conflicts": conflicts,
        "experiment_eligibility": "blocked",
        "next_evidence": next_evidence,
        "safety": {"generic_discovery_read_only": True, "active_writes_authorized": bool(result.writable)},
        "metrics": {
            "devices_reported": 1,
            "unique_vid_pid_identities": 1 if device.vendor_id is not None and device.product_id is not None else 0,
            "protocol_family_matches": len(candidates),
            "proven_operations": sum(1 for item in operations.values() if item["proof_state"] == "proven"),
            "unresolved_conflicts": len(conflicts),
            "requires_architecture_change": None,
        },
    }
    if integrated_evidence is not None:
        report["integrated_evidence"] = _safe_nested(integrated_evidence)
    return report


def render_community_report(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, separators=(",", ": ")) + "\n"
