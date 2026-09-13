# Mouse Control v0.7.2

Mouse Control v0.7.2 is a major backend modernization release despite its 0.x
version. It makes native Logitech HID++ 2 control a first-class backend while
preserving the project's central promise: ordinary evdev remapping continues
when vendor-specific hardware control is unavailable.

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

```bash
sudo dnf install ./mouse-control-0.7.2-1.fc44.noarch.rpm
/usr/bin/mouse-control --help
```

The RPM is unsigned and does not enable remapping or start the user service.
For installation and device-access diagnostics, use `mouse-control
check-permissions` followed by `mouse-control setup` as your logged-in desktop
user.

## Release assets

- `mouse-control-0.7.2-1.fc44.noarch.rpm`
- `mouse-control_0.7.2_all.deb`
- `Mouse-Control-0.7.2-x86_64.AppImage`
- `mouse_control-0.7.2.tar.gz`
- `mouse_control-0.7.2-py3-none-any.whl`
- `SHA256SUMS`
