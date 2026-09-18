# AI handoff log

## 2026-09-17 — GitHub discovery onboarding overhaul

- Reframed the repository landing page as native Linux mouse configuration
  backed by a multi-protocol discovery engine, with package installation,
  direct TUI launch, and the unsupported-mouse testing path above the technical
  architecture.
- Distinguished direct runtime adapters (dynamic HID++ 2 and exact-model Razer
  RPC) from the broader sourced discovery repertoire; repertoire recognition
  is explicitly not presented as device support or write authority.
- Documented the current human-readable support report and allowlisted
  Automatic Discovery JSON workflow, then aligned contributor guidance and the
  new-mouse issue form around attaching those artifacts. Added a concise feature
  request form and more useful bug-environment fields.
- Verified GitHub's published latest release as v0.9.5 with the documented RPM,
  DEB, AppImage, wheel, and source asset names. Verified documented primary,
  support, discovery, updater, and CPI commands against current CLI help.
- Documentation checks: all issue-form YAML parsed; all local Markdown links in
  changed documentation resolved; `git diff --check` passed.
- Automated validation: `python3 -m compileall -q src tests` passed;
  `PYTHONPATH=src pytest -q` passed 684 tests with one existing GLib deprecation
  warning. No code or hardware behavior changed; no physical validation was
  performed.

## 2026-09-17 — v0.9.5 macro and release gate

- Starting point: `e0a1041` on `codex/persistent-discovery-fast-tui`, clean
  working tree. Macro checkpoint: `4a47212` (`Add safe sequential macro
  actions`).
- Macros are structured named TOML lists of existing key, chord, and
  mouse-button actions plus bounded millisecond delays. A small queued worker
  keeps evdev input responsive; playback is press-only and releases synthetic
  input after every step and on failure, interruption, disconnect, or shutdown.
  Setup can select or create basic macros without adding scripting, commands,
  loops, conditions, recording, or any hardware-protocol operation.
- v0.9.5 metadata, README, changelog, release notes, package manifests, and
  current download names are synchronized. Historical v0.9.4 records remain
  unchanged.
- Automated validation: focused macro/remapper/setup suite passed 79 tests;
  focused release/config suite passed 33 tests; full source suite passed 684
  tests with the existing GLib deprecation warning; compileall and
  `git diff --check` passed.
- Packaging: sdist and wheel built with correct 0.9.5 names; an isolated wheel
  install reported 0.9.5 and passed primary/CPI CLI smoke. Fedora RPM built as
  `mouse-control-0.9.5-1.fc44.noarch.rpm`; `%check` passed all 684 tests,
  compileall, and every packaged CLI smoke. The AppDir payload built and passed
  version/help/CPI smoke, but this host could not run AppImageKit's final Qt
  wrapper headlessly; the official Ubuntu release workflow remains the
  authoritative AppImage and Debian build/publish gate.
- Safety: macro execution is software-input only. Generic HID remains
  read-only, persisted discovery does not grant write authority, and PROVEN
  exact-model hardware policy is unchanged.
- Physical validation: the task report supplies prior G305 evidence for direct
  native reconnect after the affinity correction. No new v0.9.5 physical macro
  execution was performed in this automated session; that item remains
  unverified and is not inferred from tests.

## 2026-09-17 — Reconnect affinity and additive Vim navigation

- Physical pre-fix evidence: a G305 previously using Native HID rebound through
  topology-only and PROVEN learned candidates across generations 1–4, producing
  safe rejected 1000-DPI reconciliation attempts, before Native HID returned at
  generation 5. Persistent discovery itself did not rerun, and post-recovery
  DPI cycling/notifications worked.
- Root cause: `HardwareSupervisor.rebind()` reconciled and promoted each newly
  constructed candidate before considering the strength of the backend that
  had been valid before disconnect. Partial composite-interface enumeration
  therefore became observable backend churn.
- The supervisor now retains Discovery-adapter affinity and rejects/closes a
  weaker temporary candidate before reconciliation. Three simulated learned
  candidates followed by the same native adapter produce one final generation
  and no learned DPI write attempt. Learned-device affinity has separate
  regression coverage. Compatibility backends outside the universal Discovery
  surface retain their prior replacement behavior.
- Added shared TUI aliases: `h/j/k/l` exactly mirror Left/Down/Up/Right and
  `g/G` select first/last, plus Home/End translation. Enter remains activation;
  existing key behavior remains covered.
- Focused lifecycle, learned-safety, notification, remapper, DPI-cycle, and TUI
  suite passed 133 tests. Full suite passed 672 tests with the existing GLib
  warning. No new physical reconnect test was performed after the correction.

## 2026-09-17 — Persistent discovery and responsive TUI fast path

- Baseline `v0.9.4` (`97c391f`) repeated comprehensive passive discovery while
  constructing the universal backend, then initialized proven adapters and live
  setup capabilities. TUI navigation itself was already session-backed and
  measured at roughly 0.002–0.008 ms in the controller benchmark.
- Runtime binding now performs one current topology reconstruction without
  descriptor/protocol learning. Automatic Discovery rehydrates static facts only
  after stable identity and exact current-member checks; node renumbering is
  accepted, ambiguity/different unique instances/corrupt records are refused.
- Added semantic discovery progress events, determinate and indeterminate TUI
  rendering, cache-hit suppression, clean failure teardown, explicit forced TUI
  retry, and `mouse-control rediscover`. Existing evidence is replaced only after
  a successful atomic save.
- Controlled benchmark: known-profile restore 0.188 ms; forced three-interface
  descriptor path 91.367 ms with 30 ms per-interface injected I/O. CLI import/help
  remained 0.12 s. Focused discovery/lifecycle suite passed 139 tests; full suite
  passed 669 tests with the existing GLib warning. No physical hardware timing or
  acceptance was performed.

## 2026-09-17 — v0.9.4 integration and software release gates

- Starting checkpoint `49a2f1571a011ebe166d9d8a3be045b1b4f9399d` was clean and exactly matched the requested discovery foundation.
- Integrated loss-aware usbmon provenance, structured operation evidence,
  failure-side-effect/retry safety, passive semantic recognition, and the full
  canonical-to-community-report evidence path without adding runtime write authority.
- The synthetic BITMOUSE-style fixture is source-derived automated evidence;
  it trims stale reply tails and remains RECOGNIZED/read-only, not hardware-qualified.
- Validation: 660 tests passed (one existing GLib warning); compileall and diff
  checks passed; sdist/wheel, Fedora RPM `%check` plus packaged CLI smoke,
  Debian package, and AppImage version/help smoke passed.
- Architectural checkpoint: `9c79cf5`. Final G305 physical acceptance,
  release-document checkpoint, remote push, tag, CI, and published assets remain pending.

## 2026-09-17 — v0.9.4 pre-v1 discovery foundation

- Baseline: `codex/tui-only-setup` at `cad809d` with a clean working tree.
- Added a bounded temporal dialogue model, operation-specific proof lifecycle,
  separate experiment eligibility authority, multi-candidate dependent-field
  inference, scoped conflict provenance, and deterministic community reports.
- Added `mouse-control discover --output FILE` and the advanced discovery
  CLI's `--community-report FILE`; destinations are created exclusively and
  generic unknown-device discovery remains read-only.
- Validation: focused discovery/regression suite passed 112 tests; full suite
  passed 651 tests with the existing GLib warning; compileall, diff whitespace,
  and sdist/wheel build passed.
- Version metadata advanced to 0.9.4. No push, merge, tag, release,
  installation, or physical hardware validation was performed.

## 2026-09-17 — HID intelligence and native Razer consolidation

- Baseline: branch `codex/tui-only-setup`, TUI cleanup commit `e327932`.
- Removed the OpenRazer runtime backend/dependency and replaced its supported
  Mouse-Control operations with an exact-model native Razer backend. DPI and
  polling writes require an exact VID:PID, exactly one responding interface,
  fixed protocol facts, and canonical readback. Firmware and applicable
  battery/charging reads remain independent capabilities.
- Consolidated descriptor-backed input/output/feature decoding with correct
  Variable/Array, Delimiter, Buffered Bytes, unit/physical-range, collection,
  report identity, and wire-position semantics. Expanded standard HID usages
  and evdev mappings without interpreting vendor-defined payloads.
- Added protocol-neutral repeated-frame field-role inference, bounded XOR/SUM/
  selected CRC inference, and information-gain-ranked read-only experiment
  planning. Existing contrastive learning supplies repeated guided actions and
  negative controls; none of these structural results grants write authority.
- Audited every production module, package entry point, retained research CLI,
  hardware backend, and repertoire family in `docs/CODE_HEALTH_AUDIT.md`.
- Validation: focused suites passed; full suite `637 passed` with one existing
  GLib warning; `compileall`, `git diff --check`, and
  `python3 -m build --no-isolation` passed. No physical Razer validation was
  performed. No push, merge, tag, release, or installation was performed.

## 2026-09-17 — TUI-only setup routing

- Removed the `_LEGACY_SETUP`/TTY fallback and the superseded line-oriented
  setup implementation, prompt screens, action menus, and stale tests.
- Interactive `mouse-control`, explicit `mouse-control setup`, and home-screen
  setup routes now select the same full-screen TUI transaction.
- Noninteractive setup exits before curses is invoked and does not resurrect
  an old UI. Configuration/runtime APIs remain separate for automation.
- Focused setup/entry/native-HID suite passed 103 tests. Full validation passed
  626 tests with one existing GLib deprecation warning; compileall and diff
  whitespace checks passed.

## 2026-09-17 — v0.9.3 installed production and reconnect acceptance

- The locally built Fedora 44 RPM upgraded the installed package from 0.9.1 to
  0.9.3. RPM verification passed, `/usr/bin/mouse-control --version` reported
  0.9.3, imports resolved from `/usr/lib/python3.14/site-packages`, and the
  pre-upgrade configuration hash remained unchanged.
- The installed full-screen TUI opened as the normal setup path, selected the
  Logitech G305 (`046d:4074`), preserved the existing remaps and notification
  preference, and restarted the packaged user service. The operator reported
  the wizard, remapping, DPI, polling, and physical notifications worked; the
  wizard felt somewhat slow, which is retained as a non-blocking UX observation.
- Production runtime selected `Automatic Discovery (Native HID adapter)`, read
  and reconciled 1000 Hz polling and 3000 DPI, and initialized the canonical DPI
  notification watcher. Rapid physical cycles emitted exactly one ordered
  notification per real press with `replaces_id=0`.
- Two receiver reconnect cycles recovered the stable G305 evdev identity and
  returned to Native HID. The operator observed zero reconnect/RESYNC popups;
  post-LIVE physical presses remained one-for-one. Retired generations emitted
  no late notification. The first cycle briefly retried a PROVEN learned adapter
  while the receiver enumerated and logged response timeouts before Native HID
  became available; it then settled at six service tasks with no continued
  generation churn. A minor cursor recovery delay was observed.
- The SIGMACHIP device was not attached for a new installed-package smoke. Its
  accepted physical abstention evidence remains unchanged: no semantics or write
  authority were inferred from absent evidence.

## 2026-09-17 — Discovery DPI watcher reconnect

- Physical evidence supplied by the operator: the teacher-free schema-v2
  descriptor/member path emitted `800 → 1500 → 2000 → 2500 → 3000` through the
  existing runtime/notification path with vendor/native handling bypassed and
  unknown HID writes forbidden.
- Root cause of the remaining failure: the acceptance CLI owned one
  `DiscoveryBackend` directly, so EIO ended its hidraw watcher without the
  existing supervisor lifecycle being able to rediscover and replace it.
- Correction: the acceptance monitor now uses `HardwareSupervisor` and
  `DpiMonitorSupervisor` with only `DiscoveryBackend(allow_writes=False)`
  replacements. Failed watchers force a fresh generation even if a device
  returns at the same node; live node paths remain runtime-only. Replacement
  binding reruns physical/profile identity checks and reparses the current
  descriptor before accepting the persisted member.
- Physical reconnect result: EIO/ENODEV recovery, stale-handle closure,
  rediscovery/member rebind, post-reconnect stability, and a physical
  `3000 → 800` wrap are validated. About five reconnect popups isolated a
  generation-baseline defect: only the first replacement state was classified
  as resync, so later initialization states escaped as live changes.
- Reconnect semantics: a replacement generation now remains in `RESYNC` until
  its initial authoritative semantic stream reaches the watcher's normal idle
  boundary. All valid states in that phase are stored silently and the final
  state becomes the new baseline. `LIVE` then deduplicates the first same-state
  packet and emits the first changed state once. This uses neither a packet
  count nor an added sleep. Generation-gated callbacks continue to discard
  events from retired watchers.
- Safety: no HID++, vendor adapter, learned writer, desired-state mutation, or
  generic write path is entered. Ambiguous physical matches and malformed or
  changed descriptor members remain unbound with no raw fallback.
- Automated validation: focused reconnect/discovery regression suite passed 86
  tests; full suite passed 658 tests with one existing GLib
  deprecation warning. Compileall and diff whitespace checks passed.
- Physical validation: the five-stage path and reconnect transport recovery are
  physically validated from operator reports. Zero-popup generation-aware
  resync remains unverified and is the next bounded acceptance step.

## 2026-09-17 — G305 member-level corpus replay

- Root cause: the G305 Report-17 descriptor declares an opaque 19-byte vendor
  Array (`Input 0x00`), so the Variable-only member patch kept the parent field
  identity and behavior profiling combined all 570 positional observations.
- Correction: multi-count Variable members and unresolved positional vendor Array members
  now have stable `/member-N` observation identities plus explicit parent
  provenance. Standard selector Arrays retain their descriptor semantics and
  parent identity. Relative fields classify only as `relative_activity`.
- Real corpus replay: `g305-dpi-validate` yields static members 0/1/2 with
  values `1/7/16`, only member 3 cycles over `0..4`, and members 4–18 remain
  static zero. Explicit same-device negative controls are clean.
- Physical validation: the existing read-only exact-device G305 profile has
  high-confidence measured CPI states near `823/1543/2048/2567/3067`, confirmed
  wrap, and an exact state-bearing Report-17 mapping at raw offset 4. The
  current live G305 resolves unambiguously to the profile model/instance and
  exact interface-2 descriptor; offset 4 is payload member 3. This promotes the
  member-3 `DPI_STAGE_INDEX` semantic candidate to `VALIDATED` while retaining
  the raw mapping itself at `CORRELATED`.
- Safety: raw captures and descriptors are unchanged. No CPI mapping, HID
  write, runtime promotion, desired-state mutation, or write authority was
  added. Physical CPI promotion remains blocked on a later explicit gate.
- Automated validation: focused HID/runtime regression suite passed 100 tests;
  full suite passed 648 tests with one existing GLib deprecation warning.
- Runtime checkpoint: the exact-device G305 profile was upgraded to schema v2
  with a validated descriptor-backed `hid_state` source for member 3. Runtime
  reparses and verifies the live descriptor before decoding that member; an
  invalid member is refused without falling back to the correlated raw mapping.
  The acceptance monitor has an explicit write-disabled mode and continues to
  use existing `DpiState`/notification machinery. Live identity rebinding to
  interface 2 succeeded, but no operator DPI press or unplug/replug occurred
  during the monitor window, so physical notification/reconnect acceptance is
  still pending.

## 2026-09-17 — HID Semantic Engine v2

- Expanded the descriptor parser into a diagnostic schema model preserving
  collection paths, physical/unit metadata, local usage/designator/string
  declarations, complete Main flags, and stable descriptor/field identities.
- Added bounded bit-level Input decoding for numbered/unnumbered reports,
  signed non-byte-aligned values, Variable fields, and Array selectors.
- Added centralized Usage interpretation, deterministic standard mouse
  semantics, explicit expected-versus-observed evdev relationships, decoded
  field correlation, vendor-field behavior profiles, and derived trace HID
  enrichment. Raw-byte correlation remains as a compatibility fallback.
- Safety: all new paths are observational and contain no HID write primitive;
  vendor fields remain structured unknowns and cannot grant write authority.
- Automated validation: the final complete suite passed 640 tests with one
  existing GLib deprecation warning; compileall and whitespace checks passed.
  Physical G305
  and SIGMACHIP semantic validation remains pending because no sanitized
  descriptor/report corpus is present in the repository.

## 2026-09-17 — Trace evidence foundation

- Added versioned canonical USB observation/setup/transaction models under an
  observation-only `mouse_control.trace` package.
- Added Linux binary-usbmon extended-header decoding and live per-bus capture,
  with immediate current bus/address filtering derived from an unambiguous
  physical device and stable fingerprint. No deprecated text parsing was added.
- Added deterministic URB assembly covering missing halves, duplicate events,
  URB reuse, metadata mismatch, out-of-order timestamps, and capture boundaries.
- Added schema-v1 deterministic session manifests and streamed SHA-256 artifact
  hashing. No PCAP import, semantic inference, replay, or write promotion is
  part of this checkpoint.
- Automated validation: 15 focused trace tests, the 94-test trace plus
  Automatic Discovery regression suite, and the complete 626-test suite passed.
  Compileall and whitespace checks passed. Live hardware capture remains
  unverified.

## 2026-09-17 — Setup observed-state integration

- Setup Review now separates measured physical DPI/polling evidence from
  configured software DPI/polling preferences and from proven write authority.
- Exact-device calibrated profiles populate a read-only presentation snapshot;
  switching devices clears it before any new exact-device profile is loaded.
- Existing physical calibration with no transition source now offers bounded
  runtime-source learning and explicitly reuses ruler/wrap calibration.
- Absolute runtime sources are described as safely resynchronizing; trigger-only
  sources remain explicitly unsynchronized at startup and after reconnect.
- No backend capability, writable flag, configured preference, or hardware-write
  path is promoted by calibrated read-side evidence.
- Automated validation: focused Automatic Discovery/setup suite passed 168
  tests; full suite passed 611 tests with one existing GLib deprecation warning.
  Compileall and whitespace checks passed. Python sdist/wheel and Fedora 44 RPM
  builds passed; RPM `%check` passed 611 tests and packaged CLI smoke tests.
  Physical Titan validation remains pending.

## 2026-09-17 — Calibrated read-only DPI runtime integration

- Physical DPI cycles are saved as schema-v2 read-only profiles even when no
  runtime source is isolated; later runs reuse calibration and retry only
  transition capture.
- Runtime binding resolves path-independent HID/evdev source identities against
  current physical nodes and refuses ambiguous matches. Live paths may change
  the supervisor signature without becoming persisted identity.
- HID and shared-owner evdev absolute/trigger decoders feed
  `ReadOnlyDpiCycleTracker`. Trigger-only state never advances while
  unsynchronized and is invalidated on continuity loss. Observed states are
  confirmed, have no writable stage, and never invoke `set_dpi()`.
- Existing PROVEN learned-action cycling, native HID++, polling, remapping, and
  notification behavior remain separate and pass the full automated gate.
- `feature_state` is explicitly deferred: no polling is started until bounded
  read-only GET_FEATURE ownership can be implemented safely.
- Automated validation: 607 tests passed, plus compileall and whitespace
  checks. Physical Titan validation remains pending.

## 2026-09-16 — Discovery-first setup/TUI stabilization

- Root cause: the production full-screen TUI existed, but it ordered Buttons
  before DPI/Polling, did not make the comprehensive DiscoveryEngine the normal
  setup driver for known devices, and duplicated list-only DPI validation.
- Correction: discovery now drives setup before configuration; navigation uses
  explicit history/review-return state; DPI supports min/max/step capabilities;
  polling exposes protocol state separately from read-only timing measurement;
  device switches invalidate device-specific discovery state after rollback.
- Safety: unknown HID remains read-only. No speculative generic HID write path
  was added; write authority remains protocol-backed or exact-model PROVEN.
- Physical validation: pending on the G305 after installing/running this branch.

## 2026-09-17 — v0.9.4 CPI packaging gate

- Request: CPI measurement must ship as a supported installed capability in
  every v0.9.4 artifact before final G305 acceptance and release closure.
- Starting commit: `11d2d31` on `codex/tui-only-setup`. Final commit is the
  commit containing this entry.
- Implementation: registered `mouse-control cpi` on the primary CLI and
  refactored the existing calibration CLI to share one parser configuration
  and execution function. The existing namespaced executable remains
  compatible. Discovery continues to import packaged modules directly.
- Packaging: release CI now installs the wheel and Debian package and smokes
  their primary CPI command; RPM `%check` and the AppImage smoke do the same.
  No `mouse-dpi-tool` command or artifact is introduced.
- Validation: focused CPI/release/terminal tests passed 29; full suite passed
  664 with one existing GLib warning; compileall and `git diff --check` passed.
  Wheel and sdist built and contained both calibration modules. An isolated
  wheel install, Fedora RPM `%check`, installed Debian package, and AppImage
  each passed `mouse-control cpi --help`.
- Validation level: automated/package only. No physical CPI measurement or
  new write authority is claimed. The command reads evdev motion and performs
  no HID feature/output writes.
- Remaining gate: install the matching RPM and complete every operator-observed
  step in `docs/G305_HARDWARE_ACCEPTANCE.md`. Do not tag or publish until that
  physical gate and the final clean-tree release gate pass.

## 2026-09-17 — v0.9.4 G305 physical release gate

- Installed artifact: `mouse-control-0.9.4-1.fc44.noarch` built from the CPI
  checkpoint. `mouse-control cpi --help` resolved from installed packaged
  modules. The existing `/usr/bin/mouse-dpi-tool` is owned by Fedora's
  `libevdev-utils`; Mouse Control did not package or replace it.
- Startup: doctor passed permissions and service checks and detected exact G305
  identity `046d:4074`. Runtime selected Automatic Discovery's Native HID
  adapter and retained configured DPI stages, 1000 Hz polling, notifications,
  and remaps.
- Physical DPI events: the operator observed the complete slow sequence
  `1000,1500,2000,2500,3000` and two rapid complete cycles, with every popup
  ordered and no omissions or duplicates.
- Software write: installed setup applied and verified 1000 DPI by canonical
  hardware readback. Configuration and restart retained the value, and the
  journal contained no fabricated physical-button notification for the write.
- Lifecycle: two receiver unplug/reinsert cycles restored pointer/buttons,
  configured remaps, Native HID, DPI notifications, and battery/tray state.
  Reconnect itself created no popup and no duplicate device/tray identity.
  Battery disappeared during incomplete enumeration on the first cycle and
  returned on the monitor's next refresh after Native HID promotion.
- Final restart: the operator confirmed input, remaps, DPI notification, and
  battery behavior recovered without issue. Journal review found bounded
  generation changes and no repeated reconnect loop, stale-generation event,
  duplicate notification, rollback failure, or unresolved readback failure.
- Validation level: physically validated on this attached Logitech G305 plus
  the separately recorded automated/package gates. This evidence does not grant
  write authority to any other model.

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

## 2026-09-15 — Lossless setup configuration editing

- Root cause: in addition to rebuilding remaps, setup discovery replaced
  configured DPI stages/active DPI and chose the maximum supported polling
  rate. It then saved and applied those discovery-derived values.
- Correction: setup now seeds the wizard from parsed persisted values, uses
  defaults only for missing fields, separates configured polling from observed
  current polling, and merges changed setup-owned fields while retaining
  notifications and unknown TOML tables. Hardware discovery is informational;
  DPI and polling writes occur only after their respective explicit edits.
- Regression: repeated no-change setup preserves non-default DPI active/stages,
  500 Hz polling, `dpi-cycle`/key/chord mappings, notifications, and nested
  future configuration. Isolated DPI, polling, and remap edits preserve the
  other preferences.
- Acceptance interpretation: the earlier 500 Hz persistence result remains
  **inconclusive because setup was still destructive**, not a confirmed Native
  HID/HID++ regression. Install this build before repeating the physical
  polling acceptance sequence.

## 2026-09-15 — Reconnect promotion after partial receiver enumeration

Request: user attachment `pasted-text.txt` on
`feat/core-hardware-stabilization`, beginning at
`55e4af25667dc448964af3a03de99b97f856cd49`.

- Physical reproduction: a G305 operating through Native HID/HID++ was
  unplugged and reinserted. A reconnect probe during partial enumeration bound
  Generic HID / evdev. Input and remapping later recovered, but Native HID was
  never reacquired, leaving DPI event monitoring and DPI notifications absent
  until `mouse-control restart`.
- Verified root cause: `HardwareSupervisor` cleared `discovery_pending` when
  Native HID was active but did not restore it after a Generic fallback.
  `DpiMonitorSupervisor` therefore classified Generic's lack of DPI events as
  final and stopped issuing short rebind attempts. This is a backend lifecycle
  and preference defect, not a DBus notification defect.
- Implementation: preserve Generic as an immediate safe fallback, but mark it
  provisional after a previously selected non-Generic backend. Repeated
  Generic-only probes close only their unselected candidate and do not advance
  the generation. A later Native result replaces and closes Generic, advances
  the generation, and allows consumers to subscribe on the promoted backend.
- Regression: added a deterministic Native → Generic → Native supervisor race
  test that verifies fallback cleanup and generation behavior, plus a DPI
  monitor test that verifies an event after promotion reaches the notifier.
- Validation: targeted tests passed (35 tests); full suite passed (305 tests,
  one existing GLib deprecation warning); compileall and diff whitespace checks
  passed.
- Physical follow-up: reinstall/use the matching source build, remove and
  reinsert the G305 receiver, and verify that the temporary Generic bind is
  followed by Native HID promotion and resumed one-notification-per-DPI press.
  That physical receiver-reinsert validation remains pending.
