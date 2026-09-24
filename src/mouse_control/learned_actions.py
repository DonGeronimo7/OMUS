# SPDX-License-Identifier: AGPL-3.0-or-later
"""Validated, read-only learned physical-action triggers.

Action triggers are intentionally separate from learned writable operations.
They may identify that a physical action occurred, but they can never authorize
a HID write. Runtime may combine a validated trigger with an independently
PROVEN writable operation for the same exact physical model.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import pwd
from tempfile import NamedTemporaryFile
from typing import Any, Mapping, Sequence

from .device_profiles import get_profile_directory
from .learned_operations import (
    LearnedOperationError,
    StableDeviceIdentity,
    StableInterfaceIdentity,
    operation_matches_physical,
    matching_interface_node,
)
from .polling_replay import PacketPattern
from .protocol_grammar import SafetyClass, SemanticBehavior, WriteScope


LEARNED_ACTION_SCHEMA_VERSION = 1


class LearnedActionError(RuntimeError):
    """A learned action-trigger profile is malformed or ambiguous."""


@dataclass(frozen=True)
class LearnedActionTrigger:
    behavior: SemanticBehavior
    identity: StableDeviceIdentity
    interface: StableInterfaceIdentity
    press_pattern: PacketPattern
    release_pattern: PacketPattern
    observation_count: int
    safety: SafetyClass = SafetyClass.READ_ONLY
    write_scope: WriteScope = WriteScope.NEVER
    status: str = "validated"

    @property
    def write_authorized(self) -> bool:
        return False

    def matches_press(self, packet: bytes) -> bool:
        return self.press_pattern.matches(packet)

    def matches_release(self, packet: bytes) -> bool:
        return self.release_pattern.matches(packet)


def get_learned_action_directory() -> Path:
    return get_profile_directory() / "learned-actions"


def _pattern_to_json(pattern: PacketPattern) -> list[int | None]:
    return list(pattern.bytes_)


def _pattern_from_json(data: Sequence[Any]) -> PacketPattern:
    try:
        values = tuple(None if value is None else int(value) for value in data)
    except (TypeError, ValueError) as exc:
        raise LearnedActionError(f"invalid packet pattern: {exc}") from exc
    if not values:
        raise LearnedActionError("learned action packet pattern is empty")
    if any(
        value is not None and not 0 <= value <= 0xFF
        for value in values
    ):
        raise LearnedActionError("learned action packet bytes must fit in one byte")
    return PacketPattern(values)


def validate_learned_action(trigger: LearnedActionTrigger) -> None:
    if trigger.behavior is not SemanticBehavior.DPI_CYCLE_TRIGGER:
        raise LearnedActionError("unsupported learned action behavior")
    if trigger.status != "validated":
        raise LearnedActionError("learned action must be explicitly validated")
    if trigger.safety is not SafetyClass.READ_ONLY:
        raise LearnedActionError("learned action must remain read-only")
    if trigger.write_scope is not WriteScope.NEVER:
        raise LearnedActionError("learned action may never authorize writes")
    if trigger.write_authorized:
        raise LearnedActionError("learned action unexpectedly authorizes writes")
    if not trigger.identity.model_fingerprint:
        raise LearnedActionError("learned action requires model fingerprint")
    if not trigger.interface.descriptor_sha256:
        raise LearnedActionError(
            "learned action requires exact descriptor fingerprint"
        )
    if trigger.observation_count < 5:
        raise LearnedActionError(
            "learned action requires at least five guided press/release observations"
        )
    press = trigger.press_pattern.bytes_
    release = trigger.release_pattern.bytes_
    if len(press) != len(release):
        raise LearnedActionError(
            "press and release packets must have the same length"
        )
    if any(value is None for value in press + release):
        raise LearnedActionError(
            "validated action packets must be exact; wildcards are not allowed"
        )
    if press == release:
        raise LearnedActionError("press and release packets must differ")


def learned_action_to_profile(
    trigger: LearnedActionTrigger,
) -> dict[str, Any]:
    validate_learned_action(trigger)
    return {
        "schema_version": LEARNED_ACTION_SCHEMA_VERSION,
        "profile_kind": "learned-action-trigger",
        "behavior": trigger.behavior.value,
        "status": trigger.status,
        "write_authorized": False,
        "safety": trigger.safety.value,
        "write_scope": trigger.write_scope.value,
        "identity": {
            "bus": trigger.identity.bus,
            "vendor_id": trigger.identity.vendor_id,
            "product_id": trigger.identity.product_id,
        },
        "fingerprints": {
            "model": trigger.identity.model_fingerprint,
            "instance": trigger.identity.instance_fingerprint,
        },
        "interface": {
            "bus": trigger.interface.bus,
            "vendor_id": trigger.interface.vendor_id,
            "product_id": trigger.interface.product_id,
            "interface_number": trigger.interface.interface_number,
            "descriptor_sha256": trigger.interface.descriptor_sha256,
        },
        "press_pattern": _pattern_to_json(trigger.press_pattern),
        "release_pattern": _pattern_to_json(trigger.release_pattern),
        "observation_count": int(trigger.observation_count),
        "evidence": {
            "kind": "guided-physical-action",
            "initial_state": "released",
            "sequence": "press-release-alternation",
        },
    }


def validate_learned_action_profile(profile: Mapping[str, Any]) -> None:
    if profile.get("schema_version") != LEARNED_ACTION_SCHEMA_VERSION:
        raise LearnedActionError("unsupported learned-action schema")
    if profile.get("profile_kind") != "learned-action-trigger":
        raise LearnedActionError("unexpected learned-action profile kind")
    if profile.get("behavior") != SemanticBehavior.DPI_CYCLE_TRIGGER.value:
        raise LearnedActionError("learned action has unsupported behavior")
    if profile.get("status") != "validated":
        raise LearnedActionError("learned action is not validated")
    if profile.get("write_authorized") is not False:
        raise LearnedActionError("learned action can never authorize writes")
    if profile.get("safety") != SafetyClass.READ_ONLY.value:
        raise LearnedActionError("learned action must remain read-only")
    if profile.get("write_scope") != WriteScope.NEVER.value:
        raise LearnedActionError("learned action write scope must be NEVER")
    for key in ("identity", "fingerprints", "interface"):
        if not isinstance(profile.get(key), Mapping):
            raise LearnedActionError(f"learned action requires {key}")
    if not profile["fingerprints"].get("model"):
        raise LearnedActionError("learned action requires model fingerprint")
    if not profile["interface"].get("descriptor_sha256"):
        raise LearnedActionError(
            "learned action requires exact descriptor fingerprint"
        )
    evidence = profile.get("evidence")
    if (
        not isinstance(evidence, Mapping)
        or evidence.get("kind") != "guided-physical-action"
        or evidence.get("initial_state") != "released"
        or evidence.get("sequence") != "press-release-alternation"
    ):
        raise LearnedActionError(
            "learned action requires guided alternating press/release evidence"
        )
    serialized = json.dumps(profile, sort_keys=True)
    if "/dev/hidraw" in serialized or "/dev/input/event" in serialized:
        raise LearnedActionError(
            "volatile Linux device paths may not be persisted"
        )
    # Full object validation is the final pass.
    learned_action_from_profile(profile, _skip_validation=True)


def learned_action_from_profile(
    profile: Mapping[str, Any],
    *,
    _skip_validation: bool = False,
) -> LearnedActionTrigger:
    if not _skip_validation:
        validate_learned_action_profile(profile)
    identity = profile["identity"]
    fingerprints = profile["fingerprints"]
    interface = profile["interface"]
    trigger = LearnedActionTrigger(
        behavior=SemanticBehavior(str(profile["behavior"])),
        identity=StableDeviceIdentity(
            bus=identity.get("bus"),
            vendor_id=identity.get("vendor_id"),
            product_id=identity.get("product_id"),
            model_fingerprint=str(fingerprints["model"]),
            instance_fingerprint=(
                None
                if fingerprints.get("instance") is None
                else str(fingerprints["instance"])
            ),
        ),
        interface=StableInterfaceIdentity(
            bus=interface.get("bus"),
            vendor_id=interface.get("vendor_id"),
            product_id=interface.get("product_id"),
            interface_number=interface.get("interface_number"),
            descriptor_sha256=str(interface["descriptor_sha256"]),
        ),
        press_pattern=_pattern_from_json(profile["press_pattern"]),
        release_pattern=_pattern_from_json(profile["release_pattern"]),
        observation_count=int(profile["observation_count"]),
        safety=SafetyClass(str(profile["safety"])),
        write_scope=WriteScope(str(profile["write_scope"])),
        status=str(profile["status"]),
    )
    validate_learned_action(trigger)
    return trigger


def _sudo_owner() -> tuple[int, int] | None:
    if os.geteuid() != 0:
        return None
    try:
        uid = int(os.environ["SUDO_UID"])
        gid = int(os.environ["SUDO_GID"])
    except (KeyError, ValueError):
        return None
    if uid == 0:
        return None
    try:
        pwd.getpwuid(uid)
    except KeyError:
        return None
    return uid, gid


def _filename(trigger: LearnedActionTrigger) -> str:
    vendor = trigger.identity.vendor_id
    product = trigger.identity.product_id
    vendor_text = f"{vendor:04x}" if isinstance(vendor, int) else "unknown"
    product_text = f"{product:04x}" if isinstance(product, int) else "unknown"
    model = trigger.identity.model_fingerprint[:16]
    return (
        f"{vendor_text}-{product_text}-{model}-"
        f"{trigger.behavior.value}.json"
    )


class LearnedActionStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or get_learned_action_directory()

    def save(self, trigger: LearnedActionTrigger) -> Path:
        profile = learned_action_to_profile(trigger)
        validate_learned_action_profile(profile)
        self.directory.mkdir(parents=True, exist_ok=True)
        owner = _sudo_owner()
        if owner is not None:
            for path in (self.directory.parent, self.directory):
                try:
                    if path.stat().st_uid == 0:
                        os.chown(path, *owner)
                except OSError:
                    pass
        destination = self.directory / _filename(trigger)
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.directory,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp = Path(handle.name)
            json.dump(profile, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.replace(temp, destination)
            if owner is not None:
                os.chown(destination, *owner)
        except Exception:
            temp.unlink(missing_ok=True)
            raise
        return destination

    def load(self, path: Path) -> LearnedActionTrigger:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LearnedActionError(
                f"could not load learned action {path}: {exc}"
            ) from exc
        if not isinstance(raw, dict):
            raise LearnedActionError("learned-action root must be an object")
        return learned_action_from_profile(raw)

    def operations(
        self,
    ) -> tuple[tuple[Path, LearnedActionTrigger], ...]:
        if not self.directory.is_dir():
            return ()
        result: list[tuple[Path, LearnedActionTrigger]] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                result.append((path, self.load(path)))
            except LearnedActionError:
                continue
        return tuple(result)

    def find_for_physical(
        self,
        physical,
        *,
        behavior: SemanticBehavior = SemanticBehavior.DPI_CYCLE_TRIGGER,
    ) -> tuple[Path, LearnedActionTrigger] | None:
        matches = []
        for item in self.operations():
            _path, trigger = item
            if trigger.behavior is not behavior:
                continue
            if not operation_matches_physical(trigger, physical):
                continue
            try:
                matching_interface_node(trigger, physical)
            except LearnedOperationError:
                continue
            matches.append(item)
        return matches[0] if len(matches) == 1 else None
