# Mouse Control v0.9.3

## Automatic Hardware Discovery becomes materially functional

Mouse Control 0.9.3 promotes the validated Automatic Hardware Discovery
checkpoint while preserving the mature v0.8.2 runtime contract and the current
full-screen setup TUI. Discovery correlates one physical mouse across evdev and
hidraw, parses its HID descriptor into stable report/field/member identities,
collects contrastive evidence from real actions, and persists only semantics
that meet the required evidence level.

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

The v0.9.3 release retains native HID++ production behavior, OpenRazer,
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

## Downloads

- [RPM: mouse-control-0.9.3-1.fc44.noarch.rpm](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.3/mouse-control-0.9.3-1.fc44.noarch.rpm)
- [DEB: mouse-control_0.9.3-1_all.deb](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.3/mouse-control_0.9.3-1_all.deb)
- [AppImage: Mouse-Control-0.9.3-x86_64.AppImage](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.3/Mouse-Control-0.9.3-x86_64.AppImage)
- [Wheel: mouse_control-0.9.3-py3-none-any.whl](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.3/mouse_control-0.9.3-py3-none-any.whl)
- [Source: mouse_control-0.9.3.tar.gz](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.3/mouse_control-0.9.3.tar.gz)

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
