# Contributing to Mouse Control

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
Mouse Control version, what discovery recognized, what worked or failed,
whether DPI/polling changes were observed, and reconnect behavior. Do not spend
time manually collecting identifiers already present in the generated reports.

Use the bug-report template for reproducible application problems on an
already-understood setup, and the feature-request template for product or
workflow proposals.

## Pull requests

Keep pull requests focused and explain the hardware or workflow they affect.
Avoid changing validated HID++, remapping, notification, service, permission,
or backend behavior without first opening an issue that documents the objective
problem and the hardware evidence.

Before submitting a change, run:

```bash
python3 -m ruff check src tests scripts
python3 scripts/validate_workflows.py
scripts/check-wheel-reproducibility.sh
python3 -m pytest -q
python3 -m compileall -q src tests
git diff --check
```

Please add or update tests for behavior changes where practical. Do not commit
build outputs, virtual environments, caches, private diagnostic logs, or local
paths.
