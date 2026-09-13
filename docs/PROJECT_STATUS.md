# Mouse Control Project Status

Last updated: 2026-09-12

## Current architecture

Mouse Control keeps evdev/uinput remapping independent from hardware control.
Hardware discovery preserves all matching HID interfaces for a physical input
device. `NativeHidBackend` lets protocol drivers probe those interfaces and
refuses hardware writes if more than one interface claims the protocol.

One `HidSession` owns each selected hidraw interface. It serializes writes,
correlates command replies, dispatches unsolicited events without competing
readers, and wakes pending requests on disconnect.

The first driver is Logitech HID++ 2. It discovers feature-table indexes live
through ROOT and implements Adjustable DPI (`0x2201`) enumeration, reads,
validated writes, and write verification. Onboard Profiles (`0x8100`) events
are recognized by their dynamically discovered index; a resolution-slot event
causes a current-DPI query and emits canonical confirmed state.

Report Rate (`0x8060`) list/read/write and readback verification are implemented.
Persistent profile programming is deliberately not claimed yet. Its complete
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

Freedesktop DPI notifications consume canonical DPI values. Each update uses
`replaces_id = 0` for every confirmed physical transition, and notification failures do
not stop hardware handling or remapping.

## Validation status

The native session and HID++ behavior use deterministic fixtures and require no
physical hardware in CI. The Logitech G305 Lightspeed Wireless Gaming Mouse is
the physically validated reference for automatic native detection; 200–12000
DPI in 50-DPI steps; configured 800/1500/2000/2500/3000 stages; physical DPI
events and OSD; 1000/500/250/125 Hz report-rate discovery; reconnect and late
receiver insertion recovery; and side-button remapping. Other Logitech devices
remain subject to device-specific physical validation.
