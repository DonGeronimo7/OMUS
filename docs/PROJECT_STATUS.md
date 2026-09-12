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
Extended Adjustable DPI (`0x2202`) is discoverable but independent-axis packet
handling is likewise deferred.

OpenRazer remains available behind the common backend contract. Unknown or
ambiguous hardware falls back to Generic HID diagnostics and ordinary evdev
remapping without guessed capabilities or writes.

Freedesktop DPI notifications consume canonical DPI values. Each update uses
the prior notification ID as its replacement ID, and notification failures do
not stop hardware handling or remapping.

## Validation status

The native session and HID++ behavior use deterministic fixtures and require no
physical hardware in CI. Logitech G305 hardware revalidation remains required
for DPI reads, writes, button events, reconnect behavior, and interface
selection before a release claims those operations as physically validated.
