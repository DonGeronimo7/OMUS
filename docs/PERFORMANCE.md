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

The suite reports medians plus minimum/maximum observations and retained-memory
growth after repeated reconnect, Rediscover, and setup enter/exit cycles. It
uses controlled in-memory device topology and read-only HID fixtures so CI can
detect large regressions without touching hardware. Absolute timings are
host-specific; comparisons must use the same host, Python build, fixture, and
round count.

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
| Lazy command-specific imports | Cold `mouse_control.app` import | 113.328 ms | 15.471 ms | -97.857 ms | -86.3% | Runtime/research/updater imports stay absent from cold help; full regression gate passed |
| Known-path preservation | Persisted-evidence lookup | 0.0308 ms | 0.0309 ms | +0.0001 ms | +0.4% | Statistically neutral; exact identity/evidence validation was not removed |
| Known-path preservation | Known-device startup/restore | 0.0341 ms | 0.0342 ms | +0.0001 ms | +0.4% | Statistically neutral; already-cheap path still skips discovery work |
| Bounded immutable descriptor reuse | Descriptor parse/reuse | 0.0209 ms | 0.000140 ms | -0.0208 ms | -99.3% | Exact descriptor bytes key a 128-entry cache; topology snapshots retain bytes in memory only |
| Cached descriptor field identities/layout | Single HID decode | 0.0652 ms | 0.0284 ms | -0.0368 ms | -56.4% | Immutable descriptor/field facts only; packet semantics and authority unchanged |
| Cached descriptor field identities/layout | 1,000 HID decodes | 66.552 ms | 28.388 ms | -38.164 ms | -57.3% | Same decoded values and diagnostics; no write path involved |
| Snapshot plus parsed-knowledge reuse | Explicit Rediscover | 0.577 ms | 0.411 ms | -0.166 ms | -28.8% | Forced discovery still executes descriptor, protocol, observation, and validation phases |
| Event-driven notification wakeup | Idle notifier process CPU / second | 1.031 ms | 0.016 ms | -1.015 ms | -98.4% | Cross-thread queue tests preserve ordered delivery and prohibit timer sleeps |
| Event-driven notification wakeup | Idle voluntary context switches / second | 20 | 1 | -19 | -95.0% | Remaining switch is the measurement thread's one-second sleep |
| Deferred live backend initialization | Cold/transitional supervised TUI first frame | 6,347.09 ms | 464.83 ms | -5,882.26 ms | -92.7% | The complete device-selection frame is interactive first; one owned worker performs the unchanged live backend/evidence checks before hardware navigation |
| Deferred live backend initialization + single evdev validation | Warm known-device supervised TUI first frame (5-run median) | 676.22 ms | 504.15 ms | -172.07 ms | -25.4% | Direct event-node enumeration preserves every candidate and retains the existing `InputDevice` capability/permission checks; service suspension is complete before backend creation |

### Launcher / TUI first-frame pass — 2026-09-18

Starting product commit: `c4828c6cdf99f2f6dc1b9e459e99f170024920f9`.
Measurements used the same Fedora host and attached configured G305. The
supervised interactive application path ran in a fresh pseudo-terminal and
cancelled without saving after the first complete device-selection frame. The
desktop helper's terminal-selection process is unchanged; no build was
installed for this source-only pass.

| Metric | Before | After | Improvement |
|---|---:|---:|---:|
| Process invocation → first supervisor output | 25.60 ms | 25.60 ms | unchanged |
| Interpreter + application/CLI import | 16.25 ms | 16.25 ms | unchanged |
| Setup import graph | 104.38 ms | 104.38 ms | unchanged |
| Configuration load | 2.11 ms | 2.11 ms | unchanged |
| Evdev enumeration (representative live run) | 536.06 ms | 273.55 ms | -49.0% |
| Live backend construction / HID++ handshake | 5,618.49 ms | deferred after frame | removed from first-frame path |
| Capability reads | 68.85 ms | deferred after frame | removed from first-frame path |
| Persisted-state validation | 303.43 ms | deferred after frame | removed from first-frame path |
| Warm known-device first frame, median of 5 | 676.22 ms | 504.15 ms | -25.4% |
| Warm known-device observed maximum of 5 (p95 proxy) | 777.43 ms | 647.61 ms | -16.7% |
| Cold/transitional first frame | 6,347.09 ms | 464.83 ms | -92.7% |

The worker is not an uncontrolled background task: each setup app owns exactly
one non-daemon initializer, polls its result on the curses thread, and joins
and closes it on every exit path. Device selection, Help, resize, and Cancel
remain responsive while it runs. Hardware-dependent navigation is blocked with
an explicit status until initialization completes. The foreground supervisor
queues service suspension early, but backend initialization performs a
blocking completion check before opening any hardware session. Unsaved exit
therefore retains the established external restoration contract.

The permanent 500-round fixture after this pass measured cold app import at
15.655 ms, known-device restore at 0.0342 ms, explicit Rediscover at 0.4171 ms,
and first-frame row preparation at 0.00130 ms. Rediscover continues to execute
its descriptor, protocol, observation, and validation phases.

## Resident-runtime and memory audit — 2026-09-18

The desktop DPI notifier and battery tray previously polled their queues every
50 ms and 100 ms. They now use a cross-thread event/future handoff and remain
fully dormant until a state transition arrives. The DPI/battery supervision
cadences remain unchanged because they are hardware lifecycle or deliberately
slow battery sampling intervals, not UI queue polling. Hidraw and evdev waits
remain kernel-blocking readiness waits with bounded shutdown/disconnect checks.

With 1,000 post-warmup cycles under `tracemalloc`, reconnect recovery retained
120 bytes (1,944-byte peak growth), forced Rediscover retained 6,037 bytes
(185,821-byte peak growth), and setup controller enter/exit retained 32 bytes
(13,816-byte peak growth). The nearly identical Rediscover retention observed
at 200 cycles (5,769 bytes) and 1,000 cycles demonstrates bounded cache/runtime
state rather than per-cycle accumulation. Descriptor and field caches remain
explicitly bounded at 128 entries.

The setup UI already has the required structural boundary: `SetupController`
owns state and hardware orchestration, while `setup_tui_curses` is a rendering
adapter. The two existing UI surfaces have distinct purposes (interactive setup
and the small status/battery surface), so merging them would increase coupling
without eliminating measured work. No broad async rewrite or speculative module
split was justified by the profiles.
