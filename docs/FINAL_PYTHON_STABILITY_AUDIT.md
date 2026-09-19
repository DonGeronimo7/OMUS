# OMUS final Python stability and performance audit

Date: 2026-09-19

Branch: `codex/motion-transparency`

Audited production checkpoint: `b26d7228070db2e6d7aba0b79a712f8d04428ac1`

Physical acceptance checkpoint: `5cb404f` over runtime checkpoint `5a1997f`

Scope: final whole-program pre-release and pre-Rust review; no release, merge,
tag, or Rust implementation is authorized by this report.

## Decision

**PYTHON BASELINE READY FOR RELEASE AND RUST MIGRATION**

This is a technical readiness finding, not a release action or authorization to
start the Rust migration. The exact G305 acceptance evidence and the complete
deterministic suite meet the current behavioral gate. Remaining limitations are
device-specific or environment-specific validation boundaries, not established
Python release blockers.

## Evidence and method

This audit verified repository state rather than relying on prior prose. It
reviewed the production tree, entry points, package/service definitions,
runtime ownership and blocking operations, the prior motion/wake corrections,
the permanent performance fixture, and the full deterministic test suite.

Validation levels used below are those defined by
`docs/AI_HANDOFF_PROTOCOL.md`:

- **Physically validated** means observed on the named real G305 in the
  operator-provided Fedora 44 run.
- **Integration-tested** or **Unit-tested** means deterministic software
  evidence; it does not establish behavior on untested hardware.
- **Unverified** identifies claims the available environment cannot make.

No `/dev/input` or USB hardware experiment was performed during this final
documentation pass. No hardware write was issued.

## Architecture inventory

| Subsystem / owner | Purpose and start condition | Lifetime, waits, and resources | Input-path relationship |
|---|---|---|---|
| `mouse_control.app` dispatcher | Canonical `omus` and compatible `mouse-control` command routing | Process lifetime; imports command-specific modules on demand | Starts the resident runtime but does not process frames |
| setup TUI | Configuration, discovery, review, save, service choices | Foreground curses process; one owned non-daemon initialization worker and event queue; worker is joined on exit | Suspends an existing service through the foreground-session protocol before opening hardware; never competes for normal input ownership |
| configuration | Load TOML, validate stages/actions, preserve unknown tables, save selected state | Startup and explicit save; filesystem only; canonical XDG path with one-time legacy copy | Loaded before runtime construction; no per-event I/O |
| compatibility migration | Preserve legacy Mouse Control state, commands, schemas, packages, and service transition | One-time atomic copy when canonical state is absent; source is retained | No steady-state input work |
| service management | Install/start/stop/restart/status one user service | `systemctl --user` subprocesses only on explicit lifecycle actions; atomic unit write | Prevents duplicate persistent owners; not called by event forwarding |
| evdev acquisition / `MouseRemapper` | Sole grab and read of the selected physical input node | Resident; kernel `select` with a 250 ms shutdown bound; exact reconnect resolver; one device FD | Owns the latency-critical path |
| uinput output | Emit the transformed virtual device stream | Same remapper lifetime; output lock protects synthetic and ordinary output ordering | One virtual `SYN_REPORT` per trusted physical frame |
| mappings | Passthrough, button remap, key/chord/macro, DPI action | Ordinary mappings execute in-frame; macro and DPI work use separate queues/workers; workers are created only when needed | Ordinary mapping is synchronous and bounded; hardware I/O is excluded |
| hardware supervisor | Bind and reconcile the current safe backend generation | Resident when hardware management is configured; re-entrant state lock plus a separate short-held observer lock; event-driven wake interrupts bounded retry | Optional management readiness cannot mark healthy evdev input unavailable |
| DPI control | Enumerate/read/set verified DPI and maintain desired writable state | Startup/rebind reconciliation and explicit/cycle operations; ordered DPI queue; backend readback | No backend I/O while forwarding a frame |
| DPI monitoring | Deliver confirmed physical/read-only DPI changes | Protocol subscription when supported; otherwise event-driven wake or at least 30 s unsupported retry; generation-bound watcher | Uses HID subscription or remapper observer, never a competing evdev reader |
| polling/report rate | Enumerate/read and perform policy-gated verified writes | Setup/explicit operation and safe reconnect reconciliation only | Not in the input loop; native/onboard policy is preserved |
| notifications | Submit independent visible DPI notifications | Lazy D-Bus worker with an event-driven cross-thread queue; `replaces_id=0`; closes bus on shutdown | Failure is caught outside hardware and input processing |
| battery/tray | Slow battery read and optional status item | 60 s after successful reads, bounded retry after failure, event-driven wake on matching activity; three failures withdraw stale tray | No input lock; capability failure is isolated |
| native HID / HID++ | Exact-device proven protocol control and events | One reader per hidraw session, `select` with 250 ms shutdown bound, serialized requests and routed subscribers | Separate FD/session; dynamic ROOT feature resolution and readback gates |
| learned HID | Exact-model PROVEN learned operations | One `LearnedHidSession` owner and subscription routing; pending requests fail on disconnect | Never creates a second reader; read-only evidence alone cannot write |
| Automatic Discovery | Safe backend selection, evidence reuse, explicit research/discovery | Known persisted path on normal startup; comprehensive work only through explicit Rediscover/Lab commands | Optional and isolated; generic inspection is read-only |
| known-device fast path | Restore exact, validated persisted evidence | Startup lookup with stable identity and ambiguity refusal | Avoids full discovery/probing during established startup |
| generic HID fallback | Identity/diagnostics and ordinary evdev availability | Selected only when no proven control adapter safely binds | No standardized DPI/polling claim and no write primitive |
| optional Razer adapter | Exact modeled native RPC control | Created only for an exact supported match; OpenRazer is provenance, not a daemon dependency | Failure falls back without preventing remapping |
| lighting | Optional per-zone RGB state and safe reconciliation | Explicit setup/runtime reconciliation; only proven lighting-only or baseline-preserving RMW scope may write | No initialization or packet work in frame forwarding |
| persistence verifier | Separate accepted response, reported state, effect, and persistence evidence | Discovery/setup experiment only | No resident input work and no invented commit command |
| wake coordinator / device monitor | Match Linux-visible activity and interrupt reconnect backoff; record T0–T3 | Netlink/udev monitor plus condition variable; terminal `STOPPING` state; late evidence ignored | First input remains independent from full management readiness |
| reconnect | Restore evdev and management owners without stale generations | Event-driven matching evidence plus bounded fallback waits; old workers/sessions cancelled and joined | First trusted frame can forward before optional management is fully ready |
| updater | Check and install trusted official artifacts | Explicit user action only; network/package subprocesses are absent from normal runtime | No resident process or input interaction |
| doctor/support/debug/research | Diagnostics, captures, corpus and promotion workflows | Explicit commands only; bounded parsers; research paths are not imported by normal cold help/runtime | Cannot silently grant write authority or become a runtime owner |
| logging | Lifecycle, failure, and bounded retry diagnostics | Process logging; repeated optional failures use stateful suppression | No normal per-motion logging |
| D-Bus | Notification and optional tray presentation | Dedicated async worker/queue; dormant without work | No input locks and no fatal dependency |
| package/runtime environment | Console/desktop/AppImage dispatch and dependency contract | Process startup; all public launchers converge on the canonical dispatcher/TUI | No alternate obsolete resident implementation |

### Persistent synchronization and traffic summary

The evdev hot path uses the remapper output lock only for ordered virtual output.
The hardware supervisor's general lock is not acquired by the observer path;
the observer list has its own short-held lock. Macro and DPI actions use distinct
blocking queues and generation cancellation. HID sessions serialize requests
and protect waiter/subscriber state, while callbacks run without transferring
reader ownership. UI, D-Bus, wake, and worker queues are event-driven.

Steady periodic work is limited to bounded shutdown selects, battery sampling,
and fallback retry for unavailable optional management. Filesystem writes occur
on explicit configuration/evidence/update/service actions, not during motion.
Hardware traffic occurs for supported capability reads, explicit verified
writes, slow battery sampling, and lifecycle reconciliation. D-Bus traffic is
generated only for tray state or an actual notification.

## Subsystem findings

### Core input path and mappings

Physical frames, event ordering, values, and ordinary synchronization are now
transparent. `SYN_DROPPED` discards the untrusted interval through the recovery
`SYN_REPORT`, cancels pending macros, invalidates observers, and releases
tracked synthetic state. Disconnect and shutdown likewise release held keys,
buttons, and chords. Tests cover passthrough, XY and wheel framing, button to
button, button to key, chords/modifiers, macros, repeated and rapid presses,
movement plus mapping, DPI activity, reconnect, and immediate first-frame
mapping. No synchronous management operation remains in frame forwarding.

### DPI and polling

Configured stages, wraparound cycling, confirmed readback, rapid ordered
notifications, reconnect/wake reconciliation, malformed/unsupported responses,
generation replacement, and unavailable backends are covered. Read-only
observations never call `set_dpi` or update desired writable state. DPI writes
are queued off-path and successful state is accepted only according to backend
confirmation policy.

Report-rate enumeration/read/write remains capability- and policy-gated. The
G305 Host-mode transition is exact-device-only and rolls back on failure;
unknown mice are never automatically transitioned from onboard mode. Normal
reconciliation preserves onboard/native state and does not repeatedly replay a
rate that is already correct.

### Notifications and battery

Every confirmed DPI transition intentionally creates an independent direct
notification. Rapid changes are neither debounced nor coalesced, and a value
may recur after wraparound. D-Bus absence, a failed notification, and daemon
recovery cannot stop DPI handling or input.

Battery reads occur once per 60 seconds following success. Transient failures
retain the last known state; three consecutive failures withdraw it. Retry
waits are interruptible, repeated warnings are bounded, and no battery query
holds an input lock. The available deterministic evidence supports quiet idle
behavior; actual system wakeup cost varies by backend, desktop, and kernel.

### Discovery and hardware backends

Established exact devices use persisted evidence and the known-device path.
Normal startup does not run the Lab, corpus analysis, protocol inference, or a
speculative write probe. Explicit Rediscover retains the comprehensive safe
discovery workflow. Profiles are path-independent and are reused only after
current exact identity/interface validation; ambiguity and corrupt/different
device state are refused.

Native HID++, learned HID, native Razer, generic HID, and discovery selection
retain one-owner semantics. Stale generations cannot deliver current state,
duplicate backend construction is bounded, and superseded resources close.
Generic HID and recognized-but-unproven protocol families remain read-only.
Every runtime writer enforces its own exact binding and PROVEN-operation policy.

### Lighting

Lighting is an optional capability. Unsupported lighting or a zone failure
does not erase DPI, polling, battery, mapping, or service health. Shared device
configuration writes require a trustworthy baseline-preserving read/modify/
write proof, preserve every unrelated byte, and are otherwise refused. Source-
derived device fingerprints remain exact and write-disabled. No physical RGB
claim is made by this audit.

### Configuration, TUI, launchers, and service lifecycle

Fresh and existing configurations, unknown-table preservation, canonical save,
cancel/no-save, restart, missing/partial state, legacy XDG migration, and
permission/error paths are covered deterministically. Writes and migrations use
atomic replacement/copy where applicable; canonical existing state wins and
legacy source state is retained. Invalid explicit config fails clearly rather
than silently loading another file.

`omus`, `omus setup`, `omus tui`, both compatibility commands, desktop/package
launchers, AppImage structure, and `python -m mouse_control` converge on the
current dispatcher and canonical setup TUI. No obsolete home screen remains a
normal route. Setup preserves unsaved state and restores only a service it
actually suspended; cancellation and errors do not create a second owner.

Service helpers cover install, start, stop, restart, already-active/inactive,
status/failure, setup suspension/restoration, and legacy-unit replacement. The
unit target is symlink-refused and atomically written, the executable must be a
resolved regular file without group/world write permission, and `ExecStart` is
properly quoted without a shell. Crash recovery and login behavior ultimately
remain systemd user-manager responsibilities; deterministic tests verify the
unit and command contract rather than simulating a complete desktop login.

### Sleep, wake, reconnect, and cross-feature behavior

Input availability and management readiness are separate states. Matching
udev/kernel evidence cancels reconnect backoff; unrelated device events do not.
A retained receiver/session does not recreate the backend. A true node return
passes stable identity, affinity, generation, and interface validation before
replacement. Teardown enters terminal `STOPPING` before workers can rebind.

Cross-feature coverage exercises motion with mapping and slow DPI work, rapid
DPI with notification failure, battery/DPI following current backend state,
ten reconnect generations with immediate XY and mapped-button forwarding,
backend failure with ordinary remapping, and wake/shutdown during retry. These
tests found no remaining coupling that delays the ordinary frame path.

### Update, support, logging, and runtime environment

Update checks and installations require explicit action. Artifact selection,
trusted origin, checksum, package ownership, secure staging, subprocess
arguments, cancellation, and service restoration are deterministic test
surfaces. Debug, doctor, capture, promotion, and Discovery Lab commands are
operator-invoked and absent from the normal resident loop. Parsers are bounded
and malformed metadata/protocol data is rejected without execution or replay.

## Defects discovered and corrections

Two production defects were established and corrected before this final pass:

1. **Physical frame splitting.** The old remapper discarded `EV_SYN` and
   synchronized after every individual non-SYN event. That could split X and Y
   from one physical report into different virtual frames. The correction at
   `7365235` buffers one physical frame, transforms its events in order, and
   emits only at its `SYN_REPORT`; it also adds explicit `SYN_DROPPED` recovery.
2. **Input/management wake coupling.** Optional backend readiness shared state
   and locking with evdev observation, and mapped DPI cycling could perform slow
   work synchronously. The correction at `5a1997f` separates input and
   management readiness, introduces the short observer lock, and moves ordered
   DPI cycles to a generation-isolated worker.

The current audit established no additional production defect. In accordance
with the change policy, it makes no speculative refactor, compatibility removal,
or new write path.

## Performance, startup, idle, and soak results

### Physical input and wake baseline

The exact G305 physical reports contain 99,932 matched physical/virtual frames
and 160,291 matched events with zero loss, duplication, modification, ordering,
coalescing, framing, `SYN_DROPPED`, batching, or latency-spike findings. The
fast workload sustained approximately 992.6 physical and virtual frames/s.
Median forwarding latency was approximately 0.016 ms; the worst observed value
was 0.751 ms.

Ten genuine wake trials measured Linux-visible T0 to first virtual input T3 at
0.086 ms minimum, 0.129 ms median, and 0.207 ms p95/p99/maximum. This begins at
the first kernel-visible evidence and excludes pre-kernel radio wake time.

### Software startup and operation baseline

The final 500-round rerun on Python 3.14.7 measured:

| Operation | Median | p95 | Rounds |
|---|---:|---:|---:|
| empty Python process | 8.335 ms | 8.671 ms | 25 |
| cold `mouse_control.app` import | 16.417 ms | 20.077 ms | 25 |
| configuration load | 0.0165 ms | 0.0244 ms | 500 |
| topology construction | 0.0688 ms | 0.1261 ms | 500 |
| persisted evidence lookup | 0.0300 ms | 0.0371 ms | 500 |
| known-device startup fixture | 0.0338 ms | 0.0414 ms | 500 |
| explicit Rediscover fixture | 0.4316 ms | 0.5592 ms | 100 |
| one HID decode | 0.0298 ms | 0.0413 ms | 500 |
| 1,000 HID decodes | 29.271 ms | 31.263 ms | 50 |
| setup first-frame preparation | 0.00145 ms | 0.00160 ms | 500 |
| supervisor reconnect/rebind fixture | 0.00336 ms | 0.00366 ms | 500 |

The known-device milestone reached fixture runtime-ready in 0.142 ms. The
explicit Rediscover milestone reached runtime-ready in 0.565 ms. These are
deterministic software fixtures, not service-to-physical-pointer wall-clock
measurements. Physical first input and full management readiness remain
separately instrumented and must not be collapsed into one startup number.

### Idle behavior

Every periodic source is identified in the architecture table. Kernel/HID
readers block in `select`; queues, udev wake, UI, and D-Bus are event-driven.
Battery's 60-second read is purposeful telemetry. Unsupported DPI fallback is
at least 30 seconds and is immediately interruptible by matching wake evidence.
Replacing these bounded workers with busy orchestration would not improve user
latency or reliability. The prior isolated notifier measurement remains 0.016
ms CPU and one voluntary context switch per second from the measuring thread.

A fresh system-wide CPU/RSS/FD/HID/filesystem/D-Bus power trace was not possible
in this non-device audit environment. Accordingly, no new whole-system idle
power claim is made.

### Resource soak

The 500-cycle deterministic soak retained:

| Exercise | Retained | Peak growth |
|---|---:|---:|
| reconnect/recovery | 120 bytes | 2,312 bytes |
| explicit Rediscover | 5,856 bytes | 185,640 bytes |
| setup enter/exit | 32 bytes | 15,604 bytes |

The Rediscover delta is bounded cache/allocation retention, not monotonic growth.
Tests additionally assert one active watcher/session, generation cancellation,
closed superseded handles, pending-request failure on disconnect, and prompt
worker shutdown. No leak or unbounded queue/subscription growth was established.

## Failure injection and security findings

Deterministic failures include notification daemon/error, backend enumeration
and read failure, malformed HID payload/readback mismatch, device disappearance,
corrupt/different/ambiguous persisted evidence, configuration permission/error,
Discovery failure, and unsupported/read-only lighting. Ordinary pointer
functionality survives optional management failure; safety-critical ambiguity
or failed verification is surfaced and blocks the unsafe operation.

Security boundaries remain intact:

- exact transport, VID:PID, physical/interface evidence, and device-unique
  identity govern binding; volatile node paths are never persistent identity;
- ambiguous physical, backend, route, and protocol matches are refused;
- generic inspection and unproven learned/protocol knowledge have no write
  authority;
- HID++ feature indices are dynamically resolved and writes require canonical
  validation/readback where available;
- configuration and imported metadata are bounded and validated; unknown TOML
  is preserved but does not become executable authority;
- service and update paths avoid shell evaluation, defend destination/staging
  paths, and verify trusted artifacts;
- performance shortcuts cache validated state but do not bypass revalidation,
  generation, affinity, proof, or ambiguity checks.

## Legacy-code classification

| Candidate | Classification | Decision |
|---|---|---|
| `mouse-control` command and `mouse_control` package | REQUIRED COMPATIBILITY | Retain as aliases/internal namespace |
| legacy XDG Mouse Control directories | REQUIRED COMPATIBILITY | Retain as non-destructive migration source |
| legacy systemd unit detection | REQUIRED COMPATIBILITY | Retain so installation prevents duplicate owners |
| old package/artifact names and schema readers | REQUIRED COMPATIBILITY | Retain bounded readers for safe upgrade |
| named historical protocol-family knowledge | STILL ACTIVE | Retain as exact, provenance-labelled discovery knowledge |
| research/debug CLIs | STILL ACTIVE | Retain as explicit operator tools; not resident |
| prompt wizard and OpenRazer daemon backend | SAFE TO REMOVE | Already removed before this checkpoint; no reachable production path found |
| broad old-name strings in historical docs/tests | UNKNOWN — RETAIN | Evidence/history, not runtime duplication |

No additional duplicate normal-runtime implementation, obsolete polling loop,
dead selector, notification mechanism, or reachable old TUI was demonstrated.

## Validation matrix

### Physically validated

- Exact Logitech G305 `046d:4074` motion-frame transparency and approximately
  1 kHz fast workload.
- Exact G305 ten-cycle genuine sleep/wake input recovery.
- Native polling mode preservation and 3000 DPI wake reconciliation in that run.
- Previously accepted exact G305 DPI/report-rate transactions, DPI-button
  events, mappings, notifications, battery/tray, reconnect, and service restart.

### Deterministically verified only

- Other supported backend families and learned exact-model operations.
- Mapping failure/release variants, malformed input/protocol data, optional
  failure isolation, D-Bus absence/restart behavior, lighting RMW safety,
  configuration migration/atomicity, service command/idempotency contracts,
  launcher convergence, updater security, and resource-soak bounds.
- Startup phase fixtures and software performance figures.

### Unverified in this pass

- Physical behavior of non-G305 devices and any physical RGB hardware.
- Whole-desktop logout/login and crash restart on a live installed host.
- A new system-wide idle wakeup/power trace with actual hardware and desktop.
- Debian/AppImage native builds where their external builders are unavailable;
  their structure and entry paths remain covered by tests and prior evidence.

## Complete regression results

Commands executed against the clean accepted checkpoint:

```text
PYTHONPATH=src pytest -q
1178 passed, 1 warning in 8.05s

python3 -m compileall -q src tests
PASS

git diff --check
PASS

PYTHONPATH=src python3 benchmarks/run_performance.py --rounds 500 --json
PASS (results recorded above)

ruff check src tests
NOT RUN — `ruff` is not installed on this host
```

The single warning is the existing external PyGObject deprecation for
`GLib.unix_signal_add_full`; it is not a new unexplained failure. Packaging was
not rebuilt because this pass changes documentation only and the accepted
checkpoint already records wheel/sdist and Fedora RPM/package smoke evidence.

## Known limitations

- Physical claims are exact-device claims, not vendor-wide guarantees.
- Linux scheduling, USB latency, desktop services, and radio wake before the
  kernel-visible T0 boundary are outside OMUS's direct control.
- Kernel `SYN_DROPPED` means the kernel has already discarded data; OMUS safely
  refuses to invent or forward that interval.
- Trigger-only read-only DPI sources cannot regain stage certainty after
  reconnect until a legitimate synchronization source appears.
- Desktop notifications/tray require a working user D-Bus session, but their
  absence cannot affect input.
- Persistent hardware support remains limited to independently proven exact-
  model operations; discovery recognition and calibration do not imply writes.

## Rust behavioral contract

The Rust implementation may replace Python only after it demonstrably preserves
or improves all of the following:

1. Exact evdev event values, event order, and physical frame boundaries; only
   trusted `SYN_REPORT` closes a normal frame and `SYN_DROPPED` invokes recovery.
2. Passthrough, button-to-button, key/modifier/chord/macro, DPI-cycle, repeated-
   press, release, cancellation, and reconnect semantics with no stuck output.
3. One evdev owner and one reader per HID interface; no optional discovery,
   DPI, polling, notification, battery, RGB, persistence, or logging work may
   block an input frame.
4. Configured DPI stages, ordered cycling, confirmed readback, observed-versus-
   desired separation, notification behavior, wake/reconnect reconciliation,
   and independent capability failure.
5. Polling enumeration/readback, native/onboard preservation, exact safe-write
   policy, rollback, persistence vocabulary, and absence of redundant writes.
6. Independent visible DPI notifications (`replaces_id=0`), failure isolation,
   and ordered rapid transitions without coalescing.
7. Slow/event-driven battery behavior, bounded retries/logging, and no input-
   lock interaction.
8. Known-device fast startup, explicit full Rediscover, path-independent proven
   evidence reuse, ambiguity refusal, and read-only generic discovery.
9. Exact backend affinity, dynamic HID++ feature discovery, PROVEN write gates,
   canonical confirmation/readback, generation isolation, and resource cleanup.
10. Optional lighting and baseline-preserving shared-packet RMW; unsupported or
    failed RGB must not affect any other capability.
11. TOML compatibility, unknown-field preservation, atomic save/migration,
    legacy state/command/schema/package compatibility, and honest failures.
12. Canonical dispatcher/TUI/launcher convergence and foreground setup that
    never creates a competing persistent owner or loses unsaved state.
13. One intended systemd user-service owner, idempotent lifecycle commands,
    hardening/path checks, legacy-unit replacement, and prompt clean shutdown.
14. Separate first-input and full-management readiness, exact wake matching,
    retained-session fast wake, safe true reconnect, and terminal shutdown.
15. Quiet event-driven idle operation, bounded queues/caches/retries, no
    monotonic FD/thread/task/subscription growth, and phase-specific startup
    measurement.
16. Optional-component failure survival without hiding safety-critical identity,
    protocol, verification, configuration, or update failures.
17. Existing update integrity, subprocess/path/temp-file, malformed-input, and
    hardware-write security boundaries.
18. The complete deterministic Python behavioral suite and the same physical
    G305 workloads with zero integrity violations. Rust performance comparisons
    must use the Python figures in this report, not intuition or a combined
    startup number.

## Final repository state for the audited code

- Branch: `codex/motion-transparency`
- Final audited production-code commit:
  `b26d7228070db2e6d7aba0b79a712f8d04428ac1`
- Working tree before this requested report: clean
- Report change: documentation only; no production code, tests, package,
  hardware authority, service, release, tag, merge, or Rust work changed

**PYTHON BASELINE READY FOR RELEASE AND RUST MIGRATION**
