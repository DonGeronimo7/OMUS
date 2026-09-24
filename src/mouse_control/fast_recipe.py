"""Compact verified runtime recipes, separate from the research graph."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


@dataclass(frozen=True)
class FastRecipe:
    identity_fingerprint: str
    interface_number: int
    descriptor_sha256: str
    firmware: str
    transaction: str
    codec: str
    legal_values: tuple[int, ...]
    precondition: str
    verification: str
    session_lifetime: str
    evidence: tuple[str, ...]
    generation: int = 0
    evidence_revision: str = ""

    def dumps(self) -> str:
        return json.dumps({"schema": 1, **asdict(self)}, sort_keys=True, separators=(",", ":"))

    @classmethod
    def loads(cls, text: str) -> "FastRecipe":
        if len(text) > 65536:
            raise ValueError("recipe exceeds bound")
        row = json.loads(text)
        if not isinstance(row, dict) or row.pop("schema", None) != 1:
            raise ValueError("unsupported recipe schema")
        required = set(cls.__dataclass_fields__)
        if set(row) != required:
            raise ValueError("malformed recipe fields")
        if not isinstance(row.get("legal_values"), list) or len(row["legal_values"]) > 4096:
            raise ValueError("invalid or excessive recipe value domain")
        if not isinstance(row.get("evidence"), list) or len(row["evidence"]) > 4096:
            raise ValueError("invalid or excessive recipe evidence")
        row["legal_values"] = tuple(row["legal_values"])
        row["evidence"] = tuple(row["evidence"])
        try:
            recipe = cls(**row)
        except TypeError as exc:
            raise ValueError("malformed recipe values") from exc
        recipe._validate_shape()
        return recipe

    def _validate_shape(self) -> None:
        strings = (self.identity_fingerprint, self.descriptor_sha256, self.firmware,
                   self.transaction, self.codec, self.precondition, self.verification,
                   self.session_lifetime, self.evidence_revision)
        if any(not isinstance(item, str) for item in strings):
            raise ValueError("recipe text fields must be strings")
        if (not isinstance(self.interface_number, int) or self.interface_number < 0
                or not isinstance(self.generation, int) or self.generation < 0):
            raise ValueError("recipe interface and generation must be non-negative integers")
        if len(self.descriptor_sha256) != 64:
            raise ValueError("recipe descriptor fingerprint must be SHA-256")
        if any(not isinstance(item, int) or item <= 0 for item in self.legal_values):
            raise ValueError("recipe legal values must be positive integers")
        if any(not isinstance(item, str) or not item for item in self.evidence):
            raise ValueError("recipe evidence identifiers must be non-empty strings")

    def validate(self, *, identity_fingerprint: str, descriptor_sha256: str,
                 firmware: str, valid_evidence: frozenset[str],
                 current_generation: int | None = None,
                 evidence_revision: str | None = None) -> tuple[bool, tuple[str, ...]]:
        reasons = []
        if self.identity_fingerprint != identity_fingerprint:
            reasons.append("identity fingerprint changed")
        if self.descriptor_sha256 != descriptor_sha256:
            reasons.append("interface descriptor changed")
        if self.firmware != firmware:
            reasons.append("firmware changed")
        if current_generation is not None and self.generation != current_generation:
            reasons.append("connection generation changed")
        if evidence_revision is not None and self.evidence_revision != evidence_revision:
            reasons.append("evidence revision changed")
        if any(item not in valid_evidence for item in self.evidence):
            reasons.append("recipe evidence invalidated")
        return not reasons, tuple(reasons)


class FastRecipeStore:
    """Atomic, bounded compact-recipe persistence; corruption grants no authority."""

    def save(self, path: Path, recipe: FastRecipe) -> None:
        recipe._validate_shape()
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(recipe.dumps() + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.replace(temporary, path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def load(self, path: Path) -> FastRecipe:
        try:
            if path.is_symlink() or path.stat().st_size > 65536:
                raise ValueError("unsafe or oversized recipe file")
            return FastRecipe.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"invalid compact recipe: {exc}") from exc
