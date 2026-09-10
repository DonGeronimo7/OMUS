# Mouse Control

## Download v0.4.2

Download the Fedora 44 / Python 3.14 packages from the [v0.4.2 release](https://github.com/DonGeronimo7/mouse-control/releases/tag/v0.4.2).
See [CHANGELOG.md](CHANGELOG.md) for keyboard capture and hardware-backend changes since v0.3.3.

```bash
sudo dnf install ./mouse-control-0.4.2-1.fc44.noarch.rpm
/usr/bin/mouse-control --help
```

The unsigned RPM requires Python 3.14, evdev and systemd, and recommends Libratbag. OpenRazer remains optional. Installation does not activate remapping, enable a service or change input permissions. Use `/usr/bin/mouse-control` if an older pip installation shadows the command; existing user-service ExecStart paths remain unchanged.

A small Linux mouse utility focused on two jobs:

1. Remap mouse inputs with `evdev` + `uinput`.
2. Configure hardware DPI and polling through optional Libratbag or OpenRazer backends.

It intentionally does **not** manage lighting or multiple user profiles. The setup wizard automatically selects the highest polling/report rate reported by the selected hardware backend and writes that value to the config so it can be edited later. It also initializes the mouse with the project's preferred DPI stages: 800, 1500, 2000, 2500, and 3000 DPI, with 800 DPI active/default.

## Architecture

```text
Physical mouse
     |
     +---- evdev ----> mouse-control remapper ----> uinput virtual mouse/keyboard
     |
     +---- hardware registry ----> DPI + polling capabilities
                  +-- RatbagBackend (ratbagctl/ratbagd)
                  +-- OpenRazerBackend (Python client/session D-Bus)
                  +-- GenericBackend (no hardware writes)

                 |
                 v
        ~/.config/mouse-control/config.toml
```

The TOML file is the source of truth for the desired DPI and button mappings.
The registry tries Libratbag first, then OpenRazer, then Generic. Selection uses
the discovered physical device's USB VID/PID, never a display-name guess. More
than one matching hardware device is treated as ambiguous and skipped with a
warning. The configured event path is resolved to the live evdev device on each
run; no backend or vendor-specific sections are stored in the config.

`src/mouse_control/hardware/base.py` defines optional capabilities. To add a
backend, subclass `HardwareBackend`, implement confident device matching and
supported capabilities, translate library errors to `HardwareError`, and add its
factory to `hardware/registry.py`. Factories must be lazy and raise
`HardwareError` on discovery failure. The CLI and button wizard need no new
vendor branches. `mouse_control.ratbag` remains a compatibility import for the
migrated client. DPI and polling failures are reported independently and never
prevent software button remapping.

## Fedora 44 prerequisites

`evdev` is the Python dependency. Libratbag is a Fedora system dependency: Fedora 44 provides the `libratbag-ratbagd` package, which contains `ratbagd` and `ratbagctl`.

Install the system packages with:

```bash
sudo dnf install python3-evdev libratbag-ratbagd
```

The ratbag daemon normally runs through systemd/dbus. Verify it with:

```bash
systemctl status ratbagd
ratbagctl list
```

The upstream `ratbagctl` interface supports `dpi get`, `dpi get-all`, and `dpi set N` for a device's active profile/resolution.

## Optional OpenRazer on Fedora / RPM systems

Logitech/Libratbag users do **not** need OpenRazer. For Razer hardware, follow the
[upstream Fedora installation instructions](https://openrazer.github.io/#download).
For Fedora 41 and later, upstream documents:

```bash
sudo dnf install kernel-devel
sudo dnf config-manager addrepo --from-repofile=https://openrazer.github.io/hardware:razer.repo
sudo dnf install openrazer-meta
```

The meta package supplies the driver, daemon and Python client
(`python3-openrazer`). Use the repository appropriate to your Fedora release;
follow upstream's driver, permissions and Secure Boot setup as applicable.
OpenRazer is deliberately absent from mandatory Python/RPM requirements for
mouse-control. RPM packaging should leave it optional, with `python3-evdev`
required and hardware packages installed only as needed. The included `mouse-control.spec` keeps OpenRazer optional.

Run mouse-control as the logged-in user with access to input/uinput and the same
session D-Bus as the OpenRazer daemon. Running it with `sudo` can lose access to
that session. For a virtual environment that needs the RPM-provided client, use
`python3 -m venv --system-site-packages .venv` with the system Python. Check client
and daemon access from that environment without changing hardware:

```bash
python3 -c 'from openrazer.client import DeviceManager; print([d.name for d in DeviceManager().devices])'
```

A missing Python client, unavailable daemon, unsupported mouse, or failed
hardware operation leaves normal evdev/uinput remapping available. Hardware
configuration is retried on the next setup/run; this does not add a daemon retry
loop or alter the existing systemd service.

## Install from source

```bash
cd mouse-control
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Run the wizard

```bash
mouse-control setup
```

The wizard discovers a mouse, captures physical button presses, asks what each button should do, initializes the preferred DPI stages through Libratbag when available, selects the mouse's maximum supported polling rate, and writes:

```text
~/.config/mouse-control/config.toml
```

When a mouse button is detected, choose **3. Remap to keyboard key**, then
physically press the desired keyboard key at the prompt. The wizard displays
its Linux name (for example `KEY_LEFTMETA`, `KEY_F12`, or `KEY_VOLUMEUP`) and
saves the existing action format, such as `BTN_EXTRA = "key:KEY_LEFTMETA"`.
To bind Ctrl itself, press and release it; Ctrl+C cancels capture and returns
to the action menu. Option **5. Enter a keyboard key code manually** preserves
manual `KEY_*` entry, including when keyboard devices cannot be opened.

Capture listens to readable keyboard and media-key interfaces simultaneously,
prefers stable `/dev/input/by-id/...-event-kbd` paths, and avoids opening the
same device twice. It ignores queued events, keys already held when capture
starts, and autorepeat. Release a held key and press it again to assign it.
Keyboard device access requires appropriate input permissions. Keyboards are
not grabbed exclusively, so desktop shortcuts (including Super and volume
keys) may still activate during capture.

## Example configuration

```toml
[device]
name = 'Logitech Gaming Mouse G502'
event_path = '/dev/input/by-id/usb-Logitech_...-event-mouse'
phys = 'usb-0000:00:14.0-4/input0'
vendor = 1133
product = 49970

[dpi]
active = 800
stages = [800, 1500, 2000, 2500, 3000]

[polling]
rate_hz = 1000

[remap]
'BTN_LEFT' = 'passthrough'
'BTN_RIGHT' = 'passthrough'
'BTN_MIDDLE' = 'passthrough'
'BTN_SIDE' = 'key:KEY_LEFTCTRL'
'BTN_EXTRA' = 'mouse:BTN_MIDDLE'
```

Supported actions:

- `passthrough`
- `disable`
- `mouse:BTN_*`
- `key:KEY_*`

The config can be edited by hand without rerunning the wizard.

## Apply the configuration

```bash
mouse-control run
```

The remapper grabs the selected physical mouse and creates a virtual input device. Depending on Fedora's device permissions, access to the source `/dev/input/event*` device and `/dev/uinput` may require elevated permissions during development.

For initial Libratbag hardware testing, using:

```bash
sudo mouse-control setup
sudo mouse-control run
```

is acceptable. We should later replace this with a least-privilege udev/systemd setup so the entire application does not need to run as root.

## DPI behavior

When Libratbag recognizes the mouse, the wizard initializes the preferred DPI stages (800, 1500, 2000, 2500, 3000) where the hardware exposes programmable resolution slots, makes 800 DPI the active/default resolution, queries the supported polling/report rates, selects the highest reported rate during initial setup, applies it immediately, and writes both settings to the configuration for future editing. The configured DPI stages, active DPI, and polling rate are applied when `mouse-control run` starts.

Unsupported mice still get generic button remapping, but their hardware DPI is not changed by this application.

Libratbag itself supports many gaming mice and Fedora's current `libratbag-ratbagd` package includes Logitech device definitions, including several G-series models.

## Scope deliberately excluded

- RGB / lighting control
- Multiple profiles
- Hardware features beyond DPI and polling

## Default DPI stages

The setup wizard uses these five project defaults:

```toml
[dpi]
active = 800
stages = [800, 1500, 2000, 2500, 3000]
```

The wizard attempts to write those values into the mouse's available Libratbag resolution slots, with **800 DPI active and default**. On later runs, the values in the configuration file are applied again, so you can edit `active` or the `stages` list without rerunning setup.

Not every mouse exposes five programmable resolution slots or accepts every DPI value. When that happens, mouse-control applies as many of the requested stages as the hardware exposes and reports the limitation rather than pretending the unsupported settings were applied.

## OpenRazer hardware behavior and manual validation

The backend uses the [OpenRazer Python client](https://github.com/openrazer/openrazer/tree/master/pylib/openrazer/client)
and per-device `has()` capabilities. DPI writes use the configured scalar
`[dpi].active` for both axes, or zero for Y on devices with fixed, X-only DPI.
This backend does not program DPI stages: `[dpi].stages` remains compatible and
is used by Libratbag. Polling setup chooses the maximum enumerated rate. If an
older daemon cannot enumerate rates, setup retains the current rate instead of
guessing a maximum. A manually configured rate is submitted to the daemon for
validation when enumeration is unavailable.

USB identity currently comes from the client's cached `_vid`/`_pid` fields
(populated by its `getVidPid()` call); that upstream compatibility detail is
isolated inside the adapter. Missing identity fields fail safely. Receivers whose
identity differs from the selected evdev mouse are not guessed by name. Two
identical VID/PID devices cannot currently be disambiguated and fall back safely.

Before claiming physical Razer validation, test:

- Discovery and identity for the actual mouse in wired/wireless modes, including
  other connected mice and receivers.
- DPI readback and cursor response at 800 DPI and an edited configured value;
  fixed-DPI devices should reject unsupported values with a warning.
- Polling enumeration, maximum selection and readback on the installed daemon.
- Setup, remapping, unplug/reconnect and the existing user service in the user's
  session; test daemon unavailability and ensure remapping still starts.
- No lighting/profile changes. Physical DPI buttons may still change the DPI;
  this backend only applies active DPI at setup/run.

The G305 flow retains USB `046d:4074` matching, enabled resolution-slot writes,
800 DPI active/default, maximum reported polling during setup, saved TOML keys,
and the runtime active-DPI fallback. Unit tests cover that behavior; a physical
G305 smoke test remains useful after deployment.

## Tests

```bash
python3 -m pytest -q
python3 -m compileall -q src tests
```

## Rebuild the RPM

```bash
sudo dnf install rpm-build python3-devel python3-setuptools python3-pytest python3-evdev
rpmbuild --rebuild mouse-control-0.4.2-1.fc44.src.rpm
```

The source RPM contains this source snapshot and the RPM spec. Release assets
also include the source tarball and SHA256SUMS. The old standalone tuple-alias
patch is retained in repository history for v0.3.3; 0.4.2 already includes that fix.

## License status

No software license has been selected. The RPM retains the existing
`LicenseRef-Proprietary` placeholder; this release does not change licensing.
