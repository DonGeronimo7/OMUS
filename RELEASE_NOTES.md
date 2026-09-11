# Mouse Control v0.5.0

This release synchronizes the current physically validated implementation into
the published project and replaces the outdated v0.4.2 source artifacts.

- **Logitech G305 DPI notifications:** for the physically validated `046d:4074`
  profile, Mouse Control passively reads native HID++ DPI-stage events and shows
  transient Freedesktop notifications. It does not rewrite the firmware button,
  poll `ratbagctl`, or treat the G305 HID++ feature index as universal.
- **Reliable configuration and service behavior:** setup supports multiple mouse
  buttons and physical keyboard capture, preserves configuration on cancel/failure,
  temporarily stops a running user service, and restores it afterwards.
- **Hardware and permissions:** Libratbag remains the preferred hardware backend;
  OpenRazer is optional and Generic remains the safe fallback. Fedora/Nobara
  installations include scoped uaccess rules for mouse input, uinput, and the
  G305 HID++ parent interface.

## Install or upgrade

```bash
sudo dnf install ./mouse-control-0.5.0-1.fc44.noarch.rpm
/usr/bin/mouse-control --help
```

The RPM is unsigned. Installing it does not activate remapping or enable the
user service. OpenRazer is not a required dependency.

## Release assets

- `mouse-control-0.5.0-1.fc44.noarch.rpm` — installable Fedora package.
- `mouse-control-0.5.0-1.fc44.src.rpm` — source RPM.
- `mouse_control-0.5.0.tar.gz` — Python source distribution.
- `mouse_control-0.5.0-py3-none-any.whl` — Python wheel.
- `SHA256SUMS` — checksums for the published artifacts.

## Scope and limits

G305 HID++ DPI notification support is physically validated only for Logitech
G305 `046d:4074`. Other Logitech devices are not claimed to support it. Hardware
backend and notification failures warn and allow regular remapping to continue.
