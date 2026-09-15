"""Persistent, path-independent device discovery profiles.

Profiles cache facts discovery has already proven.  They never store
``/dev/hidrawN`` or ``/dev/input/eventN`` as identity.  Runtime code must still
rediscover the live interface and enforce its own write policy.
"""

from __future__ import annotations

from enum import Enum
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Mapping

from .discovery_models import DiscoveryEvidence, DiscoveryResult


PROFILE_SCHEMA_VERSION = 1


class DeviceProfileError(RuntimeError):
    """A discovery profile is malformed or unsafe to use."""


def get_profile_directory() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME")
    root = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
    return root / "mouse-control" / "devices"


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.name.lower()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)


def _evidence_to_json(item: DiscoveryEvidence) -> dict[str, Any]:
    return {
        "level": item.level.name.lower(),
        "code": item.code,
        "message": item.message,
        "source": item.source,
        "details": _json_safe(item.details),
    }


def result_to_profile(result: DiscoveryResult) -> dict[str, Any]:
    """Convert a discovery result to a stable JSON profile."""

    if result.device.ambiguous:
        raise DeviceProfileError("refusing to persist an ambiguous physical-device binding")

    protocol: dict[str, Any] | None = None
    responder: dict[str, Any] | None = None
    if result.protocol is not None:
        protocol = {
            "name": result.protocol.name,
            "version": result.protocol.version,
            "evidence": [_evidence_to_json(item) for item in result.protocol.evidence],
        }
        node = result.protocol.responder
        if node is not None:
            responder = {
                "interface_number": node.interface_number,
                "descriptor_sha256": node.descriptor_sha256,
                "bus": node.bus,
                "vendor_id": node.vendor_id,
                "product_id": node.product_id,
            }

    capabilities: dict[str, Any] = {}
    for name, raw_capability in sorted(result.capabilities.items()):
        capability = raw_capability.normalized()
        capabilities[name] = {
            "readable": capability.readable,
            "writable": capability.writable,
            "values": list(capability.values) if capability.values is not None else None,
            "minimum": capability.minimum,
            "maximum": capability.maximum,
            "step": capability.step,
            "evidence": [_evidence_to_json(item) for item in capability.evidence],
        }

    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "identity": {
            "vendor_id": result.device.vendor_id,
            "product_id": result.device.product_id,
            "bus": result.device.bus,
        },
        "fingerprints": {
            "model": result.device.model_fingerprint,
            "instance": result.device.instance_fingerprint,
        },
        "protocol": protocol,
        "responder": responder,
        "capabilities": capabilities,
        "observations": [_evidence_to_json(item) for item in result.observations],
    }


def validate_profile(profile: Mapping[str, Any]) -> None:
    """Validate the minimum schema and the no-volatile-path invariant."""

    if profile.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise DeviceProfileError(
            f"unsupported profile schema {profile.get('schema_version')!r}"
        )
    identity = profile.get("identity")
    fingerprints = profile.get("fingerprints")
    capabilities = profile.get("capabilities")
    if not isinstance(identity, Mapping):
        raise DeviceProfileError("profile identity must be an object")
    if not isinstance(fingerprints, Mapping) or not fingerprints.get("model"):
        raise DeviceProfileError("profile requires a model fingerprint")
    if not isinstance(capabilities, Mapping):
        raise DeviceProfileError("profile capabilities must be an object")

    serialized = json.dumps(_json_safe(profile), sort_keys=True)
    if "/dev/hidraw" in serialized or "/dev/input/event" in serialized:
        raise DeviceProfileError("volatile Linux device paths may not be persisted")

    for name, capability in capabilities.items():
        if not isinstance(capability, Mapping):
            raise DeviceProfileError(f"capability {name!r} must be an object")
        if capability.get("writable"):
            evidence = capability.get("evidence") or []
            if not any(
                isinstance(item, Mapping) and item.get("level") == "proven"
                for item in evidence
            ):
                raise DeviceProfileError(
                    f"writable capability {name!r} has no proven evidence"
                )


def profile_filename(profile: Mapping[str, Any]) -> str:
    identity = profile["identity"]
    model = str(profile["fingerprints"]["model"])
    vendor = identity.get("vendor_id")
    product = identity.get("product_id")
    vendor_text = f"{vendor:04x}" if isinstance(vendor, int) else "unknown"
    product_text = f"{product:04x}" if isinstance(product, int) else "unknown"
    return f"{vendor_text}-{product_text}-{model[:16]}.json"


class DeviceProfileStore:
    """Atomic persistence and matching for discovery profiles."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or get_profile_directory()

    def save(self, result: DiscoveryResult) -> Path:
        profile = result_to_profile(result)
        validate_profile(profile)
        self.directory.mkdir(parents=True, exist_ok=True)
        destination = self.directory / profile_filename(profile)
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.directory,
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
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
        return destination

    def load(self, path: Path) -> dict[str, Any]:
        try:
            profile = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DeviceProfileError(f"could not read profile {path}: {exc}") from exc
        if not isinstance(profile, dict):
            raise DeviceProfileError("profile root must be a JSON object")
        validate_profile(profile)
        return profile

    def profiles(self) -> list[tuple[Path, dict[str, Any]]]:
        if not self.directory.is_dir():
            return []
        result: list[tuple[Path, dict[str, Any]]] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                result.append((path, self.load(path)))
            except DeviceProfileError:
                continue
        return result

    def find(
        self,
        *,
        model_fingerprint: str,
        instance_fingerprint: str | None = None,
    ) -> tuple[Path, dict[str, Any]] | None:
        matches = self.profiles()
        if instance_fingerprint:
            exact = [
                item
                for item in matches
                if item[1]["fingerprints"].get("instance") == instance_fingerprint
            ]
            if len(exact) == 1:
                return exact[0]
            if len(exact) > 1:
                return None
        model = [
            item
            for item in matches
            if item[1]["fingerprints"].get("model") == model_fingerprint
        ]
        return model[0] if len(model) == 1 else None
