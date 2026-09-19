#!/usr/bin/env python3
"""Enforce repository-owned GitHub workflow security invariants."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
REMOTE_USE = re.compile(
    r"^\s*-?\s*uses:\s*([^\s@]+)@([0-9a-fA-F]+)\s+#\s*(\S.*)$",
    re.MULTILINE,
)
ANY_REMOTE_USE = re.compile(r"^\s*-?\s*uses:\s*([^\s@]+)@([^\s#]+)", re.MULTILINE)
FULL_SHA = re.compile(r"[0-9a-f]{40}")
VERSION_COMMENT = re.compile(r"v\d+(?:\.\d+){0,2}\b")

ALLOWED_JOB_WRITES: dict[tuple[str, str], set[str]] = {
    ("release-artifacts.yml", "publish"): {"contents"},
    ("release-trigger.yml", "create-tag"): {"contents"},
    ("release-trigger.yml", "dispatch"): {"actions"},
}


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        display_path = path.relative_to(ROOT)
    except ValueError:
        display_path = path
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"{display_path}: invalid YAML: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"{display_path}: workflow must be a mapping")
    return loaded


def _write_permissions(value: Any) -> set[str]:
    if value is None or value == "read-all":
        return set()
    if value == "write-all":
        return {"write-all"}
    if not isinstance(value, dict):
        return {f"invalid:{value!r}"}
    return {key for key, level in value.items() if level == "write"}


def validate_workflow(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        relative = path.relative_to(ROOT)
    except ValueError:
        relative = path
    text = path.read_text(encoding="utf-8")
    try:
        document = _load_yaml(path)
    except ValueError as exc:
        return [str(exc)]

    if re.search(r"^\s*pull_request_target\s*:", text, re.MULTILINE):
        errors.append(f"{relative}: pull_request_target is prohibited")
    if "${{ github.event." in "\n".join(
        match.group(0) for match in re.finditer(r"(?ms)^\s+run:\s*(?:\|\s*\n(?:\s+.*\n?)*)", text)
    ):
        errors.append(f"{relative}: pass event data through a quoted environment variable, not run interpolation")

    top_writes = _write_permissions(document.get("permissions"))
    if top_writes:
        errors.append(f"{relative}: workflow-level write permissions are prohibited: {sorted(top_writes)}")

    jobs = document.get("jobs")
    if not isinstance(jobs, dict):
        errors.append(f"{relative}: jobs must be a mapping")
        jobs = {}
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            errors.append(f"{relative}: job {job_name!r} must be a mapping")
            continue
        writes = _write_permissions(job.get("permissions"))
        allowed = ALLOWED_JOB_WRITES.get((path.name, str(job_name)), set())
        if writes != allowed:
            errors.append(
                f"{relative}: job {job_name!r} write permissions {sorted(writes)} "
                f"do not match allowlist {sorted(allowed)}"
            )

    matched_lines = {match.group(0) for match in REMOTE_USE.finditer(text)}
    for match in ANY_REMOTE_USE.finditer(text):
        owner_action, ref = match.groups()
        if owner_action.startswith("./"):
            continue
        if not FULL_SHA.fullmatch(ref):
            errors.append(f"{relative}: remote action {owner_action}@{ref} is not pinned to a full SHA")
        if match.group(0) not in matched_lines:
            line = text[match.start() : text.find("\n", match.start()) if "\n" in text[match.start() :] else None]
            if not VERSION_COMMENT.search(line):
                errors.append(f"{relative}: remote action {owner_action}@{ref} lacks a version comment")

    return errors


def validate_repository() -> list[str]:
    errors: list[str] = []
    paths = sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(WORKFLOW_DIR.glob("*.yaml"))
    if not paths:
        return ["no GitHub workflows found"]
    for path in paths:
        errors.extend(validate_workflow(path))
    return errors


def main() -> int:
    errors = validate_repository()
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("workflow security policy: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
