# OMUS final pre-Rust whole-system quality audit

Date: 2026-09-19

Branch: `codex/motion-transparency`

Physical acceptance baseline: `5a1997f852fc026553df6549e6154493994e77c1`

## Result and scope

The Python implementation is the behavioral oracle for a future Rust port. This
audit reviewed the normal evdev/uinput path, remapping, DPI and polling control,
notifications, HID/HID++ and learned-HID ownership, Automatic Discovery,
lighting, battery reporting, wake/reconnect, service/configuration migration,
background workers, persistence, failure isolation, and shutdown.

The audit found and corrected two production architectural defects before this
report:

1. The remapper destroyed physical evdev frame boundaries by synchronizing after
   every non-SYN event. It now buffers and transforms one physical frame and
   emits one virtual `SYN_REPORT` at the corresponding boundary. `SYN_DROPPED`
   invalidates the incomplete stream, releases synthetic state, and discards
   through the recovery report.
2. Input readiness and optional hardware-management readiness shared state and
   a management lock could reach the evdev observer. They are separate now;
   input observation uses a short dedicated lock and mapped DPI work is ordered
   on its own worker.

No additional production defect was established by the final inventory and
targeted lifecycle pass. Consequently, the final pass makes no speculative
runtime rewrite or feature removal.

## Input, latency, and wake findings

- One remapper owns and grabs the selected evdev node. Events retain physical
  order and exact values inside the physical frame; button mapping may replace
  events but does not create an extra synchronization boundary for ordinary
  passthrough/remapped input.
- Relative X/Y values are neither scaled nor accumulated. Wheel and other
  non-key events use the same ordered frame path.
- Macros are deliberately asynchronous synthetic actions and have their own
  virtual key frames. DPI cycling is asynchronous and ordered so hardware I/O
  cannot hold a motion frame.
- Disconnect, shutdown, macro failure, and `SYN_DROPPED` release all tracked
  synthetic keys/chords. Incomplete pending frames never survive reconnect.
- The diagnostic observes the production path but grants no hardware authority
  and performs no HID write.

Operator-provided Fedora 44 reports from the exact Logitech G305 acceptance run
contain 99,932 matched physical/virtual frames and 160,291 matched events.
Loss, duplication, modification, ordering, unexpected coalescing, framing,
batching, and reported latency-spike counters are all zero. The sustained-fast
workload reached about 992.6 effective physical and virtual frames/second.

Forwarding latency, reported separately rather than as a pass criterion:

| Workload | Frames | min | median | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|---:|
| A — precise circles | 24,423 | 0.011 ms | 0.016 ms | 0.035 ms | 0.046 ms | 0.537 ms |
| B — fast sweeps | 21,167 | 0.011 ms | 0.016 ms | 0.029 ms | 0.038 ms | 0.324 ms |
| C — motion + buttons/DPI | 13,764 | 0.010 ms | 0.016 ms | 0.033 ms | 0.044 ms | 0.308 ms |
| wake run | 40,578 | 0.010 ms | 0.016 ms | 0.032 ms | 0.043 ms | 0.751 ms |

Ten genuine wake trials recorded first virtual input (T0→T3) at 0.086 ms
minimum, 0.129 ms median, and 0.207 ms p95/p99/maximum. T0→T1 and T0→T2 were
already satisfied when the first Linux-visible evidence arrived and therefore
recorded 0.000 ms. Native polling mode was preserved and desired 3000 DPI was
reconciled. This is exact-device evidence, not a universal wireless claim.

## Background activity and resource ownership

| Owner | Trigger / wait | Shutdown and isolation |
|---|---|---|
| evdev remapper | kernel `select`, 250 ms bound | shared stop event; releases keys, ungrabs and closes |
| macro worker | blocking queue, created on demand | generation queue cancelled and joined |
| DPI-cycle worker | blocking queue when configured | no evdev-path hardware I/O; cancelled on reconnect |
| HID / learned-HID session | sole-reader `select`, 250 ms bound | pending waiter failed, FD closed once, reader joined |
| DPI event monitor | protocol event subscription | retry is interruptible and log-spam suppressed |
| unsupported DPI monitor | event-driven wake or ≥30 s retry | never changes input readiness |
| battery monitor | 60 s successful-read interval | three failures remove tray; retry interruptible |
| D-Bus notifier/tray | blocking cross-thread queue | dormant while idle; bus disconnected on close |
| device monitor | netlink/udev readiness | signals generation changes; no input ownership |
| setup initializer | one owned non-daemon worker | joined/closed on every setup exit path |

There is no timer polling in the ordinary event forwarding path. UI queues are
event-driven. Hardware reads/writes occur only for enabled capabilities,
explicit operations, slow battery sampling, or lifecycle reconciliation.
The permanent 500-round fixture retained 120 bytes across reconnect cycles,
5,148 bytes across Rediscover cycles (bounded caches; 184,964-byte peak), and
32 bytes across setup enter/exit cycles (15,604-byte peak). No unbounded growth
was observed. A system-wide power/wakeup trace was not repeated in this final
pass; the prior measured idle notifier result remains 0.016 ms CPU and one
voluntary context switch per second, the latter belonging to the measurement
thread.

## Hardware, failure isolation, and security

- Ordinary evdev remapping starts independently of missing, unsupported, or
  failed hardware backends.
- Automatic Discovery is the sole public backend. Native HID++ and Razer
  implementations are proven internal adapters, not competing owners.
- Generic discovery is read-only. Writes require an exact physical binding,
  independently `PROVEN` operation, backend enforcement, and canonical
  readback/protocol confirmation where available. Ambiguous candidates are
  refused.
- HID++ feature indices are resolved dynamically. One session owns each hidraw
  reader and multiplexes replies/events; callback and notification failures do
  not kill the reader or remapper.
- Battery, notifications, lighting zones, polling, and DPI fail independently.
  Unsupported capabilities do not erase other confirmed capabilities.
- The user service invokes a resolved non-group/world-writable regular file
  without a shell, writes its unit atomically, refuses a symlink destination,
  applies process hardening, and stops/disables the legacy unit before enabling
  OMUS to prevent duplicate grabs.
- Configuration edits preserve unknown forward-compatible TOML. XDG legacy
  state is copied atomically once and retained as rollback evidence.

## Legacy and compatibility decisions

No obsolete normal-runtime implementation remains to remove. The old prompt
wizard and OpenRazer runtime backend were already removed. Retained names and
paths are intentional compatibility contracts: the `mouse-control` executable,
`mouse_control` import namespace, legacy XDG migration source, legacy systemd
unit detection/replacement, older safe package filename recognition, schema
readers, and explicitly identified protocol families. Research CLIs remain
operator-invoked and are not imported by cold help or the normal remapper.

## Startup, shutdown, and validation

Current 500-round software benchmark medians on the audit host:

- empty Python process: 8.180 ms;
- cold `mouse_control.app` import: 15.981 ms;
- configuration load: 0.016 ms;
- known-device restore: 0.034 ms;
- explicit Rediscover: 0.435 ms;
- one HID decode: 0.029 ms; 1,000 decodes: 28.772 ms;
- setup first-frame preparation: 0.0015 ms;
- supervisor reconnect/rebind: 0.0034 ms.

Shutdown is interruptible during idle select, DPI/battery retry, management
rebind, and disconnected-device waits. The deterministic ten-cycle reconnect
soak verifies node renumbering, immediate XY/button forwarding, and release
safety. The focused final audit set passed 164 tests with one external GLib
deprecation warning. `git diff --check`, compileall, and the complete 1,178-test
suite pass; the full suite retains the same external GLib warning.

## Remaining limitations

- Physical acceptance here covers the G305 `046d:4074`; other models require
  their own exact-device evidence.
- Linux scheduler/USB latency outside OMUS and pre-kernel wireless wake time are
  outside the diagnostic's T0 boundary.
- `SYN_DROPPED` necessarily loses data already discarded by the kernel; OMUS
  safely refuses to invent or forward the untrustworthy interval.
- D-Bus desktop presentation depends on a working user session and tray host;
  its absence never affects input.
- System-wide idle power and wakeups depend on enabled features and desktop/
  kernel behavior; only the owned-worker inventory and prior notifier measure
  are claimed here.

## Rust behavioral contract

A Rust implementation must reproduce these observable invariants before it can
replace Python:

1. Preserve every physical evdev frame, event order, and exact REL value; only
   `SYN_REPORT` closes an ordinary frame and `SYN_DROPPED` invokes recovery.
2. Keep a single evdev owner and one reader per HID interface. Never let
   discovery, readback, notification, DPI, polling, battery, RGB, or persistence
   work block the input frame path.
3. Preserve remap/chord/macro semantics and release every synthetic key on all
   failure and shutdown paths.
4. Preserve exact identity, ambiguity refusal, proof-gated writes, dynamic
   HID++ discovery, readback verification, and capability-level isolation.
5. Preserve event-driven idle behavior, bounded retry/logging/caches/queues,
   reconnect affinity, wake metrics, and prompt cancellation.
6. Preserve configuration, service, command, schema, and package compatibility
   until a separately approved migration removes it.
7. Pass the Python deterministic suite and the same physical G305 workloads
   with zero motion integrity violations; report latency honestly and
   separately.
