# OMUS Project Status

## 2026-09-24 — Final Discovery engineering-hardening checkpoint

- Canonical Automatic Discovery outcomes now feed the existing full-screen
  Hardware Discovery and Lab pages. Recognition, inferred state, proven state,
  fast-path reuse, stopping reason, and one requested human action are visibly
  distinct; device rebinding clears the presentation snapshot.
- Compact runtime recipes now validate generation and evidence revision as well
  as identity, descriptor, firmware, and evidence ancestry. Parsing is strict
  and bounded; persistence is atomic and rejects corruption, oversized files,
  symlinks, schema drift, extra/missing fields, and invalid value domains.
- EvidenceGraph, Genome, pipeline, community-import, and grammar/integrity/
  bitfield/record/alignment entry points have explicit deterministic budgets.
  Unknown or excessive input fails closed without changing runtime authority.
- Offline HID++ and native Razer corpus paths remain distinct and
  non-authorizing. Full source suite passes 1,435 tests with the existing
  private-bus skip; source distribution and wheel builds succeed. Physical
  G305, Razer, HID-BPF, UHID/vendor-app, and unknown-device acceptance remain
  separate unexecuted gates.

## 2026-09-24 — Discovery integration and corpus hardening checkpoint

- The canonical offline pipeline now joins exact interface quarantine, existing
  repertoire-to-Genome compilation, active fingerprint selection, Advice
  compilation, grammar inference, and precise human escalation in one
  explainable execution trace. Descriptor mismatch fails before corpus work.
- All 20 existing protocol-repertoire families compile into 62 independent
  identity/operation Genome records. This includes current HID++, native Razer,
  LAMZU, Darmoshark, WLMOUSE, RAWM and other established repertoire knowledge;
  no compiled corpus record is promoted to `WRITE_VERIFIED` by translation.
- Added bounded checksum/CRC candidates, controlled bitfield inference,
  repeated-record detection, cross-model alignment, compact runtime recipes,
  and attributed community evidence. Ambiguity and invalidated evidence fail
  closed. A small canonical presentation model exposes pipeline decisions and
  the next requested human action for later full-screen TUI wiring.
- Compact recipe decode measures 3.41 microseconds and interface admission 923
  nanoseconds on the development workstation. Research graph traversal and
  inference remain outside the runtime input path.

## 2026-09-24 — Deferred Discovery autonomy offline checkpoint

- Added exact, generation-bound research-interface quarantine with separate
  normal-input, configuration, receiver, firmware, bootloader, and unknown
  roles. Passive observation remains the default; mutation needs an exact
  descriptor/role policy and still requires the existing experiment authority.
- Added conservative trace grammar inference, retained byte-order alternatives,
  operation-specific Protocol Genome records with transitive evidence
  invalidation, and an offline orchestrator that reports the exact evidence or
  human action needed when automatic analysis cannot continue.
- Added a testable HID-BPF loader lifecycle shell, deterministic Virtual Oracle
  teaching replay, and firmware artifact inspection/dry-run matching. These
  paths provide no physical write primitive and do not claim live kernel,
  UHID, vendor-software, firmware-update, or hardware validation.
- The new modules are outside the input forwarding path. Exact interface
  admission benchmarks below one microsecond on the development workstation;
  existing performance regressions remain green.

## 2026-09-24 — Discovery autonomy P0 software checkpoint

- Reconciled the September 21 deterministic Discovery implementation over the
  v1.0.4-derived IR branch: bounded experiment execution, mutation policy,
  public protocol codecs/priors, HID++ 0x2202 vocabulary, symbolic actions,
  reactive modeling, Virtual Peripheral Oracle core, and HID-BPF admission
  contract. No public/static evidence grants runtime write authority.
- Added offline active fingerprint selection, a provenance-bound Advice
  Compiler, ordered/register dialogue inference, bounded autonomous candidate
  ranking through the existing `ExperimentAuthority`, and explicit scoped
  family-equivalence hypotheses. Passive/read evidence is preferred; stale
  generations, invalidated evidence, missing baselines/verifiers/rollback, and
  hidden-state conflicts are refused.
- Automated validation is software-only. No new device, HID-BPF kernel adapter,
  virtual transport adapter, cross-model writer, or firmware operation is
  physically validated or enabled by this checkpoint.

## 2026-09-20 — Offline Discovery IR/evidence foundation

- Dedicated local branch adds capability IR, differential proof-plan compilation,
  byte/bit-preserving offline state proposals, an explainable persisted evidence
  DAG with transitive invalidation, and a pinned kernel vocabulary importer.
- Seed corpus: 52 lexical/enum facts from three Linux v6.12 Roccat files. No
  inferred DPI/polling setters, new runtime authority, HID-BPF attachment, automatic
  experiment execution, or Lab integration is claimed.
- New focused tests: 39 passed. Full suite: 1,320 passed, one private-bus sandbox
  skip; that integration test passed separately outside the sandbox. Physical
  validation remains pending. See `DISCOVERY_IR_HANDOFF.md` for scope and metrics.

## 2026-09-20 — v1.0.4 runtime recovery and proof-acceleration candidate

- The accepted runtime-persistence, hardware-truth DPI, bounded receiver-probe,
  and capability-proof acceleration work is prepared as a backwards-compatible
  v1.0.4 patch release over integrated main `f757cbc`.
- Runtime recovery covers reboot/login, service/process failure, tray or D-Bus
  availability changes, and device reconnect while retaining optional-backend
  isolation and the accepted purple battery presentation.
- Current DPI comes from confirmed hardware state; configured stages remain
  choices. Known-owner capability proof reuses immutable protocol knowledge
  without extra HID traffic or broader write authority.
- Physical performance evidence remains scoped to the exact tested G305/Fedora
  environment. Publication still requires protected review and the complete
  artifact, checksum, provenance, and VirusTotal release gates.

## 2026-09-20 — installed Discovery proof acceptance

- Main baseline is protected PR #20 at `9b93b4a`; Discovery implementation is
  `4640054` on `codex/discovery-proof-acceleration`.
- Installed G305 acceptance passed native slow/rapid transitions, normal software
  stages, mixed ownership, receiver recovery, service restart and mouse off/on.
  Capability knowledge remains separate from canonical live DPI and battery.
- Acceptance exposed a same-topology native-session replacement defect. The
  regression-backed correction advances the owner generation even if paths and
  descriptors match; non-native settling remains bounded.
- Final source and RPM gates: **1,282 passed each**, no skips. Warm proof:
  **73.474 µs / zero requests**. Corrected reconnect: **87 ms remapping / 5.00 s
  DPI management**. Normal cycles remain approximately 20 ms / two requests.
  Ordinary service retains eight threads and 18 descriptors.
- See `DISCOVERY_PROOF_ACCEPTANCE.md` for exact measurements, failed/intermediate
  trials, the software-control test method and remaining evidence limits.
  Hosted-check approval is the remaining integration gate. No tag, release,
  version change or broader hardware-support claim is part of this work.

## 2026-09-19 — v1.0.3 battery tray patch candidate

- The live-approved horizontal battery tray artwork is integrated on `main`
  with rounded pixel-aligned geometry, proportional fill, the canonical OMUS
  purple gradient, transparent background, and a restrained low-battery outline.
- Desktop-panel acceptance confirmed the renderer itself displays correctly;
  DankMaterialShell tinting was the only interference and is external to OMUS.
- Battery polling, backend behavior, reconnect recovery, StatusNotifier
  registration, tooltip, DBusMenu, Ayatana label, and tray lifecycle remain
  unchanged. This patch does not expand hardware support or write authority.

## 2026-09-19 — v1.0.2 secure updater patch candidate

- The published v1.0.1 RPM redirects once from the canonical OMUS `github.com`
  release URL to the exact `release-assets.githubusercontent.com` host with
  ephemeral signed query parameters before returning the artifact.
- The updater now validates each redirect hop, permits only exact GitHub
  release infrastructure over HTTPS, bounds redirects, strips sensitive
  headers across origins, and retains canonical release and SHA-256 checks.
- DNF still runs once against configured repositories and falls back to the
  verified canonical release RPM only when the installed version remains old.
- This is a v1.0.2 patch candidate only; v1.0.1 was not mutated or retagged.

## 2026-09-19 — v1.0.1 final Python baseline release candidate

- The accepted motion-frame, wake/reconnect, physical G305, and whole-program
  audit commits are integrated linearly over public v1.0.0 and versioned as the
  next stabilization release, v1.0.1.
- Canonical Python, RPM, Debian, Arch, AppImage, README, changelog, and release-
  note version surfaces agree. Release notes scope the approximately 100,000-
  frame, approximately 993 Hz, 0.016 ms median, and ten-wake measurements to the
  exact G305/Fedora 44 acceptance system.
- The reviewed pip 26.2 lock update is included to address the repository's
  open pip advisories without importing stale pre-rebrand branch content.
- Local source and focused gates pass 1,178 and 282 tests respectively; the
  Fedora RPM `%check` passes 1,178 tests and installed-file inspection confirms
  the OMUS desktop, icon, executable, service, package, and version identity.
- The canonical final Python behavioral baseline is the annotated `v1.0.1` tag
  and the exact commit to which that tag resolves. Rust work remains separate
  and has not begun.

## 2026-09-19 — Final pre-Rust whole-system audit candidate

- The complete runtime/background/security/compatibility inventory found no
  additional proven production defect after the motion-frame and wake-path
  corrections. No speculative rewrite or supported feature removal was made.
- The Python behavior is recorded as the Rust migration oracle in
  `docs/PRE_RUST_QUALITY_AUDIT.md`, including input framing, ownership, failure
  isolation, security, lifecycle, resource, compatibility, and physical
  acceptance requirements.
- Focused lifecycle/input/hardware/service coverage passes 164 tests. Current
  500-round benchmarks remain aligned with the established performance
  baseline: 15.981 ms cold app import, 0.034 ms known-device restore, 0.435 ms
  explicit Rediscover, and 28.772 ms per 1,000 HID decodes.
- The complete gate passes: `git diff --check`, compileall, and 1,178 tests
  with one external GLib deprecation warning.

## 2026-09-19 — G305 physical motion/wake acceptance

- Operator-provided Fedora 44 evidence from the exact stabilization commit
  physically validates workloads A/B/C and a ten-cycle genuine G305 wake soak.
- Across 99,932 physical motion frames and 160,291 motion events, virtual counts
  matched exactly with zero loss, duplication, modification, ordering,
  coalescing, framing, `SYN_DROPPED`, batching, or latency-spike findings.
- Ten wake trials recovered first virtual input in 0.086–0.207 ms (median
  0.129 ms) with motion transparency retained. Native polling mode was
  preserved and 3000 DPI reconciliation succeeded through the Native HID
  adapter. Scope remains the exact Logitech G305 reference device.

## 2026-09-19 — Motion-frame transparency correction

- The production remapper now buffers each physical evdev frame and emits one
  virtual synchronization only at the corresponding `SYN_REPORT`; ordered
  `REL_X`/`REL_Y` values and remapped buttons remain inside that frame.
- `SYN_DROPPED` discards the incomplete frame and all input through the recovery
  `SYN_REPORT`, invalidates observer continuity, cancels macros, and releases
  tracked synthetic keys/buttons before normal framed forwarding resumes.
- Input recovery and optional hardware-management readiness are now independent.
  DPI/battery retry state cannot mark healthy evdev input unavailable or wake a
  management retry on every rapid motion event. Slow backend discovery,
  reconciliation, and DPI cycling no longer hold the ordinary pointer path.
- A production-path, read-only diagnostic records exact physical and virtual
  motion frames, loss/duplication/modification/order/framing metrics, effective
  rates, separate first-input/full-ready wake times, and latency distributions
  without changing hardware authority.
- Automated validation passes 1,178 tests, including a deterministic ten-cycle
  ENODEV/node-renumbering soak with immediate XY and remapped-button input.
  Physical G305 workloads and ten natural sleep/wake cycles remain pending
  because the environment exposes no `/dev/input` or USB device access.

## 2026-09-19 — OMUS v1.0.0 rebrand candidate

- Public identity is OMUS (One Mouse Universal System), with canonical `omus`
  and `omus-launcher` entry points and the tagline “Every mouse. One system.”
- The `mouse-control` entry point and `mouse_control` Python namespace remain
  compatibility surfaces backed by the same application dispatcher.
- Config, data, and cache state migrate by atomic copy into XDG `omus`
  directories only when the canonical directory is absent. Legacy state is
  retained; existing canonical state wins; repeated startup is idempotent.
- The canonical user unit is `omus.service`. Installation disables/stops the
  legacy unit before enabling OMUS, preventing duplicate evdev/HID ownership.
- RPM/DEB package transitions provide/replace the old package identity, and the
  updater accepts both v0.9.9-era and OMUS v1.0.0 artifact names from the
  canonical `DonGeronimo7/OMUS` endpoint.
- The approved transparent Omega/mouse PNG is packaged as `omus` at 16, 24,
  32, 48, 64, 128, 256, and 512 pixels with true RGBA alpha.
- Automated validation passes 1,153 tests. Wheel/sdist and Fedora RPM builds,
  RPM `%check`, installed wheel command smoke tests, desktop validation, and
  AppStream validation pass. Debian/AppImage tools are unavailable locally.
- No HID/discovery/remapping architecture or hardware write authority changed.

## 2026-09-19 — v0.9.9 release candidate

- Canonical release metadata now targets v0.9.9 and documents the accepted TUI,
  updater, service, CLI-parity, and safe multi-zone lighting work.
- A dedicated release-published workflow scans exactly the RPM, DEB, AppImage,
  wheel, and source archive through `cssnr/virustotal-action` v2.0.0 pinned to
  immutable commit `5edfa4c982eb0caec6d568ea27cf715269f5c23b` at four uploads per
  minute. It excludes checksums, SBOM, and provenance material.
- Repository-owned follow-up verification waits for each analysis, preserves
  filename, SHA-256, detection counts, and direct links in release notes, and
  fails on any malicious or suspicious result. The README badge reports only
  workflow status; VirusTotal remains a point-in-time signal, not certification.
- The release retains the existing exact-hardware proof gates. New sourced
  lighting families remain write-disabled and are not physically validated.

## 2026-09-19 — Parallel pre-v1 TUI updater reconciliation

- Reconciled the dedicated updater work at `d3bb3bb` into the broader canonical
  TUI at `bd22e15` without merging or cherry-picking either implementation.
  The unified controller, Updates screen, navigation, Lighting, Tools / Advanced,
  About, Service controls, and capability-parity inventory remain authoritative.
- The updater now owns the structured installed/latest/installation-policy
  result used by the TUI. Source checkouts, unknown/package-source installs, and
  incompatible AppImages are represented honestly and cannot expose an update
  action. RPM, DEB, AppImage, and pip continue through their existing updater
  paths; checksums, trusted origins, package ownership, approval, and service
  restoration remain in `updater.py`.
- Entering, redrawing, backing out of, or cancelling the Updates screen performs
  no network or updater operation. A check occurs only from its explicit action,
  and updater UI status remains independent of configuration choices and Review /
  Save. The update action uses the existing updater with interactive approval
  semantics and temporarily leaves curses so package-manager interaction remains
  usable.
- Focused validation passed 218 updater/TUI/navigation tests, 64 lighting tests,
  143 service/lifecycle tests, and 74 packaging/entry-point tests. The complete
  suite and Fedora RPM `%check` each passed 1131 tests with the existing GLib
  warning. Compileall, whitespace, workflow policy, wheel/sdist, RPM, and
  packaged-command smoke checks passed. No host installation, push, merge, tag,
  release, or physical hardware validation occurred.

## 2026-09-18 — Post-v0.9.8 canonical TUI and lighting foundation

- The canonical TUI now includes dedicated Lighting, Updates, Tools / Advanced,
  About, and complete service-control surfaces. A checked-in product capability
  inventory maps every public `mouse-control` command and installed research
  entry point to its TUI route and shared implementation; regression coverage
  prevents new top-level CLI commands from silently becoming TUI-only gaps.
- Lighting is an optional protocol-neutral capability with multiple zones,
  native Off/Static/Breathing/Spectrum modes, RGB24 `#RRGGBB`, brightness,
  speed, per-mode persistence vocabulary, readback, and lighting-only versus
  shared-device-config write scope. Existing configurations load unchanged.
- Shared-device-config lighting is refused unless an exact backend explicitly
  proves trustworthy baseline-preserving RMW. Volatile state is reconciled once
  per live backend and after a genuine rebind; lighting failures remain isolated
  from DPI, polling, remapping, buttons, battery, and service health.
- OpenRGB-derived lighting facts are retained as source-backed, exact-fingerprint
  knowledge with runtime writes disabled. The post-v0.9.8 audit records the
  status and remaining hardware gate for every requested research family; no
  new HID write path or support claim was created.
- Automated validation passed 1122 tests with the existing GLib warning,
  compileall, and whitespace checks. Wheel/sdist and installed-wheel smoke
  validation passed; the final Fedora RPM and `%check` passed all 1122 tests
  plus packaged command smoke checks.
  Debian and AppImage build tools were unavailable locally; their launcher and
  packaging structure remain covered by the full suite. Physical lighting and
  device acceptance remain pending.

## 2026-09-19 — OpenSSF Scorecard maximum hardening

- All Python workflow environments now use separate reviewed inputs and exact,
  SHA-256-checked transitive locks. CI, audit, build, SBOM, release, AppImage,
  and fuzz paths install with hash enforcement and local artifacts use
  dependency-free installation only after the lock is present.
- ClusterFuzzLite now continuously exercises the bounded HID descriptor/report
  and offline vendor-capture parsers. Its builder image is digest-pinned, its
  Actions are full-SHA pinned, and both real Atheris targets built and passed
  100-run libFuzzer smokes without hardware, network, persistence, or writes.
- Future releases export and verify genuine GitHub/Sigstore SLSA provenance as
  a downloadable release asset. The original v0.9.8 provenance was verified
  against every exact checksum-listed artifact and published; older releases
  lacked original attestation records and remain untouched.
- Security reporting, development/change control, regression-test rules,
  dependency maintenance, and Best Practices evidence are now explicit.
  External badge enrollment, PyPI ownership, branch protection, and repository
  security toggles remain separate owner-verifiable controls.
- Locked CI validation passed 1101 tests, Ruff, workflow/lock validation,
  compilation, and whitespace checks. The clean Fedora RPM `%check` also passed
  1101 tests plus packaged CLI smokes; wheel reproducibility, clean wheel/sdist
  builds, and dependency audit passed. No runtime or hardware path changed, and
  no physical hardware validation was performed.

## 2026-09-18 — PR #6 clean-build and runtime-teardown remediation

- The no-isolation reproducibility environment now installs explicit pinned
  build backends: `setuptools==83.0.0` and `wheel==0.48.0`. The project build
  contract retains its distro-compatible minimum while a regression test keeps
  the clean CI environment synchronized with both required backend packages.
- Runtime teardown now sets the shared shutdown event before moving the wake
  coordinator to `STOPPING`. Coordinator stop notifications are not reported as
  wake evidence, late activity cannot revive a stopped coordinator, and DPI and
  battery retry loops treat `STOPPING` as terminal before backend rebind.
- Regression coverage proves teardown performs no backend reselection and no
  repeated DPI or polling reconciliation writes, both monitor loops exit
  promptly, and real matching device-return evidence still cancels long
  reconnect backoff. The three race-sensitive runtime cases passed 50 repeated
  iterations each.
- Focused lifecycle/wake/hardware/notification coverage passed 114 tests; the
  full suite passed 1086 tests with the existing GLib warning. Compileall,
  Ruff, workflow validation, dependency audit, wheel reproducibility, clean
  no-isolation wheel/sdist builds, Fedora RPM build and `%check`, and
  whitespace checks passed. The source manifest includes the pinned requirement
  inputs required by package-level metadata tests. No physical hardware test,
  merge, tag, release, or `main` modification occurred.

## 2026-09-18 — Pre-v1 repository and release supply-chain hardening

- GitHub workflows now default to read-only permissions; the only job-scoped
  writes are the exact CodeQL/Scorecard SARIF, tag, dispatch, and release OIDC/
  attestation/publication capabilities that need them. A repository-owned
  validator rejects mutable remote Actions, broad or unallowlisted writes,
  malformed workflow YAML, unsafe event interpolation, and incomplete security
  workflow/Dependabot configuration.
- Immutable-SHA CodeQL v4 `security-extended`, OpenSSF Scorecard publication,
  resolved-environment `pip-audit`, and low-noise monthly Dependabot workflows
  cover Python and GitHub Actions dependencies. Ruff enforces a deliberately
  narrow correctness-oriented rule set without formatting or hardware changes.
- Releases retain the five-artifact allowlist and SHA256SUMS, add a reproducible
  CycloneDX 1.6 project dependency SBOM, and use keyless GitHub attestations to
  bind provenance to the exact wheel, sdist, RPM, DEB, AppImage, and SBOM bytes
  and bind that SBOM to the five primary artifacts before publication.
- Two clean source-snapshot wheel builds were byte-identical. Sdist byte
  reproducibility remains deferred because setuptools-generated directory and
  metadata mtimes vary; RPM/DEB/AppImage reproducibility and an artifact-
  filesystem AppImage SBOM remain separate future work rather than unsupported
  claims.
- Automated validation passed 1082 tests with the existing GLib warning,
  compileall, Ruff, workflow-policy validation, dependency audit, and diff
  checks. Wheel/sdist, isolated wheel, Fedora RPM, Debian, and AppImage builds
  and packaged CLI smoke checks passed. Two already-documented threaded retry
  assertions each passed immediately in isolation before the clean full rerun.
- No runtime, hardware, Discovery, TUI, remapping, reconnect, wake, notification,
  persistence, protocol, or write-authority behavior changed. Cloud CodeQL,
  Scorecard publication, first-release attestations, and Best Practices owner
  enrollment remain pending; no push, merge, tag, release, install on the host,
  or physical hardware validation occurred.

## 2026-09-18 — Event-driven wireless wake stabilization

- The resident runtime now shares a Linux event-driven wake coordinator across
  evdev remapping, the hardware supervisor, DPI events, and battery refresh.
  Exact VID:PID kernel/udev add/change evidence cancels reconnect backoff;
  mismatched identities only remain ordinary unrelated system events.
- A receiver that remains enumerated retains its existing readers, backend,
  protocol, capabilities, proof, desired state, and routing. Its first valid
  evdev or HID report follows the existing kernel-blocking reader path without
  discovery or backend reconstruction. A true node return still passes through
  the established stable-identity resolver, adapter-affinity checks, generation
  guard, and current interface/evidence validation before replacement.
- Wake instrumentation records monotonic T0 (first matching Linux event/input),
  T1 (recognized), T2 (backend usable), and T3 (runtime event handled), logs
  each completed sample, and reports bounded repeated-trial minimum, median,
  p95, and maximum statistics at runtime shutdown.
- Deterministic tests cover retained-session wake, exact/mismatched device
  events, cancellation of a simulated 60-second reconnect delay, ordered
  latency statistics, event-driven shutdown, and no backend factory call on an
  ordinary known-device wake. The wider reconnect/discovery/remapping/
  notification/security set passed 123 tests; the complete suite passed 982
  tests with the existing GLib warning. Compileall and whitespace checks
  passed. Physical latency and first-click/motion acceptance on an actually
  sleeping wireless mouse remain pending.

## 2026-09-18 — Canonical TUI presentation and stabilization milestone

- The existing curses setup application now uses a shared presentation model
  for full/compact/minimum layouts, focus-preserving viewports, wrapped text,
  semantic status labels, contextual key guides, and long-screen scrolling.
  Normal terminals use a bordered dashboard/navigation rail; narrow terminals
  retain the same controller and actions through a compact breadcrumb layout.
- Device, capability, battery/power, button-mapping, Discovery Lab, vendor
  capture, review, service, and no-device states are presented through the same
  canonical TUI. Imported evidence and LAMZU/Aurora knowledge retain explicit
  recognized/vendor/unverified/read-only boundaries; no write authority was
  changed.
- Idle timeout wakes no longer repaint the screen. Curses updates are batched,
  the existing single initialization worker remains authoritative, and hardware
  reads such as the battery snapshot occur during worker-owned initialization,
  never in the redraw path.
- All installed/source/desktop/AppImage dispatch routes remain structurally
  converged on `mouse_control.app` and the canonical setup TUI. The no-device
  path now opens a safe empty state instead of falling back to line output.
- Automated validation at this checkpoint: the focused TUI/lifecycle/Lab/
  importer suite passed 153 tests; the complete suite passed 976 tests with the
  existing GLib warning; compileall and whitespace checks passed. Wheel, sdist,
  isolated-wheel, and Fedora RPM builds passed; RPM `%check` passed all 976
  tests and packaged command smoke checks. Debian/AppImage builders were not
  locally available, so their launcher structure was checked by tests.
- A live PTY probe in the available no-device environment reached its first
  usable Help response in 228.6 ms median / 232.2 ms p95 across 12 runs and
  emitted zero terminal bytes while consuming 0 ms sampled CPU over a settled
  three-second idle interval. Physical mouse acceptance remains pending.

## 2026-09-18 — Discovery Lab v1 Vendor Capture Importer

- Discovery Lab now has a generic, offline vendor-capture ingestion layer with
  adapter-based format detection/parsing, provenance-preserving normalization,
  deterministic manifests, deduplication, conflict retention, staged review,
  and content-addressed local persistence. V1 accepts canonical Mouse Control
  JSON and JSONL; raw PCAP/PCAPNG remains an adapter extension rather than an
  incomplete dependency claim.
- Normalized records retain raw frames, original lengths/sequences, timing and
  direction only when supplied, HID/USB channel metadata, transaction
  relationships, warnings, and source references. Unknown facts remain unknown.
  Imported evidence wraps existing `DiscoveryEvidence` and projects into the
  existing Lab observation, temporal dialogue, timing, pushed-state, routing,
  and power models where known grammar supports it.
- Source SHA-256, provenance category, optional vendor/device/family identity,
  dates, reference text, notes, parser version, review state, warnings, and
  conflicts are persisted locally by digest. Independent sources remain
  independent corroboration; temporal repetition is retained; contradictory
  meanings, identities, and report lengths force conflicted evidence rather
  than last-writer-wins behavior.
- The first end-to-end fixture is the existing LAMZU Aurora repertoire. It
  covers modern Feature-0 response alignment/status, Input-4 battery/DPI/
  polling/LOD/profile/connection/performance pushes, Power Investigator,
  routed VID/PID ambiguity, dangerous/unknown command suppression, bootloader
  refusal, and the separate legacy report-8 family without duplicating the
  Aurora protocol module.
- Import status is `IMPORTED_UNREVIEWED`, `ACCEPTED`, or `REJECTED`. Even
  accepted records remain no stronger than `OBSERVED`/`DECODED`; imports cannot
  create experiments, `PROVEN` capabilities, setters, wider parameter ranges,
  permissive `WriteScope`, routing certainty, or write authority.
- Parsing is bounded for bytes, record count, frame length, nesting, node count,
  timestamps, byte values, and content-addressed output paths. It is local-only,
  executes no imported code, performs no network activity, opens no hardware,
  and has no packet replay or HID write primitive.
- Validation at this checkpoint: the focused importer/evidence/persistence/
  grammar/temporal/routing/Lab/TUI/security/Aurora/power suite passed `238`
  tests; the full suite passed `966` tests with one existing GLib deprecation
  warning; `compileall` and `git diff --check` passed. LAMZU Thorn V2 physical
  validation remains `UNVERIFIED — NEEDS PHYSICAL TEST`.

## 2026-09-18 — LAMZU Aurora protocol-family knowledge milestone

- Automatic Discovery now treats current LAMZU/Aurora as a declarative family:
  64-byte Feature Report 0 control framing, sibling Input Report 4 events,
  vendor-observed 0/1 response alignment, status/poll/resend bounds, command
  recipes, model catalog, dependencies, and explicit provenance. The separate
  VID `3554` report-8/16-byte/checksum/flash-layout generation remains a distinct
  family and cannot collide with the modern grammar.
- Thorn, Thorn V2, and 54H20 wired/wireless/receiver identities are retained as
  vendor-declared model knowledge. USB receiver `0032` and routed/internal
  identity `002e` remain separate and ambiguous until physical routing evidence
  resolves them. Known mouse/receiver DFU identities are filtered from normal
  selection and refused again at the Discovery boundary.
- Vendor operations cover global state, battery, profile, sleep/debounce,
  polling, DPI/XY, LOD, sensor model, Angle Tune/snapping, Motion Sync, ripple,
  performance/20K, indicators, buttons, macros, Rapid Trigger, Scroll Bhop, and
  routed identity. They are descriptive encoders/decoders only. No operation is
  eligible for an automatic hardware request and both families use
  `WriteScope.NEVER`.
- Sensor codes 1/2/4, fine LOD, signed Angle Tune, BE16 fields, independent
  Rapid Trigger buttons, Scroll Bhop modes/windows, and the Competition→20K
  dependency are represented from vendor evidence. Catalog 50K/5-stage/8K
  claims remain unverified rather than becoming capabilities.
- Input Report 4 events project into the existing pushed-state model. Battery
  percent/charging events feed the existing Power Investigator, preserving raw
  100% while charging, freshness, stale-read replacement, route evidence, and
  contradictions. Routed VID/PID replies create only candidate/ambiguous
  Routing Mapper evidence and never prove ownership.
- Factory/profile reset, identity/descriptor writes, pairing, DFU, erase,
  firmware control, arbitrary targets, and unknown commands are explicit
  `DO_NOT_PROBE` knowledge. Aurora vendor facts cannot authorize writes or
  bypass per-operation exact-hardware proof.
- Validation at this checkpoint: the focused Lab/discovery/protocol/TUI/security
  suite passed `278` tests; the full suite passed `934` tests with one existing
  GLib deprecation warning; `compileall` and `git diff --check` passed. Physical
  validation remains `UNVERIFIED — NEEDS PHYSICAL TEST`.

## 2026-09-18 — Discovery Lab battery/charging/power-state milestone

- `LabExperiment` now retains canonical power evidence with raw and decoded
  values, candidate semantics, explicit units only when proven, charging/source/
  battery states, freshness, cadence, routed owner, confidence, proof state,
  contradictions, and narrowly scoped cross-session provenance.
- A value in `0..100` remains only a percentage candidate. Promotion requires
  known protocol semantics, independent agreement, or repeated directional
  evidence at distinct levels. Unknown buckets and voltage-like values retain
  their exact representation without an invented percentage conversion.
- Repeated controlled cable transitions can correlate a binary charging field;
  the cable action alone never labels arbitrary changing bytes. Explicit
  charging, external-power, full, low-battery, stale/fresh, and mouse-versus-
  receiver evidence remain separate, and conflicting sources are not averaged.
- Slow battery trends may accumulate across sessions only for the same exact
  device-unique identity. When immediate evidence is insufficient, the planner
  prefers one charging transition or a mouse-only power-cycle cache check and
  otherwise leaves a passive candidate pending rather than asking the user to
  drain the battery.
- The existing orchestrator invokes the investigator after differential and
  routing analysis when plans, semantic state, routed namespaces, or periodic
  status evidence suggest power telemetry. The Lab page presents battery/power state,
  confidence context, cadence, contradictions, passive follow-up, and the next
  bounded experiment. Replay hashes source/owner identifiers and retains only
  scoped power/protocol facts.
- Focused Lab/discovery/protocol/TUI/security validation passes 232 tests; the
  complete suite passes 905 with the existing GLib warning. Compileall and diff
  checks pass. Physical hardware validation and passive runtime persistence
  remain pending. No hardware write, forced discharge, network activity,
  install, push, merge, tag, or release occurred.

## 2026-09-18 — Discovery Lab receiver/child routing milestone

- `LabExperiment` now retains canonical generation-bound routing evidence and a
  derived receiver/child graph. Physical receiver identity, logical child
  candidates, receiver-local ownership, interfaces, endpoints, channels,
  namespaces, reports, record types, internal targets, and asymmetric routes
  remain distinct.
- Target-field inference requires repeated controlled cross-child contrast.
  Constant bytes are not treated as device IDs, indistinguishable children stay
  ambiguous, and selected-device USB routes without child evidence stay
  explicitly unmapped. Unrelated physical fingerprints are excluded.
- Existing dialogue and pushed-state associations map cross-interface request/
  response and asynchronous routes without requiring transport symmetry.
  Repeated timing may strengthen an existing correlation but cannot establish
  ownership by itself. Every routing analysis first feeds the Differential
  Analyzer.
- Route graphs support one or many children, many interfaces per child, shared
  interfaces, receiver-local namespaces, and shared VID:PID with observed
  internal targets. Old-generation routes are never carried forward; explicit
  rediscovery comparison reports stable, remapped, missing, and new routes.
- Ambiguity produces a bounded other-child control, repeated selected-child
  action, or mouse-only power-cycle plan through the existing information-gain
  and human-cost machinery. Persistence evidence may support a route candidate
  but never proves ownership or storage location by itself.
- Focused Lab/discovery/protocol/TUI/security validation passes 123 tests; the
  complete suite passes 889 with the existing GLib warning. Compileall and diff
  checks pass. Physical hardware validation remains pending. No hardware write,
  slot scan, routing probe, install, push, merge, tag, or release occurred.

## 2026-09-18 — Discovery Lab state/effect/persistence verification milestone

- `LabExperiment` now retains canonical effect evidence, cross-generation
  persistence evidence, restoration requirements, and a derived persistence
  assessment. Accepted requests, reported state, fresh/stale state, independent
  physical effect, reversion, and unknown effect remain distinct.
- The verifier implements a conservative seven-level evidence ladder from
  immediate effect through idle, fresh reread, device reconnect, receiver
  reconnect, power cycle, and host/session restart. Stronger persistence is
  never inferred from a weaker checkpoint; stale post-reconnect state cannot
  prove survival.
- Protocol/physical disagreement, stale/fresh disagreement, automatic
  reversion, and vendor/physical contradiction remain explicit. Commit/apply
  and volatile-until-commit evidence can be identified without inventing or
  executing an unknown commit command.
- Power-cycle evidence may support device storage; observed host reapplication
  supports host storage; host restart alone leaves storage location unknown.
  Cross-generation state comparison is allowed only through persistence
  evidence while protocol dialogue remains generation-isolated.
- Persistence uncertainty produces bounded idle, reread, reconnect, receiver-
  reconnect, or power-cycle plans through the existing information-gain and
  human-cost planner. Disruptive testing can stop on user refusal or insufficient
  value. Original-state restoration remains manual unless separately authorized.
- Focused Lab/discovery/protocol/TUI/security validation passes 140 tests; the
  complete suite passes 876 with the existing GLib warning. Compileall and diff
  checks pass. Physical hardware validation remains pending. No hardware write,
  install, push, merge, tag, or release occurred.

## 2026-09-18 — Discovery Lab controlled-action orchestration milestone

- The Lab now models all supported physical, passive, external-vendor,
  bounded-engine, and unavailable action classes. Eight initial templates cover
  quiet, movement, generic buttons, one/multiple DPI stages, reconnect,
  charging, and vendor-setting demonstrations.
- `LabExperimentPlan` selects the safest maximum-information action, instruments,
  bounded repeat count, semantic negative control, timing-derived observation
  windows, success/stop criteria, and minimum human instruction. Equal-value
  actions are ordered by physical effort, duration, risk, equipment, and repeat
  burden. Bounded engine actions remain excluded without separate authority.
- Execution is event-driven and feeds every completed plan into the existing
  Differential Analyzer. Hypotheses retain strengthened, supported, weakened,
  rejected, conflicted, or unresolved outcomes and negative evidence. An
  unresolved result retains the recalculated next plan; resolved, conflicted,
  cancelled, and no-safe-action outcomes retain explicit stop reasons.
- DPI and polling ambiguity automatically select and invoke the existing
  independent physical CPI and polling verifiers in the TUI. Timing profiles
  determine bounded capture/settling windows when available; conservative
  defaults explicitly retain uncertainty otherwise.
- Focused Lab/protocol/TUI/measurement/authority/security validation passes 122
  tests; the complete suite passes 858 with the existing GLib warning.
  Compileall and diff checks pass. Physical hardware validation remains pending.
  No hardware write, install, push, merge, tag, or release occurred.

## 2026-09-18 — Discovery Lab protocol timing profiler milestone

- `LabExperiment` now retains canonical timing observations and profiles derived
  from recorded timestamps. Evidence carries experiment/device/generation,
  source IDs, exact start/end/duration, relationship, interval/repeat,
  confidence/proof state, classification, and freshness where applicable.
- The profiler automatically extracts request/response and ACK latency,
  busy/poll cycles, existing burst timing and quiet completion, nudge/action/
  periodic pushed-state timing, stale-read settling windows, and explicit
  disconnect/reconnect/first-valid-state lifecycle timing. It never sleeps,
  captures, polls, or writes hardware.
- Repeated samples retain count/minimum/median/maximum/spread and MAD-based
  rejected outliers. Timing classes are contextual rather than universal
  millisecond thresholds; insufficient ordinary evidence remains `UNKNOWN`.
- Baseline/action timing distributions produce separately ranked timing deltas
  without assigning semantics. Timing uncertainty participates in the existing
  information-gain recommendation path, and the cohesive Lab screen renders
  normal-language timing summaries.
- Focused Lab/discovery/protocol/TUI/security validation passes 171 tests; the
  complete suite passes 849 with the existing GLib warning. No physical
  validation, runtime write, install, push, merge, tag, or release occurred.

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

## 2026-09-20 — runtime persistence stabilization candidate

The battery tray now owns a recoverable session-bus/watcher lifecycle, subscribes
to owner changes before initial registration, checks replies, and retains unknown
battery presentation during transient absence. No artwork or asset dependency
changed. Closed tray instances cannot be resurrected by late updates.

Initial native protocol failures remain pending even when a PROVEN learned
fallback is usable. The battery worker retries with capped backoff; equivalent
candidates are discarded before reconciliation, and matching live DPI/rate state
avoids redundant writes. Polling DPI fallback accepts readiness and returns on a
backend generation change so event monitoring can recover after promotion.

RPM/DEB ship graphical-session systemd integration and a configuration-aware XDG
login bootstrap. A kernel lock prevents duplicate `run` instances. The installed
RPM has been exercised on Fedora/niri/DMS; the exact evidence and remaining
reboot/physical acceptance gate are in `RUNTIME_PERSISTENCE_HANDOFF.md`.
Automated source and RPM gates pass 1,217 tests. No new write authority, generic
HID write, udev scope, updater policy, or physical hardware support is claimed.


## 2026-09-20 — hardware-authoritative DPI correctness checkpoint

Runtime now reads live DPI silently instead of restoring/assuming persisted
active DPI. Native stage reports observe hardware without a second software
cycle. Confirmed setter results are reused; failed/unchanged writes cannot report
requested DPI as success. Learned read errors no longer promote stale cached
state. Generation/wake changes invalidate the cursor, and unchanged tray
snapshots reuse artwork. Source and RPM gates pass 1,234 tests.

The corrected local RPM is installed; G305 transaction median remains 19.99 ms
with two HID transactions, and service restart preserves 3000 DPI. The user
reported notification absence/delay during initial reconnect/startup; subsequent
notifications resume. The observed 16-second management recovery remains a
performance acceptance issue under investigation. See `DPI_TRUTH_HANDOFF.md`.


## 2026-09-20 — DPI recovery performance acceptance

Read-only receiver version probes now share one existing timeout window through
the sole HID reader, instead of waiting sequentially per slot. Every candidate
is still checked, ambiguous responders rejected, and feature IDs resolved through
ROOT; normal writes remain serialized and verified. Source and RPM: 1,244 passed
each. The updated local RPM is installed, without publication.

Installed startup reached remapping in 2,428 ms versus roughly 6,170 ms;
USB management recovery improved from 16,042 to 5,074 ms, with remapping at
109 ms. Synchronized cycles remain approximately 20 ms and two HID transactions.
The user confirmed timing/sensitivity agreement, and final USB testing showed two
matching five-stage sequences. Initial readiness still takes time; this is not
a guarantee of immediate notifications before hardware observation is ready.
Full evidence, validation limits, and Git checkpoints: `DPI_TRUTH_HANDOFF.md`.
