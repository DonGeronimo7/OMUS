# Mouse Control

![Mouse Control — Linux gaming mouse configuration and remapping](assets/mouse-control-social-preview.png)

Open-source Linux gaming mouse remapping and hardware discovery: map mouse
buttons to keyboard keys, configure proven DPI and polling rates, and safely
help expand support for new hardware.

[![Current release: v0.9.3](https://img.shields.io/badge/current%20release-v0.9.3-2ea44f)](https://github.com/DonGeronimo7/mouse-control/releases/tag/v0.9.3)
[![CI](https://github.com/DonGeronimo7/mouse-control/actions/workflows/ci.yml/badge.svg)](https://github.com/DonGeronimo7/mouse-control/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-3DA639)](LICENSE)
[![Platform: Linux](https://img.shields.io/badge/platform-Linux-FCC624?logo=linux&logoColor=black)](https://github.com/DonGeronimo7/mouse-control)

Mouse Control is a terminal-native Linux gaming mouse utility for people whose
vendor software does not work on Linux. Ordinary button remapping uses
`evdev`/`uinput`, so it remains useful on Wayland and does not depend on
vendor-specific hardware control.

Where a validated backend exists, Mouse Control also exposes DPI and
polling/report-rate control. Native Logitech HID++ support is built in,
OpenRazer is optional, and Automatic Discovery can safely gather evidence for
unknown hardware without guessing write commands.

## Current release: v0.9.3

The current release is [v0.9.3](https://github.com/DonGeronimo7/mouse-control/releases/tag/v0.9.3).

Mouse Control v0.9.3 promotes the validated Automatic Hardware Discovery
checkpoint: learned HID state is persisted with descriptor-backed semantic
identity, rebound conservatively after reconnect, and exposed through the
normal setup and runtime paths without guessing unknown-device writes.

Run:

```bash
mouse-control setup
```

The setup wizard is now a full-screen keyboard-driven TUI with revisitable
sections for:

- Device
- Hardware / Discovery
- Buttons
- DPI
- Polling
- Service
- Review / Save

If the selected mouse already has proven hardware support, setup simply shows
those capabilities and lets you configure them. If the mouse is unknown,
setup can offer **Guided Discovery** directly. Users do not need to know HID,
`hidraw`, protocol teachers, feature reports, write scopes, or discovery CLI
commands.

## Safe Guided Discovery

Guided Discovery begins read-only. It first performs passive physical-device,
interface, descriptor, and known-adapter discovery. If DPI behavior is still
unknown and the existing learner can safely observe it, setup can guide five
samples:

1. Quiet/idle control.
2. Normal movement and one left click without the DPI/profile button.
3. DPI-button sample.
4. DPI-button sample.
5. DPI-button sample.

The workflow reuses the same underlying learning code as
`mouse-control-discover`; setup does not maintain a second protocol-learning
implementation.

Observation does **not** grant hardware write authority. Descriptor similarity,
VID/PID similarity, protocol resemblance, observed report bytes, and evidence
from another model are not enough. Writable DPI or polling control is exposed
only when the existing exact-model PROVEN requirements are satisfied, including
reversible proof, readback, physical verification where required, rollback,
unambiguous identity, and safe control ownership.

There is no speculative generic polling writer. If a capability cannot yet be
proved safely, setup says that it is **not yet learned** and ordinary button
remapping remains available.

## DPI configuration

The DPI editor separates **live testing** from **accepting** a stage.
Choose a DPI stage, enter a candidate value, and test it on the real mouse.
Moving the mouse at that temporary value does not silently change the staged
configuration.

The editor provides:

- **Test live** — temporarily apply and verify the candidate DPI.
- **Accept value** — explicitly save the verified candidate into that setup stage.
- **Set to current** — read the mouse's current verified DPI, including a value
  selected using the physical DPI button, and use it as the candidate.
- **Cancel / Back** — leave the staged configuration unchanged and restore the
  hardware DPI that was active when the editor opened when restoration is
  possible.

Configured defaults remain 800, 1500, 2000, 2500, and 3000 DPI. Hardware values
are never guessed; live editing is offered only when a writable DPI capability
is already proven for the selected mouse.

## What Mouse Control does

- Remaps gaming-mouse buttons to mouse actions, keyboard keys, or keyboard chords.
- Passes through or disables buttons.
- Supports a configurable `dpi-cycle` action.
- Configures DPI only through validated writable capabilities.
- Configures polling/report rate only through validated writable capabilities.
- Uses native Logitech HID++ discovery for supported capabilities.
- Uses independently PROVEN exact-model learned operations where available.
- Uses optional OpenRazer integration for applicable Razer hardware.
- Falls back to read-only generic HID diagnostics plus evdev/uinput remapping.
- Preserves DPI notifications, reconnect recovery, late receiver insertion,
  battery/tray behavior, and user-service controls from the v0.9.0 runtime.

Mouse Control deliberately excludes RGB/lighting control, multiple profiles,
and unrelated hardware features.

## Get Mouse Control

Release page: [Mouse Control v0.9.3](https://github.com/DonGeronimo7/mouse-control/releases/tag/v0.9.3)

- **Fedora / Nobara / RPM:** [mouse-control-0.9.3-1.fc44.noarch.rpm](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.3/mouse-control-0.9.3-1.fc44.noarch.rpm)
- **Debian / Ubuntu / Mint:** [mouse-control_0.9.3-1_all.deb](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.3/mouse-control_0.9.3-1_all.deb)
- **Other distributions:** [Mouse-Control-0.9.3-x86_64.AppImage](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.3/Mouse-Control-0.9.3-x86_64.AppImage)
- **Arch Linux:** included [`PKGBUILD`](PKGBUILD)
- **Python wheel:** [mouse_control-0.9.3-py3-none-any.whl](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.3/mouse_control-0.9.3-py3-none-any.whl)
- **Source:** [mouse_control-0.9.3.tar.gz](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.3/mouse_control-0.9.3.tar.gz)

### Fedora, Nobara, and other RPM systems

```bash
sudo dnf install ./mouse-control-0.9.3-1.fc44.noarch.rpm
```

The RPM installs the Python/runtime dependencies, desktop launcher, icons, and
Mouse Control udev rules. It does not silently enable the background service.

### Debian, Ubuntu, Mint, and other DEB systems

```bash
sudo apt install ./mouse-control_0.9.3-1_all.deb
```

### AppImage

```bash
chmod +x Mouse-Control-0.9.3-x86_64.AppImage
./Mouse-Control-0.9.3-x86_64.AppImage setup
```

The AppImage bundles user-space application components but does not replace host
systemd, udev, kernel input support, or optional vendor drivers. Native packages
remain preferable when you want packaged host integration.

### Source

```bash
git clone https://github.com/DonGeronimo7/mouse-control.git
cd mouse-control
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Updating

```bash
mouse-control update
```

Use `mouse-control update --check` for a non-modifying check and
`mouse-control update --yes` for a non-interactive update. v0.9.3 retains
visible interactive package-manager confirmation input instead of waiting for
an unseen prompt.

Repository packages may intentionally lag the newest GitHub release. Mouse
Control detects its documented installation methods and delegates changes to the
installation owner rather than manually overwriting package-managed files.

## Quick start

Run setup as your logged-in desktop user:

```bash
mouse-control setup
```

After reviewing and saving configuration, install the user service once if you
want automatic background operation:

```bash
mouse-control install-service
mouse-control start
mouse-control status
```

Service commands:

```bash
mouse-control start
mouse-control stop
mouse-control restart
mouse-control status
```

`mouse-control run` remains the explicit foreground/debug command.

## Button mappings

The configuration is stored at:

```text
~/.config/mouse-control/config.toml
```

Supported mapping actions include:

- `passthrough`
- `disable`
- `mouse:BTN_*`
- `key:KEY_*`
- `chord:KEY_*+KEY_*`
- `dpi-cycle`

Keyboard shortcut capture now grabs the selected keyboard exclusively while the
capture is active, preventing the captured shortcut from also reaching the
desktop. Manual Linux action entry remains available when keyboard-device
permissions do not allow capture.

Example:

```toml
[remap]
BTN_EXTRA = "chord:KEY_LEFTCTRL+KEY_LEFTSHIFT+KEY_S"
```

## Trying an unsupported mouse?

Start with the normal setup wizard:

```bash
mouse-control setup
```

If Automatic Discovery cannot already provide proven advanced hardware control,
the Hardware / Discovery section can offer Guided Discovery. You may always
skip it and continue with normal remapping.

For developer diagnostics and community hardware acceptance, the lower-level
commands remain available. For example:

```bash
mouse-control doctor --report
mouse-control support
sudo mouse-control-discover --full-access --generic-only --learn-dpi-button --verbose
```

These advanced paths are useful for debugging and reports; ordinary users do
not need them to reach the guided setup workflow.

Hardware reports can be attached to the repository's
[hardware compatibility issue template](https://github.com/DonGeronimo7/mouse-control/issues/new?template=hardware-compatibility.yml).
Review reports before posting and remove anything you do not want to share.

## How Mouse Control chooses hardware support

Every selected mouse is represented through the Automatic Discovery hardware
surface.

1. Mouse Control correlates the physical mouse with its Linux input and HID
   interfaces.
2. A validated protocol adapter such as Logitech HID++ may bind when identity
   and ownership are unambiguous.
3. Optional integrations such as OpenRazer may expose proven capabilities for a
   matching device.
4. Independently PROVEN learned operations for the exact model may expose DPI or
   polling control through the same surface.
5. If no proven hardware capability applies, Mouse Control keeps hardware
   discovery conservative/read-only and ordinary remapping continues.

Known backends are teachers/reference adapters, not the generic backbone. Their
protocol bytes or write authority are not transferred to another mouse model.

## Hardware support

The detailed evidence-based record is in
[`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md).

| Hardware / backend | Status | Notes |
| --- | --- | --- |
| Logitech G305 | Physically validated | Native HID++ automatic detection; 200–12000 DPI in 50-DPI steps; configured 800/1500/2000/2500/3000 stages; physical DPI events/OSD; 1000/500/250/125 Hz discovery; reconnect, late insertion, and side-button remapping. |
| Logitech HID++ | Architecture available; device testing needed | Feature indexes are discovered live. The G305 is the primary physical reference; other Logitech mice are not automatically claimed as validated. |
| OpenRazer-supported mice | Needs broader validation | Optional backend; broader physical Razer validation is still needed. |
| Generic HID / evdev mice | Safe fallback | Exact identity/read-only diagnostics plus software remapping; no unvalidated DPI or polling writes. |

## Device permissions

The Fedora RPM installs:

```text
/usr/lib/udev/rules.d/71-mouse-control-uaccess.rules
```

The rules grant the active local logind session the access Mouse Control needs
for relevant mouse/uinput paths while avoiding a blanket world-readable input
policy. For a source install, install the supplied rule and reload udev:

```bash
sudo install -Dm644 src/mouse_control/udev/71-mouse-control-uaccess.rules \
  /etc/udev/rules.d/71-mouse-control-uaccess.rules
sudo udevadm control --reload-rules
```

Then reconnect the device or log out/in and run:

```bash
mouse-control check-permissions
mouse-control setup
```

Do not run the normal Mouse Control runtime as root.

## Logitech G305 / HID++ reference

The G305 remains the physically validated reference device for native HID++ and
the learned-runtime safety model. Feature indexes are discovered dynamically
where required; model-specific notification details are not generalized to
unrelated hardware.

The Adjustable DPI query/write path and passive physical DPI notification route
remain deliberately distinct. Runtime owns a selected HID interface and
multiplexes transaction replies with unsolicited events so competing readers do
not consume each other's traffic.

## Optional OpenRazer integration

OpenRazer is optional. A missing client, daemon, or supported capability must not
break ordinary remapping. Razer users should install OpenRazer through their
Linux distribution according to upstream guidance, then run Mouse Control as
the logged-in desktop user so both applications share the desktop session.

## Safety and compatibility contract

The complete v0.8.2 stability contract, plus the v0.9.0 runtime behavior and
v0.9.1 TUI, remains the compatibility baseline for v0.9.3 and future releases.
In particular, development must not regress:

- ordinary evdev/uinput remapping;
- keyboard keys and held chords;
- configured `dpi-cycle` behavior;
- direct DPI notifications;
- native Logitech HID++;
- learned DPI and learned polling;
- learned-action triggering;
- reconnect and late receiver insertion;
- battery/tray behavior;
- setup rollback and configuration preservation;
- user-service behavior;
- updater behavior; or
- release packaging.

## Development and validation

```bash
PYTHONPATH=src pytest -q
python -m compileall -q src tests
```

The v0.9.3 release checkpoint passes 658 automated tests with one known GLib
deprecation warning. Compile and whitespace checks, packaging, physical
hardware smoke, and published-asset validation remain explicit release gates.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for contributions and hardware reports.
See [`RELEASE_NOTES.md`](RELEASE_NOTES.md) for release-specific details.

## License

Mouse Control is licensed under the GNU General Public License, version 3 or
later. See [`LICENSE`](LICENSE).
