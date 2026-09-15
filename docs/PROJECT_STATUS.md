# Mouse Control Project Status

Last updated: 2026-09-14

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

OpenRazer remains available behind the common backend contract. Unknown or
ambiguous hardware falls back to Generic HID diagnostics and ordinary evdev
remapping without guessed capabilities or writes.

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
The new transactional polling writes, Host-mode physical DPI-event behavior,
and unified state reconciliation are covered by fixtures but still require the
physical acceptance procedure in `docs/G305_HARDWARE_ACCEPTANCE.md`. Other
Logitech devices remain subject to device-specific physical validation.

Future hardware support should supply a capability adapter for an exactly
identified and validated protocol, then pass the universal behavior suite.
Hardware additions should not redesign established remapping, notification,
lifecycle, or service behavior.
