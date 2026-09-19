# OMUS — Codex Operating Instructions

## Purpose and authority

OMUS is a headless Linux mouse remapper. Optimize for correctness,
architecture preservation, demonstrated hardware evidence, regression
prevention, and clear Git handoffs. Repository state is authoritative: if chat
context conflicts with committed code, tests, this file, project status, or the
latest handoff, inspect the repository and call out the conflict.

Keep evdev/uinput remapping independent from optional hardware configuration.
A missing, unsupported, or failed backend must never prevent ordinary remapping
from starting.

## Mandatory startup sequence

Before modifying code:

1. Read `AGENTS.md`, `docs/AI_HANDOFF_PROTOCOL.md`,
   `docs/PROJECT_STATUS.md`, and the latest relevant `docs/AI_HANDOFF_LOG.md`.
2. Read each task-specific skill named by the task. For Automatic Discovery,
   discovery bindings, or unknown hardware, read
   `.codex/skills/automatic-discovery/SKILL.md`. For non-trivial implementation,
   runtime, backend, lifecycle, remapper, notification, or regression work,
   read `.codex/skills/testing-regression/SKILL.md`.
3. Inspect the branch, HEAD, working tree, recent commits, and task-relevant
   code. Preserve unrelated user changes; do not rely on prior conversation to
   describe HEAD accurately. Verify the remote branch before a push.

## Permanent compatibility and Git discipline

The complete v0.8.2 behavior is permanent unless the user explicitly changes
that requirement. Preserve remapping, uinput lifecycle, reconnect recovery,
notifications, G305 HID++ behavior, `DpiCycler`, PROVEN learned operations,
polling, service behavior, and configuration compatibility. New tests do not
excuse regression of an established path.

Unless explicitly authorized, work only on the assigned feature branch: never
modify `main`, merge, tag, publish, release, rewrite intentional history, or
squash existing commits. Before a push, verify the remote, inspect the final
diff, run validation, and push only the feature branch. Treat each green
architectural milestone as a checkpoint: run the full gate, commit it, push it
when requested, and start the next layer clean. Keep one architectural layer
dirty; if corrective patches begin to stack, consolidate from the last
known-good checkpoint.

## Hardware safety invariants

- Match hardware writes by exact transport plus USB/Bluetooth VID:PID and
  exact interface evidence; product names and VID:PID alone never authorize a
  write when multiple physical candidates exist.
- Refuse ambiguous physical, hidraw, backend, and protocol matches.
  `/dev/hidrawN`, `/dev/input/eventN`, and USB/sysfs parent paths are live
  locations, not persistent physical identities; only a device-unique identity
  may identify an instance.
- Never guess HID feature indexes, report IDs, packet layouts, payload values,
  DPI, polling rates, or semantics. Empty capabilities are unknown, not a
  default. Descriptor shape and changing bytes are evidence, not semantics.
- Generic HID inspection/discovery is read-only. It must never send
  `SET_REPORT`, `HIDIOCSFEATURE`, `HIDIOCSOUTPUT`, `HIDIOCSINPUT`, output or
  feature reports, or raw hidraw writes. Enable these only in narrowly scoped,
  tested, device-evidenced protocol drivers.
- Hardware failures become `HardwareError` and preserve evdev remapping. A
  protocol acknowledgement is not success proof; use canonical readback or a
  protocol-defined confirmation where possible.
- Capability failures are independent: unavailable DPI must not erase
  independently proven polling, battery, button, or other support.
- Writable claims require independently `EvidenceLevel.PROVEN` protocol
  evidence. Physical calibration and read-side correlations never grant write
  authority. Runtime backends enforce their own write policy.
- Resolve Logitech HID++ feature IDs dynamically through ROOT. The USB G305
  (`046d:4074`) is the validated reference only; do not generalize its events
  or receiver slot. Do not broaden hidraw udev access without exact reviewed
  VID:PID/interface evidence.

## Architecture boundaries

Use native HID sessions and validated protocol drivers for hardware control;
do not reintroduce daemon ownership of HID protocol traffic. Keep OpenRazer
optional. Generic HID is identity/diagnostics plus evdev remapping and must not
claim standardized DPI or polling controls.

Automatic Discovery learns; it never guesses. Profiles are path-independent,
cache only proven facts, and may participate in runtime/setup only through an
unambiguous physical binding plus independently PROVEN exact-model operations.
Read-only evidence never grants write authority.

For read-only discovery, keep physical calibration, observation, and write
authority separate. Trigger-only state must never invent a current stage and
loses synchronization on reconnect; an absolute source may resynchronize.
Observed physical DPI transitions never call `set_dpi()`, `DpiCycler`, or
update desired hardware state as though OMUS wrote the hardware.
`MouseRemapper` owns grabbed evdev input: observers use its stream and never
open competing readers. Preserve one-reader HID ownership through the existing
session/subscription mechanism.

## Implementation and validation

Prefer small additive interfaces, root-cause fixes, behavioral tests, exact
identity, and conservative fallbacks. Avoid speculative abstractions, broad
rewrites of proven paths, unrelated refactors, and universal conclusions from
one captured trace. Add tests for identity, ambiguity, malformed reports,
unsupported capabilities, hardware-failure fallback, and explicit no-write
behavior where relevant.

Run focused tests during development. Before handoff, run and record exact
results for:

```bash
git diff --check
python3 -m compileall -q src tests
PYTHONPATH=src pytest -q
```

Report automated and physical validation separately using the labels in
`docs/AI_HANDOFF_PROTOCOL.md`; fixtures and reasoning never establish physical
validation. Do not commit generated build artifacts or hardware captures with
serial numbers/unrelated USB data.

## Handoff

Follow `docs/AI_HANDOFF_PROTOCOL.md` and
`docs/codex/HANDOFF_TEMPLATE.md`. Record the goal, starting/final commit and
working tree, files and behavior changed, exact test results, safety boundaries
(including write authority and read-only limits), separate validation levels,
evidence, risks/blockers, Git discipline, and one next bounded task. Do not
claim "done", "supported", "fixed", or "validated" beyond the evidence.
