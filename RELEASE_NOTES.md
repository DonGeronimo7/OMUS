# Mouse Control v0.6.9

This release prepares the physically validated implementation for broad Linux
community hardware testing while preserving existing remapping, service, and
hardware-backend behavior.

- **Community testing infrastructure:** adds a compatibility matrix and GitHub
  hardware/bug report templates, with a privacy-safe report suitable for issues.
- **Read-only diagnostics:** `mouse-control doctor` reports dependency, service,
  permission, backend, and safely obtainable mouse status. `doctor --fix` only
  proposes a native package command and never executes privileged operations.
- **Linux packaging preparation:** adds Debian metadata, Arch/AUR PKGBUILD, and
  AppImage build preparation. Host udev, systemd, ratbagd, and OpenRazer remain
  host-managed rather than bundled.

- **Controlled Logitech HID++ discovery:** explicit `debug-dpi` discovery uses
  dynamic ROOT feature lookup, discovers Device Name and Adjustable DPI metadata,
  temporarily coordinates with ratbagd, persists selected schema-versioned
  capability data, and restores ratbagd afterward.
- **Passive normal runtime:** ordinary `mouse-control run` startup loads cached
  metadata and performs no direct active HID++ discovery traffic. Missing,
  ambiguous, stale, or conflicting notification metadata fails safely without
  disabling remapping or Libratbag configuration.
- **Validated G305 notifications:** the physically validated Logitech G305
  (`046d:4074`, HID++ 4.2) uses independent routes: Adjustable DPI `0x2201` is
  dynamically discovered at index `0x1a`, while the native firmware DPI-cycle
  notification is the Onboard Profiles `0x8100` event at index `0x07`, event
  `0x01`, SWID `0x00`. The native button remains `resolution-cycle-up`.
- **Preserved architecture:** Ratbag, optional OpenRazer, and Generic backends,
  keyboard capture, `BTN_EXTRA` remapping, polling, setup/service recovery, and
  clean shutdown behavior remain supported. Solaar is not a dependency.

Only Logitech G305 `046d:4074` HID++ DPI notifications are physically validated
for this release. Other compatible Logitech devices may be discoverable, but
their notification behavior is not claimed as physically validated.

## Install or upgrade

```bash
sudo dnf install ./mouse-control-0.6.9-1.fc44.noarch.rpm
/usr/bin/mouse-control --help
```

The RPM is unsigned. Installing it does not activate remapping or enable the
user service. OpenRazer remains optional.

## Proposed release assets

- `mouse-control-0.6.9-1.fc44.noarch.rpm` — installable Fedora package.
- `mouse-control_0.6.9_all.deb` — installable Debian package.
- `mouse_control-0.6.9.tar.gz` — Python source distribution.
- `mouse_control-0.6.9-py3-none-any.whl` — Python wheel.
- `SHA256SUMS` — checksums for the published artifacts above.

Any source RPM built during validation is internal and is not included in the
public checksum manifest unless publication is requested separately.
