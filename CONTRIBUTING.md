# Contributing to Mouse Control

Contributions are welcome, especially hardware compatibility reports. This
project needs reports from mice that work perfectly as much as reports of
failures: together they build an evidence-based compatibility database.

## Report a bug or mouse result

Use the [Hardware compatibility template](https://github.com/DonGeronimo7/mouse-control/issues/new?template=hardware-compatibility.yml) for any mouse result, including a fully working setup. Use the bug-report template for reproducible application problems that are not primarily hardware compatibility reports.

Before filing, run:

```bash
mouse-control doctor --report
```

Include the relevant output after reviewing it. The report is designed to omit
usernames, home paths, serial numbers, cache contents, and unrelated USB
devices, but please do not include credentials, private logs, or identifying
information you do not want to make public.

For hardware reports, include the manufacturer/model, connection type,
distribution, desktop environment or compositor when relevant, installation
method, Mouse Control version, and what worked or failed. Successful reports
are particularly valuable right now.

## Pull requests

Keep pull requests focused and explain the hardware or workflow they affect.
Avoid changing validated HID++, remapping, notification, service, permission,
or backend behavior without first opening an issue that documents the objective
problem and the hardware evidence.

Before submitting a change, run:

```bash
python3 -m pytest -q
python3 -m compileall -q src tests
git diff --check
```

Please add or update tests for behavior changes where practical. Do not commit
build outputs, virtual environments, caches, private diagnostic logs, or local
paths.
