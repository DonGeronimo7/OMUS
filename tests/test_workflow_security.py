from __future__ import annotations

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.validate_workflows import (
    ROOT,
    validate_dependabot,
    validate_repository,
    validate_workflow,
)


def _write_workflow(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "workflow.yml"
    path.write_text(body, encoding="utf-8")
    return path


def test_repository_workflows_follow_security_policy() -> None:
    assert validate_repository() == []


def test_mutable_remote_action_is_rejected(tmp_path: Path) -> None:
    path = _write_workflow(
        tmp_path,
        """name: unsafe
on: push
permissions: read-all
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
""",
    )

    errors = validate_workflow(path)

    assert any("not pinned to a full SHA" in error for error in errors)


def test_unallowlisted_write_permission_is_rejected(tmp_path: Path) -> None:
    path = _write_workflow(
        tmp_path,
        """name: unsafe
on: push
permissions: read-all
jobs:
  test:
    permissions:
      contents: write
    runs-on: ubuntu-latest
    steps: []
""",
    )

    errors = validate_workflow(path)

    assert any("do not match allowlist" in error for error in errors)


def test_malformed_workflow_is_rejected(tmp_path: Path) -> None:
    path = _write_workflow(tmp_path, "jobs: [\n")

    assert any("invalid YAML" in error for error in validate_workflow(path))


def test_workflow_validator_uses_repository_root() -> None:
    assert (ROOT / ".github" / "workflows").is_dir()


def test_dependabot_requires_both_ecosystems_and_monthly_groups(tmp_path: Path) -> None:
    path = tmp_path / "dependabot.yml"
    path.write_text("version: 2\nupdates: []\n", encoding="utf-8")

    errors = validate_dependabot(path)

    assert any("missing github-actions" in error for error in errors)
    assert any("missing pip" in error for error in errors)
