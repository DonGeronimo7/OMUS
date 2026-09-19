# Development and change-control policy

OMUS accepts focused, reviewable changes that preserve the established
remapping and hardware-safety contracts. The repository, tests, recorded
hardware evidence, and project status are authoritative when they differ from a
discussion or proposal.

## Change control

Open an issue before changing a validated hardware protocol, remapper lifecycle,
service integration, permissions, or release process. A pull request must state
the problem, intended behavior, affected paths, safety boundary, validation,
and remaining risk. Keep unrelated refactors separate. Maintainers review the
diff and required checks before merging; direct changes to the protected default
branch are not part of the normal workflow.

Major new functionality must include automated tests. A deterministic bug fix
must include a regression test that demonstrates the failure before the fix and
passes afterward. If a result depends on physical hardware and cannot be
automated, record that limitation and report automated and physical validation
separately. Test fixtures and reasoning do not count as physical validation.

Python code targets the supported Python versions declared in `pyproject.toml`.
Ruff is the enforced static-analysis and style baseline. Prefer small additive
interfaces, explicit errors, conservative fallbacks, and type annotations where
they clarify an interface. Never broaden hardware write authority from names,
ambiguous identity, descriptor shape, or read-only observations.

## Required validation

Run these checks from the repository root before requesting review:

```bash
python3 -m ruff check src tests scripts fuzz
python3 scripts/validate_workflows.py
python3 scripts/verify_dependency_locks.py
scripts/check-wheel-reproducibility.sh
PYTHONPATH=src python3 -m pytest -q
python3 -m compileall -q src tests fuzz
git diff --check
```

Release changes must additionally build the wheel, source archive, RPM, DEB,
and AppImage paths they affect. The release workflow remains the authoritative
clean-environment integration check.

## Dependency policy

Human-reviewed requirement inputs live in `requirements/*.in`. Generated
`requirements/*.lock.txt` files pin every resolved package to an exact version
and require SHA-256 hashes. CI, auditing, release, SBOM, fuzzing, and AppImage
tool environments install from the relevant lock with `--require-hashes`.

To regenerate the locks, first bootstrap the lock tooling from its own reviewed,
hash-checked lock, then run the deterministic helper:

```bash
python3 -m venv .lock-venv
.lock-venv/bin/python -m pip install --require-hashes \
  -r requirements/lock-tools.lock.txt
PATH="$PWD/.lock-venv/bin:$PATH" scripts/regenerate-locks.sh
python3 scripts/verify_dependency_locks.py
```

Review both the input and the complete resolution diff. Dependabot proposes
updates, and the scheduled dependency-audit workflow checks the locked graph for
known vulnerabilities. A dependency update is not complete until the normal
test and packaging gates pass.

## Releases and security

Follow the documented release process and
[`SECURITY_SUPPLY_CHAIN.md`](SECURITY_SUPPLY_CHAIN.md). Do not create or move a
tag to make a check pass, and do not publish artifacts from a local working tree.
Report suspected vulnerabilities privately according to [`SECURITY.md`](../SECURITY.md).
