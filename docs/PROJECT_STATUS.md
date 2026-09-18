# Mouse Control Project Status

## 2026-09-18 — Discovery Lab differential analyzer milestone

- The canonical setup TUI now exposes `Hardware Discovery → Discovery Lab →
  Run Full Automatic Lab — Differential Analyzer milestone`. It runs a bounded
  selected-device baseline/action/post-action/negative-control workflow with
  three automatically chosen positive repeats.
- `LabExperiment` is the common generation-isolated evidence record for Lab
  instruments. It retains exact stable physical context, interval/repeat
  identity, path-independent HID and Feature evidence, optional canonical USB,
  logical-record and dialogue evidence, physical CPI/polling evidence,
  provenance, confidence/proof state, analysis, and next recommendation.
- The analyzer ranks constant, changed, action-correlated, counter, length,
  status, integrity, and trailing padding/stale candidates. It also compares
  timing, request/response transactions and echoes, reuses dependency and
  integrity inference, retains contradictions, produces conservative labelled-
  action hypotheses, and uses the existing information-gain planner.
- Deterministic replay fixtures exclude volatile paths, evdev history, keyboard
  history, clipboard content, and screen data. The Lab remains local-only and
  read-only; ambiguity is refused, generation mixing is rejected, recognition
  never grants writes, and `write_authorized` is always false.
- Focused Lab/discovery/protocol/security validation passes 176 tests; the
  complete suite passes 841 with the existing GLib warning. No physical
  validation, hardware write, install, push, merge, tag, or release occurred.

## 2026-09-18 — fixed-frame logical-record reassembly milestone

- Discovery now separates fixed HID transport reports from variable logical
  records. The generic read-only reassembler handles one record per frame,
  records spanning frames, adjacent records in one frame, and declared-length
  tails without treating padding as protocol content.
- Complete, incomplete, and invalid records retain source frames, transport and
  logical lengths, timestamps, physical/source/channel/namespace/report/
  generation identity, declared and captured lengths, integrity state, known
  field bytes, and exact opaque regions. Reconnects invalidate partial old-
  generation records; streams never cross source, physical device, channel,
  namespace, report ID, direction, or transport boundaries.
- Optional wrappers use the existing bounded integrity algorithms. A protected
  record is valid only after validation; unsupported integrity stays `UNKNOWN`
  and cannot be promoted, while a failed check makes the record `INVALID`.
  Unwrapped records remain explicitly unknown rather than implicitly valid.
- The repertoire adds a recognition-only RAWM-style declarative recipe over
  independently reconstructed abstract fixtures. It requires coherent complete-
  state record structure, preserves unresolved bytes, uses `WriteScope.NEVER`,
  and adds no setter, whole-state write, or runtime transaction.
- The retained benchmark grows from 18 to 27 cases: 12 recognized, 13
  candidates, 1 unknown, and 1 ambiguous. Fixture-only coverage is 44.4%,
  abstention 51.9%, ambiguity 3.7%, recognized precision/known-case recall
  100%, and unknown/collision false recognition 0%; no broader 90% claim is
  made.
- Focused protocol/discovery validation passes 156 tests; the complete suite
  passes 831 with the existing GLib warning. No physical validation, hardware
  write, write-authority change, install, push, merge, tag, or release occurred.

## 2026-09-18 — asynchronous pushed-state recognition milestone

- The generation-aware temporal assembler now represents meaningful state that
  has no request owner. Records retain exact stream identity, semantic state
  identity, decoded opaque state, freshness/reasons, periodic position, optional
  subtype/transform proof, controlled-action correlation, and optional observed
  read-side nudge association.
- Freshness is explicit (`FRESH`, `STALE`, `UNKNOWN_FRESHNESS`). Successful
  immediate reads start unknown; a later disagreeing accepted push demotes the
  old read to stale. Periodic cadence, a bounded nudge, monotonic counters, and
  controlled-action transitions can establish fresh evidence. Old-generation
  pushes are retained as rejected stale evidence and cannot update current state.
- The repertoire now recognizes MCHOSE Realtek/L7-style Input report `0x13`,
  subtype `0x1D`, and actually verified XOR-FF source/result pairs through the
  generic pushed-state recipe. It remains distinct from MCHOSE V3,
  `WriteScope.NEVER`, semantic-offset agnostic, and has no nudge executor,
  setter, capability, or runtime write path.
- The benchmark grows from 11 to 18 cases: 8 recognized, 8 candidates, 1
  unknown, and 1 ambiguous. Fixture-only coverage is 44.4%, abstention 50%,
  ambiguity 5.6%, recognized precision/known-case recall 100%, and unknown/
  collision false recognition 0%; no broader 90% claim is made.
- Focused protocol/discovery validation passes 81 tests; the complete suite
  passes 818 with the existing GLib warning. No physical validation, hardware
  write, write-authority change, install, push, merge, tag, or release occurred.

## 2026-09-18 — bounded response-burst recognition milestone

- The existing temporal assembler now supports one trigger followed by zero or
  more exactly correlated responses. Replay timestamps drive quiet-interval and
  absolute-deadline completion; maximum-count, explicit-end, and connection-
  generation completion are also distinct, bounded result states.
- Burst isolation requires exact physical/source/transport/channel/namespace/
  report/grammar/generation evidence plus transaction-tag equality when present.
  Wrong mouse/dongle context, ordinary input events, late records, and stale
  generations are excluded without wall-clock sleeps or hardware interaction.
- The repertoire expresses Finalmouse ULX-style mouse and dongle telemetry as
  generic bounded bursts with length+command+payload framing. It remains
  recognition-only, `WriteScope.NEVER`, and contains no runtime setter or
  semantic claim for opaque LE16 fields.
- The project-owned benchmark grows from 6 to 11 cases: five recognized, four
  candidates, one unknown, and one ambiguous. On this small fixture only,
  precision/known-case recall remain 100%, unknown/collision false recognition
  remain 0%, coverage is 45.5%, abstention 45.5%, and ambiguity 9.1%.
- Focused protocol/discovery validation passes 69 tests; the complete suite
  passes 806 tests with the existing GLib warning. No physical validation,
  hardware write, write-authority change, install, push, merge, tag, or release
  occurred.

## 2026-09-18 — open-set protocol-recognition corpus foundation

- Protocol-family semantic recognition is now data-driven. Reusable passive
  discriminators cover frame length/constants, cross-frame field correlation,
  SUM8 integrity, declared semantic length, and paired report namespaces; the
  BITMOUSE path no longer contains a family-specific recognizer.
- Recognition explicitly returns `UNKNOWN`, `CANDIDATE`, `AMBIGUOUS`, or
  `RECOGNIZED`, requires independent evidence categories and a winner margin,
  and converts broken checksum/target/sequence/length relations into negative
  evidence instead of nearest-family matches.
- Keychron M6 paired `B3→B4` and `B5→B6` dialogues and exact Holtek Venus
  `04d9:fc55` interface/report topology are now declarative repertoire facts.
  Holtek remains structural-only; all new knowledge has `WriteScope.NEVER` and
  creates no capability, transaction, backend, or runtime write.
- The initial project-owned six-case corpus includes identity-blinded positive,
  near-miss, unknown, structural-collision, dialogue, and structure-only cases.
  It reports 100% recognized precision/known-case recall, 0% unknown/collision
  false recognition, 33.3% coverage, 50% abstention, and 16.7% ambiguity on
  this small fixture only; it does not claim the broader 90% objective.
- Focused discovery/protocol validation passes 60 tests. The complete suite
  passes 797 tests with the existing GLib deprecation warning. Physical
  hardware validation was not performed and no new hardware support is claimed.

## 2026-09-18 — launcher / TUI first-frame performance candidate

- The canonical device-selection frame now renders before the live HID backend
  handshake. One TUI-owned, non-daemon initializer performs the unchanged
  backend, capability, and exact-evidence checks; hardware navigation remains
  unavailable until it completes, and every exit joins/closes the worker.
- The foreground supervisor queues background-service suspension without
  blocking process startup. Backend initialization still waits synchronously
  for suspension completion before opening hardware, preserving ownership and
  unsaved-exit restoration.
- Evdev discovery now enumerates the same event-node namespace directly instead
  of using `evdev.list_devices()` to open every node before Mouse Control opens
  and validates it again. Existing capability, permission, stable-path, and
  unknown-device checks remain authoritative.
- On the acceptance host, warm known-device first-frame median improved from
  676.22 ms to 504.15 ms across five supervised launches; a cold/transitional
  sample improved from 6,347.09 ms to 464.83 ms. Every benchmark cancellation
  restored the service and preserved the configuration hash. Automated source
  validation passes 787 tests; installed/package and physical interaction
  validation remain separate.

## 2026-09-18 — externally supervised foreground lifecycle candidate

- Interactive launches now enter one transient systemd user service. Its
  `ExecStartPre` records and suspends a previously active background runtime;
  its `ExecStopPost` restores that runtime after the foreground process exits,
  including SIGTERM and terminal/window disappearance. The TUI process no
  longer owns background-service restoration.
- A saved service preference is distinct from temporary foreground suspension.
  Saved Enable installs/enables without starting until teardown; saved Keep
  disabled disables the user unit and suppresses restoration. Unsaved staged
  choices do not change the supervisor record.
- A packaged `mouse-control-launcher` now owns graphical terminal selection.
  The desktop file uses `Terminal=false`; the helper prefers valid `$TERMINAL`,
  opportunistically uses `xdg-terminal-exec`, then discovers common installed
  emulators with their specific command syntax. No terminal is a package
  dependency and there remains one canonical TUI.
- Source and Fedora RPM automated gates pass 783 tests. Live G305 sessions
  restored the active service after no-argument cancel, explicit `tui` cancel,
  `python -m mouse_control` cancel, SIGTERM, and compositor-driven terminal
  close; an initially inactive service remained inactive. Native HID and the
  DPI watcher returned in the journal.
- On the niri acceptance host, the real installed desktop entry launched
  through `gtk-launch` with `$TERMINAL` unset and `xdg-terminal-exec` absent;
  the helper selected installed Kitty and terminal disappearance restored the
  service. An unchanged Save preserved the exact configuration SHA-256 and
  restored the service. Wheel/sdist, RPM, and AppImage payloads contain the
  helper. The user subsequently confirmed physical remaps, DPI-button
  notifications, tray visibility, and battery behavior all work. The candidate
  therefore has both automated/package evidence and user-observed physical
  acceptance on the attached G305; that evidence does not generalize hardware
  write authority to another model.

## 2026-09-18 — Redragon M724 and Ryunix Kyu Pro MX1 protocol knowledge

- The discovery repertoire now recognizes the exact Redragon M724 K1NG 1K
  Feature-report control collection and records its upstream-sourced session,
  DPI, reciprocal polling, commit, responder-marker, and abandoned-session
  hazard facts. It has no executable transaction and `WriteScope.NEVER`.
- The exact wired/wireless Ryunix Kyu Pro MX1 identities now have passive
  telemetry structure for active state, DPI stage, polling, battery, charging,
  and opaque LED mode. Its configuration report remains non-authorizing and it
  also has `WriteScope.NEVER`.
- Report matching can now require exact HID usage page/application usage, and
  codecs can constrain their raw domain to observed values. These are additive
  recognition/evidence capabilities, not runtime hardware support.
- Full automated validation passes 741 tests with the existing GLib warning.
  The representative benchmark remains within prior noise: cold import 15.493
  ms, known-device restore 0.0334 ms, forced Rediscover 0.416 ms, and 1,000 HID
  decodes 29.035 ms. No physical device, write, installation, tag, merge, push,
  or release was performed.

## 2026-09-18 — v0.9.7-1 updater and measured Python performance candidate

- `origin/main` now contains the canonical full-screen TUI correction at
  `1e21f89`; v0.9.7 work is isolated on `codex/v0.9.7-python-performance`.
- Release versions are explicitly separated across display/tag, PEP 440, RPM
  Version/Release, distribution suffix, and architecture. The verified DNF
  fallback recognizes the real `0.9.6` to `0.9.6-2` asset shape and freezes
  previous-updater compatibility for the `0.9.7-1` generated RPM.
- Command-specific imports are deferred; immutable descriptor bytes and bounded
  parsed field knowledge are reused; notification/tray queues are event-driven.
  Exact measurements and stable-cycle memory results are in `docs/PERFORMANCE.md`.
- The full source and RPM `%check` gates pass 738 tests with the existing GLib
  warning. Wheel/sdist, isolated wheel import/help, Fedora RPM build/content,
  AppImage shell syntax, desktop validation, and focused security checks pass.
- Current read-only doctor evidence found no safely readable mouse. This
  candidate therefore has automated/package evidence only; current-version
  G305 physical acceptance, DEB build/install, and AppImage build/smoke remain
  final pre-tag gates. No tag or release was created.

## 2026-09-18 — v0.9.6-2 canonical TUI regression correction

- The desktop launcher, no-argument `mouse-control`, explicit `setup`/`tui`,
  RPM, DEB, AppImage, and `python -m mouse_control` paths converge on the
  full-screen setup TUI through the normal application dispatcher.
- The older line-oriented launcher screen and its unused executable wrapper
  are removed. No alternate interactive UI or configuration-sensitive launcher
  branch remains.
- Hardware control, remapping, configuration, service, discovery, notification,
  battery, and reconnect behavior are unchanged. Automated/package evidence is
  recorded in the matching handoff-log entry; physical launcher observation is
  separate and must not be inferred from tests.

## 2026-09-18 — v0.9.6-2 lifecycle patch released

- Unsaved setup sessions now restore and verify a previously active service
  after cancellation, interruption, setup failure, or hardware rollback
  failure. A restoration failure returns an error instead of false success;
  an initially inactive service remains inactive.
- Setup has a cache-only known-device initialization path. It rebuilds current
  topology and reuses persisted evidence only after the existing exact model,
  instance, transport, and responder checks pass. Missing, corrupt, ambiguous,
  or mismatched evidence continues to require discovery, while explicit
  Rediscover still forces the complete pipeline.
- The published artifact made no-argument established-user launches select the
  older home screen while first-run launches entered setup. The correction
  above removes that split; explicit noninteractive commands remain unchanged.
- Automated validation passes 710 tests locally and in Fedora RPM `%check`.
  The authoritative release workflow passed Python 3.12/3.13/3.14, wheel/sdist,
  Debian, Fedora 44 RPM, AppImage, packaged CLI smokes, exact-asset publication,
  and checksum generation. A follow-up CI-only correction verifies incremental
  RPM Version and Release fields separately; it does not move the release tag.
- Live G305 acceptance confirmed cache reuse in setup, cancel-without-save
  service restoration, Native HID/1000-DPI/DPI-watcher recovery, explicit full
  Rediscover, and final active service state. Human observation of remaps and
  popup appearance remains pending and is not inferred from logs.
- Release `v0.9.6-2` was published from product commit `05979b8` with the five
  expected install/source artifacts plus `SHA256SUMS`.

## 2026-09-18 — v0.9.6 security hardening candidate

- Direct GitHub RPM, DEB, and AppImage updates now require a strict official
  release `SHA256SUMS` manifest and verify the selected artifact before any
  privileged install or atomic AppImage replacement. Unsafe names, mismatched
  versions/architectures, malformed/duplicate/unexpected manifest entries,
  untrusted redirects, symlinks, and target-identity races fail closed.
- Release Actions are immutable-SHA pinned and least-privilege scoped. The
  publish job validates an exact five-artifact set and generates its checksum
  manifest. AppImageKit and the portable CPython input are SHA-256 pinned and
  verified before execution/extraction.
- User-service installation resolves a non-group/world-writable executable,
  atomically replaces a non-symlink unit, uses an absolute systemctl path, and
  applies compatible process hardening. Existing event/uinput/G305 udev scope
  remains narrow; its comments now accurately acknowledge validated writes.
- `SECURITY.md` records reporting, updater trust, privacy/network, device-write,
  usbmon, service, and limitation boundaries. The audit found no malware,
  backdoor, telemetry, credential access, or exfiltration behavior.
- Automated validation passes 700 tests. Bandit reports 0 medium/high and 52
  manually reviewed low findings; pip-audit reports no known vulnerabilities.
  Wheel/sdist, Fedora RPM `%check`/CLI smokes, Ubuntu 24.04 DEB build/install,
  and final AppImage build/version/help/CPI smokes pass. Debian's distro
  setuptools compatibility and AppImage cache/build-path cleanup were the only
  release-wrap corrections.
- The installed Fedora 44 v0.9.6 RPM passed physical G305 acceptance: exact
  Native HID binding, remapping/passthrough, ordered slow/rapid DPI popups, two
  receiver reconnect cycles, and a service restart recovered without false
  startup/reconnect notifications, stuck input, retry flooding, or service
  restart. Full DPI-watcher recovery after receiver insertion remained bounded
  but took roughly 18–25 seconds.

## 2026-09-17 — v0.9.5 macro and release candidate

- Button remaps can reference structured named macros containing ordered key,
  chord, mouse-button, and explicit millisecond-delay steps. Playback reuses
  the established uinput path on a small worker and is interrupted on
  disconnect/shutdown with synthetic-input cleanup.
- Setup can select or create a basic macro using the existing modal menu
  patterns and Vim/arrow navigation. The format is declarative only: no
  commands, scripts, loops, branching, recording, or hardware operations.
- This release candidate retains the persistent learned-device fast path,
  semantic progress, reconnect adapter affinity, and Vim navigation described
  below. Generic HID remains read-only and all hardware writes remain
  independently PROVEN and exact-model scoped.
- Automated and packaging results are recorded in the final handoff entry once
  the release gate completes. v0.9.5-specific physical acceptance is separate
  and must not be inferred from automated coverage.

## 2026-09-17 — Reconnect adapter affinity and Vim navigation

- `HardwareSupervisor` now remembers the strongest accepted universal
  Discovery adapter: exact native protocol adapters outrank PROVEN learned
  adapters, which outrank topology-only bindings. During reconnect, weaker
  partial-enumeration candidates are closed before desired-state reconciliation
  and do not advance the generation.
- A previously native device therefore remains on its disconnected generation
  while composite members settle, then replaces it directly with the same
  native adapter. A previously learned device similarly waits for its learned
  members. No write-authority, discovery, identity, or generation-isolation
  rule was weakened.
- The shared setup input translation/controller path adds `h/j/k/l` as exact
  Left/Down/Up/Right aliases and `g/G` as first/last, while preserving arrows,
  Enter, Escape, Back, Quit, Help, Home, and End. First/last movement uses the
  controller's selectable-row count.
- Automated validation passes 672 tests with the existing GLib warning.
  Physical confirmation of the reduced G305 reconnect generation count remains
  pending; the pre-fix five-generation trace and eventual Native HID recovery
  were supplied by the operator.

## 2026-09-17 — Persistent discovery fast path and semantic progress

- Normal backend startup now rebuilds the current physical/member graph directly;
  it no longer invokes the comprehensive discovery engine before proven protocol
  adapters perform their own bounded initialization.
- Automatic Discovery profiles can be restored only after fresh stable model,
  transport, VID:PID, true-instance (when available), and exact responder-member
  matching. Live `/dev` nodes always come from the current graph. Corrupt,
  ambiguous, changed-member, and different-instance records fall back safely.
- A healthy known-device profile skips HID descriptor parsing, protocol detection,
  feature baselines, and learning. `mouse-control rediscover` and the TUI retry
  action explicitly force the full pipeline; the prior record remains until the
  replacement is atomically saved.
- Discovery emits frontend-neutral semantic progress with determinate milestone
  counts and indeterminate states for observation work. The TUI renders this only
  for genuine discovery and clears it cleanly on failure; cache hits render as
  immediately ready.
- Automated validation passes 669 tests with the existing GLib warning. A
  controlled three-interface benchmark measured the learned-profile path at
  0.188 ms versus 91.367 ms for forced descriptor work. Physical startup and
  reconnect timing remain pending on installed hardware.

## 2026-09-17 — v0.9.4 integrated release-candidate closure

- Canonical usbmon evidence now retains optional extended binary-header fields
  and capture-quality/completeness facts through deterministic JSONL replay.
- Operation proof retains its existing state ladder while orthogonal tri-state
  evidence records acceptance, response validity, readable/physical effects,
  persistence, failure side effects, and recovery. Mutating failures with a
  possible side effect cannot be blindly resent.
- One automated BITMOUSE-style fixture now exercises canonical observation,
  temporal dialogue, dependency inference, structural plus semantic recognition,
  operation-scoped proof, and privacy-filtered community reporting end to end.
  Declared semantic length excludes stale HID tail bytes, and RECOGNIZED remains
  write-disabled.
- Automated validation passes 664 tests with the existing GLib warning;
  compileall, diff validation, sdist/wheel, Fedora RPM `%check` and CLI smoke,
  Debian package build, and AppImage version/help smoke pass.
- The v0.9.4 G305 physical acceptance sequence passed on the installed Fedora
  RPM. Published release artifacts remain the final release gate; no tag or
  release existed when this status was recorded.

## 2026-09-17 — v0.9.4 pre-v1 discovery foundation

- Protocol-neutral temporal dialogue assembly now retains physical/source/
  channel/report/generation identity while distinguishing delayed replies,
  busy/poll flows, tagged and grammar-separated overlap, echoes, unsolicited
  events, physical actions, reconnect invalidation, and stale responses.
- Operation-scoped proof states now distinguish observation, recognition,
  decoding, hypothesis, experiment eligibility/execution, verification,
  PROVEN authority, conflict, and revocation. Experiment eligibility is a
  separate descriptive authority and cannot grant runtime write permission.
- Dependent-field inference retains alternative literal/duplicate/byte-order/
  scale/affine/lookup/stage explanations; unexplained changing bytes prevent
  promotion.
- `mouse-control discover --output FILE` and
  `mouse-control-discover --community-report FILE` generate deterministic,
  allowlisted JSON reports without device paths, serials, usernames, or input
  history. Reports include proof state, protocol candidates, scoped conflicts,
  safety status, trajectory metrics, and requested next evidence.
- Generic discovery remains read-only. No new HID writer, runtime promotion,
  or desired-state mutation was added. Razer protocol implementation remains
  automated-test evidence only pending physical qualification.

## 2026-09-17 — HID intelligence consolidation and native Razer runtime

- The descriptor engine now preserves Delimiter alternate usage sets, handles
  Array selectors/nulls/multi-byte values correctly, treats Buffered Bytes as
  opaque blobs, and exposes units, physical values, wire positions, collection
  paths, report direction, and stable member identity through one decoder.
- Standard HID usage interpretation and evdev correlations were expanded while
  vendor-defined usages remain opaque.
- Exact modeled Razer Viper V2/V3 variants now use a native 90-byte RPC backend
  for DPI, polling, firmware, battery, and charging, with DPI/polling readback.
  OpenRazer remains provenance only; its runtime adapter/dependency was removed.
- Protocol-neutral repeated-frame role inference, bounded checksum/CRC
  inference, contrastive controls, and information-gain experiment selection
  feed Automatic Discovery without granting write authority.
- The complete production-module/repertoire disposition is recorded in
  `docs/CODE_HEALTH_AUDIT.md`.
- Automated validation: 637 tests passed with the existing GLib deprecation
  warning; compileall, diff validation, and sdist/wheel build passed. Native
  Razer physical hardware validation remains pending.

Last updated: 2026-09-17

## TUI-only interactive setup

The full-screen setup TUI is the sole supported interactive setup experience.
`mouse-control` in a terminal, `mouse-control setup`, and `mouse-control tui`
route directly to the same TUI transaction. Redirected or programmatic CLI
setup is rejected before curses is imported or invoked;
it never falls back to the retired line-oriented prompt wizard. The legacy
routing alias, prompt flow, action menus, and setup-only compatibility tests
have been removed. Runtime/configuration APIs remain available independently
for noninteractive operation.

## v0.9.3 release preparation

The accepted Automatic Discovery checkpoint is
`2995cbed24f9cef30ce5e94bfc7c29555e438639`. It includes descriptor-backed
semantic persistence and exact-member rebinding, teacher-free read-only DPI
recognition, generation-aware RESYNC/LIVE handling, and independently PROVEN
exact-model learned transactions. Native HID++, native Razer RPC, remapping, polling,
notifications, reconnect, service behavior, configuration compatibility, and
the current full-screen TUI remain separate established paths under the v0.8.2
compatibility baseline.

Automated release-entry validation passes 658 tests with one existing GLib
deprecation warning. The Fedora 44 RPM upgrades the installed v0.9.1 package to
v0.9.3 without changing the existing configuration. The installed full-screen
TUI selects the G305, preserves its remaps, and starts the packaged service from
`/usr`; production Native HID discovery, 1000 Hz polling, 3000 DPI reconciliation,
remapping, and one-popup-per-physical-press behavior are physically validated.

Two receiver reconnect cycles recovered the exact G305 evdev identity and
settled back to the Native HID adapter. RESYNC/rebind emitted zero false DPI
popups; after the watcher entered LIVE, rapid physical presses produced ordered
one-for-one notifications with no stale-generation duplicates. The first cycle
had a minor cursor recovery delay and several transient learned-adapter response
timeouts before Native HID became available; the service then settled without
continued generation churn or resource growth. This is a non-blocking lifecycle
observation, not a new support claim. The existing physical record also
validates the teacher-free five-stage cycle, wraparound, representative learned
writes with readback, and conservative SIGMACHIP abstention. Published-asset
validation remains the final release gate.

## 2026-09-17 G305 member-level corpus replay

The read-only HID corpus replay path now profiles stable members independently
instead of combining every value from a multi-count field. Multi-count Variable
members use stable `HID-F.../member-N` identities. Opaque multi-count vendor Arrays without
a selector range receive the same positional observation identities while
retaining their descriptor-declared Array flags and parent field provenance;
ordinary HID selector Arrays remain parent-scoped.

The real sanitized `g305-dpi-validate` Report-17 corpus replays with static
header members `1`, `7`, and `16`, a single cyclic member 3 over stages `0..4`,
and static zero members thereafter. Explicit same-device idle, movement,
button, wheel, and side-button controls are clean. The existing exact-device
physical profile independently records high-confidence CPI states near
`823/1543/2048/2567/3067`, confirmed wrap, and the exact state-bearing Report-17
identity at raw offset 4, which resolves to member 3. The read-only semantic
candidate is therefore `DPI_STAGE_INDEX` at `VALIDATED`; its raw mapping remains
`CORRELATED`. Relative controls are activity, never persistent or cyclic state.
No HID write, runtime binding, desired-state mutation, or write authority was
added by semantic validation.

The exact-device G305 profile now persists that validated member as a schema-v2
read-only `hid_state` transition source. Runtime rebinding matches the model,
instance, interface number, descriptor hash, report shape, parent field, and
member index, then reparses the live sysfs descriptor and decodes the named
member rather than trusting a raw byte offset. The older raw mapping remains
`CORRELATED`; configured DPI labels and measured CPI remain separate. A
write-disabled acceptance backend bypasses HID++ and all learned writers while
using the existing `DpiState` and notification path. Automated sequence,
duplicate suppression, notification, identity refusal, and reconnect tests
pass. The live teacher-free path is physically validated across all five
persisted stages (`800/1500/2000/2500/3000`) through the existing notification
path.

Disconnect-class hidraw failures now return control to the existing generation-
checked runtime supervisor. The stale descriptor watcher closes before a fresh
write-disabled Discovery backend resolves the current device, reparses the live
descriptor, and rebinds the exact persisted member identity. Each replacement
generation stays in `RESYNC` while its initial authoritative semantic stream is
active; every state in that stream is accepted silently and the final state
becomes the new generation's baseline. Only after the stream reaches its normal
idle boundary does the watcher enter `LIVE`, where the first same-state packet
is deduplicated and the first changed state produces one notification.
Ambiguous and malformed replacements are refused, and retired generations
cannot deliver events. EIO, ENODEV, node renumbering, descriptor reparse,
multi-state resync, repeated reconnect, and stale-watcher behavior are
unit-tested. Physical EIO/rebind recovery and the `3000 → 800` wrap are
validated; the generation-aware zero-popup resync change still requires
physical retest.

## 2026-09-17 HID Semantic Engine v2

Automatic Discovery now parses HID report descriptors as semantic schemas. It
preserves collection hierarchy, complete Main-item flags, physical ranges,
units, local usage/designator/string declarations, stable descriptor and field
identities, and non-fatal validity diagnostics. A bounded bit-level decoder
handles numbered and unnumbered Input reports, signed non-byte-aligned values,
Variable members, and Array selectors. Standard buttons, axes, wheels,
keyboard/consumer controls, power/battery fields, and vendor-defined fields are
kept distinct; vendor fields remain structured unknowns.

Descriptor-backed decoded fields are available to action correlation through
stable field identities, while the existing raw-byte algorithms remain the
fallback for descriptorless or undecodable traffic. Deterministic field
behavior profiles classify static, momentary, enum, cyclic, counter,
continuous, and persistent observations without granting semantics or write
authority. Expected Linux event relationships remain separate from observed
evdev confirmation. Trace HID enrichment is a derived record linked to, and
never substituted for, immutable raw evidence.

This layer is entirely read-only. It adds no replay, HID write, vendor
transaction inference, DPI/polling write promotion, or desired-state mutation.
Synthetic golden descriptors are automated-test evidence only; G305 and
SIGMACHIP descriptor/report behavior has not been physically validated in this
milestone.

## 2026-09-17 trace evidence foundation

Automatic Discovery now has an additive, observation-only USB trace foundation.
It defines versioned protocol-neutral observations and transactions, decodes the
Linux binary usbmon extended ABI, resolves each live capture from a stable
physical-device fingerprint to the device's current USB bus/address, and pairs
URB submit/completion events without assigning vendor semantics. Missing,
reused, mismatched, and capture-boundary URBs remain explicit evidence instead
of being silently discarded. Deterministic schema-v1 session manifests and
streamed artifact hashing establish the first corpus/reproducibility boundary.

This foundation does not import PCAP/PCAPNG, infer semantic fields, promote a
protocol hypothesis, or expose any execution path. Captured writes remain raw
evidence and grant no write authority. Live usbmon behavior is unit-tested
against ABI fixtures but has not yet been physically validated on a USB bus.

## 2026-09-17 setup observed-state separation

Setup now loads an exact-device calibrated read-only profile into a dedicated
presentation snapshot. Review labels measured physical DPI, measured polling,
configured software preferences, and proven write controls independently, so a
new unknown mouse cannot appear to inherit another mouse's hardware readings.
An existing physical calibration is shown before deeper learning; when its
runtime source is unresolved, setup offers transition-source capture and states
that ruler calibration will be reused. Absolute and trigger-only learned sources
retain their distinct synchronization semantics. This presentation state never
changes backend write capabilities or configuration values.

## v0.9.0 release status

Automatic Discovery is now integrated into the production runtime. A single
protocol-neutral learned HID session can share exact-model PROVEN DPI and
report-rate transactions with validated read-only physical action events.
Normal polling reconciliation retains the no-takeover safety boundary, and
v0.8.2 behavior remains the compatibility contract for future releases.

Physically calibrated schema-v2 DPI profiles now persist independently from
runtime-source inference. Later guided runs reuse the ruler/wrap calibration
and retry only passive transition capture. At runtime, stable interface facts
bind HID absolute/trigger and evdev absolute/trigger sources to current nodes;
ambiguous matches are refused. Absolute observations resynchronize a read-only
cycle tracker, while trigger-only observations advance only from genuinely
synchronized state and lose synchronization on continuity loss. Evdev evidence
is observed inside the existing grabbed `MouseRemapper` stream, so no competing
event-node reader is opened. These paths emit confirmed observed DPI without
calling writable `DpiCycler.cycle()` or granting generic write authority.
Passive `feature_state` polling remains deliberately unsupported until a
bounded read-only GET_FEATURE owner can be added without competing HID readers.

## 2026-09-16 discovery-first setup stabilization

Interactive setup now follows Device -> Hardware Discovery -> DPI -> Polling ->
Buttons -> Service -> Review. Selecting a mouse triggers the same comprehensive
safety-first DiscoveryEngine used by diagnostics, with stage progress surfaced
inside the full-screen TUI. Known protocol capabilities, exact-model learned
operations, range-based DPI, and independent polling facts are consumed before
configuration.

DPI setup accepts either enumerated values or min/max/step ranges; live tests
remain reversible and require confirmed hardware state before the staged value
changes. Polling setup distinguishes protocol-reported state from read-only evdev
timing measurement. Review edits carry an explicit return target, and device
switching rolls back temporary DPI where possible and invalidates all
device-specific discovery state.

This architecture change is automated-testable but is not a new physical hardware
validation claim. G305 acceptance remains a separate physical gate.

## Current architecture

Mouse Control keeps evdev/uinput remapping independent from hardware control.
Hardware discovery preserves all matching HID interfaces for a physical input
device. `NativeHidBackend` lets protocol drivers probe those interfaces and
refuses hardware writes if more than one interface claims the protocol.

One `HardwareSupervisor` owns the selected physical backend and exposes a
stable reference to DPI cycling, DPI events, polling control, and battery
status. Startup and reconnect use the same explicit `DesiredHardwareState`
reconciliation. Backend replacement is generation-guarded, closes the old
backend, resolves the current exact transport plus VID:PID without guessing
ambiguous devices, and reapplies safe live polling and DPI state before event
monitoring resumes.

One `HidSession` owns each selected hidraw interface. It serializes writes,
correlates command replies, dispatches unsolicited events without competing
readers, logs subscriber failures without killing the reader, and wakes
pending requests on disconnect.

The first driver is Logitech HID++ 2. It discovers feature-table indexes live
through ROOT and implements Adjustable DPI (`0x2201`) enumeration, reads,
validated writes, and write verification. Onboard Profiles (`0x8100`) events
are recognized by their dynamically discovered index; a resolution-slot event
causes a current-DPI query and emits canonical confirmed state.

Report Rate (`0x8060`) list/read/write and readback verification are implemented.
Onboard Profiles (`0x8100`) live mode read/write mechanics are separate from
backend safety policy. Automatic Onboard -> Host transition is allowed only
for the USB Logitech G305 (`0003:046d:4074`), is verified before the rate
write, rolls back to the original mode if the transaction fails, and remains
in Host mode after a verified success. Unknown mice already in Host mode may
use their advertised live report-rate control, but are never transitioned
automatically. Persistent profile programming is deliberately not claimed. Its complete
record format needs additional protocol fixtures and physical write validation
so unrelated profile fields are never damaged.

Native HID exposes protocol-neutral read-only battery state when a validated
HID++ battery feature is available. ROOT discovery selects Unified Battery
(`0x1004`) or Battery Status (`0x1000`) with separate decoders. The physically
observed G305 exposes `0x1000` at a dynamically resolved index of `0x05`; its
observed `5a 32 00` payload decodes to 90% discharging. The optional SNI tray
item draws a compact monochrome battery with proportional ARGB fill (without
percentage text), and supplies the exact percentage and status through its
tooltip and standard DBusMenu. Icon, tooltip, and menu derive from the same
BatteryState and refresh together.
Extended Adjustable DPI (`0x2202`) is discoverable but independent-axis packet
handling is likewise deferred.

OpenRazer is protocol provenance only, not a runtime dependency or backend.
Exact modeled Razer devices use Mouse Control's native RPC implementation;
unknown or ambiguous hardware falls back to Generic HID diagnostics and
ordinary evdev remapping without guessed capabilities or writes.

Backends now return confirmed DPI state where live readback is available.
Legacy setters without readback remain compatible, while `DpiCycler` records
their result as requested/unconfirmed rather than treating it as hardware fact.

Freedesktop DPI notifications consume canonical DPI values. Each update uses
`replaces_id = 0` for every confirmed physical transition, and notification failures do
not stop hardware handling or remapping.

## Validation status

The native session, HID++ transaction, lifecycle, reconnect, notification,
remapping, configuration, service, and backend behavior use deterministic fixtures and require no
physical hardware in CI. The Logitech G305 Lightspeed Wireless Gaming Mouse is
the reference identity for automatic native detection and Host-mode policy.
The Logitech G305 reference path has completed physical validation for exact-model learned DPI writes, 1000/500/250/125 Hz report-rate changes, persistent-session requirements, exact rollback, and Host-mode physical DPI-button trigger behavior. Deterministic fixtures continue to cover session, reconnect, notification, remapping, configuration, service, and backend behavior without requiring hardware in CI. Other devices still require their own device-specific physical validation.

Future hardware support may supply a validated protocol adapter or promote an exact-model learned operation only after the required proof, then must pass the universal behavior suite.
Hardware additions should not redesign established remapping, notification,
lifecycle, or service behavior.

## 2026-09-15 acceptance blocker investigation

Automated validation: 295 tests pass, including 11 new cases spanning actual
HID++ ROOT discovery, native policy, optional supervisor forwarding, setup
choices, and verified/failed transactions. Compile and whitespace checks pass.
Python sdist/wheel and local Fedora RPM builds pass; RPM `%check` also passes
295 tests, compileall, and the staged CLI smoke test. A wheel installed in an
isolated virtual environment passes `mouse-control --help`.
No polling implementation change was required: reviewed commit `1c7b23f`
already contains the correction to the old capability policy.

Physical validation: the user reported a passing initial doctor/environment
checkpoint and a blocked first polling screen. No polling write occurred in
that checkpoint; no physical writes were performed in this investigation.
The system-installed 0.8.1 still contains the old discovery-time Host-only
writability flag and lacks the new transaction, while the checkout uses the
G305-specific policy. An isolated fixture against that installed package
reproduced readable `1000/500/250/125`, current `1000`, writable `False`.

Remaining physical acceptance: execute the explicit source command in
`G305_HARDWARE_ACCEPTANCE.md` for `1000 -> 500 Hz`; install matching code for
the service before continuing lifecycle acceptance. Package version alone is
not proof of source parity. All rate transitions, combined Host-mode behavior,
and reconnect acceptance remain pending.

## 2026-09-15 setup remap preservation

Setup now begins with the existing valid `[remap]` table and changes only
buttons explicitly captured in the wizard. Skip/keep mappings is idempotent,
including the canonical `dpi-cycle` action. The button-action menu offers
`dpi-cycle` directly; no device or button code receives an implicit DPI role.
The G305 physical validation sequence remains pending: confirm the
`BTN_FORWARD = 'dpi-cycle'` mapping survives setup, restart Mouse Control, and
verify physical DPI cycling before attempting the verified `500 -> 250 Hz`
polling transition.

## 2026-09-15 setup configuration preservation

Setup now loads persisted desired DPI stages, active DPI, polling rate, remaps,
and notifications before probing hardware. Capability discovery is display-only:
it reports supported/current hardware state without replacing valid preferences.
Only an explicit DPI or polling selection results in the corresponding hardware
write. Setup merges its owned fields into the parsed TOML and retains unknown
forward-compatible tables. The prior physical polling persistence observation
is therefore **inconclusive**: setup's destructive initialization, not Native
HID/HID++ behavior, could have restored 1000 Hz.

Physical acceptance remains required after installing this build: verify
custom DPI/active DPI, `BTN_FORWARD = 'dpi-cycle'`, other mappings, and a
configured 500 Hz rate survive setup; then run the documented 1000→500→250→125→1000
polling sequence and separate reconnect acceptance.

## 2026-09-15 reconnect promotion after partial enumeration

Physical reproduction: a normally operating G305 using Native HID/HID++ was
unplugged and reinserted. During incomplete receiver enumeration the
supervisor rebound to Generic HID / evdev. Evdev remapping recovered, but no
later Native HID rebind occurred, so Native-HID DPI event monitoring and DPI
notifications remained unavailable until a daemon restart.

Root cause: after Native HID had cleared `HardwareSupervisor.discovery_pending`,
a Generic fallback rebind did not set it again. `DpiMonitorSupervisor` then
treated Generic's unsupported DPI events as conclusive and used its unsupported
wait path instead of continuing supervisor rebind discovery. This was a
backend-selection lifecycle defect, not a notification delivery failure.

Correction: a Generic fallback following any previously selected non-Generic
backend is provisional. The supervisor continues retrying discovery, retains
the current Generic backend without generation churn for repeated Generic-only
probes, and atomically promotes to Native when it becomes safely available.
Promotion closes the superseded fallback, advances the generation, and lets
existing generation-aware consumers bind a fresh DPI event watcher.

Automated validation: 305 tests pass, including delayed Native HID discovery
after a Generic fallback and DPI event/notification recovery after promotion.
`python3 -m compileall -q src tests` and `git diff --check` pass. Physical
receiver-reinsert validation on the G305 remains pending; no physical recovery
claim is made from the fixtures alone.

## 2026-09-17 v0.9.4 CPI packaging gate

Physical CPI measurement is a first-class installed command at
`mouse-control cpi`; the compatibility executable
`mouse-control-sensor-calibrate` remains available. Discovery and calibration
share packaged `mouse_control` modules directly, with no repository-relative
helper, shell-out, or `mouse-dpi-tool` executable.

Automated validation passes 664 tests with one existing GLib deprecation
warning; compileall and whitespace checks pass. The wheel installed in an
isolated virtual environment, Fedora RPM `%check`, an installed Debian package,
and the AppImage all pass `mouse-control cpi --help`. The wheel and sdist
contain both calibration modules and no `mouse-dpi-tool` artifact.

These packaging checks did not themselves establish physical validation. The
separate installed-RPM G305 acceptance below supplies that evidence.

## 2026-09-17 v0.9.4 installed-RPM G305 acceptance

The installed `mouse-control-0.9.4-1.fc44.noarch` package selected the exact
G305 `046d:4074` through Automatic Discovery's Native HID adapter. Setup and
restart retained stages `1000/1500/2000/2500/3000`, 1000 Hz polling,
notifications, and configured remaps.

Operator-observed physical validation passed: one slow five-stage DPI cycle,
two rapid cycles with all ten ordered one-for-one popups, a setup-driven
software write to 1000 with canonical readback and no fabricated physical-event
popup, two receiver unplug/reinsert cycles, remap recovery, battery/tray
recovery, no reconnect-created popup or duplicate identity, and a final service
restart with input, remaps, DPI notifications, and battery reporting intact.

The journal showed bounded provisional rebinds followed by Native HID recovery,
not repeated reconnect loops or stale-generation delivery. One first-cycle
learned-adapter candidate refused an undemonstrated 1000-DPI write as designed;
the supervisor then promoted Native HID and reconciled 1000 successfully.
