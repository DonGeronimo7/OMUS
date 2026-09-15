# AI handoff log

## 2026-09-15 — G305 polling acceptance runtime mismatch

Request: user attachment `pasted-text.txt`, continuing reviewed commit
`1c7b23f474f790275573464049c935e8df29971d` on
`feat/core-hardware-stabilization`.

The requested `docs/AI_HANDOFF_PROTOCOL.md` and this log did not exist in the
checkout, tracked history, or inspected local handoff files. This new entry
records actual evidence; it does not reconstruct a missing prior handoff.
The final response follows the user's explicit HANDOFF schema.

- Failure: physical setup listed `1000/500/250/125` and current `1000`, but
  disallowed changes before the first `1000 -> 500` write.
- Root cause: `/usr/bin/mouse-control` imports the old system-installed 0.8.1
  package. Its `_discover_report_rate` caches writability from current Host
  mode; its native backend forwards that flag and lacks the transition path.
  The reviewed checkout already fixes that policy. Version equality hid the
  deployment mismatch. Actual physical mode was not captured; an Onboard
  fixture against the installed package reproduces the reported result.
- Correction: document an explicit source invocation and require CLI/service
  implementation parity before continuing acceptance. Preserve the existing
  protocol and safety policy without a superficial wizard override.
- Regression: 11 new cases use actual driver discovery and native backend,
  directly and via HardwareSupervisor, through setup selection and application.
  They cover 500 Hz success, Host failure, rate-write failure, exact-readback
  mismatch, rollback, and unknown/non-USB/missing-transport identity refusal.
- Validation: targeted suite 71 passed; full suite 295 passed (one existing
  GLib deprecation warning); compileall and diff whitespace checks passed.
- Packaging: `python3 -m build --no-isolation` produces sdist/wheel; local
  `rpmbuild -ba` with `_topdir=/tmp/mouse-control-acceptance-rpm` and
  `_tmppath=/tmp` passes, including `%check` (295 tests), compileall, and
  staged CLI help. The default RPM temporary directory was read-only, so it
  was redirected to `/tmp`. Wheel installation into an isolated system-site
  virtual environment and its CLI help both pass. Existing RPM changelog-date
  and GLib deprecation warnings remain. System installation/service unchanged.
- Lifecycle review: existing supervisor generation/reconciliation, backend
  cleanup, canonical DPI/notification, battery, remapping/chord, and shutdown
  coverage passes. No runtime lifecycle changes were made or physical recovery
  claims inferred. Setup uses NativeHidBackend directly; daemon consumers use
  the shared HardwareSupervisor, which forwards polling policy unchanged.
- Resume: the exact source command in `G305_HARDWARE_ACCEPTANCE.md`, first
  `1000 -> 500 Hz`. All physical polling and remaining acceptance are pending.

## HOLD — Future Minimal Resident Runtime

No prior HOLD entry was available to amend. Preserve the user's architecture
refinement here for future work; do not implement it in this polling task.

Steady-state intent: evdev/uinput for remapping and chords; a small extensible
HID watcher for DPI, reconnect/reset and future hardware/status events; one
minimal desktop runtime for tray/menu and notifications.

Persist hardware settings onboard where safely validated; otherwise retain
minimal `DesiredHardwareState` and reconcile only on lifecycle events, never
continuously merely to maintain configuration. Safe persistent profile
programming is not a prerequisite for this optimization. A few resident state
values are acceptable. This work remains **HOLD** pending a separate bounded
task; no memory/runtime optimization has begun.

## 2026-09-15 — Setup remap preservation and DPI-cycle selection

- Root cause: setup initialized every run from built-in left/right/middle
  defaults, so Skip/keep mappings regenerated `[remap]` and removed other
  valid entries such as `BTN_FORWARD = 'dpi-cycle'`. The action menu also did
  not expose the already-supported `dpi-cycle` action.
- Correction: seed setup from an existing valid `[remap]` table, overlay only
  deliberately captured buttons, and offer canonical `dpi-cycle` as action 8.
  No HID++, Host-mode, polling, backend, or runtime remapping behavior changed;
  no global `BTN_FORWARD` meaning was added.
- Validation: targeted setup/wizard/runtime suite passes 58 tests; full suite
  passes 299 tests (one existing GLib deprecation warning). Compileall and
  whitespace checks pass.
- Physical follow-up: confirm `BTN_FORWARD = 'dpi-cycle'`, run setup with
  Skip/keep mappings, confirm it remains, restart Mouse Control, and verify
  physical DPI cycling. Only then proceed from verified 500 Hz to 250 Hz.
