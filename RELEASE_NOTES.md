# Mouse Control v0.4.2

Fedora 44 / Python 3.14 release containing both changes since v0.3.3:

- **Keyboard capture:** bind a mouse button by physically pressing a keyboard or
  media key. Manual key-code entry remains available; saved mapping syntax is unchanged.
- **Hardware backends:** extensible Ratbag → OpenRazer → Generic selection, with
  optional Razer DPI/polling support through OpenRazer. Preserves Logitech G305
  stage configuration and maximum polling behavior. Hardware failures warn and
  allow remapping to continue.

See [CHANGELOG.md](https://github.com/DonGeronimo7/mouse-control/blob/main/CHANGELOG.md)
for the complete history and [README](https://github.com/DonGeronimo7/mouse-control#readme)
for optional Fedora OpenRazer packages and usage.

## Install or upgrade

```bash
sudo dnf install ./mouse-control-0.4.2-1.fc44.noarch.rpm
/usr/bin/mouse-control --help
```

The RPM is unsigned. OpenRazer is optional; Logitech users do not need it.
Installing this package does not enable/start services or modify input permissions.
Existing TOML configurations and service commands remain compatible.

## Downloads

- `mouse-control-0.4.2-1.fc44.noarch.rpm` — installable Fedora 44 package.
- `mouse-control-0.4.2-1.fc44.src.rpm` — source RPM with complete source and spec.
- `mouse-control-0.4.2.tar.gz` — source snapshot.
- `SHA256SUMS` — checksums for those three downloads.

## Validation and limits

38 tests and Python compile checks passed. RPM payload and dependency checks
passed. System-wide installation and physical hardware testing were not performed.
Razer wired/wireless identity, DPI/polling readback, reconnect and user-session
service behavior still need real-hardware verification. OpenRazer applies active
DPI only; programmable stages remain a Libratbag capability. Ambiguous VID/PID
matches fall back safely. No lighting, profiles or macros were added.
