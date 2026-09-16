# Mouse Control v0.9.0

**Automatic Discovery foundation release**

Mouse Control 0.9.0 moves hardware support onto the Automatic Discovery
runtime while preserving the complete v0.8.2 remapping, notification,
reconnect, setup, service, updater, and packaging behavior as a compatibility
contract.

- Adds protocol-neutral physical-device discovery across matching HID
  interfaces instead of treating a known vendor backend as the generic
  backbone.
- Promotes exact-model learned DPI and report-rate operations only after
  reversible transaction proof, hardware readback, independent physical
  verification, and exact rollback. Read evidence alone never grants write
  authority.
- Adds a single-reader learned HID session so learned transactions and
  unsolicited events can safely share one hidraw interface without competing
  readers.
- Integrates validated read-only physical action triggers with the existing
  configured `dpi-cycle` path, confirmed write/readback, and direct DPI
  notifications.
- Preserves polling ownership safety: normal startup/reconnect reconciliation
  never takes Host/software control merely to apply a saved polling rate.
  Explicit user-requested changes may use only a separately PROVEN reversible
  takeover branch.
- Keeps unknown hardware conservative: unsupported devices retain evdev/uinput
  remapping and read-only discovery evidence until their own exact protocol is
  safely demonstrated and promoted.
- The Logitech G305 remains the physically validated reference device for the
  v0.9.0 learned-runtime path; its write authority is never generalized to
  other models.

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
