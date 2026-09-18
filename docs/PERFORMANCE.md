# Mouse Control Python Performance

## Measurement rules

Performance work follows this order: measure, remove unnecessary work, then
optimize code that remains measurably important. Timings in this document are
automated software measurements, not physical-device validation. Hardware
safety, updater verification, and the v0.8.2 compatibility contract take
priority over benchmark movement.

Run the permanent representative suite with:

```bash
PYTHONPATH=src python3 benchmarks/run_performance.py --rounds 500 --json
```

The suite reports medians plus minimum/maximum observations. It uses controlled
in-memory device topology and read-only HID fixtures so CI can detect large
regressions without touching hardware. Absolute timings are host-specific;
comparisons must use the same host, Python build, fixture, and round count.

The opt-in `PerformanceRecorder` exposes these runtime milestones without
changing production behavior when no recorder is active:

- configuration load;
- evdev mouse enumeration;
- physical identity resolution and topology construction;
- persisted-evidence lookup;
- descriptor acquisition and parsing;
- protocol binding;
- hardware validation;
- TUI frame preparation;
- runtime ready.

Process start and import completion are measured in fresh subprocesses because
they occur before an in-process recorder can exist. Explicit Rediscover is
always measured separately from cached known-device restoration.

## Baseline — 2026-09-18

Starting product commit: `933e7c8d68625c72e5c4d45b2f81f11b98e5d88c`

Host: Fedora Linux 7.2.4 x86_64, AMD Ryzen 5 7600X (6 cores / 12 threads),
CPython 3.14.7. Command: 500 rounds; process/import use 25 fresh processes,
Rediscover uses 100 rounds, and bulk decode uses 50 rounds.

| Representative operation | Baseline median |
|---|---:|
| Process start (`python -c pass`) | 8.329 ms |
| Process start through `mouse_control.app` import | 113.328 ms |
| Configuration load | 0.0169 ms |
| Three-interface topology construction | 0.0714 ms |
| Persisted-evidence lookup | 0.0308 ms |
| Known-device startup/restore | 0.0341 ms |
| Explicit Rediscover (three descriptors) | 0.577 ms |
| Descriptor parse | 0.0209 ms |
| Single HID report decode | 0.0652 ms |
| 1,000 HID report decodes | 66.552 ms |
| TUI first-frame row preparation | 0.00139 ms |
| Supervisor reconnect/rebind | 0.00313 ms |

One traced known-device run recorded topology at 0.00568 ms, persisted lookup
at 0.142 ms, and runtime-ready at 0.175 ms. One forced Rediscover trace recorded
descriptor parsing at 0.0302 ms, protocol binding at 0.00114 ms, validation at
0.00231 ms, and runtime-ready at 0.772 ms. Individual trace values are
diagnostic, not stable performance claims; the repeated medians above are the
comparison baseline.

No optimization had been applied when these figures were recorded. The main
measurable target is cold import completion; the known-device path is already
far cheaper than forced discovery and must remain free of descriptor parsing,
protocol probing, semantic inference, promotion logic, and research probes.

## Optimization accounting

For each accepted change, add one row after measuring before and after on the
same host. Do not enter an improvement without the matching test and safety
explanation.

| Change | Operation | Before | After | Absolute | Percent | Tests / safety |
|---|---|---:|---:|---:|---:|---|
| Baseline only | — | — | — | — | — | 728-test updater checkpoint; performance gate pending |
