# AI Development Handoff Log

This is the concise chronological coordination trail between ChatGPT and Codex.
Read `docs/AI_HANDOFF_PROTOCOL.md` for the full protocol and
`docs/PROJECT_STATUS.md` for authoritative architectural status.

## 2026-09-14 — Protocol established

- ChatGPT and Codex now coordinate through committed Git state rather than chat
  memory alone.
- ChatGPT is the project manager/reviewer; Codex is the primary implementation
  engineer for handed-off coding tasks.
- Codex startup must read `AGENTS.md`, `docs/AI_HANDOFF_PROTOCOL.md`,
  `docs/PROJECT_STATUS.md`, and the latest entry here before implementation.
- Every Codex implementation handoff must identify branch/commit, files and
  behavior changed, automated and physical validation, remaining risks, and the
  next bounded task.
- Validation claims are explicitly separated into code-reviewed, unit-tested,
  integration-tested, physically validated, and unverified.
- Repository state and physical evidence take precedence over stale chat
  descriptions.

### Current coordination focus

The active investigation is native Logitech HID++ Report Rate (`0x8060`) write
behavior on the physically validated G305. Read capability and supported-rate
discovery are established; do not claim native polling-rate write completion
until a real G305 rate transition is independently confirmed by protocol
readback/confirmation and physical testing. Preserve evdev remapping and avoid
unsafe persistent onboard-profile writes while investigating.

## 2026-09-14 — FUTURE HANDOFF: Minimal Resident Runtime

**Status:** HOLD. Do not begin this work until the current native HID++ polling
rate/onboard-persistence investigation is complete and the user explicitly
starts this task.

### Goal

Make the steady-state Mouse Control daemon exceptionally lightweight without
altering behavior. The design principle is that persistent hardware
configuration belongs in validated onboard mouse memory; the resident daemon
should retain only state required to react to live events and provide desktop
integration.

The current user-observed service RSS is approximately 40 MB. Treat that as a
rough observation, not a benchmark. Establish reproducible RSS, PSS, USS/private
memory, thread count, idle CPU/wakeups, and loaded-module baselines before making
optimization claims.

### Target steady-state architecture

The preferred resident architecture is intentionally small:

1. **evdev/uinput remapping path** — preserve all existing button mappings,
   passthrough behavior, keyboard mappings, keyboard chords, reconnect handling,
   and stuck-key/button release guarantees.
2. **small extensible HID event watcher** — keep a native event path resident
   for events that cannot be obtained correctly from evdev. Initially this
   includes confirmed DPI-change observation needed for immediate OSD behavior;
   design it so future vendor/device events and battery/status events can plug
   into the same mechanism. Prefer event-driven hardware observation over
   polling whenever the protocol exposes equivalent events.
3. **one desktop-integration runtime** — provide the StatusNotifierItem tray,
   menu/status surface, and DPI desktop notifications without unnecessary
   duplicate threads, asyncio loops, queues, or D-Bus connections.
4. **minimal hotplug/rebind state** required to recover the above paths after a
   receiver/device disconnect.

Hardware settings such as DPI stages/default DPI and polling rate should not be
continuously supervised in RAM when the specific device/backend has a physically
validated, safe onboard-persistence implementation. Configuration commands
should perform a bounded transaction: discover capabilities -> write validated
settings -> read back/verify canonical hardware state -> persist onboard when
safe -> exit.

For devices without safe writable onboard storage, preserve the existing
backend behavior required for correct operation. Do not make Logitech/G305
persistence assumptions generic.

### Required behavior preservation

This task is an architectural/memory optimization, not a feature tradeoff. The
following behavior is non-negotiable:

- all existing evdev/uinput remaps and passthrough behavior;
- keyboard mappings and held keyboard chords;
- current disconnect/reconnect recovery and release of synthetic outputs;
- configured DPI stages and hardware behavior;
- an immediate independent desktop notification for every physical DPI-stage
  press/change that currently produces one, including rapid presses;
- correct confirmed DPI value in that notification;
- battery/status tray and menu behavior currently exposed to the user;
- polling-rate behavior and all hardware-safety restrictions;
- optional-backend failure must never block ordinary remapping;
- generic HID remains read-only unless a separately validated protocol driver
  authorizes writes.

Do not reduce notification frequency, add latency, weaken reconnect handling,
remove tray/menu functionality, replace event handling with slower polling, or
silently disable hardware features to improve a memory number.

### Investigation before implementation

Before restructuring the daemon, attribute steady-state memory rather than
assuming Python objects are responsible. Measure at minimum:

- RSS, PSS, USS/private memory and swap;
- thread count and thread roles;
- loaded Python modules on the `mouse-control run` path;
- number of asyncio event loops and D-Bus connections;
- idle CPU and practical wakeup frequency;
- memory after startup, after DPI activity, after tray/menu use, after a
  disconnect/reconnect, and after an extended idle period.

Quantify the contribution/necessity of command-only imports, DPI supervisor and
notifier infrastructure, battery monitor/tray infrastructure, HID sessions, and
other long-lived objects. Prefer lazy command-specific imports where they reduce
the resident `run` process without complicating behavior.

The existing architecture has separate DPI-notification and battery-tray
thread/asyncio/D-Bus machinery. Investigate consolidation into one desktop
runtime, but accept it only if measurements show a worthwhile reduction and the
behavior/regression burden remains low.

### Acceptance criteria

- Produce reproducible before/after memory measurements on the same system and
  workload. Report RSS and PSS/private memory; do not market an RSS-only result.
- Aim first for materially below the current ~40 MB observed RSS. `<25 MB RSS`
  is a useful initial engineering target and `<20 MB RSS` is a stretch target,
  not a requirement and never justification for behavioral compromise.
- Demonstrate no functional regressions with the full automated suite plus
  targeted lifecycle/concurrency tests.
- Physically validate the G305 paths affected by the change: remapping/chords,
  DPI cycling and every-press OSD including rapid presses, battery tray/menu,
  disconnect/reconnect, and polling behavior relevant to the final architecture.
- Confirm that steady-state memory does not grow materially after repeated DPI
  events, tray interactions, and reconnect cycles.
- Record idle CPU/wakeup impact so a RAM win does not create a power/CPU
  regression.
- Keep the small HID watcher extensible through backend/protocol interfaces;
  do not hard-code the daemon around G305 event payloads.

### Safety / sequencing dependency

Do **not** remove current DPI/polling supervisors merely because onboard storage
is expected to work. First establish, through the active hardware investigation,
which settings can be safely persisted and read back on the G305 and what mode
transitions are required. Persistent ONBOARD_PROFILES writes remain prohibited
until that path is explicitly proven safe.

When this future task begins, re-read current HEAD and `docs/PROJECT_STATUS.md`.
The architecture may have changed since this handoff was recorded; adapt the
plan to repository reality while preserving the intent and acceptance criteria
above.

### Deliverable

Use a bounded optimization branch. Provide the standard Codex HANDOFF report
from `docs/AI_HANDOFF_PROTOCOL.md`, including exact before/after measurements,
commit hash, tests, physical-validation evidence, unresolved risks, and the next
bounded task. Do not merge, tag, release, or push to `main` without explicit user
authorization.
