# Mouse Control v0.9.9

Mouse Control v0.9.9 completes the canonical full-screen product experience,
adds a conservative native-lighting foundation, and extends the hardened
release pipeline with point-in-time VirusTotal analysis of every primary
distributable.

## Complete canonical TUI

- The single canonical controller now includes dedicated Lighting, Updates,
  Tools / Advanced, About, and complete Service-control pages.
- A checked-in capability inventory enforces CLI/TUI parity while preserving
  installed research and expert workflows under Tools / Advanced.
- Update checks run only after an explicit action. RPM, DEB, AppImage, and pip
  reuse the existing updater, checksum, trusted-origin, package-ownership,
  approval, and service-restoration paths. Source, unknown, package-source, and
  incompatible AppImage installs are represented honestly and cannot expose an
  unsafe update action.

## Safe native-lighting architecture

- Optional per-device lighting supports multiple zones and native Off, Static,
  Breathing, and Spectrum modes, with RGB24 `#RRGGBB`, brightness, speed, and
  per-mode persistence vocabulary.
- Lighting failures remain independent from DPI, polling, remapping, buttons,
  battery, and service health. Volatile state is reconciled once per live
  backend and after a genuine rebind.
- Shared-device-config lighting is refused unless the exact backend proves a
  trustworthy baseline-preserving read/modify/write operation.
- Source-backed lighting protocol knowledge remains write-disabled. No newly
  sourced lighting family is claimed as physically validated, and unqualified
  lighting writes remain disabled.

## Retained discovery, reliability, and supply-chain protection

- Existing Automatic Discovery, protocol knowledge, native HID++, G305,
  remapping, reconnect, notifications, service lifecycle, updater, and
  PROVEN-only hardware-write behavior are retained.
- CodeQL, OpenSSF Scorecard, dependency auditing, immutable action pins,
  least-privilege permissions, workflow-policy checks, wheel reproducibility,
  exact artifact allowlists, `SHA256SUMS`, CycloneDX SBOM generation, and
  keyless GitHub provenance/SBOM attestations remain release gates.
- The five primary artifacts are submitted at four per minute through the
  immutable-pinned VirusTotal action. The follow-up verifier waits for completed
  analyses, records filename, SHA-256, detection counts, and direct report links
  in these release notes, and fails the scan workflow on any malicious or
  suspicious result. VirusTotal is a point-in-time signal, not certification.

## Validation boundary

The canonical TUI received user physical acceptance before this release. New
lighting families and their write behavior remain unverified on physical
hardware. Automated tests and hosted packaging checks do not broaden hardware
write authority.

## Downloads

- RPM: `mouse-control-0.9.9-1.fc44.noarch.rpm`
- DEB: `mouse-control_0.9.9_all.deb`
- AppImage: `Mouse-Control-0.9.9-x86_64.AppImage`
- Wheel: `mouse_control-0.9.9-py3-none-any.whl`
- Source: `mouse_control-0.9.9.tar.gz`
- CycloneDX SBOM: `mouse-control-0.9.9.cdx.json`
- Integrity manifest: `SHA256SUMS`

---
# Mouse Control v0.9.7-2

Accepted responsiveness revision for the canonical desktop-launched TUI. It
preserves Mouse Control's hardware authority and compatibility model while
moving live backend initialization behind the first complete device-selection
frame.

## Fast canonical launcher

- The real device-selection frame is shown before live backend, capability, and
  exact-evidence initialization. One owned non-daemon worker performs that
  unchanged work and is deterministically joined and cleaned up on every exit.
- Hardware-dependent navigation remains explicitly unavailable until
  initialization completes. Device selection, Help, resize, and Cancel remain
  responsive while it runs.
- Foreground service suspension is requested early but completed synchronously
  before any hardware session opens; unsaved exits retain the established
  external restoration behavior.
- Evdev discovery no longer opens each event node solely for prevalidation;
  normal candidate, capability, permission, stable-path, and Rediscover
  validation stay authoritative.

## Downloads

- RPM: `mouse-control-0.9.7-2.fc44.noarch.rpm`
- DEB: `mouse-control_0.9.7-2_all.deb`
- AppImage: `Mouse-Control-0.9.7-2-x86_64.AppImage`
- Wheel: `mouse_control-0.9.7.post2-py3-none-any.whl`
- Source: `mouse_control-0.9.7.post2.tar.gz`
- Integrity manifest: `SHA256SUMS`

---
# Mouse Control v0.9.7-1

Measured performance and updater-correctness release. It preserves Mouse
Control's behavior and hardware authority model while removing avoidable Python
startup, HID parsing/decoding, and idle UI work.

## Reliable foreground TUI lifecycle

- Foreground graphical and terminal sessions are externally supervised by a
  transient systemd user unit. A previously active background runtime is
  suspended while the canonical TUI owns the device and restored after Save,
  unsaved cancel, SIGTERM, or terminal disappearance.
- The persisted service preference remains distinct from temporary suspension;
  saving an explicit disable choice suppresses restoration as intended.
- The desktop entry launches the packaged `mouse-control-launcher`. It uses a
  valid user-configured terminal, an existing `xdg-terminal-exec`, or a
  dynamically discovered terminal emulator with the appropriate invocation.
  No terminal emulator or terminal-launch utility is a new package dependency.
- No alternate setup interface was added: graphical, terminal, AppImage, and
  source launches continue to use the same canonical full-screen TUI.

## Correct incremental RPM updates

- The release model now explicitly separates the GitHub/display tag, Python
  PEP 440 version, RPM Version and Release, distribution suffix, and architecture.
- The direct fallback accepts exactly one safe, version-exact, architecture-
  compatible RPM such as `mouse-control-0.9.7-1.fc44.noarch.rpm`.
- Official repository validation, DNF-first behavior, SHA-256 verification, DNF
  package ownership, and verified post-install version checks remain mandatory.
- Regression coverage includes the published `0.9.6` to `0.9.6-2` failure and
  verifies that the immediately previous updater recognizes this release name.

## Measured Python performance

- Cold `mouse_control.app` import fell from 113.328 ms to 15.471 ms (-86.3%).
- Immutable descriptor reuse reduced repeated parse work from 0.0209 ms to
  0.000140 ms (-99.3%).
- Cached descriptor field layouts reduced representative 1,000-report decode
  from 66.552 ms to 28.388 ms (-57.3%).
- Snapshot reuse reduced forced Rediscover from 0.577 ms to 0.411 ms (-28.8%).
- Event-driven UI queues reduced idle notifier CPU from 1.031 ms/s to 0.016
  ms/s and voluntary context switches from 20/s to 1/s in the same probe.
- Reconnect, Rediscover, and setup enter/exit retained-memory checks remain
  bounded across 1,000 post-warmup cycles.

## Safety and compatibility

Known devices still use exact physical identity and persisted PROVEN evidence;
explicit Rediscover still executes the complete discovery path. No hardware
write authority, generic-HID read-only boundary, updater validation, feature,
configuration behavior, or v0.8.2 compatibility requirement was removed.

## Downloads

- RPM: `mouse-control-0.9.7-1.fc44.noarch.rpm`
- DEB: `mouse-control_0.9.7-1_all.deb`
- AppImage: `Mouse-Control-0.9.7-1-x86_64.AppImage`
- Wheel: `mouse_control-0.9.7.post1-py3-none-any.whl`
- Source: `mouse_control-0.9.7.post1.tar.gz`
- Integrity manifest: `SHA256SUMS`

---
# Mouse Control v0.9.6-2

Small lifecycle bug-fix revision on top of v0.9.6.

## Lifecycle corrections

- Cancelling or otherwise leaving setup without saving now restores and verifies
  the background service when it was running before setup began. Hardware DPI
  rollback failure cannot suppress the service-restoration attempt, and a real
  restoration failure is reported as an error instead of false success.
- Setup now restores valid persisted discovery evidence through a cache-only,
  exact-device topology binding. Known configured mice enter configuration
  immediately without a deep Automatic Discovery transaction.
- Missing, corrupt, ambiguous, incompatible, or differently bound evidence
  continues to abstain and require discovery. Explicit Rediscover still forces
  the full discovery pipeline.
- No-argument launch, the desktop application launcher, `mouse-control setup`,
  and `mouse-control tui` all open the same full-screen TUI. The obsolete
  line-oriented launcher screen is not shipped.

## Safety and compatibility

No hardware write authority or identity rule was relaxed. Remapping, macros,
DPI/polling preferences, notifications, battery monitoring, reconnect behavior,
and the complete v0.9.6 security hardening remain unchanged.

## Downloads

- RPM: `mouse-control-0.9.6-2.fc44.noarch.rpm`
- DEB: `mouse-control_0.9.6-2_all.deb`
- AppImage: `Mouse-Control-0.9.6-2-x86_64.AppImage`
- Wheel: `mouse_control-0.9.6.post2-py3-none-any.whl`
- Source: `mouse_control-0.9.6.post2.tar.gz`
- Integrity manifest: `SHA256SUMS`

---
# Mouse Control v0.9.6

Security hardening release focused on update integrity, supply-chain
verification, least-privilege hardware access, privacy guarantees, and
defense-in-depth. The audit found no malware, backdoor, telemetry, credential
access, or data-exfiltration path.

## Security changes

- Direct GitHub RPM, DEB, and AppImage updates now require the exact selected
  artifact in a strict release `SHA256SUMS` manifest and verify SHA-256 before
  invoking a package manager or replacing an executable.
- The updater rejects malformed or duplicate manifests, unsafe names, missing
  or unexpected assets, wrong versions/architectures, untrusted redirects,
  symlinked AppImage targets, and target-identity races.
- Release Actions are pinned to immutable commits with least-privilege tokens.
  Release publication accepts exactly the five expected artifacts and publishes
  their SHA-256 manifest.
- AppImageKit and the portable CPython runtime are pinned and hash-verified
  before execution or extraction.
- User-service installation resolves and validates its executable, refuses a
  symlinked unit destination, writes atomically, and enables compatible systemd
  process hardening.

These changes are proactive hardening plus fixes for insufficient artifact
verification and build-input integrity. No evidence was found that the prior
paths had been maliciously exploited. Release checksums are bound to the
official GitHub release over HTTPS but are not independently signed.

## Compatibility

The v0.9.5 runtime, TUI, Automatic Discovery, macros, remapping, notifications,
DPI/polling control, reconnect behavior, packaging, and exact-model hardware
write policy are preserved. No new device-write authority is introduced.

## Downloads

- RPM: `mouse-control-0.9.6-1.fc44.noarch.rpm`
- DEB: `mouse-control_0.9.6-1_all.deb`
- AppImage: `Mouse-Control-0.9.6-x86_64.AppImage`
- Wheel: `mouse_control-0.9.6-py3-none-any.whl`
- Source: `mouse_control-0.9.6.tar.gz`
- Integrity manifest: `SHA256SUMS`

---
# Mouse Control v0.9.5

## Persistent Automatic Discovery

Mouse Control includes an evidence-driven automatic HID discovery engine
designed to learn unsupported gaming mice without requiring vendor-specific
Linux software. It correlates physical devices and HID interfaces, interprets
descriptors and observed reports, uses known protocol evidence where available,
and persists only proven device knowledge. Unknown-device inspection remains
read-only, and hardware writes still require independent PROVEN exact-model
authority.

Once a physical device has been successfully learned, Mouse Control reuses its
persisted proven knowledge instead of rediscovering it every launch. The fast
path validates stable model, transport, VID:PID, true instance identity when
available, and the exact responder interface against the freshly enumerated
device. Live `/dev` paths are rebound rather than treated as identity. Corrupt,
ambiguous, or changed records safely fall back instead of being trusted.

Use `mouse-control rediscover` when you intentionally want to replace the
persisted evidence for a device.

## Faster startup and interaction

- Known devices avoid repeated descriptor parsing, protocol detection,
  feature baselines, and learning work.
- Ordinary TUI/menu transitions perform no discovery work.
- Automatic Discovery reports real semantic progress while it is active and
  clears that progress cleanly on completion or failure.
- Reconnect logic remembers backend affinity: exact native adapters outrank
  PROVEN learned adapters, which outrank topology-only bindings. Partial
  enumeration no longer causes avoidable adapter thrash.
- Setup navigation is more responsive while retaining the existing safe
  hardware transaction boundaries.

## Vim-style TUI navigation

The existing arrow, Home/End, Enter, and Escape controls remain available.
The TUI also supports:

```text
h = left
j = down
k = up
l = right
g = first
G = last
```

## Basic software-input macros

Buttons can now run small ordered macros composed from the same keyboard-key,
keyboard-chord, and mouse-button actions used by ordinary remapping, with
optional explicit millisecond delays. The setup TUI can select an existing
macro or create and assign a basic one.

Macro playback uses the existing uinput output path, runs outside the input
loop, and is interrupted on disconnect or shutdown. Synthetic keys and buttons
are released after each step and during cleanup, including failure paths.
Macros are deliberately not a scripting engine: there is no command execution,
Python, recording, looping, branching, application awareness, or
hardware-protocol access.

Example configuration:

```toml
[macros]
copy_paste = [
  { type = "chord", value = "KEY_LEFTCTRL+KEY_C" },
  { type = "delay", milliseconds = 100 },
  { type = "chord", value = "KEY_LEFTCTRL+KEY_V" },
]

[remap]
BTN_EXTRA = "macro:copy_paste"
```

## Compatibility and safety

This release preserves the complete v0.8.2 behavior contract and the existing
v0.9.x Automatic Discovery, remapping, DPI, polling, notification, HID++,
learned-operation, reconnect, setup, service, and updater paths. Optional
hardware discovery/control failures still cannot prevent ordinary remapping
from starting.

Generic HID discovery remains read-only. Persistent evidence never turns a
read-side observation into write authority, and macros are software input only;
they cannot invoke hardware operations.

## Known limitations

- Some mice expose no usable host-visible DPI state or safe control and remain
  remapping-only.
- New or changed hardware may need an explicit discovery pass.
- Macro timing is intended for ordinary human-scale sequences, not
  high-resolution real-time guarantees.
- Macro steps are sequential taps plus delays; held-step scripting, loops,
  conditions, recording, and application-aware behavior are intentionally out
  of scope.
- G305 physical evidence applies only to the tested Logitech G305 path and does
  not imply universal Logitech support.

## Downloads

- [RPM: mouse-control-0.9.5-1.fc44.noarch.rpm](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.5/mouse-control-0.9.5-1.fc44.noarch.rpm)
- [DEB: mouse-control_0.9.5-1_all.deb](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.5/mouse-control_0.9.5-1_all.deb)
- [AppImage: Mouse-Control-0.9.5-x86_64.AppImage](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.5/Mouse-Control-0.9.5-x86_64.AppImage)
- [Wheel: mouse_control-0.9.5-py3-none-any.whl](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.5/mouse_control-0.9.5-py3-none-any.whl)
- [Source: mouse_control-0.9.5.tar.gz](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.5/mouse_control-0.9.5.tar.gz)


---
# Mouse Control v0.9.4

## Pre-v1 discovery architecture milestone

Mouse Control 0.9.4 establishes the final major discovery-architecture layer
planned before v1 qualification work becomes primarily a matter of community
evidence and protocol recipes. It adds bounded temporal dialogue assembly,
operation-specific proof states, conservative experiment eligibility,
dependent-field inference, and a deterministic privacy-conscious community
report while preserving the mature v0.8.2/v0.9.3 runtime contract and the
current full-screen setup TUI.

The release path is now integrated rather than merely colocated: canonical
trace evidence flows through temporal dialogue assembly, dependency inference,
structural and semantic family recognition, operation-scoped proof, and a
privacy-filtered community report. The automated BITMOUSE-style acceptance
fixture demonstrates that complete chain while keeping recognition distinct
from PROVEN runtime write authority.

## Installed CPI measurement

Physical ruler calibration is available from every installed artifact as
`mouse-control cpi`. It measures CPI and observed polling directly from Linux
evdev motion, performs repeated-pass consistency and outlier checks, and can
compare against an optional configured DPI label without using that label in
the calculation. Automatic Discovery and qualification flows call the same
installed Python implementation directly; no source-tree script or subprocess
coupling is required. Mouse Control does not install `mouse-dpi-tool`, avoiding
a command-name conflict with libevdev.

## Evidence fidelity and transaction safety

- Canonical usbmon observations retain optional setup/data flags, interval,
  start frame, transfer flags, descriptor count, source representation, header
  availability, loss information, timebase, and completeness/truncation status.
- Operation evidence independently records transport acceptance, protocol
  response validity, readable-state change, physical effect, reconnect and
  power-cycle persistence, failure side effects, and recovery evidence. Unknown
  facts remain unknown rather than becoming false.
- Failed mutating steps that may have changed device state are not automatically
  resent. The transaction outcome carries retry, recovery, expected-disconnect,
  and connection-generation facts so callers can inspect and recover first.

## Semantic recognition and reports

The passive BITMOUSE-style discriminator requires compatible descriptor shape
plus the asymmetric `0x72` request/reply grammar, leading request checksum,
target and sequence correlation, and declared semantic response length. Bytes
after that declared length are excluded from evidence. Community evidence keeps
safe descriptor/report structure, dialogue relationships, dependencies,
candidate discriminators, connection generation, provenance IDs, and the next
safe observation recipe while recursively redacting path- and identity-bearing
material.

For the physically validated G305 acceptance path, the teacher-free runtime can
rebind the exact persisted descriptor member and recognize the configured DPI
cycle `800 → 1500 → 2000 → 2500 → 3000 → 800`. Those confirmed read-side states
flow through the existing `DpiState` and desktop-notification path with the
native/vendor backend bypassed and generic writes disabled.

## Proven learned transactions

Automatic Discovery can execute an exact-model learned raw-HID transaction only
after its write semantics have been independently promoted to PROVEN under the
existing policy. The validated G305 acceptance path uses the shared transaction
engine, exact write readback, and a matching independent learned read query.
This is separate from production native Logitech HID++, which remains the
preferred backend for known Logitech hardware.

## Reconnect and notification continuity

Descriptor-backed profiles do not persist `/dev/hidrawN` as identity. After a
disconnect, Mouse Control rediscovers the same unambiguous physical device,
reparses the live replacement descriptor, and rebinds the exact saved semantic
member. Each replacement watcher establishes a silent RESYNC baseline before it
enters LIVE notification handling; retired generations cannot emit late events.
Malformed, changed, or ambiguous replacement identity is refused rather than
falling back to a raw byte.

## Safety and conservative unknown-device handling

- Unknown HID discovery is read-only.
- Writes require independently validated, PROVEN, exact-model semantics.
- Mouse Control does not blindly probe arbitrary HID writes or borrow packets
  from another device family.
- Unsupported devices remain remapping-only instead of receiving guessed DPI or
  polling behavior.
- Missing optional hardware control never prevents ordinary evdev/uinput
  remapping from starting.

The SIGMACHIP `1c4f:0048` generalization experiment correctly found ordinary
mouse traffic but no action-specific DPI evidence and no write semantics. The
result remained unsupported rather than being converted into a capability
claim.

## Compatibility

The v0.9.4 release retains native HID++ production behavior, native exact-model Razer support,
configured DPI stages and software cycling, polling safety policy, one popup per
real transition, remapping and keyboard chords, reconnect and late insertion,
configuration preservation, user-service behavior, and the v0.9.1 TUI flow.
The complete v0.8.2 stability and functionality contract remains the baseline.

## Known limitations

- Some mice expose no host-visible DPI state or control and remain remapping-only.
- New hardware may require an explicit learning/discovery pass.
- Write semantics require strong independent evidence; read-side correlation
  alone never grants write authority.
- Automatic Discovery cannot manufacture protocol information that a device
  does not expose.
- G305 is a hardware validation target for both native HID++ production and
  learned acceptance; that evidence does not imply universal automatic support
  for every mouse.
- BITMOUSE-style coverage in this release is source-derived automated semantic
  evidence only. It does not provide a production runtime writer or hardware
  qualification for that family.

## Downloads

- [RPM: mouse-control-0.9.4-1.fc44.noarch.rpm](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.4/mouse-control-0.9.4-1.fc44.noarch.rpm)
- [DEB: mouse-control_0.9.4-1_all.deb](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.4/mouse-control_0.9.4-1_all.deb)
- [AppImage: Mouse-Control-0.9.4-x86_64.AppImage](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.4/Mouse-Control-0.9.4-x86_64.AppImage)
- [Wheel: mouse_control-0.9.4-py3-none-any.whl](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.4/mouse_control-0.9.4-py3-none-any.whl)
- [Source: mouse_control-0.9.4.tar.gz](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.4/mouse_control-0.9.4.tar.gz)

---
# Mouse Control v0.9.1

## Setup that hides the protocol machinery

Mouse Control 0.9.1 turns the existing setup flow into a full-screen,
keyboard-driven terminal interface. Device selection, hardware capability
status, button mappings, DPI, polling, service behavior, and final review are
revisitable without exposing HID internals to ordinary users.

Unknown mice now enter the existing Automatic Discovery workflow directly from
`mouse-control setup`. Passive discovery runs first. When DPI behavior is still
unknown, setup can guide the same safe five-sample observation workflow used by
the advanced discovery CLI: quiet control, normal-use control, and three DPI
button samples. The discovery CLI remains available for developers and hardware
acceptance work.

## DPI configuration

DPI editing now separates **testing** from **accepting**. A candidate can be
applied to the live mouse and moved around with before it changes the staged
configuration. `Set to current` can capture the mouse's current verified DPI,
including a value selected with the physical DPI button. Only an explicit
Accept changes the setup stage. Back/Cancel restores the hardware DPI that was
active when the editor opened and leaves the staged configuration untouched.

## Safety remains unchanged

Guided discovery begins read-only. Observation, descriptor similarity,
VID/PID similarity, protocol-family resemblance, and known-device evidence do
not grant write authority. Writable DPI or polling support still requires the
existing exact-model PROVEN path, reversible proof, readback, physical
verification where required, rollback, unambiguous identity, and safe control
ownership. No speculative generic polling writer was added.

Ordinary evdev/uinput remapping remains fully usable when DPI or polling is not
yet learned.

## Other v0.9.1 UX fixes

- Interactive updater confirmations are visible again instead of waiting on an
  unseen package-manager prompt.
- Keyboard shortcut capture exclusively grabs the selected keyboard while the
  capture is active, preventing the shortcut from leaking into the desktop.
- Terminal setup uses the standard-library curses restoration path so success,
  cancel, Ctrl+C, exceptions, resize handling, and hardware failures do not
  intentionally leave terminal input/cursor state behind.

## Compatibility

The complete v0.9.0 runtime and safety contract is retained. Native HID++,
learned DPI/polling, remapping, keyboard keys and chords, configured DPI-cycle,
direct DPI notifications, reconnect and late receiver insertion, battery/tray,
service behavior, updater behavior, and packaging remain regression-tested.

## Validation

The final feature branch passed 526 tests on Python 3.12, with the same full
suite and compile checks passing on Python 3.13 and Python 3.14. Fedora 44 RPM
CI also remains part of the release gate.

## Downloads

- [RPM: mouse-control-0.9.1-1.fc44.noarch.rpm](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.1/mouse-control-0.9.1-1.fc44.noarch.rpm)
- [DEB: mouse-control_0.9.1-1_all.deb](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.1/mouse-control_0.9.1-1_all.deb)
- [AppImage: Mouse-Control-0.9.1-x86_64.AppImage](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.1/Mouse-Control-0.9.1-x86_64.AppImage)
- [Wheel: mouse_control-0.9.1-py3-none-any.whl](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.1/mouse_control-0.9.1-py3-none-any.whl)
- [Source: mouse_control-0.9.1.tar.gz](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.1/mouse_control-0.9.1.tar.gz)

---
# Mouse Control v0.9.0

## Automatic Discovery foundation

Mouse Control 0.9.0 is a major architectural release. It makes it practical to
add support for new Linux gaming mice without pretending that an unknown device
is safe to configure. Instead of requiring a developer to begin with every
manufacturer’s private protocol, Automatic Discovery connects the Linux input
and HID interfaces for one physical mouse, studies its read-only behavior, and
collects evidence from real actions. A capability is promoted only after its
behavior has been demonstrated for that exact model.

For users, this means a clear path to helping with an unsupported mouse today:
install v0.9.0, configure ordinary remapping with `mouse-control setup`, run
`mouse-control doctor --report` and `mouse-control support`, and attach the
reviewed report to the hardware-support issue template. `mouse-control support
--guided` can record an optional button press. Advanced testers can use
`sudo mouse-control-discover --full-access --generic-only --learn-dpi-button
--verbose` for the guided, read-only discovery workflow.

Normal evdev/uinput button remapping remains available when advanced hardware
control is unavailable. That is deliberate: an unproven DPI or polling feature
must never prevent a mouse from working as a Linux input device.

## Safety model

Automatic Discovery does not guess commands or send them to unknown hardware.
Unknown devices remain conservative and read-only while their identity,
interfaces, report behavior, and any requested operation are evaluated.
Writable DPI or polling control requires exact-model evidence, reversible
transaction proof, readback, independent physical verification, and rollback
where applicable. The Logitech G305 is the physically proven reference for the
learned-runtime path; its write authority does not transfer to another model.

Known protocol adapters—including Logitech HID++—are teachers and references,
not the generic backbone. The project continues to refuse ambiguous device or
protocol matches rather than choosing one.

## What changed underneath

- Physical-device topology correlates evdev, hidraw, and sysfs interfaces.
- Protocol-neutral HID descriptor/report analysis and grammar/repertoire tools
  record evidence without inventing vendor semantics.
- Known protocols can teach semantic behavior without hard-coding their write
  authority into generic discovery.
- Exact-model learned operations support reversible write proof, readback, and
  behavioral verification for DPI and polling/report-rate control.
- One learned HID session owns a selected interface reader so transactions and
  unsolicited events do not compete.
- Runtime/reconnect integration keeps ownership-safe Host/onboard transitions
  separate from ordinary reconciliation and preserves remapping on failure.

## Compatibility preserved

v0.9.0 carries forward the complete v0.8.2 stability and functionality
contract: remapping, notifications, reconnect behavior, setup preservation,
service/runtime controls, updater behavior, and packaging. This remains the
baseline for future development.

## Downloads

- [RPM: mouse-control-0.9.0-1.fc44.noarch.rpm](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.0/mouse-control-0.9.0-1.fc44.noarch.rpm)
- [DEB: mouse-control_0.9.0-1_all.deb](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.0/mouse-control_0.9.0-1_all.deb)
- [AppImage: Mouse-Control-0.9.0-x86_64.AppImage](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.0/Mouse-Control-0.9.0-x86_64.AppImage)
- [Wheel: mouse_control-0.9.0-py3-none-any.whl](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.0/mouse_control-0.9.0-py3-none-any.whl)
- [Source: mouse_control-0.9.0.tar.gz](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.0/mouse_control-0.9.0.tar.gz)

## Known issue

Interactive `mouse-control update` can still wait for package-manager
confirmation without displaying the prompt. If that occurs, type `y` and press
Enter, or use `mouse-control update --yes` for the non-interactive path.

The v0.8.2 stability and functionality contract remains a release blocker for
all future development.


---
# Mouse Control v0.8.2

This stabilization release keeps ordinary evdev/uinput remapping independent
of optional hardware backends while native hardware control recovers cleanly.

- Setup preserves valid remaps, including the configurable `dpi-cycle` action,
  and retains untouched DPI/polling settings.
- Setup writes hardware settings only for explicit relevant edits and merges
  configuration without discarding unrelated or unknown entries.
- On reconnect, Mouse Control can temporarily use Generic HID/evdev, then
  promote back to the preferred native or vendor backend. Native promotion
  restores DPI monitoring, notifications, and DPI/polling reconciliation.

**Updater note:** When updating through Mouse Control's built-in updater,
installation may pause without displaying the package manager's confirmation
prompt. If this happens, type `y` and press Enter. The update will then
continue and finish normally. This does not apply to `mouse-control update
--yes`. This temporary known UX issue—waiting for invisible user input—is
planned for correction in the next development cycle.

---

# Mouse Control v0.8.1

The setup wizard now lets you revisit DPI, polling, and button choices from
Review without losing accepted edits. Enter a DPI value to test it immediately;
Back discards that test, and cancelling setup restores the original DPI when
possible.

The polling screen shows hardware-reported rates and the current rate when
readable. It offers selection only when the backend permits safe writes.
Finishing saves the exact accepted DPI stages for normal runtime cycling.

---

# Mouse Control v0.8.0

Mouse buttons can now hold keyboard chords, for example
`chord:KEY_LEFTCTRL+KEY_LEFTSHIFT+KEY_S`. The keys stay held while the mouse
button is pressed. Overlapping chords safely share modifiers, and disconnect
or shutdown releases synthetic keys so they do not remain stuck.

The setup wizard can capture a chord, and you can also enter one manually in
the configuration. Chord support is not general macro/sequencing support.

For isolated configuration and runtime testing, use
`mouse-control run --config /path/to/config.toml`. This runs with the selected
file without changing the normal installed configuration.

---

# Mouse Control v0.7.11

## RPM updater reliability

RPM ownership detection now retains the stable package name. After DNF runs,
Mouse Control verifies the installed RPM version; warnings, noisy output, or a
nonzero DNF result cannot report a false failure when the target version is
installed.

If a native DNF upgrade leaves the old version installed, Mouse Control still
uses the validated GitHub RPM fallback and verifies the final installed version.

`mouse-control update --yes` now passes DNF `--assumeyes` for both native and
fallback installs. Updates without `--yes` keep their normal confirmation flow.
