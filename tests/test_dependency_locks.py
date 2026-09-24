# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.verify_dependency_locks import LOCK_NAMES, validate_repository


def test_generated_dependency_locks_are_exact_and_hash_checked():
    assert validate_repository() == []


def test_workflow_python_environments_use_hash_locks():
    workflow_paths = (
        ROOT / ".github/workflows/ci.yml",
        ROOT / ".github/workflows/dependency-audit.yml",
        ROOT / ".github/workflows/release-artifacts.yml",
    )
    for path in workflow_paths:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "pip install" not in line:
                continue
            if "--no-deps" in line:
                assert re.search(r"(?:dist|release-assets)/\*\.whl|\s\.\s*$", line), (
                    path,
                    number,
                    line,
                )
                continue
            assert "--require-hashes" in line, (path, number, line)
            assert re.search(r"requirements/[a-z]+\.lock\.txt", line), (
                path,
                number,
                line,
            )


def test_every_lock_is_shipped_and_has_a_declared_input():
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    assert "recursive-include requirements *.in *.txt" in manifest
    for name in LOCK_NAMES:
        assert (ROOT / f"requirements/{name}.in").is_file()
        assert (ROOT / f"requirements/{name}.lock.txt").is_file()
