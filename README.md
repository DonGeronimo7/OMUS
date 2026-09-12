# Mouse Control

## Download v0.6.9

Release artifacts are prepared for the intended v0.6.9 release.
See [CHANGELOG.md](CHANGELOG.md) for the complete history.

```bash
sudo dnf install ./mouse-control-0.6.9-1.fc44.noarch.rpm
/usr/bin/mouse-control --help
```

The unsigned RPM requires Python 3.14, evdev, dbus-next and systemd, and recommends Libratbag. OpenRazer remains optional. Installation does not activate remapping or enable the user service. It installs narrowly scoped logind/uaccess rules for mouse event devices and `/dev/uinput`; see [Device permissions](#device-permissions). Use `/usr/bin/mouse-control` if an older pip installation shadows the command.

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

Setup does not rewrite firmware button actions. In particular, a G305 DPI
button configured as `resolution-cycle-up` remains firmware-controlled, so
normal mouse and keyboard assignment is independent of experimental DPI
observation.

Capture listens to readable keyboard and media-key interfaces simultaneously,
prefers stable `/dev/input/by-id/...-event-kbd` paths, and avoids opening the
same device twice. It ignores queued events, keys already held when capture
starts, and autorepeat. Release a held key and press it again to assign it.
Keyboard device access requires explicit access granted by the local desktop
environment. Keyboards are not grabbed exclusively, so desktop shortcuts
(including Super and volume keys) may still activate during capture.

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

[notifications]
dpi_changes = true

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
`notifications.dpi_changes` defaults to `true` when absent, so existing configs
receive DPI-change popups. Set it to `false` to disable them.

## Hardware Compatibility Testing

Mouse Control needs community testing across manufacturers and models. Logitech
HID++ devices receive enhanced capabilities only when they have been safely
discovered and cached; Libratbag and OpenRazer support is optional. Other Linux
mice use the generic evdev remapping fallback where technically possible.
Results are community-tested, reported working, experimental, or not yet tested
rather than universal compatibility claims. See [the compatibility matrix](docs/COMPATIBILITY.md).

1. Install the native package for your distribution and run `mouse-control setup`.
2. Verify remapping and test the native DPI button if present.
3. Verify DPI notifications and polling control if supported.
4. Run `mouse-control doctor --report` and submit the result using the hardware template.

`mouse-control doctor` is read-only: it reports only relevant mouse names and
VID:PID values, selected backends, safe HID++ cache status, and runtime
readiness. It excludes user names, home paths, serial numbers, cache contents,
and unrelated USB devices. `mouse-control doctor --fix` merely proposes the
native package-manager command and requires confirmation; it never runs a
privileged command, changes repositories, or enables optional backends.

For normal users, native packages are recommended. `pip` may need Python
development headers when it must compile `evdev`, particularly on a new Python
version without a compatible wheel.

## Apply the configuration

```bash
mouse-control run
```

The remapper grabs the selected physical mouse and creates a virtual input device.

## Device permissions

The Fedora RPM installs `/usr/lib/udev/rules.d/71-mouse-control-uaccess.rules`.
It gives the active local logind session an ACL for event devices that udev
classifies as mice, excluding any interface also classified as a keyboard, plus
`/dev/uinput`. It does not change device modes, add users to `input`, or grant
access to every logged-in user. The ACL is tied to the active local seat, so
`mouse-control setup` and the systemd user service can run as the desktop user.

After installing or upgrading the RPM, log out and back in (or reconnect the
mouse) and check the session with:

```bash
mouse-control check-permissions
mouse-control setup
```

Source installs can copy the same rule to `/etc/udev/rules.d/` and reload udev:

```bash
sudo install -Dm644 src/mouse_control/udev/71-mouse-control-uaccess.rules \
  /etc/udev/rules.d/71-mouse-control-uaccess.rules
sudo udevadm control --reload-rules
```

Do not run `mouse-control run` as root. `uinput` can inject input events, so
access is deliberately limited to the active local session. The supplied rule
does not grant direct keyboard-event access: reading those events can expose
keystrokes. The wizard's manual `KEY_*` entry remains available if the desktop
does not already permit temporary keyboard capture. Administrators who require
physical keyboard capture must provide their own, explicitly reviewed access
policy for that device; this project intentionally does not install one.

## DPI behavior

When Libratbag recognizes the mouse, the wizard initializes the preferred DPI stages (800, 1500, 2000, 2500, 3000) where the hardware exposes programmable resolution slots, makes 800 DPI the active/default resolution, queries the supported polling/report rates, selects the highest reported rate during initial setup, applies it immediately, and writes both settings to the configuration for future editing. The configured DPI stages, active DPI, and polling rate are applied when `mouse-control run` starts.

Unsupported mice still get generic button remapping, but their hardware DPI is not changed by this application.

The G305 uses a passive HID++ monitor because Libratbag's cached active-resolution
state does not reliably follow firmware-owned DPI changes. The monitor resolves
the selected hidraw interface dynamically by exact USB identity and physical path.
During explicit diagnostic discovery, HID++ ROOT queries discover the protocol
version, DEVICE NAME (`0x0005`), and ADJUSTABLE DPI (`0x2201`) feature indexes.
Runtime monitoring then opens the node read-only and sends no commands. On the
physically validated G305, DEVICE NAME is index `0x03`, ONBOARD PROFILES
(`0x8100`) is index `0x07`, and ADJUSTABLE DPI is index `0x1a`. The native
`0x11 0x01 0x07 0x10 STAGE` packet is an ONBOARD PROFILES resolution-slot
notification; its passive event index remains independent of the dynamically
discovered ADJUSTABLE DPI query index. These indexes are device-specific, not
universal Logitech values. The stage byte indexes the configured `[dpi].stages`.

Normal `mouse-control run` startup does not issue ROOT queries because ratbagd
owns the active HID++ request/reply path. It loads metadata from
`~/.cache/mouse-control/hidpp-capabilities.json` (or `$XDG_CACHE_HOME`). An
uncached or stale device keeps Libratbag configuration and ordinary remapping;
only passive DPI notifications remain disabled until the diagnostic is run.
Entries are isolated by VID/PID, validated structurally, rebound to the current
exact hidraw identity, and expire after 30 days.
Existing hand-written `dpi-cycle` mappings remain parseable for compatibility,
but setup does not offer or require that action. OpenRazer retains its existing
monitoring path; generic devices do not start a monitor.

Changes are sent directly to `org.freedesktop.Notifications` on the user session
D-Bus using the lightweight `dbus-next` library. Each call supplies the previous
notification ID as the replacement ID, so rapid hardware DPI cycling updates one
popup instead of stacking several. A missing notification server, session-bus
startup race or notification error never affects evdev/uinput remapping. An
application-owned cycle notifies immediately after a successful hardware write
and never notifies after a failed write.

### Logitech HID++ discovery and read-only DPI diagnostic

Run `mouse-control debug-dpi`, press the physical DPI button several times, then
press Ctrl+C. If ratbagd is active, the command temporarily stops it (system
authorization may be requested), finds unambiguous Logitech HID++ devices,
performs the short initialization exchange, saves the resulting capability
metadata, and restores ratbagd in an exception-safe cleanup path. It then opens
the selected node read-only and prints interrupt-IN reports. For a validated
decoder, pressing the physical DPI button teaches the diagnostic the separate
unsolicited-event feature index; that observed index is persisted independently
from the ROOT-discovered `0x2201` query index. Conflicting candidate indexes are
not saved. It never changes a
firmware button mapping or polls HID++ continuously. Hidraw node numbers are
deliberately not hardcoded.

The installed udev rule grants the active local logind session access only to
the G305 HID++ child interface matched through its parent HID device
(`KERNELS=="0003:046D:4074.*"`, `DRIVERS=="logitech-hidpp-device"`). It does
not grant access to all hidraw devices or even all Logitech receiver interfaces.
After installing the rule, reload it and reconnect the receiver (or reboot):

```bash
sudo install -Dm0644 src/mouse_control/udev/71-mouse-control-uaccess.rules \
  /etc/udev/rules.d/71-mouse-control-uaccess.rules
sudo udevadm control --reload-rules
```

If diagnostic access is still denied before reconnecting, it prints an exact
temporary `setfacl` command for that one node. Do not broadly change
`/dev/hidraw*` permissions.

If an earlier experimental setup already persisted `button 8`, restore the
native action once before testing:

```bash
ratbagctl chanting-squirrel profile 0 button 5 action set special resolution-cycle-up
ratbagctl chanting-squirrel profile 0 button 5 action get
```

The second command must report `resolution-cycle-up`. Current setup runs never
change this mapping again.

For OpenRazer hardware, use the same procedure and its supported DPI readback
tool/API in place of `ratbagctl`. Physical Ratbag/OpenRazer hardware and desktop
notification-server behavior remain manual validation items.

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
- No lighting/profile/button-mapping changes. G305 DPI notification observes
  the native firmware action passively; other Logitech models require their own
  hardware-validated event profile before this monitor is enabled for them.

The G305 flow retains USB `046d:4074` matching, enabled resolution-slot writes,
800 DPI active/default, maximum reported polling during setup, saved TOML keys,
and the runtime active-DPI fallback. Unit tests cover that behavior; a physical
G305 smoke test remains useful after deployment.

## Tests

```bash
python3 -m pytest -q
python3 -m compileall -q src tests
```

## License

Mouse Control is licensed under the GNU General Public License, version 3 or
later. See [LICENSE](LICENSE). It does not bundle libratbag, OpenRazer, evdev,
or systemd; those projects retain their own licenses.

## Rebuild the RPM

```bash
sudo dnf install python3-build python3-devel python3-pytest python3-evdev python3-dbus-next \
  pyproject-rpm-macros rpm-build systemd-rpm-macros
python3 -m build --sdist
rpmbuild -ba mouse-control.spec --define "_sourcedir $PWD/dist"
```

The source RPM contains this source snapshot and the RPM spec. The old
standalone tuple-alias patch is retained in repository history for v0.3.3;
v0.4.2 already included that fix.
