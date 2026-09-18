# AI handoff log

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
