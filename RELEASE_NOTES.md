# Mouse Control v0.6.3

This release synchronizes the current physically validated implementation while
preserving the existing input-remapping, service, and hardware-backend behavior.

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
sudo dnf install ./mouse-control-0.6.3-1.fc44.noarch.rpm
/usr/bin/mouse-control --help
```

The RPM is unsigned. Installing it does not activate remapping or enable the
user service. OpenRazer remains optional.

## Proposed release assets

- `mouse-control-0.6.3-1.fc44.noarch.rpm` — installable Fedora package.
- `mouse_control-0.6.3.tar.gz` — Python source distribution.
- `mouse_control-0.6.3-py3-none-any.whl` — Python wheel.
- `SHA256SUMS` — checksums for the published artifacts above.

Any source RPM built during validation is internal and is not included in the
public checksum manifest unless publication is requested separately.
