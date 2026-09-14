# Mouse Control v0.7.4

Mouse Control v0.7.4 adds an optional live battery indicator while retaining
the native Logitech HID++ modernization introduced across the v0.7.x feature
set. Ordinary evdev remapping remains available when vendor-specific hardware
control is unavailable.

## Community hardware testing

`mouse-control support` provides a built-in, read-only hardware reporting
workflow for unsupported mice. Users select a mouse and generate a privacy-safe
local report with relevant device identity, input capabilities, backend status,
HID interfaces, and HID report-descriptor topology. Reports remain local until
the user chooses to share them.

The command optionally offers guided button capture. It has no telemetry or
automatic uploads and performs no hardware writes during probing. Unknown
hardware is expected and does not make report generation fail. This is for
community testing; it does not claim Turtle Beach Kone II compatibility.

## Battery tray integration

- A standard StatusNotifierItem tray icon draws a clean monochrome battery
  with proportional live fill and no embedded percentage text.
- The tooltip and right-click `com.canonical.dbusmenu` show the live device
  name, exact battery percentage, and battery status when the device provides
  it.
- Icon, tooltip, and menu update from the same battery state, so their values
  remain in agreement.
- The integration is desktop-independent and uses standard SNI/DBusMenu
  interfaces; desktop-specific menu styling is outside Mouse Control.

## Native Logitech HID++

- Native Logitech DPI and report-rate support no longer requires `libratbag`,
  `ratbagd`, or `ratbagctl`.
- HID++ ROOT feature discovery resolves feature indexes dynamically; no G305
  feature indexes are hard-coded.
- The backend enumerates DPI, reads and writes DPI with hardware readback,
  receives confirmed live DPI notifications, and recognizes physical DPI events.
- It enumerates and reads report rates, and enables report-rate writes only
  where capability detection determines that they are safe.
- It does not force profile-mode switching. OpenRazer remains optional for
  supported Razer hardware.

## Validated hardware

Physically validated: **Logitech G305 Lightspeed Wireless Gaming Mouse**.

The validated capabilities are automatic native HID++ detection; 200–12000 DPI
in 50-DPI steps; configured 800/1500/2000/2500/3000 stages; physical DPI event
monitoring and DPI OSD; 1000/500/250/125 Hz report-rate discovery; reconnect
recovery; late receiver insertion; and side-button remapping.

The architecture is generalized, but the G305 is the primary physical
reference. This release does not claim that all Logitech mice have been
physically validated.

## Reconnect, lifecycle, and notifications

Evdev reconnect resilience, HID reconnect, fresh backend rediscovery, startup
without a mouse, late receiver insertion, watcher recovery, and monitor
recovery now work without requiring a service restart after reconnect.

Notifications return to a simplified v0.6.9-style Freedesktop path with
asynchronous submission and failure isolation. The first confirmed DPI event
is no longer incorrectly suppressed, and HID reconnect no longer stops
monitoring.

## CLI and generic fallback

Service management is available through:

```text
mouse-control start
mouse-control stop
mouse-control restart
mouse-control status
```

`mouse-control run` remains foreground/debug execution.

Unknown mice retain evdev remapping. Generic HID discovery is a read-only
fallback and extension point; USB HID itself does not standardize DPI or
report-rate controls. Future vendor protocol drivers can be added without
affecting the Logitech HID++ backend.

## Install or upgrade

Packaging artifacts are intentionally not part of this source checkpoint.
The v0.7.4 source is ready for the separate packaging and release workflow.
