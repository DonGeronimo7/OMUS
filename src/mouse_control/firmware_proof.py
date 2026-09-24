"""Read-only firmware artifact inspection and dry-run matching.

No function in this module opens hardware or exposes a flashing primitive.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
from pathlib import Path


@dataclass(frozen=True)
class FirmwareRecipe:
    family: str
    runtime_identity: str
    bootloader_identity: str
    image_size: int
    header_magic: bytes
    expected_sha256: str
    transport: str
    provenance: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class FirmwareInspection:
    path: str
    size: int
    sha256: str
    prefix_hex: str


@dataclass(frozen=True)
class FirmwareDryRun:
    inspection: FirmwareInspection
    recipe: FirmwareRecipe
    compatible: bool
    reasons: tuple[str, ...]
    writes_enabled: bool = False


def inspect_firmware(path: Path, *, maximum_size: int = 64 * 1024 * 1024) -> FirmwareInspection:
    data = path.read_bytes()
    if not data or len(data) > maximum_size:
        raise ValueError("firmware image is empty or exceeds inspection bound")
    return FirmwareInspection(str(path), len(data), hashlib.sha256(data).hexdigest(), data[:32].hex())


def dry_run_firmware(inspection: FirmwareInspection, recipe: FirmwareRecipe, *,
                     connected_runtime_identity: str, valid_evidence: frozenset[str]) -> FirmwareDryRun:
    reasons: list[str] = []
    if connected_runtime_identity != recipe.runtime_identity:
        reasons.append("connected runtime identity does not exactly match recipe")
    if inspection.size != recipe.image_size:
        reasons.append("image size does not match recipe")
    if recipe.expected_sha256 and inspection.sha256 != recipe.expected_sha256:
        reasons.append("image SHA-256 does not match reviewed artifact")
    if recipe.header_magic and not bytes.fromhex(inspection.prefix_hex).startswith(recipe.header_magic):
        reasons.append("image header magic does not match parser family")
    if not recipe.provenance.strip():
        reasons.append("artifact provenance missing")
    if not recipe.evidence or any(item not in valid_evidence for item in recipe.evidence):
        reasons.append("recipe evidence missing or invalidated")
    if not recipe.bootloader_identity:
        reasons.append("bootloader identity unresolved")
    return FirmwareDryRun(inspection, recipe, not reasons, tuple(reasons), False)
