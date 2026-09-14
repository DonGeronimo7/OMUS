# Mouse Control

[![Current release](https://img.shields.io/github/v/release/DonGeronimo7/mouse-control?display_name=tag&label=release)](https://github.com/DonGeronimo7/mouse-control/releases/latest)
[![CI](https://github.com/DonGeronimo7/mouse-control/actions/workflows/ci.yml/badge.svg)](https://github.com/DonGeronimo7/mouse-control/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-3DA639)](LICENSE)
[![Platform: Linux](https://img.shields.io/badge/platform-Linux-FCC624?logo=linux&logoColor=black)](https://github.com/DonGeronimo7/mouse-control)

A Linux mouse configuration and remapping utility designed to work across
hardware vendors. Mouse Control provides software button remapping through
evdev/uinput and uses available hardware integrations for DPI and polling-rate
configuration. When a vendor-specific feature is unavailable, ordinary
software remapping can still be available.

The current release is [v0.7.4](https://github.com/DonGeronimo7/mouse-control/releases/tag/v0.7.4).

## Install

## Community hardware testing

`mouse-control support` creates a local, privacy-safe report for an unsupported
mouse selected by the user. It records relevant device identity, input
capabilities, backend status, HID interfaces, and deterministic HID
report-descriptor topology. Reports are never uploaded automatically and there
is no telemetry or hardware write during probing. `--guided` optionally records
one requested side-button press. Unknown hardware is expected and still yields
a useful report; this does not claim Turtle Beach Kone II compatibility.

Choose the package that fits your Linux distribution. Native packages are the
best choice when available: they install the dependencies and udev integration
needed by the host system.

### Fedora, Nobara, and other RPM-based distributions

Download the v0.7.4 RPM from the [release assets](https://github.com/DonGeronimo7/mouse-control/releases/tag/v0.7.4), then install it with DNF:

```bash
sudo dnf install ./mouse-control-0.7.4-1.fc44.noarch.rpm
```

This unsigned Fedora 44 package declares Python, evdev, dbus-next, and systemd
dependencies and native HID integration. OpenRazer is optional. If an older pip
installation shadows the command, use `/usr/bin/mouse-control`.

### Debian, Ubuntu, Mint, and other DEB-based distributions

Download `mouse-control_0.7.4_all.deb` from the [release assets](https://github.com/DonGeronimo7/mouse-control/releases/tag/v0.7.4), then let APT resolve its declared dependencies:

```bash
sudo apt install ./mouse-control_0.7.4_all.deb
```

### AppImage and other distributions

Download [Mouse-Control-0.7.4-x86_64.AppImage](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.7.4/Mouse-Control-0.7.4-x86_64.AppImage), make it executable, and run it:

```bash
chmod +x Mouse-Control-0.7.4-x86_64.AppImage
./Mouse-Control-0.7.4-x86_64.AppImage setup
```

The AppImage can contain the Python application and user-space libraries such
as Python, evdev, and dbus-next as provided by its build. It does not bundle
host system components: systemd, udev rules, kernel input support, or
the OpenRazer daemon/driver remain distribution-managed. Do not install a
permanent user service from an arbitrary AppImage download location. Use the
native package when you need the packaged udev and service integration.

### Arch Linux

The repository includes a [PKGBUILD](PKGBUILD) for v0.7.4, but this project does
not currently claim to publish an AUR package. Review and build it locally, or
install from source. OpenRazer remains an optional dependency.

### Source installation

For developers and advanced users, download the source distribution from the
[release assets](https://github.com/DonGeronimo7/mouse-control/releases/tag/v0.7.4), or clone this repository:

```bash
git clone https://github.com/DonGeronimo7/mouse-control.git
cd mouse-control
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Source installations may need their distribution's Python development headers
to build `evdev`. See [Device permissions](#device-permissions) for the udev
rule required by a source installation.

## Quick start

Run setup as your logged-in desktop user:

```bash
mouse-control setup
```

The wizard detects or selects a mouse, records buttons, configures mappings,
and saves a configuration. For the normal background service workflow:

```bash
mouse-control start
mouse-control status
mouse-control restart
mouse-control stop
```

Run `mouse-control install-service` once before `start`. `mouse-control run`
remains the explicit foreground/debug command; it does not start the service.

## Hardware support

Mouse Control does not claim universal hardware support. The matrix below
separates physically validated behavior from expected fallback paths and work
that needs community testing. The detailed, evidence-based record is in
[docs/COMPATIBILITY.md](docs/COMPATIBILITY.md).

| Hardware / backend | Status | Notes |
| --- | --- | --- |
| Logitech G305 | Physically validated | Native HID++ automatic detection; 200–12000 DPI in 50-DPI steps; configured 800/1500/2000/2500/3000 stages; physical DPI events/OSD; 1000/500/250/125 Hz discovery; reconnect, late insertion, and side-button remapping. |
| Logitech HID++ | Architecture available; device testing needed | Feature indexes are discovered live. The G305 is the primary physical reference; other Logitech mice are not claimed as validated. |
| OpenRazer-supported mice | Needs broader validation | Optional backend; physical Razer validation is still needed. |
| Generic HID / evdev mice | Needs broader validation | Exact HID identity and read-only diagnostics plus software remapping; no unvalidated DPI or polling writes. |

## Help test your mouse

Hardware reports—successful as well as unsuccessful ones—build a useful Linux
compatibility database. We especially welcome reports for Logitech, Razer,
SteelSeries, Corsair, Glorious, Roccat/Turtle Beach, ASUS, Cooler Master,
HyperX, generic USB mice, and other manufacturers. This is an invitation to
test, not a claim that those mice are already supported.

1. Install Mouse Control and run `mouse-control setup`.
2. Test button remapping and normal mouse operation.
3. Where relevant, test DPI, DPI notifications, polling, and the background service.
4. Run `mouse-control doctor --report`.
5. Submit the sanitized output with the [Hardware compatibility issue template](https://github.com/DonGeronimo7/mouse-control/issues/new?template=hardware-compatibility.yml).

`mouse-control doctor` is read-only. `mouse-control doctor --report` is meant
for public reports and, as implemented, excludes usernames, home paths, serial
numbers, cache contents, and unrelated USB devices. Review its output before
posting it and remove anything you do not want to share.

## How Mouse Control chooses a backend

Mouse Control uses the best available integration for the selected device and
falls back gracefully when vendor-specific functionality is unavailable:

1. Native HID where a validated protocol driver confidently claims one interface.
2. OpenRazer where its optional daemon/client can confidently recognize it.
3. Generic HID identity with evdev/software remapping when no validated hardware backend is available.

Hardware configuration failures are reported independently and do not prevent
ordinary software remapping from starting.

`mouse-control debug-hid --seconds 10` is the vendor-neutral, read-only
development path. It matches hidraw interfaces to the selected evdev mouse by
bus type and exact VID:PID, prints their report descriptors, and captures input
reports while buttons are pressed. It never sends feature or output reports.
USB HID does not standardize mouse DPI or polling-rate configuration, so a
vendor protocol must be validated before those writes are enabled.

## Optional hardware integrations

### OpenRazer

Logitech users do not need OpenRazer. For Razer hardware, follow the
[upstream installation instructions](https://openrazer.github.io/#download) for
your distribution. OpenRazer is intentionally optional; a missing client,
daemon, or supported capability leaves generic remapping available. Run Mouse
Control as the logged-in desktop user so it can access the same session D-Bus
as the daemon, rather than using `sudo`.

## Device permissions

The Fedora RPM installs
`/usr/lib/udev/rules.d/71-mouse-control-uaccess.rules`. It gives the active
local logind session an ACL for mouse event devices and `/dev/uinput`, while
excluding interfaces also classified as keyboards. It does not change device
modes, add users to `input`, or grant access to every logged-in user. After an
RPM install or upgrade, log out and back in (or reconnect the mouse), then run:

```bash
mouse-control check-permissions
mouse-control setup
```

For a source installation, install the supplied rule and reload udev:

```bash
sudo install -Dm644 src/mouse_control/udev/71-mouse-control-uaccess.rules \
  /etc/udev/rules.d/71-mouse-control-uaccess.rules
sudo udevadm control --reload-rules
```

Do not run `mouse-control run` as root. Keyboard capture is deliberately not
granted by this rule because reading keyboard events can expose keystrokes; the
wizard retains manual `KEY_*` entry when desktop policy does not permit capture.

## Logitech G305 and HID++ notes

The G305 is the reference hardware for the currently validated HID++ DPI
behavior. Its two routes are deliberately distinct:

- Adjustable DPI query feature `0x2201`: dynamically discovered feature-table index.
- Physically observed passive DPI notification: Onboard Profiles event index `0x07` on the G305.

These indexes are device-specific and must not be collapsed into one mapping.
Normal `mouse-control run` owns one selected hidraw interface, performs live
HID++ ROOT discovery, and multiplexes replies with unsolicited events. Live
feature discovery is authoritative. An unsupported or ambiguous device retains
ordinary remapping without hardware writes.

`mouse-control debug-dpi` is the explicit diagnostic workflow. It can
discover HID++ features and observe the
physical DPI button. It does not change firmware button mappings, and normal
runtime does not import Solaar or add it as a dependency. For full diagnostic
details, see [RELEASE_NOTES.md](RELEASE_NOTES.md).

## Configuration and behavior

The configuration is saved at `~/.config/mouse-control/config.toml`. Supported
mapping actions are `passthrough`, `disable`, `mouse:BTN_*`, and `key:KEY_*`.
The configuration can be edited by hand.

When supported by a native driver, setup uses project defaults of 800, 1500, 2000,
2500, and 3000 DPI, selects 800 DPI as active/default, and chooses the highest
reported polling rate. Hardware that lacks enough programmable slots or rejects
values reports the limitation rather than pretending that settings were applied.
Generic devices do not receive hardware DPI writes.

Mouse Control deliberately excludes RGB/lighting control, multiple profiles,
and hardware features beyond DPI and polling.

## Development and validation

```bash
python3 -m pytest -q
python3 -m compileall -q src tests
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for bug reports, hardware reports, and
pull requests. Packaging notes are available for [AppImage](packaging/appimage/README.md),
[Debian](debian/control), and [RPM](mouse-control.spec) builds.

## License

Mouse Control is licensed under the GNU General Public License, version 3 or
later. See [LICENSE](LICENSE).
