# Contributing to OMUS

Contributions are welcome, especially hardware compatibility reports. This
project needs reports from mice that work perfectly as much as reports of
failures: together they build an evidence-based compatibility database.

## Test a mouse

Use the [New mouse / discovery result template](https://github.com/DonGeronimo7/mouse-control/issues/new?template=hardware-compatibility.yml)
for any mouse result, including a fully working setup. Unknown, obscure, OEM,
rebrand, wireless, older, and unusual devices are especially useful.

Run the normal guided flow first:

```bash
mouse-control
```

Select the mouse and open **Hardware / Discovery**. If guided discovery is
offered, follow it; you do not need to understand HID or mouse protocols.

Then create both shareable reports when possible:

```bash
mouse-control support --guided
mouse-control discover --output mouse-control-discovery.json
```

The support command saves a text report in your home directory. The discovery
command saves an allowlisted JSON artifact at the path you choose. These reports
are designed to omit usernames, device paths, serial numbers, input history,
cache contents, and unrelated USB devices. Review every file before posting and
remove anything you do not want to share.

Include the exact model, connection type, distribution, installation method,
OMUS version, what discovery recognized, what worked or failed,
whether DPI/polling changes were observed, and reconnect behavior. Do not spend
time manually collecting identifiers already present in the generated reports.

Use the bug-report template for reproducible application problems on an
already-understood setup, and the feature-request template for product or
workflow proposals.

## Pull requests

Keep pull requests focused and explain the hardware or workflow they affect.
Avoid changing validated HID++, remapping, notification, service, permission,
or backend behavior without first opening an issue that documents the objective
problem and the hardware evidence. Follow the project's
[development and change-control policy](docs/DEVELOPMENT_POLICY.md).

Every major new feature must include automated tests. Every deterministic bug
fix must include a regression test that fails without the fix. When a regression
cannot be automated (for example, because it requires unavailable physical
hardware), document the reason, the manual evidence, and the remaining risk in
the pull request.

Before submitting a change, run:

```bash
python3 -m ruff check src tests scripts fuzz
python3 scripts/validate_workflows.py
python3 scripts/verify_dependency_locks.py
scripts/check-wheel-reproducibility.sh
PYTHONPATH=src python3 -m pytest -q
python3 -m compileall -q src tests scripts fuzz
git diff --check
```

Please add or update tests for behavior changes where practical. Do not commit
build outputs, virtual environments, caches, private diagnostic logs, or local
paths.

Dependency versions are maintained as reviewed input files and reproducible,
hash-checked lock files. Do not edit a generated `requirements/*.lock.txt` by
hand; use the documented regeneration procedure in
[`docs/DEVELOPMENT_POLICY.md`](docs/DEVELOPMENT_POLICY.md).
