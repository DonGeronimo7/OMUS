"""Deterministic, versioned manifest support for trace sessions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from .models import TRACE_SCHEMA_VERSION, CaptureSource


SESSION_MANIFEST_SCHEMA_VERSION = 1


def sha256_file(path: Path, *, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class TraceSessionManifest:
    session_id: str
    mouse_control_commit: str
    operating_system: str
    kernel: str
    capture_source: CaptureSource
    device_fingerprint: str
    descriptor_fingerprint: str | None
    experiment_definition: str | None
    random_seed: int | None
    started_ns: int
    ended_ns: int | None = None
    raw_capture_sha256: str | None = None
    normalized_evidence_sha256: str | None = None
    trace_schema_version: int = TRACE_SCHEMA_VERSION
    schema_version: int = SESSION_MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.session_id or not self.device_fingerprint:
            raise ValueError("session and device fingerprint are required")
        if self.started_ns < 0 or (self.ended_ns is not None and self.ended_ns < self.started_ns):
            raise ValueError("manifest timestamps are invalid")

    def to_json(self) -> str:
        payload = asdict(self)
        payload["capture_source"] = self.capture_source.value
        return json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"

    @classmethod
    def from_json(cls, text: str) -> "TraceSessionManifest":
        raw = json.loads(text)
        if raw.get("schema_version") != SESSION_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported trace session manifest schema")
        if raw.get("trace_schema_version") != TRACE_SCHEMA_VERSION:
            raise ValueError("unsupported trace evidence schema")
        raw["capture_source"] = CaptureSource(raw["capture_source"])
        return cls(**raw)
