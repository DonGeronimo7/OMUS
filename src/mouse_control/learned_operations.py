"""Persistence and safety model for learned writable mouse operations.

Calibrated read profiles and learned write profiles are deliberately separate.
A read-only profile can never be upgraded in place. A learned operation starts
DEMONSTRATED and becomes writable only after an explicit promotion experiment
records independent physical verification.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import json
import os
from pathlib import Path
import pwd
from tempfile import NamedTemporaryFile
from typing import Any, Mapping, Sequence

from .device_profiles import get_profile_directory
from .protocol_codec import decode_value, encode_value
from .protocol_grammar import CodecKind, CodecSpec, SafetyClass, SemanticBehavior, WriteScope
from .transaction_inference import FramePattern, InferredTransactionGrammar, SemanticField


LEARNED_OPERATION_SCHEMA_VERSION = 1


class LearnedOperationError(RuntimeError):
    """A learned operation profile is malformed, ambiguous, or unsafe."""


class LearnedOperationState(str, Enum):
    DEMONSTRATED = "demonstrated"
    PROVEN = "proven"


@dataclass(frozen=True)
class StableDeviceIdentity:
    bus: int | None
    vendor_id: int | None
    product_id: int | None
    model_fingerprint: str
    instance_fingerprint: str | None = None


@dataclass(frozen=True)
class StableInterfaceIdentity:
    bus: int | None
    vendor_id: int | None
    product_id: int | None
    interface_number: int | None
    descriptor_sha256: str | None


@dataclass(frozen=True)
class LearnedOperation:
    behavior: SemanticBehavior
    state: LearnedOperationState
    identity: StableDeviceIdentity
    interface: StableInterfaceIdentity
    demonstrated_values: tuple[int, ...]
    write_request: FramePattern
    write_field: SemanticField
    write_reply: FramePattern
    read_request: FramePattern
    read_reply: FramePattern
    read_field: SemanticField
    safety: SafetyClass = SafetyClass.REVERSIBLE
    write_scope: WriteScope = WriteScope.EXACT_MODEL
    demonstration_count: int = 0
    promotion_evidence: Mapping[str, Any] | None = None

    @property
    def write_authorized(self) -> bool:
        return self.state is LearnedOperationState.PROVEN

    def accepts(self, value: int) -> bool:
        # Version 1 deliberately limits execution to values actually demonstrated.
        return int(value) in self.demonstrated_values

    def render_write(self, value: int) -> bytes:
        if not self.accepts(value):
            raise LearnedOperationError(
                f"value {value} was not part of the demonstrated training set"
            )
        encoded = encode_value(value, self.write_field.codec, width=self.write_field.width)
        return _render(self.write_request, self.write_field, encoded)

    def render_read(self) -> bytes:
        if any(value is None for value in self.read_request.bytes_):
            raise LearnedOperationError("read request contains unresolved wildcard bytes")
        return bytes(int(value) for value in self.read_request.bytes_)

    def decode_readback(self, packet: bytes) -> int:
        if not self.read_reply.matches(packet):
            raise LearnedOperationError("readback packet does not match the learned reply grammar")
        start = self.read_field.offset
        end = start + self.read_field.width
        return decode_value(packet[start:end], self.read_field.codec, width=self.read_field.width)


def _render(pattern: FramePattern, field: SemanticField, encoded: bytes) -> bytes:
    if len(encoded) != field.width:
        raise LearnedOperationError("encoded semantic field has unexpected width")
    output = bytearray()
    for offset, value in enumerate(pattern.bytes_):
        if field.offset <= offset < field.offset + field.width:
            output.append(encoded[offset - field.offset])
        elif value is None:
            raise LearnedOperationError(
                f"cannot render unresolved wildcard at byte {offset}"
            )
        else:
            output.append(value)
    return bytes(output)


def operation_from_grammar(
    grammar: InferredTransactionGrammar,
    *,
    identity: StableDeviceIdentity,
    interface: StableInterfaceIdentity,
    behavior: SemanticBehavior = SemanticBehavior.DPI_VALUE,
) -> LearnedOperation:
    return LearnedOperation(
        behavior=behavior,
        state=LearnedOperationState.DEMONSTRATED,
        identity=identity,
        interface=interface,
        demonstrated_values=grammar.demonstrated_values,
        write_request=grammar.write_request,
        write_field=grammar.write_field,
        write_reply=grammar.write_reply,
        read_request=grammar.read_request,
        read_reply=grammar.read_reply,
        read_field=grammar.read_field,
        demonstration_count=grammar.demonstration_count,
    )


def promote_operation(
    operation: LearnedOperation,
    *,
    target_value: int,
    measured_value: float,
    deviation_fraction: float,
    calibration_confidence: str,
    raw_readback_value: int,
    state_evidence: Mapping[str, Any] | None = None,
) -> LearnedOperation:
    if operation.state is LearnedOperationState.PROVEN:
        return operation
    if operation.safety is not SafetyClass.REVERSIBLE:
        raise LearnedOperationError("only reversible operations may be promoted")
    if operation.write_scope is not WriteScope.EXACT_MODEL:
        raise LearnedOperationError("initial learned writes must use exact-model scope")
    if not operation.accepts(target_value):
        raise LearnedOperationError("promotion target was not previously demonstrated")
    if raw_readback_value != target_value:
        raise LearnedOperationError("generic readback did not confirm the promotion target")
    if abs(float(deviation_fraction)) > 0.15:
        raise LearnedOperationError("physical calibration differs by more than 15%")
    if calibration_confidence not in {"high", "medium"}:
        raise LearnedOperationError("physical calibration confidence is too low")

    evidence = {
        "target_value": int(target_value),
        "raw_readback_value": int(raw_readback_value),
        "measured_value": float(measured_value),
        "deviation_fraction": float(deviation_fraction),
        "calibration_confidence": str(calibration_confidence),
        "state_evidence": dict(state_evidence or {}),
    }
    return replace(
        operation,
        state=LearnedOperationState.PROVEN,
        promotion_evidence=evidence,
    )


def get_learned_operation_directory() -> Path:
    return get_profile_directory() / "learned-operations"


def _codec_to_json(codec: CodecSpec) -> dict[str, Any]:
    return {
        "kind": codec.kind.value,
        "scale": codec.scale,
        "offset": codec.offset,
        "base": codec.base,
        "mask": codec.mask,
        "shift": codec.shift,
        "values": {str(int(key)): int(value) for key, value in codec.values.items()},
    }


def _codec_from_json(data: Mapping[str, Any]) -> CodecSpec:
    try:
        kind = CodecKind(str(data["kind"]))
        values = {int(key): int(value) for key, value in dict(data.get("values") or {}).items()}
        return CodecSpec(
            kind=kind,
            scale=int(data.get("scale", 1)),
            offset=int(data.get("offset", 0)),
            base=None if data.get("base") is None else int(data["base"]),
            mask=None if data.get("mask") is None else int(data["mask"]),
            shift=int(data.get("shift", 0)),
            values=values,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise LearnedOperationError(f"invalid codec: {exc}") from exc


def _field_to_json(field: SemanticField) -> dict[str, Any]:
    return {
        "offset": field.offset,
        "width": field.width,
        "codec": _codec_to_json(field.codec),
    }


def _field_from_json(data: Mapping[str, Any]) -> SemanticField:
    try:
        return SemanticField(
            offset=int(data["offset"]),
            width=int(data["width"]),
            codec=_codec_from_json(data["codec"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise LearnedOperationError(f"invalid semantic field: {exc}") from exc


def _pattern_to_json(pattern: FramePattern) -> list[int | None]:
    return list(pattern.bytes_)


def _pattern_from_json(data: Sequence[Any]) -> FramePattern:
    values: list[int | None] = []
    try:
        for value in data:
            values.append(None if value is None else int(value))
    except (TypeError, ValueError) as exc:
        raise LearnedOperationError(f"invalid frame pattern: {exc}") from exc
    return FramePattern(tuple(values))


def operation_to_profile(operation: LearnedOperation) -> dict[str, Any]:
    return {
        "schema_version": LEARNED_OPERATION_SCHEMA_VERSION,
        "profile_kind": "learned-operation",
        "behavior": operation.behavior.value,
        "status": operation.state.value,
        "write_authorized": operation.write_authorized,
        "safety": operation.safety.value,
        "write_scope": operation.write_scope.value,
        "identity": {
            "bus": operation.identity.bus,
            "vendor_id": operation.identity.vendor_id,
            "product_id": operation.identity.product_id,
        },
        "fingerprints": {
            "model": operation.identity.model_fingerprint,
            "instance": operation.identity.instance_fingerprint,
        },
        "interface": {
            "bus": operation.interface.bus,
            "vendor_id": operation.interface.vendor_id,
            "product_id": operation.interface.product_id,
            "interface_number": operation.interface.interface_number,
            "descriptor_sha256": operation.interface.descriptor_sha256,
        },
        "demonstrated_values": list(operation.demonstrated_values),
        "demonstration_count": operation.demonstration_count,
        "write": {
            "request": _pattern_to_json(operation.write_request),
            "field": _field_to_json(operation.write_field),
            "reply": _pattern_to_json(operation.write_reply),
        },
        "readback": {
            "request": _pattern_to_json(operation.read_request),
            "reply": _pattern_to_json(operation.read_reply),
            "field": _field_to_json(operation.read_field),
        },
        "promotion_evidence": (
            None if operation.promotion_evidence is None
            else dict(operation.promotion_evidence)
        ),
    }


def operation_from_profile(profile: Mapping[str, Any]) -> LearnedOperation:
    validate_learned_operation_profile(profile)
    identity = profile["identity"]
    fingerprints = profile["fingerprints"]
    interface = profile["interface"]
    write = profile["write"]
    readback = profile["readback"]
    return LearnedOperation(
        behavior=SemanticBehavior(str(profile["behavior"])),
        state=LearnedOperationState(str(profile["status"])),
        identity=StableDeviceIdentity(
            bus=identity.get("bus"),
            vendor_id=identity.get("vendor_id"),
            product_id=identity.get("product_id"),
            model_fingerprint=str(fingerprints["model"]),
            instance_fingerprint=(
                None if fingerprints.get("instance") is None
                else str(fingerprints.get("instance"))
            ),
        ),
        interface=StableInterfaceIdentity(
            bus=interface.get("bus"),
            vendor_id=interface.get("vendor_id"),
            product_id=interface.get("product_id"),
            interface_number=interface.get("interface_number"),
            descriptor_sha256=interface.get("descriptor_sha256"),
        ),
        demonstrated_values=tuple(int(value) for value in profile["demonstrated_values"]),
        demonstration_count=int(profile.get("demonstration_count", 0)),
        write_request=_pattern_from_json(write["request"]),
        write_field=_field_from_json(write["field"]),
        write_reply=_pattern_from_json(write["reply"]),
        read_request=_pattern_from_json(readback["request"]),
        read_reply=_pattern_from_json(readback["reply"]),
        read_field=_field_from_json(readback["field"]),
        safety=SafetyClass(str(profile["safety"])),
        write_scope=WriteScope(str(profile["write_scope"])),
        promotion_evidence=profile.get("promotion_evidence"),
    )


def validate_learned_operation_profile(profile: Mapping[str, Any]) -> None:
    if profile.get("schema_version") != LEARNED_OPERATION_SCHEMA_VERSION:
        raise LearnedOperationError("unsupported learned-operation schema")
    if profile.get("profile_kind") != "learned-operation":
        raise LearnedOperationError("unexpected learned-operation profile kind")
    if profile.get("safety") != SafetyClass.REVERSIBLE.value:
        raise LearnedOperationError("learned operation must be explicitly reversible")
    if profile.get("write_scope") != WriteScope.EXACT_MODEL.value:
        raise LearnedOperationError("learned operation must initially be exact-model scoped")
    if profile.get("status") not in {state.value for state in LearnedOperationState}:
        raise LearnedOperationError("invalid learned-operation status")
    authorized = profile.get("write_authorized")
    if authorized is not (profile.get("status") == LearnedOperationState.PROVEN.value):
        raise LearnedOperationError("write authority does not match promotion status")

    fingerprints = profile.get("fingerprints")
    identity = profile.get("identity")
    interface = profile.get("interface")
    if not isinstance(identity, Mapping):
        raise LearnedOperationError("learned operation requires stable device identity")
    if not isinstance(fingerprints, Mapping) or not fingerprints.get("model"):
        raise LearnedOperationError("learned operation requires model fingerprint")
    if not isinstance(interface, Mapping) or not interface.get("descriptor_sha256"):
        raise LearnedOperationError("learned operation requires exact descriptor fingerprint")
    values = profile.get("demonstrated_values")
    if not isinstance(values, list) or len(values) < 3:
        raise LearnedOperationError("learned operation requires at least three demonstrated values")
    if len({int(value) for value in values}) != len(values):
        raise LearnedOperationError("demonstrated values must be unique")
    if not isinstance(profile.get("write"), Mapping) or not isinstance(profile.get("readback"), Mapping):
        raise LearnedOperationError("learned operation requires write and readback grammar")

    serialized = json.dumps(profile, sort_keys=True)
    if "/dev/hidraw" in serialized or "/dev/input/event" in serialized:
        raise LearnedOperationError("volatile Linux device paths may not be persisted")

    # Fully deserialize as the final structural validation pass, but avoid
    # recursion back into validate_learned_operation_profile.
    for section_name in ("write", "readback"):
        section = profile[section_name]
        for key in ("request", "reply"):
            _pattern_from_json(section[key])
    _field_from_json(profile["write"]["field"])
    _field_from_json(profile["readback"]["field"])


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


def _filename(operation: LearnedOperation) -> str:
    vendor = operation.identity.vendor_id
    product = operation.identity.product_id
    vendor_text = f"{vendor:04x}" if isinstance(vendor, int) else "unknown"
    product_text = f"{product:04x}" if isinstance(product, int) else "unknown"
    model = operation.identity.model_fingerprint[:16]
    return f"{vendor_text}-{product_text}-{model}-{operation.behavior.value}.json"


class LearnedOperationStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or get_learned_operation_directory()

    def save(self, operation: LearnedOperation) -> Path:
        profile = operation_to_profile(operation)
        validate_learned_operation_profile(profile)
        self.directory.mkdir(parents=True, exist_ok=True)
        owner = _sudo_owner()
        if owner is not None:
            for path in (self.directory.parent, self.directory):
                try:
                    if path.stat().st_uid == 0:
                        os.chown(path, *owner)
                except OSError:
                    pass
        destination = self.directory / _filename(operation)
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

    def load(self, path: Path) -> LearnedOperation:
        try:
            profile = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LearnedOperationError(f"could not load {path}: {exc}") from exc
        if not isinstance(profile, dict):
            raise LearnedOperationError("learned-operation root must be an object")
        return operation_from_profile(profile)

    def operations(self) -> tuple[tuple[Path, LearnedOperation], ...]:
        if not self.directory.is_dir():
            return ()
        result: list[tuple[Path, LearnedOperation]] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                result.append((path, self.load(path)))
            except LearnedOperationError:
                continue
        return tuple(result)

    def find_for_physical(
        self,
        physical,
        *,
        behavior: SemanticBehavior = SemanticBehavior.DPI_VALUE,
        proven_only: bool = False,
    ) -> tuple[Path, LearnedOperation] | None:
        matches: list[tuple[Path, LearnedOperation]] = []
        for item in self.operations():
            _path, operation = item
            if operation.behavior is not behavior:
                continue
            if proven_only and not operation.write_authorized:
                continue
            if not operation_matches_physical(operation, physical):
                continue
            matches.append(item)
        return matches[0] if len(matches) == 1 else None


def operation_matches_physical(operation: LearnedOperation, physical) -> bool:
    if physical.ambiguous:
        return False
    identity = operation.identity
    if identity.model_fingerprint != physical.model_fingerprint:
        return False
    if (
        identity.instance_fingerprint is not None
        and identity.instance_fingerprint != physical.instance_fingerprint
    ):
        return False
    for expected, actual in (
        (identity.bus, physical.bus),
        (identity.vendor_id, physical.vendor_id),
        (identity.product_id, physical.product_id),
    ):
        if expected is not None and actual is not None and expected != actual:
            return False
    return True


def matching_interface_node(operation: LearnedOperation, physical):
    candidates = []
    interface = operation.interface
    for node in physical.hidraw_nodes:
        if all(
            expected is None or actual == expected
            for expected, actual in (
                (interface.bus, node.bus),
                (interface.vendor_id, node.vendor_id),
                (interface.product_id, node.product_id),
                (interface.interface_number, node.interface_number),
                (interface.descriptor_sha256, node.descriptor_sha256),
            )
        ):
            candidates.append(node)
    if len(candidates) != 1:
        raise LearnedOperationError(
            f"expected exactly one live interface for learned operation, found {len(candidates)}"
        )
    return candidates[0]
