# AI handoff log

## 2026-09-19 — v0.9.9 release candidate and VirusTotal gate

- Advanced canonical release metadata from v0.9.8 to v0.9.9 and documented the
  accepted canonical TUI, updater, complete Service controls, CLI/TUI parity,
  safe multi-zone lighting model, and retained discovery/security work.
- Added a release-published VirusTotal workflow for exactly the RPM, DEB,
  AppImage, wheel, and source archive. `cssnr/virustotal-action` v2.0.0 is pinned
  to immutable commit `5edfa4c982eb0caec6d568ea27cf715269f5c23b`; submissions are
  limited to four per minute and use only `secrets.VT_API_KEY`. The successful
  publisher explicitly dispatches the scan with job-scoped `actions: write`,
  avoiding GitHub's workflow-token event suppression.
- The repository-owned verifier waits for completed analyses, matches the
  action's SHA-256 against the downloaded bytes, records direct report links and
  malicious/suspicious counts in release notes, and fails the workflow when
  either count is nonzero. Checksums, SBOM, and provenance are not submitted.
- Removed the stale README no-lighting claim, added a truthful workflow-status
  badge, and removed one unused Lighting TUI import exposed by the release Ruff
  gate. No hardware behavior or write authority changed.
- Local validation: focused TUI/updater/lighting/service/lifecycle coverage
  passed 205 tests; release/security coverage passed 35 tests; the complete
  suite passed 1135 tests with the existing GLib warning. Compileall, Ruff,
  workflow-policy validation, `git diff --check`, and resolved-environment
  `pip-audit` (no known vulnerabilities) passed. Wheel/sdist build, installed
  wheel version/help/CPI smokes, Fedora 44 RPM build, RPM `%check` (1135 tests,
  one warning), and packaged command smokes passed. The user's prior physical
  TUI acceptance is retained; no new lighting family was physically validated.

## 2026-09-19 — Parallel canonical-TUI updater reconciliation

- Compared the updater/TUI implementations at unified-addendum commit
  `bd22e158847f49a934f5f5eeb2e1e6b2d2f019c1` and dedicated-updater commit
  `d3bb3bbc198a33825df2e716a431dcf47d3c4d4e`. Reconciliation was manual on
  `codex/post-v0.9.8-unified-addendum`; no merge or cherry-pick was used.
- Retained the unified addendum's single controller/state location, complete
  twelve-screen navigation, Lighting architecture, Service controls, Tools,
  About, and capability inventory. Adopted the dedicated branch's stronger
  updater-owned compatibility policy, explicit-check-only behavior, dynamic
  update action, protected source/unknown/package-source/AppImage states,
  interactive approval, curses suspension during execution, and failure/
  cancellation isolation from `SetupChoices`.
- Release fetching, version comparison, asset selection, package detection,
  SHA256SUMS and trusted-origin verification, package-manager execution, and
  service restoration remain centralized in `updater.py`; no second controller,
  updater state model, release logic, or package logic was created.
- Validation passed: updater/TUI/navigation `218`; lighting `64`; service and
  lifecycle `143`; packaging metadata/entry points `74`; full suite `1131
  passed, 1 warning`; Fedora RPM `%check` `1131 passed, 1 warning`. Compileall,
  `git diff --check`, workflow validation, wheel/sdist, Fedora RPM, and packaged
  command smokes passed. The warning is the existing GLib warning. Build and
  installation staging remained under `/tmp`; no host installation occurred.
- Remaining acceptance is physical only: installed desktop/terminal layout and
  navigation, a real explicit GitHub check, each supported installation/update
  path on a disposable host, service restoration, and exact-model lighting/RMW/
  reconnect behavior. No push, main merge, tag, or release occurred.

## 2026-09-18 — Post-v0.9.8 unified addendum foundation

- Started from clean tagged `v0.9.8` (`e3c48c5`) and created
  `codex/post-v0.9.8-unified-addendum`; `main` was not modified.
- Added complete canonical TUI product surfaces and an enforced CLI/TUI map;
  update and service controls reuse the existing updater/service paths.
- Added optional multi-zone native-lighting models, per-device config, RGB24
  validation, persistence/write-scope vocabulary, volatile reconnect restore,
  no-repeat reconciliation, and mandatory shared-record RMW proof gating.
- Added source-backed/write-disabled lighting knowledge plus a comprehensive
  research ledger. No generic HID writer or runtime authority was added.
- Validation: 1122 full-suite tests passed with the existing GLib warning;
  compileall and diff checks passed. Wheel/sdist, installed-wheel smoke, and
  Fedora RPM `%check` passed at the packaging checkpoint. Debian/AppImage tools
  and physical RGB hardware were unavailable. No install, push, merge, tag, or
  release occurred.

## 2026-09-19 — OpenSSF Scorecard maximum hardening

- Created `codex/openssf-scorecard-hardening` from current `origin/main`
  `4146562`. Recorded the public Scorecard 5.5.0 baseline (5.5 aggregate), then
  addressed the actionable fuzzing, dependency-pinning, security-policy, and
  signed-release evidence gaps without weakening established runtime behavior.
- Added seven environment-specific, exact-version, SHA-256-checked pip locks,
  deterministic regeneration/verification, and hash-enforced CI/audit/release/
  AppImage installs. Added bounded ClusterFuzzLite HID descriptor/report and
  offline vendor-capture parser targets with immutable builder/action pins.
- Future releases export the genuine GitHub/Sigstore SLSA bundle and verify all
  checksum-listed artifacts against the repository, workflow, commit, ref, and
  predicate before publishing. Independently verified v0.9.8's original bundle
  and all artifact digests, uploaded it to the release, downloaded it again,
  and confirmed byte identity. Four older releases had no original attestation
  records and were left untouched.
- Added direct private-report guidance, response/disclosure expectations,
  change control, mandatory feature/regression tests, dependency policy, and an
  honest Best Practices evidence/gap map. PyPI publishing remains unwired
  because the public name has no verified project ownership or Trusted
  Publisher configuration.
- Validation: locked CI suite `1101 passed`; Fedora RPM `%check` `1101 passed,
  1 warning` plus packaged CLI smokes; Ruff, workflow policy, lock policy,
  compileall, whitespace, clean wheel/sdist, wheel reproducibility, and locked
  dependency audit passed. Both real Atheris targets completed 100 libFuzzer
  runs without crashes. No hardware access, physical validation, runtime or
  write-authority change, merge, tag, or release occurred.

## 2026-09-18 — PR #6 cloud CI remediation

- Continued `codex/openssf-pre-v1-hardening` from pushed checkpoint `1c25ffc`.
  The repository-security failure came from invoking `build --no-isolation`
  after installing `requirements/dev.txt` without the declared setuptools/wheel
  backend. Added explicit pins for `setuptools==83.0.0` and `wheel==0.48.0` plus
  a metadata regression; the older initially evaluated setuptools pin was
  rejected after `pip-audit` identified its current advisory.
- The Python 3.12 retry/write storms came from stopping the wake coordinator
  before setting the shared shutdown event. Its generation change released DPI
  and battery waits while teardown still appeared live, allowing repeated
  rebind and desired-state reconciliation. Teardown now publishes shutdown
  intent first; STOPPING is terminal to both loops, is not returned as wake
  evidence, and cannot be revived by late input activity.
- Added deterministic coverage for zero teardown rebinds, exactly one initial
  DPI and polling write, prompt DPI/battery retry termination, no late wake
  revival, and pinned no-isolation build requirements. Existing matching-device
  wake-backoff cancellation remains covered and unchanged.
- Validation: 50 repetitions of each of the two cloud failures and the new
  end-to-end teardown test passed (`150` executions); focused lifecycle/wake/
  hardware/notification coverage passed `114`; the full suite passed
  `1086 passed, 1 warning`. Compileall, Ruff, workflow validation, whitespace,
  clean no-isolation wheel/sdist builds, two-build byte-identical wheel
  comparison, and dependency audit (`No known vulnerabilities found`) passed.
- The Fedora RPM gate exposed that the new metadata test needed
  `requirements/dev.txt` inside the sdist. The source manifest now includes all
  pinned requirement inputs; the rebuilt RPM passed `%check` (`1086 passed, 1
  warning`) and packaged CLI smoke checks.
- No hardware access, physical test, `main` change, merge, tag, or release
  occurred. PR #6 CI, CodeQL, dependency audit, and Scorecard status require the
  post-push cloud rerun.

## 2026-09-18 — Maximum pre-v1 OpenSSF and supply-chain hardening

- Created `codex/openssf-pre-v1-hardening` from the requested clean checkpoint
  `96be5a1`. Workflow permissions now default to `read-all`; exact job-scoped
  allowlists retain only CodeQL/Scorecard SARIF, tag, dispatch, and release
  OIDC/attestation/publication writes. All remote Actions are pinned to verified
  40-character SHAs with version comments.
- Added CodeQL v4 Python `security-extended`, OpenSSF Scorecard publication,
  monthly grouped Dependabot updates, scheduled resolved-environment
  `pip-audit`, and a policy validator with regression tests for workflow YAML,
  permissions, immutable pins, unsafe event interpolation, required security
  wiring, and Dependabot configuration.
- Release publication now verifies the exact five primary artifacts, generates
  a deterministic CycloneDX 1.6 project dependency SBOM, verifies the exact
  six-file checksum allowlist, attests those final digests, binds the SBOM to
  the five primary artifacts, and only then publishes them with SHA256SUMS.
  The SBOM is intentionally not described as an AppImage filesystem inventory.
- Added conservative Ruff correctness checks and a clean-snapshot wheel
  reproducibility gate. Wheels were byte-identical; sdist content/order matched
  but setuptools build-time mtimes differed, so wider artifact reproducibility
  was deferred. Fuzzing was deferred because a new Atheris dependency and CI
  surface was not justified for this release-hardening milestone.
- Validation: the clean full suite passed `1082 passed, 1 warning`; compileall,
  Ruff, workflow validation, `git diff --check`, resolved-environment
  `pip-audit` (`No known vulnerabilities found`), wheel reproducibility, and
  CycloneDX JSON validation passed. Wheel/sdist and isolated installed-wheel
  smokes passed. Fedora RPM built with `%check` (`1082 passed, 1 warning`) and
  packaged smokes. A disposable Debian trixie environment built and installed
  `mouse-control_0.9.7-2_all.deb`; a disposable Ubuntu 24.04 environment built
  `Mouse-Control-0.9.7-2-x86_64.AppImage`; both passed version/help/CPI smokes.
- Two known threaded hardware/DPI retry timing assertions each failed once in
  separate full runs, passed immediately alone, and the clean full rerun passed.
  No runtime or hardware code was changed. No hardware access, physical test,
  host package install, push, merge, tag, or release occurred.
- Cloud/owner gates: GitHub CodeQL is pending cloud analysis; OpenSSF Scorecard
  is pending its post-push run; artifact attestation is pending the first
  release execution; Best Practices badge status is pending owner enrollment
  and self-certification. Branch/ruleset, account security, private
  vulnerability reporting, Dependabot security-update settings, and repository
  Actions/security settings remain owner actions.

## 2026-09-18 — Discovery Lab replacement-view navigation cleanup

- Continued `codex/discovery-90-corpus` from clean Advanced Tools checkpoint
  `550457f`. Replaced the modal menu chain for Advanced Tools, all six expert
  groups, all tool details, and the Vendor Capture introduction with an
  in-place Lab content-view stack under the unchanged boxed navigation rail.
- Added compact Discovery Lab breadcrumbs. `b` pops exactly one Lab view and
  restores the parent view's cursor and scroll state; `h/l` returns to
  top-level page navigation, and `q` retains the setup application's existing
  quit-confirmation semantics.
- Read-only detail screens use `j/k scroll` and `g/G top/bottom` without
  advertising an invalid Enter action. Confirmation, warning, error, Help,
  and short input interactions remain focused overlays.
- Preserved all 28 Advanced Tools routes and their existing status/context
  presentation. Vendor import still uses the same bounded local importer and
  existing review/staging confirmation; only its normal navigation preface is
  now a content page.
- Safety: no Discovery, protocol, wake, service, persistence, remapper,
  backend, hardware, or write-authority behavior changed. No hardware access
  or physical validation was performed.
- Validation: focused TUI/Lab/importer coverage passed 181 tests before the
  final expanded per-inspector/modal checks; the final focused navigation set
  passed 102 tests. The complete suite passed 1075 tests with the existing
  GLib warning; compileall and `git diff --check` passed. One first full run
  exposed the previously documented DPI-monitor retry timing assertion; that
  test passed immediately alone and the clean complete rerun passed.

## 2026-09-18 — Discovery Lab Advanced Tools dashboard

- Continued `codex/discovery-90-corpus` from clean TUI polish checkpoint
  `35f4608`. Preserved the boxed unnumbered rail, shared hierarchy, responsive
  curses layout, navigation keys, and default Full Automatic Lab path.
- Added a grouped Advanced Tools dashboard with 28 repository-backed routes
  across Inspect & Evidence, Protocol Analysis, Hardware Investigators,
  Routing & Persistence, Experiment Planning, and Capture & Corpus. An explicit
  audit mapping covers all 13 existing `LabInstrument` values.
- Inspectors present bounded live context from existing discovery results,
  descriptors/snapshots, canonical Lab experiments, differential/dialogue/
  timing/dependency/integrity analysis, CPI/polling/power/freshness evidence,
  routing/persistence/restoration state, action/planner state, imports, and
  repertoire/corpus knowledge. Status vocabulary is limited to READY,
  READ ONLY, NEEDS HARDWARE, NO EVIDENCE, OBSERVED, DECODED, PROVEN, or DISABLED.
- Only two expert routes execute: the existing `execute_lab_plan` path and the
  existing vendor importer. Every tool shows description, status, and current
  context before opening. No raw HID transmission, new executor, write path,
  authority promotion, protocol behavior, persistence behavior, or backend
  behavior was added.
- Validation: focused TUI/Lab/analyzer/importer coverage passed 237 tests; the
  prescribed Automatic Discovery/runtime set passed 90 tests; the complete
  suite passed 1070 tests with the existing GLib warning. Compileall and
  `git diff --check` passed. A known threaded DPI-monitor timing assertion
  appeared only when the runtime set was combined with the new UI test module;
  the test passed alone, the prescribed runtime set passed both here and from
  archived clean `35f4608`, and the complete suite passed. Physical hardware
  validation was not performed.

## 2026-09-18 — Final TUI hierarchy and navigation polish

- Continued `codex/discovery-90-corpus` from clean wake checkpoint `f52a9e2`.
  Preserved the accepted curses layout and all controller/runtime behavior.
- Removed visible numeric rail prefixes and gave each compact named item a
  boxed-row treatment with stronger active and quieter inactive emphasis.
- Added shared primary/heading/action/metadata row roles, compacted DPI and
  polling capability summaries, aligned selectable values, and reduced the
  READY/status treatment to a small semantic badge with muted explanation.
- Footer and Help terminology now match actual controls: `h/l` changes pages,
  `g/G` selects first/last, `b` goes back, `q` quits, and Enter names follow
  the focused action (`run`, `import`, `measure`, `set`, `edit`, or `save`).
- Safety: no Discovery, protocol, wake, service, persistence, write-authority,
  backend, remapper, or hardware-control behavior changed. No hardware access,
  install, push, merge, tag, or release occurred.
- Validation: focused TUI/setup/Lab/importer coverage passed 142 tests. The
  complete suite passed 983 tests with the existing GLib warning; compileall
  and `git diff --check` passed. Two prior full runs each exposed a different
  threaded runtime timing failure; both failed tests and their complete modules
  passed immediately in isolation before the clean full run. Physical hardware
  validation was not performed.

## 2026-09-18 — Near-zero-latency mouse wake handling

- Request: attachment `6381a25d-bbbf-4cd9-aa7d-823d2f6426b6/pasted-text.txt`
  on `codex/discovery-90-corpus`, starting at `9637a9a`.
- Preserved the fastest case: enumerated evdev/hidraw sessions remain open and
  their kernel-blocking readers handle the first valid report directly. Wake
  activity does not invoke Automatic Discovery, descriptor/corpus work, proof
  reevaluation, configuration reload, or backend reconstruction.
- Added one shared wake coordinator plus a receive-only Linux AF_NETLINK device
  listener. Exact selected VID:PID add/change evidence interrupts evdev, DPI,
  battery, and hardware retry waits immediately; the existing stable identity,
  adapter-affinity, interface/evidence, and generation checks still authorize
  any actual rebind. Concurrent consumers cannot duplicate initialization.
- Added monotonic T0/T1/T2/T3 samples and repeated min/median/p95/max summaries.
  The remapper marks T3 only after the first non-SYN event has followed the
  normal mapping/passthrough and uinput synchronization path.
- Safety: the listener has no connect/send operation and grants no hardware or
  write authority. Generic discovery remains read-only. Hardware writes,
  installation, push, merge, tag, and release were not performed.
- Validation: focused lifecycle/discovery/remapping/notification/security
  coverage passed 123 tests; the complete suite passed 982 tests with the
  existing GLib warning; compileall and `git diff --check` passed. Physical
  sleep/wake latency remains `UNVERIFIED — NEEDS PHYSICAL TEST`.

## 2026-09-18 — Canonical TUI redesign and post-overhaul validation

- Continued `codex/discovery-90-corpus` from clean `fd36184` without changing
  the Discovery execution/proof architecture. Added one shared curses
  presentation system with full/compact/minimum layouts, panels, semantic
  statuses, contextual keys, focus-visible viewports, PageUp/PageDown evidence
  scrolling, wrapped modal/status text, 256-color enhancement with monochrome
  fallback, and batched screen updates.
- Expanded the dashboard/review surface for exact identity, connection,
  battery/power snapshots, mappings, limitations, LAMZU/Aurora proof wording,
  and vendor-capture digest/authority summaries. The no-device condition now
  remains inside the canonical full-screen TUI.
- Removed the prior 20 Hz idle repaint behavior while preserving the one owned
  post-frame initialization worker, deterministic join/cleanup, responsive
  navigation, transactional save/cancel, and external service restoration.
- Validation: focused TUI/lifecycle/Lab/importer tests passed 153; full suite
  passed 976 with the existing GLib warning; compileall and diff checks passed.
  Wheel/sdist, isolated installed-wheel smoke, and Fedora RPM builds passed;
  RPM `%check` passed 976 tests plus packaged command smokes. Debian/AppImage
  build tools were unavailable; structural launcher coverage passed.
- Performance: live no-device PTY startup reached an interactive Help response
  in 228.6 ms median / 232.2 ms p95 across 12 runs, below the 500 ms target.
  Settled three-second idle sampling produced zero redraw bytes and 0 ms sampled
  CPU. Deterministic known-device and Rediscover paths remained sub-millisecond.
- Physical validation: `PHYSICAL ACCEPTANCE PENDING`. No novel write, install,
  push, merge, tag, release, or hardware-support promotion occurred.

## 2026-09-18 — Discovery Lab v1 Vendor Capture Importer

- Continued `codex/discovery-90-corpus` from clean Aurora checkpoint `ebe9039`.
- Added a generic offline importer for canonical JSON/JSONL captures with
  bounded parsing, source SHA-256/provenance, raw-frame preservation,
  deterministic normalized/evidence IDs, manifests, deduplication,
  independent-source corroboration, explicit conflicts, review staging, and
  atomic content-addressed local persistence.
- Projected sufficiently described records into existing Lab observations,
  temporal dialogues/timing, pushed states, Routing Mapper, and Power
  Investigator evidence. The Aurora fixture reuses the shared repertoire for
  response alignment/status, events, routed identity, bootloader and dangerous
  exclusions, and legacy-family separation.
- Added `Discovery Lab → Import Vendor Capture` to the normal TUI. It presents
  format, counts, families, warnings/conflicts, dangerous observations, review
  state, and an explicit write-disabled statement without changing the normal
  automatic Lab action.
- Safety: no import can exceed `DECODED`, become experimentable or `PROVEN`,
  grant a setter/write scope, replay a packet, open hardware, or contact a
  network service. Prohibited/private provenance is refused. No hardware
  request/write, install, push, merge, tag, or release occurred.
- Automated validation: focused importer/evidence/persistence/grammar/temporal/
  routing/Lab/TUI/security/Aurora/power suite `238 passed`; full suite
  `966 passed, 1 warning` (the existing GLib deprecation warning);
  `python3 -m compileall -q src tests` and `git diff --check` passed.
- LAMZU Thorn V2 physical validation remains `UNVERIFIED — NEEDS PHYSICAL TEST`.

## 2026-09-18 — LAMZU Aurora first-class protocol-family knowledge

- Continued `codex/discovery-90-corpus` from clean checkpoint `7698607` and
  consumed the supplied Aurora 1.0.32 research package as vendor evidence, not
  physical proof.
- Added reusable declarative vocabulary for sourced frame grammars, operations,
  async events, model identities, state dependencies, status/timing policies,
  and dangerous-operation knowledge. Existing repertoire families retain their
  behavior.
- Added modern `lamzu-aurora-feature64` and separate legacy
  `lamzu-legacy-report8` families. Modern knowledge covers alignment/status,
  Thorn identities, the full command/event repertoire, sensor/LOD/Angle Tune,
  Rapid Trigger, Scroll Bhop, Competition→20K dependency, and routed identity.
  Legacy knowledge covers report 8 framing/checksum, battery/profile/version,
  flash grammar/layout, and forbidden reset/pairing/update operations.
- Input Report 4 battery state projects into existing pushed-state and Power
  Investigator evidence. Routed identity projects into candidate/ambiguous
  Routing Mapper evidence; `0032` and `002e` remain unresolved. Known DFU
  identities are filtered from mouse selection and refused by Discovery.
- The Lab page reports the LAMZU family candidate, vendor knowledge, incomplete
  exact-hardware proof, and disabled writes. No separate vendor UI or capture
  stack was added.
- Safety: every Aurora operation is non-automatic, both families use
  `WriteScope.NEVER`, and the explicit dangerous-operation denylist contains no
  planner action or executor. No HID/Feature write, device probe, install,
  network activity, push, merge, tag, or release occurred.
- Automated validation: focused Lab/discovery/protocol/TUI/security suite
  `278 passed`; full suite `934 passed, 1 warning` (the existing GLib
  deprecation warning); `python3 -m compileall -q src tests` passed; and
  `git diff --check` passed.
- Physical Thorn V2 validation remains pending: descriptors, response layout,
  routed identity, sensor code, all read semantics, DPI/polling/battery physical
  correlation, persistence, and each independently promoted setter must be
  verified on the exact device.
- Next bounded v1 milestone: vendor capture importer, preserving the same
  local-only replay, exact-identity, proof, routing, and no-write boundaries.

## 2026-09-18 — Discovery Lab battery/charging/power-state investigator

- Continued `codex/discovery-90-corpus` from clean checkpoint `c408b80` and
  extended the existing experiment, differential, timing, freshness,
  persistence, routing, proof, planner, orchestrator, and TUI architecture.
- Added canonical power evidence and conservative percentage, raw-level,
  voltage-like, charging, external/battery-power, full, low-battery, cadence,
  freshness, ownership, and cross-session analysis. Raw and interpreted values
  remain separate; `0..100` alone never establishes percentage semantics.
- Percentage confirmation requires known protocol semantics, independent
  agreement, or repeated directional evidence at distinct charge levels.
  Cross-session trends require exact device-unique identity. Fresh state may
  supersede a stale cache without erasing it, and contradictory routed or
  independent sources remain explicit.
- Repeated controlled cable transitions may correlate binary charging state,
  but a cable action does not label arbitrary fields. Planning prefers one
  charging transition or a mouse-only power-cycle cache check; otherwise the
  candidate remains pending for normal future evidence rather than forced
  discharge or waiting.
- The orchestrator automatically runs the investigator after differential and
  routing analysis when a power plan/state/namespace or periodic status candidate
  suggests it. The TUI adds a concise Battery / Power section, and replay redacts session,
  source, routed-owner, and independent-reference identities. Passive runtime
  persistence remains a deliberate extension point rather than a new capture
  scope.
- Validation: 232 focused tests and 905 full-suite tests pass with the existing
  GLib warning; compileall and diff checks pass. Physical validation remains
  pending. No hardware write, charging command, forced load/discharge, network
  activity, install, push, merge, tag, or release occurred.
- Next bounded milestone: vendor capture importer using the same selected-device,
  local-only, replay, proof, and no-write boundaries.

## 2026-09-18 — Discovery Lab receiver/child routing mapper

- Continued `codex/discovery-90-corpus` from clean checkpoint `b905564` and
  extended the same experiment, topology, dialogue, timing, persistence,
  differential, proof, planner, and TUI models.
- Added canonical routing evidence and a generation-bound receiver/child graph
  for physical receivers, logical children, receiver-local ownership,
  interfaces/endpoints, channels/namespaces, reports, records, internal targets,
  and asymmetric request/response or async routes.
- Internal target candidates require repeated controlled cross-child contrast;
  constant bytes, timing proximity, and structural namespace separation do not
  establish ownership. Unrelated USB fingerprints are excluded and unowned
  selected-device routes remain explicitly unmapped.
- Route rediscovery compares old/new exact-device graphs without carrying old
  authority across generations. Persistence and repeated timing can support but
  never independently prove route ownership. Every routing run feeds the
  existing Differential Analyzer.
- Ambiguity now generates safe information-gain plans for another-child
  controls, repeated selected-child actions, or mouse-only power cycling. The
  TUI summarizes logical routes, receiver-local evidence, unresolved ownership,
  and the next experiment.
- Validation: 123 focused tests and 889 full-suite tests pass with the existing
  GLib warning; compileall and diff checks pass. Physical validation remains
  pending. No write, child-ID probe, receiver-slot scan, install, push, merge,
  tag, or release occurred.
- Next bounded milestone: battery/charging investigator using the same effect,
  persistence, routing, timing, and authority boundaries.

## 2026-09-18 — Discovery Lab state/effect/persistence verification

- Continued `codex/discovery-90-corpus` from clean checkpoint `d211361` and
  extended the same `LabExperiment`, plan, timing, controlled-action, proof,
  information-gain, and TUI architecture without adding a capture stack.
- Added explicit effect states and methods plus a seven-level persistence ladder.
  Fresh state supersedes but does not erase stale evidence; protocol/physical
  disagreement, reversion, and cross-source conflicts remain contradictions.
- Added conservative session, reconnect, receiver, power-cycle, host-restart,
  device/host storage, commit/apply, volatile-until-commit, reverted, and unknown
  classifications. Cross-generation state comparison requires exact physical
  identity; protocol transaction correlation remains generation-isolated.
- Persistence uncertainty now selects bounded idle, reread, reconnect, receiver-
  reconnect, or power-cycle plans with timing-derived windows and human-cost/
  disruptive-test stops. Original-state recovery is requested manually and can
  be marked verified, but is never automatically written without authority.
- The Lab page presents effect, persistence, strongest tested level,
  contradictions, restoration needs, and next uncertainty. Replay retains the
  new findings deterministically with redacted source IDs and no unrelated
  keyboard, clipboard, screen, evdev, or USB history.
- Validation: 140 focused tests and 876 full-suite tests pass with the existing
  GLib warning; compileall and diff checks pass. Physical validation remains
  pending. No hardware write, install, push, merge, tag, or release occurred.
- Next bounded milestone: receiver/child routing mapper using the same exact-
  identity, generation, experiment, proof, and authority boundaries.

## 2026-09-18 — Discovery Lab controlled-action orchestration

- Continued `codex/discovery-90-corpus` from clean checkpoint `89a78e1` and
  reused `LabExperiment`, timing, differential, inference, physical verifier,
  proof, authority, and TUI layers rather than adding a second evidence model.
- Added the full controlled-action vocabulary, five safety classes, eight
  initial action templates, canonical experiment plans, timing-derived bounded
  windows, semantic negative controls, question-specific repeats, multi-
  instrument selection, and information-gain choice with human-cost tie breaks.
- The event-driven executor captures the existing canonical intervals, invokes
  automatically selected CPI/polling verification, always runs the Differential
  Analyzer, retains hypothesis lifecycle and negative evidence, records explicit
  stop reasons, and recalculates the next safe experiment when ambiguity remains.
- The Lab page now explains the current question, best experiment, why it was
  selected, automatic work, the user's minimum physical action, strengthened or
  rejected findings, and the next uncertainty.
- Safety/privacy: no generic write primitive or authority transition was added;
  bounded-engine actions need separate existing authority; plans and experiments
  always report `write_authorized == false`; replay is deterministic, local,
  selected-device scoped, and excludes evdev/keyboard/clipboard/screen history.
- Validation: 122 focused Lab/protocol/TUI/measurement/authority/security tests
  and 858 full-suite tests pass with the existing GLib warning; compileall and
  diff checks pass. Physical validation remains pending. No install, push,
  merge, tag, release, or hardware write occurred.
- Next bounded milestone: state/effect/persistence verifier using the same plan,
  experiment, timing, proof, and authority boundaries.

## 2026-09-18 — Discovery Lab protocol timing profiler

- Continued `codex/discovery-90-corpus` from clean checkpoint `91cdbd2`; reused
  the canonical `LabExperiment`, `DialogueRecord`, bounded burst,
  `PushedStateRecord`, freshness, logical-record, generation, proof, and
  information-gain architecture rather than adding a timing capture stack.
- Added canonical experiment-attached timing evidence for request/response and
  ACK, busy/poll/ready cycles, burst first-response/gaps/quiet/duration,
  nudge/action/periodic pushes, stale-read settling, commit/last-valid to
  disconnect, reconnect duration, and first valid new-generation state.
- Repeated distributions retain raw samples, accepted count, minimum, median,
  maximum, spread, and MAD-based outliers. Classification uses established
  protocol context and relative baseline/action distributions, never universal
  millisecond truth; insufficient ordinary evidence stays unknown.
- The existing differential analysis now ranks baseline/action timing deltas
  alongside packet/field evidence. Timing ambiguity creates read-only
  information-gain recommendations such as repeat without a nudge, repeat
  request/push timing, or extend the busy observation window.
- The Discovery Lab page displays stable/variable medians, stale-state settling
  warnings, and meaningful timing deltas. Replay timing evidence is deterministic
  and hashes source identifiers; it retains no keyboard, clipboard, screen, or
  unrelated USB activity.
- Validation: 171 focused Lab/discovery/protocol/TUI/security tests and 849 full-
  suite tests pass with the existing GLib warning; compileall and diff checks
  pass. No physical validation, hardware write, install, push, merge, tag, or
  release occurred.
- Next bounded milestone: Controlled Action Matrix using the same experiment,
  timing, safety, and TUI models.

## 2026-09-18 — first-class Discovery Lab differential analyzer

- Continued `codex/discovery-90-corpus` from clean checkpoint `c7ca4d0` and
  added the first bounded master-Lab milestone without replacing the existing
  capture, logical-record, dialogue, inference, proof, or provenance layers.
- Added a canonical generation-isolated `LabExperiment` with explicit baseline,
  action, post-action, negative-control, and repeat identity. It retains stable
  device context, HID/Feature, USB, logical-record, dialogue, timing, physical
  CPI/polling, provenance, confidence/proof, contradiction, analysis, and next-
  experiment evidence. Deterministic replay output redacts volatile paths and
  excludes evdev/keyboard history.
- The Differential Protocol Analyzer ranks constant, changed, action-specific,
  counter, length, status, integrity, and padding/stale fields; compares timing
  and request/response transactions; reuses dependency, integrity, semantic,
  and information-gain machinery; and keeps invalid records and negative-
  control collisions as contradictions.
- The setup TUI now has `Hardware Discovery → Discovery Lab → Run Full
  Automatic Lab — Differential Analyzer milestone`. It automatically selects
  baseline, three labelled-action repeats, post-action, and ordinary-use
  negative control, then displays known/uncertain/learned state, the next useful
  experiment, and whether that experiment requires a write.
- Security boundary: selected-device existing read-only acquisition only; no
  output/Feature write, setter, generic fuzzing, upload, telemetry, or write-
  authority transition. Ambiguous physical identity is refused and evidence
  cannot cross a connection generation.
- Validation: 176 focused Lab/discovery/protocol/TUI/security tests and 841
  complete-suite tests pass with the existing GLib warning; compileall and diff
  checks pass. No physical validation, hardware write, installation, push,
  merge, tag, or release.
- Next bounded milestone: Protocol Timing Profiler using the same experiment
  record, interval model, TUI page, and read-only authority boundary.

## 2026-09-18 — generic fixed-frame logical-record reassembly

- Continued `codex/discovery-90-corpus` from clean checkpoint `ec7d88f` and
  inserted a generic read-only logical-record layer between fixed HID transport
  frames and semantic recognition. It does not change temporal dialogue or
  simple protocols that do not need reconstruction.
- The reassembler represents single-frame, fragmented, and concatenated
  records with explicit transport/logical lengths and `COMPLETE`, `INCOMPLETE`,
  or `INVALID` state. It retains exact stream/generation identity, all source
  frames, timestamps, declared/captured lengths, integrity state, known field
  bytes, and exact opaque regions. Padding and stale tails are not searched for
  fabricated records.
- Existing integrity hypotheses now validate individual records. Optional
  protected wrappers remain `UNKNOWN` for unsupported algorithms, become
  `VALID` only after calculation, cannot be promoted while unknown, and produce
  invalid non-semantic evidence on mismatch. No checksum engine was duplicated.
- Added a RAWM-style recognition-only recipe using project-owned abstract
  fixtures for complete-state field presence, optional protection, and opaque
  preservation. Family-specific facts are declarative; the reassembler has no
  RAWM branch. The family is `WriteScope.NEVER` and no setter, whole-state
  write, or runtime transaction exists.
- Extended the benchmark from 18 to 27 cases. Outcomes: 12 recognized, 13
  candidate, 1 unknown, 1 ambiguous; fixture precision/known recall remain
  100%, unknown/collision false recognition remain 0%, coverage is 44.4%,
  abstention 51.9%, and ambiguity 3.7%.
- Validation: 156 focused protocol/discovery tests and 831 complete-suite tests
  passed with the existing GLib warning; compileall and diff checks passed. No
  runtime writer, physical test, installation, push, merge, tag, or release.
- No transport-to-logical message-framing form currently identified in the
  mouse research corpus needs another primitive. Payload-driven burst
  terminators/expected counts and multiplexed response namespaces remain a
  separate temporal-dialogue limitation, not a logical-record framing gap.

## 2026-09-18 — generic asynchronous pushed-state discovery

- Continued `codex/discovery-90-corpus` from clean checkpoint `db66379` and
  reused the current dialogue/generation/open-set architecture. Pushed state is
  a generic request-independent record, not a MCHOSE-specific subsystem.
- Added explicit fresh/stale/unknown freshness authority, periodic grouping,
  bounded read-side nudge association, monotonic-counter and controlled-action
  evidence, stale immediate-read supersession, and old-generation rejection.
  A nudge is only an observed eligibility/correlation fact; no command executor
  or write permission was added.
- Added recognition-only MCHOSE Realtek/L7 facts: Input report 13, subtype 1D,
  verified XOR-FF source/result transformation, periodic unsolicited delivery,
  optional nudge-delayed delivery, and possible stale Feature buffers. Unknown
  offsets and semantics remain opaque; the family is `WriteScope.NEVER` and is
  explicitly separate from MCHOSE V3.
- Extended the retained benchmark from 11 to 18 cases with periodic, nudged,
  stale-read/fresh-push, subtype, transform, generation, and unknown-async
  fixtures. Outcomes: 8 recognized, 8 candidate, 1 unknown, 1 ambiguous.
- Validation: 81 focused protocol/discovery tests and 818 complete-suite tests
  passed with the existing GLib warning; compileall and diff checks passed. No
  runtime writer, physical test, installation, push, merge, tag, or release.
- The current research corpus has no remaining asynchronous delivery shape that
  needs another temporal primitive. Remaining async work is recipe/corpus
  population; RAWM fragmented logical records are a separate framing problem.

## 2026-09-18 — Finalmouse-style bounded response bursts

- Continued `codex/discovery-90-corpus` from clean checkpoint `c9f7eb8` without
  restarting recognition architecture. `DialogueAssembler` now owns a generic
  bounded-burst lifecycle with timestamp-driven quiet/deadline completion,
  maximum count, explicit end, and generation-change invalidation.
- Burst results preserve the request, all qualifying responses, start/last
  timestamps, exact completion reason, confidence, generation, channel, and
  grammar. Correlation requires exact physical/source/transport/channel/
  namespace/report/grammar/generation and tag evidence; wrong contexts,
  unrelated events, late replies, and stale generations are excluded.
- Added recognition-only Finalmouse ULX-style facts: distinct mouse/dongle
  namespace pairs, one trigger to multiple telemetry records, and project-owned
  length+command+payload fixtures. Unknown multi-response traffic abstains and
  cross-target mouse/dongle traffic cannot satisfy the family recipe.
- The benchmark retains all six prior cases and adds five burst cases for 11
  total. Outcomes are 5 recognized, 4 candidate, 1 unknown, 1 ambiguous;
  coverage is 45.5%. These fixture metrics do not claim broader 90% coverage.
- Validation: 69 focused protocol/discovery tests and 806 complete-suite tests
  passed with the existing GLib warning; compileall and diff checks passed. No
  runtime writer, write authority, physical test, installation, push, merge,
  tag, or release was added or performed.
- Known model limit: one burst currently has one response channel/namespace/
  report/grammar. Payload-driven automatic terminators/expected counts and
  intentionally multiplexed response namespaces remain future primitives.

## 2026-09-18 — open-set protocol-recognition corpus foundation

- Starting point: clean `main` at `9deabf5`, isolated on local branch
  `codex/discovery-90-corpus`. The supplied research payload was treated as a
  substantial first ingestion milestone, not authority to invent missing
  offsets, packets, semantics, or physical proof.
- Added reusable declarative semantic predicates and explicit open-set
  `UNKNOWN`/`CANDIDATE`/`AMBIGUOUS`/`RECOGNIZED` decisions with independent
  evidence categories and a score margin. BITMOUSE checksum, marker, target,
  sequence, and declared-length recognition now uses the generic recipe.
- Added Keychron M6 paired-namespace recognition and exact Holtek Venus
  structural knowledge. Holtek remains `CANDIDATE` without passive semantic
  evidence. Both entries are `WriteScope.NEVER`; recognition itself always
  reports write authorization false and has no execution primitive.
- Added a collision matrix, explicit provenance/proof limits, project-owned
  positive/near-miss/unknown/collision/identity-blinded fixtures, and metric
  calculation for precision, recall, false recognition, coverage, abstention,
  ambiguity, and per-family recall. The six-case fixture is intentionally too
  small for a broad 90% claim.
- Validation: focused discovery/protocol suite passed 60 tests; complete suite
  passed 797 tests with one existing GLib warning; compileall and diff checks
  passed. No physical device, install, push, merge, tag, release, or hardware
  write was performed.

## 2026-09-18 — launcher / TUI first-frame performance pass

- Starting point: `c4828c6cdf99f2f6dc1b9e459e99f170024920f9` on a new
  `codex/launcher-tui-startup-performance` branch. Profiling found the live
  backend/HID++ handshake (5,618.49 ms in the slow sample), not imports
  (104.38 ms), dominated the pre-frame path.
- The TUI now renders its real device-selection screen first and performs live
  backend/capability/exact-evidence initialization in one owned worker. It
  remains responsive for selection/help/cancel, blocks hardware navigation
  until ready, and deterministically joins/closes the worker.
- Foreground service suspension is queued before process startup and completed
  synchronously before backend creation. Direct event-node enumeration removes
  duplicate evdev prevalidation without dropping the comprehensive candidate
  scan or existing capability/permission checks.
- Same-host supervised timing: warm known-device median 676.22 → 504.15 ms
  (five runs), observed max 777.43 → 647.61 ms; cold/transitional first frame
  6,347.09 → 464.83 ms. Cancel-without-save restored the service after every
  run and preserved the exact configuration SHA-256.
- Validation: focused lifecycle/TUI suites passed 124 tests; the full suite
  passed 787 tests with the existing GLib warning. The 500-round performance
  suite retained known-device restore (0.0342 ms) and explicit Rediscover
  (0.4171 ms). Compileall, diff validation, package checks, and final commit are
  recorded in the final task handoff.

## 2026-09-18 — external foreground-session supervision candidate

- The acceptance claim at `7fb39fb` was treated as failed. Reproduction began
  with an active live G305 service: externally sending SIGTERM to
  `mouse-control setup` after it suspended the runtime left the service
  inactive. This directly proved that the TUI's Python `finally` could not own
  the required guarantee.
- The canonical installed application entry now replaces itself with
  `systemd-run --user --pty --wait --collect`. One transient
  `mouse-control-foreground.service` records/stops the prior runtime in
  `ExecStartPre`, runs the canonical module entry, and restores in
  `ExecStopPost`. The fixed unit name serializes foreground owners; systemd
  owns teardown independently of curses, Python exceptions, and TUI signals.
- Runtime suspension and the persisted service choice are separate. The
  process writes a preference marker only after configuration save. Enable
  installs/enables without starting until post-teardown; Keep disabled disables
  the unit and suppresses restoration. Cancel and unsaved staged disable leave
  the pre-session marker unchanged. Restoration consumes its marker once and
  does not save configuration or enter discovery.
- Live software/system integration: active service restoration passed after
  no-argument cancel, explicit `tui` cancel, `python -m mouse_control` cancel,
  foreground SIGTERM, and a niri/Kitty compositor window close. The inactive
  precondition remained inactive after cancel. Final state was active; journal
  evidence showed the exact G305 Native HID adapter, 1000-DPI reconciliation,
  and `DPI event watcher ready` after restoration.
- Graphical-launch correction: the desktop entry now invokes the packaged
  `mouse-control-launcher` with `Terminal=false`. It prefers a valid
  `$TERMINAL`, then an already installed `xdg-terminal-exec`, then Kitty, foot,
  Alacritty, WezTerm, GNOME Terminal, Console/kgx, Konsole, Xfce Terminal, MATE
  Terminal, or xterm using terminal-specific argument conventions. None is a
  dependency. Missing-terminal failure prints an actionable error and uses
  `notify-send` only when already available.
- Current niri acceptance: the user-local editable package and desktop entry
  were refreshed for testing, not installed as a release. With `$TERMINAL`
  unset and no `xdg-terminal-exec`, the real `gtk-launch mouse-control` path
  selected Kitty, displayed the canonical supervised TUI, and window closure
  restored the active service. An unchanged Save restored active and retained
  the exact pre-test configuration SHA-256
  `25ff898ebd639a2f2c5ffcfa20dd1486351078d82983d63985af7ec94012c17b`.
- Automated/package validation: focused lifecycle/entry/service suites passed
  104 tests before the final package gate; the source gate passed 783 tests
  with the existing GLib warning;
  compileall and `git diff --check` passed. Wheel/sdist built and contained the
  supervisor and graphical helper modules/scripts. Fedora RPM build and
  `%check` passed the same 783 tests plus packaged command smokes; inspection
  confirmed no terminal dependency. The AppImage built in extract-and-run tool
  mode, contains its launcher wrapper/module and `Terminal=false` desktop file,
  and its unpacked AppDir version/help smokes passed.
- Physical acceptance: the user subsequently confirmed remap input, physical
  DPI-button notifications, tray visibility, and battery behavior all work on
  the attached G305. Together with the live lifecycle evidence above, this
  completes the requested current-machine acceptance. It does not establish
  physical support or write authority for another model. No merge, tag, or
  release was performed.

## 2026-09-18 — v0.9.7-1 scoped TUI service-suspension correction

- Follow-up evidence: a direct user-manager trace showed the running service
  being stopped for TUI ownership and receiving no later start request. The
  earlier adjacent `restart`/`stop` journal jobs were not evidence of a TUI
  cleanup callsite; this checkout has one persistent-service stop callsite.
- Root cause: that initial stop was outside the `try/finally` that made the
  restoration decision. The lifecycle was consequently not represented as one
  authoritative scoped ownership operation.
- Correction: the successful service suspension is now acquired inside the
  setup transaction's `try` block and recorded explicitly. The same finalizer
  restores an established previously active service exactly once on save,
  cancel, EOF/interrupt, or recoverable failure. A staged `Keep disabled`
  choice is discarded on cancel; a saved explicit disable remains respected.
- Regression coverage records actual service state transitions and requires
  `active → stop → restart → active` on established cancellation, with no
  stop after the final restart. Focused lifecycle/TUI tests passed 90; complete
  suite passed 746 with one existing GLib deprecation warning; compileall and
  whitespace checks passed.
- Physical validation: a real Logitech G305 session opened the canonical TUI,
  showed its cancel confirmation, exited with status 0, and restored the
  enabled `mouse-control.service` to active. The service's Native HID backend,
  DPI watcher, and tray path returned. An unchanged-config scripted Save
  navigation did not reach Review/Save and was not counted; it was terminated
  and the enabled service restored. No package install, push, merge, tag, or
  release was performed.

## 2026-09-18 — v0.9.7-1 established-runtime TUI restoration fix

- Goal: preserve an already active Mouse Control runtime when its established
  configuration is opened in the canonical TUI and then canceled, abandoned,
  or saved through the transient `Keep disabled` selection.
- Root cause: the setup finalizer conditioned service restoration after a save
  on the in-session `enable_service` choice. That choice is appropriate for
  first-run activation, but it allowed an already running established service
  to remain stopped after a TUI session. The configuration snapshot was also
  loaded only after the service pause.
- Correction: setup loads the persisted configuration before pausing the
  runtime and treats a successfully parsed non-empty configuration as the
  established-session boundary. An active established service is restarted on
  every finalizer path unless `install_service()` has already restored it. A
  first-run cancellation with no saved configuration still does not fabricate
  configuration or start a runtime.
- Regression coverage: cancellation preserves the full existing configuration
  while discarding staged DPI/remap edits; cancellation and handled failures
  restore established services; restart failure is surfaced; first-run cancel
  remains inactive; and a saved established session through `Keep disabled`
  still restores the running service.
- Validation: focused TUI/service lifecycle suite passed 88 tests; complete
  suite passed 744 tests with one existing GLib deprecation warning; compileall
  and whitespace checks passed. No hardware, package install, push, merge,
  tag, or release was performed. G305 acceptance must be repeated on this
  commit before release.

## 2026-09-18 — Redragon M724 + Ryunix Kyu Pro MX1 protocol knowledge delta

- Goal: import newly upstream-researched protocol facts into the universal
  discovery repertoire without making either family executable or writable.
  Starting branch/head: `codex/v0.9.7-python-performance` at `09aea626`.
- Redragon M724: exact `04d9:fc7a` plus Feature Report 2, 16-byte numbered
  frame, `FFA0:0001` control collection, and optional report IDs 3–6 identify
  the record. It describes F5 open/close, F3 write prefix, the indivisible
  F1 commit-code order `04,01,02,08,10`, reciprocal polling raw domain
  `01,02,04,08`, nominal DPI/range math, and FA FA responder evidence. The
  `SessionGrammar` is deliberately descriptive—not an engine transaction—so
  the failure-critical close cannot be omitted by an execution path. Upstream
  physical verification is recorded as provenance only. `WriteScope.NEVER`.
- Ryunix: exact `04f3:026e` / `04f3:026f`, input Report 4, seven-byte numbered
  frame, and `000a:00c7` collection identify read-only telemetry. The decoder
  validates active/charging flags, 125/250/500/1000 reciprocal polling codes,
  and battery 0–100, while retaining DPI stage and LED code as observations.
  Report 5 alone cannot match and no RGB/configuration path exists.
- Generalization: descriptor report definitions retain application collection
  usages; repertoire signatures may require them; `CodecSpec` may limit a
  semantic codec to directly observed raw values. The added `SessionGrammar`
  records mandatory teardown/hazards without expanding `TransactionEngine` or
  providing an adapter that can emit frames.
- Safety: structural recognition remains insufficient to authorize writes.
  Both candidates are exact-identity constrained and return false for write
  authorization even with that identity. Generic Holtek/Redragon and Ryunix
  lookalikes do not match; neither creates a capability, backend, transaction,
  desired-state update, or hardware write. Generic HID remains read-only.
- Provenance: `CREDITS.md` cites OpenMouse commits
  `b7183b395b2b0350c1e50cbcd9616c56f8de2e7a`,
  `73f57898340636e0a0fdab8ce8f517449e065e33`, and
  `37739057a4b1a5484d8e131f1a6b47d753cad7ce`; its unresolved licensing review
  remains explicit. No upstream implementation or test vector was vendored.
- Validation: focused repertoire/descriptor/transaction tests passed 25;
  `git diff --check` and compileall passed; full suite passed 741 tests versus
  the 738-test baseline, with one existing GLib warning. A 500-round benchmark
  found no clear regression: cold import 15.493 ms, known restore 0.0334 ms,
  Rediscover 0.416 ms, single decode 0.0283 ms, bulk 1,000 decode 29.035 ms.
- Physical validation: none. Remaining unknowns include Redragon button/LED/
  profile/report-3 grammars, active-stage read/selection, and individual commit
  meanings; Ryunix Report 5 configuration semantics are intentionally unknown.
  Any future promotion requires exact local hardware evidence, an execution
  adapter with guaranteed session cleanup for M724, and the existing proof/
  authorization/readback requirements.
- Git discipline: no push, merge, tag, installation, or release. Final commit
  is the local protocol-knowledge checkpoint containing this entry.

## 2026-09-18 — v0.9.7-1 integration, updater, and Python performance

- Goal: integrate the canonical TUI checkpoint, correct the incremental-RPM
  updater bootstrap failure, and reduce measured Python work without changing
  features or hardware authority. Starting product commit was `1e21f89` after
  its validated fast-forward to and push on `origin/main`.
- Git: work continued on `codex/v0.9.7-python-performance`. Commits are
  `933e7c8` updater compatibility, `a59aa9f` baselines/instrumentation,
  `95991a5` lazy command imports, `f24ef80` immutable descriptor reuse,
  `3b677fd` event-driven UI wakeups, and `e2983a5` release metadata, followed
  by the final documentation/gate commit containing this entry. Main received
  only the authorized canonical-TUI fast-forward. No tag or release was made.
- Updater: `ReleaseVersion` separates tag/display, PEP 440, RPM Version, RPM
  Release, distro suffix, and architecture. Strict selection still requires an
  official release, safe exact filename, one compatible architecture, manifest
  SHA-256 verification, DNF installation/ownership, and post-install version
  verification. Focused updater/release coverage passed 79 tests.
- Performance: cold app import measured 113.328 to 15.471 ms (-86.3%);
  descriptor parse/reuse 0.0209 to 0.000140 ms (-99.3%); one representative
  decode 0.0652 to 0.0284 ms (-56.4%); 1,000 decodes 66.552 to 28.388 ms
  (-57.3%); explicit Rediscover 0.577 to 0.411 ms (-28.8%). Persisted lookup
  (0.0308 to 0.0309 ms) and known-device restore (0.0341 to 0.0342 ms) remained
  statistically neutral and already skip the expensive discovery path.
- Runtime: replacing 50/100 ms notification/tray polling with cross-thread
  event wakeups reduced the controlled idle probe from 1.031 to 0.016 ms CPU/s
  and 20 to 1 voluntary context switches/s. At 1,000 post-warmup cycles,
  reconnect retained 120 bytes, Rediscover 6,037 bytes, and setup enter/exit 32
  bytes; the bounded descriptor caches are limited to 128 entries.
- Safety: no hardware writer or write authority was added. Current topology and
  exact identity still bind persisted facts; ambiguous/stale/corrupt evidence
  abstains; generic HID remains read-only; explicit Rediscover still forces all
  discovery phases; observed events do not invent desired hardware state.
- Validation: `git diff --check` and compileall passed; the full source suite
  passed 738 tests with one existing GLib deprecation warning. The focused
  security/updater/service/release suite passed 89 tests. Wheel/sdist built,
  an isolated wheel install reported `0.9.7-1` and passed CLI help, and Fedora
  RPM `mouse-control-0.9.7-1.fc44.noarch.rpm` built with `%check` passing all
  738 tests plus packaged CLI smokes. AppImage shell syntax and desktop-file
  validation passed (one non-failing category hint). Local DEB/AppImage builds
  were not available in this environment and are pending their release jobs.
- Physical validation: read-only doctor reported no safely readable mouse and
  warned that the service was stopped. No current-branch G305 write, remap,
  notification, battery, reconnect, or interactive TUI observation was made;
  validation level is automated/package only. Prior-version physical evidence
  is not promoted to v0.9.7-1 evidence.
- Next bounded task: run the v0.9.7-1 DEB/AppImage release jobs and the complete
  installed G305 acceptance checklist, then tag/publish only if both pass.

## 2026-09-18 — v0.9.6-2 canonical TUI launcher correction

- Root cause: the desktop file correctly invoked `mouse-control`, but the
  primary dispatcher sent no-argument established-user launches to the older
  line-oriented `run_home_screen()` while `mouse-control setup` entered the
  current full-screen curses TUI. The AppImage wrapper also bypassed the
  declared application entry point by invoking `mouse_control.cli` directly.
- Correction: no-argument, explicit `setup`/`tui`, packaged console-script,
  AppImage, and `python -m mouse_control` execution now converge through the
  normal application dispatcher on the full-screen setup TUI. The obsolete
  home/service-menu implementation and unused `packaging/mouse-control` wrapper
  were removed; noninteractive commands remain unchanged.
- Regression coverage: entry-point tests prove no-argument and both explicit
  TUI commands reach the same function, the console script delegates through
  `mouse_control.app:main`, source module execution uses that application entry,
  packaging has one desktop source with exact `Exec=mouse-control`, and no
  active legacy launcher or direct AppImage CLI-module route remains.
- Validation: the focused launcher/setup/package suite passed 100 tests; the
  complete source suite passed 711 tests with the existing GLib warning;
  compileall and `git diff --check` passed. Wheel/sdist and Fedora RPM builds
  passed; RPM `%check` passed all 711 tests.
- Artifact inspection/install: the wheel contains `__main__.py` and one primary
  `mouse_control.app:main` console script. The RPM installed through DNF in a
  disposable Fedora 44 system and the DEB installed through APT in disposable
  Ubuntu 24.04; both installed exact `Exec=mouse-control`, generated the primary
  executable from `mouse_control.app:main`, and passed version/help/TUI-help and
  source-module smokes. The AppImage built successfully, passed the same smokes,
  and its extracted AppRun delegates to `usr/bin/mouse-control`, whose wrapper
  executes `python -m mouse_control`.
- Host desktop clicking remains unverified: replacing the host's already
  installed 0.9.6-2 RPM requires an interactive sudo password unavailable to
  this session. No physical hardware behavior was exercised or inferred. No
  hardware writer, authority, identity, remapping, reconnect, notification,
  battery, service, or configuration behavior changed.

## 2026-09-18 — v0.9.6-2 publication and CI fixture follow-up

- Product commit `05979b8` was fast-forwarded to `main`, tagged
  `v0.9.6-2`, and published through release-artifact run `35320372190`.
  Python 3.12/3.13/3.14, Fedora RPM, Debian, AppImage, wheel/sdist, packaged
  CLI smokes, the exact published asset set, and checksum generation passed.
- The parallel ordinary CI run built the RPM, passed its 710-test `%check`, and
  passed packaged CLI smokes, but its final metadata assertion compared RPM
  `VERSION` (`0.9.6`) with the combined project version (`0.9.6-2`). The CI-only
  follow-up now derives and checks RPM Version and Release independently and
  adds a release-metadata regression assertion. Product code and release assets
  are unchanged; the published tag remains at `05979b8`.
- Physical G305 evidence remains as recorded below. Remap behavior and popup
  appearance still require human observation and are not claimed by this
  follow-up.

## 2026-09-18 — v0.9.6-2 incremental lifecycle patch candidate

- Starting point: clean `9c76d3b` on `main`; work performed on
  `codex/v0.9.6-2-lifecycle-fix` without rewriting prior history.
- Root causes: setup cleanup logged service-restart failure after an earlier
  return value was fixed, so false success was possible; the setup controller
  could recognize cached evidence only by entering the Automatic Discovery
  entrypoint; and no-argument launch unconditionally selected first-run setup.
- Correction: setup now computes its result after rollback and verified service
  restoration. Cache-only setup initialization rebuilds current topology and
  delegates exact binding to `DeviceProfileStore`; it never parses descriptors,
  probes protocols, or broadens write authority. Valid established launches use
  the existing home screen; invalid/absent configurations retain first-run setup.
- Safety: no hardware writer, evidence level, device identity, readback rule, or
  remapping/runtime path changed. Missing, corrupt, ambiguous, incompatible, or
  differently bound evidence abstains. Explicit Rediscover remains forced.
- Automated/package validation: focused lifecycle/discovery/runtime/security/
  release suites passed; full source suite passed 710 with the existing GLib
  warning; compileall and whitespace checks passed. Python sdist/wheel build,
  isolated wheel version/CPI smokes, Fedora RPM build, RPM `%check` (710 tests),
  and packaged CLI smokes passed. Debian/AppImage and Bandit/pip-audit remain CI
  gates because their local tooling is unavailable.
- Physical G305 validation: setup displayed immediate known-device reuse;
  cancel-without-save restored the service to active Native HID operation with
  configured 1000 DPI and the DPI watcher ready. With the service stopped,
  explicit Rediscover completed topology, four-interface descriptor collection,
  HID++2 matching, capability validation, and evidence persistence; the service
  was then restored active. Remap and popup appearance require human observation
  and remain pending.
- This candidate was subsequently published as recorded in the entry above.

## 2026-09-18 — v0.9.6 release-wrap software and physical gates

- Ubuntu 24.04 exposed a release-blocking Debian build incompatibility: its
  no-isolation setuptools rejected the newer PEP 639 license keys. The metadata
  now uses the compatible setuptools form while retaining the same GPL
  identifier and shipping `LICENSE` plus `CREDITS.md` in wheel/sdist/package
  outputs.
- The final AppImage was built through the pinned, SHA-verified AppImageKit and
  portable CPython inputs. Its payload now removes runtime bytecode/cache files
  and redundant pip-generated project launchers containing the temporary AppDir
  path. Version/help/CPI smokes and extraction inspection pass.
- Automated validation after the corrections: full source and Fedora RPM
  `%check` suites each passed 700 tests; the focused security/hardware suite
  passed 215; DEB build/install and CLI/CPI smokes passed; AppImage smokes
  passed; compileall, diff check, workflow YAML/action-pin validation, and
  artifact scans passed. pip-audit found no known vulnerabilities. Bandit 1.9.4
  found 0 high/medium and 44 reviewed low findings in `src`.
- The Fedora 44 `mouse-control-0.9.6-1.fc44.noarch` candidate preserved the
  existing configuration and selected exact G305 `046d:4074` through the Native
  HID adapter. Operator-observed remapping/passthrough, two ordered DPI cycles,
  two receiver reconnect cycles, and a service restart passed with no false
  startup/reconnect popup or stuck input. The journal showed bounded reconnect
  recovery, no stale notification, retry flood, or service restart.
- Remaining gate at this checkpoint: push the release commit, run and inspect
  authoritative CI artifacts, merge through the established release path, and
  verify the published tag, five assets, `SHA256SUMS`, and updater lookup.

## 2026-09-18 — v0.9.6 security hardening release candidate

- Started from clean `be03fad` on `codex/github-discovery-onboarding`; created
  `codex/security-hardening-v0.9.6` and preserved both post-v0.9.5 documentation
  and provenance commits.
- Fixed a high-severity update-integrity gap: direct GitHub packages/AppImages
  were previously installed after only non-empty checks. v0.9.6 requires a
  strict official `SHA256SUMS`, verifies before mutation, restricts redirects,
  and hardens AppImage staging/identity/atomic replacement.
- Fixed supply-chain weaknesses by immutable-SHA pinning Actions, least-privilege
  scoping, exact artifact-set enforcement, checksum publication, and digest
  verification for AppImageKit and portable CPython before use.
- Hardened per-user service installation and documented the audited security,
  hardware-write, udev, input, usbmon, filesystem, network, and privacy model.
  No malware, backdoor, telemetry, credential access, or exfiltration was found.
- Validation: focused security/hardware suite 114 passed; full source and RPM
  `%check` suites each passed 700 with one existing GLib warning. Compileall,
  diff check, workflow YAML parsing, sdist/wheel build and content inspection,
  and RPM CLI smokes passed. pip-audit found no known vulnerabilities. Bandit
  found 0 medium/high and 52 reviewed low findings (fixed-argument subprocesses,
  state assertions, and best-effort cleanup).
- Remaining release gates: Debian build is unverified because its tooling is
  absent. AppDir creation and both pinned input hashes passed, but AppImageKit
  could not create the final wrapper without a graphical/FUSE-capable host.
  Checksums are not independently signed; Arch's tag-based PKGBUILD still uses
  `SKIP`; Python/AppImage dependency resolution is version-ranged rather than a
  fully hashed lock. No physical device retest was performed.

## 2026-09-17 — Open-source credit, provenance, and license audit

- Added `CREDITS.md` as the project-level record for protocol-research credit,
  source links, current upstream license metadata where available, distribution
  scope, and a strict distinction between cited facts and imported expression.
- The audit found no vendored third-party source tree or retained upstream
  copyright header in the current tree. Git history shows the current native
  and repertoire modules were introduced in-tree, but cannot prove that every
  protocol constant was never translated from upstream expression; that limit is
  recorded instead of being presented as a legal conclusion.
- Added source-level pointers from the native Razer implementation and protocol
  repertoire to the record. The `bitmouse-72` fixture and unlicensed/unclear
  OpenMouse and AJAZZ source status are explicit maintainer-review items and
  remain non-authorizing/write-disabled where applicable.
- Added the credits record to source, wheel, RPM, Debian, Arch, and AppImage
  distribution paths. Wheel/sdist build inspection verified both `LICENSE` and
  `CREDITS.md` are present in wheel license metadata and that the sdist includes
  the credit record. Updated SPDX metadata to the current string form.
- Validation: release-metadata and package tests passed 15; full suite passed
  685 with one existing GLib deprecation warning; compileall and `git diff
  --check` passed. No hardware behavior or write authority changed.

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
