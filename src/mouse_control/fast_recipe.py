"""Compact verified runtime recipes, separate from the research graph."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import json


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

    def dumps(self) -> str:
        return json.dumps({"schema": 1, **asdict(self)}, sort_keys=True, separators=(",", ":"))

    @classmethod
    def loads(cls, text: str) -> "FastRecipe":
        if len(text) > 65536:
            raise ValueError("recipe exceeds bound")
        row = json.loads(text)
        if row.pop("schema", None) != 1:
            raise ValueError("unsupported recipe schema")
        row["legal_values"] = tuple(row["legal_values"])
        row["evidence"] = tuple(row["evidence"])
        return cls(**row)

    def validate(self, *, identity_fingerprint: str, descriptor_sha256: str,
                 firmware: str, valid_evidence: frozenset[str]) -> tuple[bool, tuple[str, ...]]:
        reasons = []
        if self.identity_fingerprint != identity_fingerprint:
            reasons.append("identity fingerprint changed")
        if self.descriptor_sha256 != descriptor_sha256:
            reasons.append("interface descriptor changed")
        if self.firmware != firmware:
            reasons.append("firmware changed")
        if any(item not in valid_evidence for item in self.evidence):
            reasons.append("recipe evidence invalidated")
        return not reasons, tuple(reasons)
