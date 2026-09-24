#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Detect obvious regressions in current OMUS licensing metadata."""

from __future__ import annotations

from pathlib import Path
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]
EXPRESSION = "AGPL-3.0-or-later"
PYTHON_TREES = ("src/mouse_control", "scripts", "fuzz", "benchmarks", "tests")


def _python_files() -> list[Path]:
    files: list[Path] = []
    for relative in PYTHON_TREES:
        files.extend((ROOT / relative).glob("*.py"))
        if relative == "src/mouse_control":
            files.extend((ROOT / relative).glob("**/*.py"))
    return sorted(set(files))


def check() -> list[str]:
    errors: list[str] = []
    with (ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]

    if project.get("license") != EXPRESSION:
        errors.append(f"pyproject.toml: project.license must be {EXPRESSION!r}")
    expected_files = [
        "LICENSE",
        "CREDITS.md",
        "DUAL-LICENSING.md",
        "docs/LICENSING_PROVENANCE.md",
    ]
    if project.get("license-files") != expected_files:
        errors.append(f"pyproject.toml: project.license-files must be {expected_files!r}")

    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    if "GNU AFFERO GENERAL PUBLIC LICENSE" not in license_text[:200]:
        errors.append("LICENSE: canonical GNU Affero GPL text is missing")

    current_surfaces = {
        "README.md": EXPRESSION,
        "DUAL-LICENSING.md": EXPRESSION,
        "omus.spec": f"License:        {EXPRESSION}",
        "PKGBUILD": f"license=('{EXPRESSION}')",
        ".SRCINFO": f"license = {EXPRESSION}",
        "packaging/omus.metainfo.xml": f"<project_license>{EXPRESSION}</project_license>",
    }
    for relative, marker in current_surfaces.items():
        if marker not in (ROOT / relative).read_text(encoding="utf-8"):
            errors.append(f"{relative}: missing current license marker {marker!r}")

    header = f"SPDX-License-Identifier: {EXPRESSION}"
    for path in _python_files():
        first_lines = "\n".join(path.read_text(encoding="utf-8").splitlines()[:3])
        if header not in first_lines:
            errors.append(f"{path.relative_to(ROOT)}: missing SPDX header")

    return errors


def main() -> int:
    errors = check()
    if errors:
        print("license consistency validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("license consistency validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
