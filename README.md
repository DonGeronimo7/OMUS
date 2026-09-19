# Mouse Control

The full-screen TUI is the complete interactive Mouse Control application.
The CLI remains available for scripting, diagnostics, and advanced workflows;
ordinary product capabilities are reachable from the TUI.

Lighting is an optional per-device capability. Mouse Control models native
Off, Static, Breathing, and Spectrum effects, full `#RRGGBB` color, zones,
brightness, speed, and persistence only when the exact hardware reports them.
It does not provide host-streamed animation or whole-PC RGB synchronization,
and lack of lighting support never reduces DPI, polling, remapping, button, or
battery support. Source-backed protocol knowledge improves recognition without
granting hardware write authority.

**Native Linux mouse configuration backed by automatic hardware discovery.**

Configure buttons, DPI, and polling where those controls are proven safe. If
Mouse Control has never seen your exact mouse, its guided discovery workflow
can inspect what the device exposes, learn from your actions, and produce a
privacy-conscious report that helps expand support.

[![Current release: v0.9.9](https://img.shields.io/badge/release-v0.9.9-2ea44f)](https://github.com/DonGeronimo7/mouse-control/releases/tag/v0.9.9)
[![CI](https://github.com/DonGeronimo7/mouse-control/actions/workflows/ci.yml/badge.svg)](https://github.com/DonGeronimo7/mouse-control/actions/workflows/ci.yml)
[![VirusTotal release scan](https://github.com/DonGeronimo7/mouse-control/actions/workflows/virustotal-release.yml/badge.svg)](https://github.com/DonGeronimo7/mouse-control/actions/workflows/virustotal-release.yml)
[![CodeQL](https://github.com/DonGeronimo7/mouse-control/actions/workflows/codeql.yml/badge.svg)](https://github.com/DonGeronimo7/mouse-control/actions/workflows/codeql.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/DonGeronimo7/mouse-control/badge)](https://scorecard.dev/viewer/?uri=github.com/DonGeronimo7/mouse-control)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-3DA639)](LICENSE)
![Linux](https://img.shields.io/badge/Linux-supported-6f42c1)
![Wayland](https://img.shields.io/badge/Wayland-supported-6f42c1)

> **Your unsupported mouse is exactly what we need.** If Mouse Control already
> recognizes it, great. If it does not, run discovery. Every unfamiliar device
> can reveal a protocol pattern or hardware behavior shared by other mice.

The current release is [v0.9.9](https://github.com/DonGeronimo7/mouse-control/releases/tag/v0.9.9).

## Install and run

Download the package for your system from the
[v0.9.9 release](https://github.com/DonGeronimo7/mouse-control/releases/tag/v0.9.9),
then install it as shown below.

### Fedora, Nobara, and other RPM systems

[Download the RPM](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.9/mouse-control-0.9.9-1.fc44.noarch.rpm), then run:

```bash
sudo dnf install ./mouse-control-0.9.9-1.fc44.noarch.rpm
```

### Debian, Ubuntu, Mint, and other DEB systems

[Download the DEB](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.9/mouse-control_0.9.9_all.deb), then run:

```bash
sudo apt install ./mouse-control_0.9.9_all.deb
```

### Other x86-64 Linux distributions

[Download the AppImage](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.9/Mouse-Control-0.9.9-x86_64.AppImage), then run:

```bash
chmod +x Mouse-Control-0.9.9-x86_64.AppImage
./Mouse-Control-0.9.9-x86_64.AppImage setup
```

Native packages are preferred: they install the desktop launcher, service
integration, dependencies, and device-access rules. The AppImage bundles the
user-space application but cannot replace the host's systemd, udev, or kernel
input support. An [Arch `PKGBUILD`](PKGBUILD),
[Python wheel](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.9/mouse_control-0.9.9-py3-none-any.whl),
and [source archive](https://github.com/DonGeronimo7/mouse-control/releases/download/v0.9.9/mouse_control-0.9.9.tar.gz)
are also published.

Launch the guided interface as your normal desktop user:

```bash
mouse-control
```

`mouse-control setup` and `mouse-control tui` open the same interface. Do not
run normal setup or the background service as root.

## What to expect

The full-screen terminal interface guides you through device selection,
hardware discovery, DPI, polling, button mappings, service setup, and a final
review. Nothing is saved until you choose **Review / Save**.

- Use arrow keys or `h/j/k/l` to move.
- Use Enter to select and Escape to go back.
- Use `g/G` to jump to the first or last item.
- Unknown DPI or polling support never prevents ordinary button remapping.

Mouse Control can:

- remap mouse buttons to mouse actions, keys, shortcuts, DPI cycling, or simple
  ordered macros;
- configure and verify DPI and polling/report rate on proven hardware paths;
- observe physical DPI-stage changes and send desktop notifications;
- recover remapping and supported hardware features after reconnects;
- inspect HID structure and behavior through Automatic Discovery;
- retain exact-device, path-independent knowledge that has met its evidence
  requirements; and
- update supported installations without making users reinstall each release
  by hand.

Mouse Control also models native per-device lighting where an exact backend
reports independently proven capability and write authority. Unqualified and
source-backed-only lighting writes remain disabled.

## Test an unsupported mouse

Obscure hardware is useful here. We especially welcome inexpensive OEM and
rebrand mice, smaller gaming brands, wireless and MMO mice, lightweight esports
mice, older models, configurable office mice, unusual trackballs, and devices
that normally require Windows software or are not supported by Piper/libratbag.

The shortest testing flow is:

1. Install Mouse Control and connect the mouse.
2. Run `mouse-control`.
3. Select the mouse under **Device**.
4. Open **Hardware / Discovery** and choose **Run Guided Discovery** if offered.
5. Follow the on-screen actions. You can skip discovery and still save normal
   button mappings.
6. Generate the reports below and attach them to a
   [New mouse / discovery result issue](https://github.com/DonGeronimo7/mouse-control/issues/new?template=hardware-compatibility.yml).

Guided Discovery begins read-only. For DPI-button learning it collects quiet,
normal-use, and repeated button samples so ordinary movement can be separated
from action-specific reports. Recognizing a button or state is useful evidence;
it does not by itself authorize Mouse Control to write a DPI or polling value.

### Create reports to attach

Create the simple, human-readable hardware report:

```bash
mouse-control support --guided
```

After you confirm, it saves `mouse-control-<mouse-name>-report.txt` in your home
directory. It includes selected-device and basic system information, not a dump
of unrelated USB devices.

Create the structured Automatic Discovery report in the current directory:

```bash
mouse-control discover --output mouse-control-discovery.json
```

This JSON report is allowlisted and designed for community sharing: it excludes
device paths, serial numbers, usernames, and input history. **Review every file
before posting it** and remove anything you do not want to share.

In the issue, tell us the exact model and connection type, what Mouse Control
recognized, what worked or did not, whether DPI buttons or polling changes were
observed, and what happened after reconnecting. The generated reports already
contain technical identifiers such as VID:PID when available; you do not need
to gather them manually.

Every new device can help distinguish a reusable protocol family from a
one-model quirk. OEM and rebrand mice are particularly valuable because several
brands may share controllers, firmware families, report layouts, or sensors.

## Known hardware and discoverable hardware

Not appearing in a compatibility table does **not** mean a mouse is useless to
Mouse Control.

- **Known / validated hardware** has model-specific evidence for the listed
  operations. See [`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md).
- **Discoverable hardware** can still use evdev/uinput remapping and enter the
  read-only learning pipeline even when no hardware write has been proven.

| Hardware path | Current evidence |
| --- | --- |
| Logitech G305 | Physically tested reference for remapping, DPI, DPI notifications, and 1000/500/250/125 Hz polling. |
| Other Logitech HID++ mice | Native dynamic protocol detection exists, but G305 evidence is not generalized to another model. |
| Exact modeled Razer Viper V2/V3 variants | Native 90-byte RPC implementation with DPI/polling readback plus applicable firmware and battery reads; broader physical testing remains welcome. |
| Other mice | Remapping plus safe discovery/diagnostics; hardware controls appear only when the exact operation reaches the required proof level. |

## Update

Open the normal Mouse Control application and choose **Updates** to see the
installed version and installation type. Choose **Check for Updates** when you
want to contact the official release endpoint; simply opening or redrawing the
screen does not perform a network request. When a compatible stable release is
available, the same verified updater used by the command line offers the Update
action while preserving package-manager ownership and approval.

The command-line form remains available:

```bash
mouse-control update
```

The updater recognizes documented RPM, DEB, AppImage, Python, and source
installations and respects the installation owner. It does not overwrite a
package-managed install behind the package manager's back.

```bash
mouse-control update --check   # check without changing anything
mouse-control update --yes     # update without a confirmation question
```

## Security and privacy

Normal runtime is local-only: there is no telemetry, analytics, crash upload,
or automatic hardware-report upload. The explicit updater contacts the official
GitHub release endpoint and verifies direct-download artifacts against the
release's SHA-256 manifest before installation or AppImage replacement.
Generic HID discovery remains read-only, hardware writes require exact proven
authority, and the shipped udev rules avoid blanket keyboard or hidraw access.

See [SECURITY.md](SECURITY.md) for vulnerability reporting, updater trust,
device-write, usbmon, service, and privacy boundaries.
Release checksums, SBOMs, attestations, offline provenance, and dependency-lock
policy are documented in
[`docs/SECURITY_SUPPLY_CHAIN.md`](docs/SECURITY_SUPPLY_CHAIN.md). Contributors
should also follow [`CONTRIBUTING.md`](CONTRIBUTING.md) and the
[`development policy`](docs/DEVELOPMENT_POLICY.md).

## How discovery works

Most mouse tools begin with a known model or protocol implementation. Mouse
Control also has a protocol-neutral discovery pipeline, so an unknown mouse
does not begin from zero. It combines five layers:

1. **Native protocol knowledge** — implemented adapters and a growing repertoire
   of known packet shapes, transactions, encodings, transport behavior, and
   device-family semantics.
2. **HID structural interpretation** — descriptors, collections, usages, report
   IDs, fields, lengths, interface relationships, and exact physical binding.
3. **Behavioral discovery** — reports are compared with quiet controls and with
   actions the user deliberately performs.
4. **Evidence and provenance** — observations, correlations, physical
   validation, conflicts, and source provenance remain distinct.
5. **Runtime promotion** — only an independently PROVEN operation on an
   unambiguous exact device may become writable runtime behavior.

This is a native multi-protocol mouse stack, not “HID++ plus a generic
fallback.” Direct runtime protocol adapters currently include dynamically
discovered Logitech HID++ 2 and an exact-model Razer RPC implementation.
Separately, the discovery repertoire contains sourced structural or semantic
knowledge for additional families, including ASUS ROG, SteelSeries,
Sinowealth/ODM, Attack Shark X11, AJAZZ AJ-series, MCHOSE V3, and a
BITMOUSE-style `0x72` grammar.

Those categories matter. A family in the discovery repertoire is **not** a
claim that every related device is supported, and a structural match never
grants write access. Some entries guide passive recognition or the next useful
observation only; some are deliberately write-disabled. See
[`docs/discovery-architecture.md`](docs/discovery-architecture.md) and
[`src/mouse_control/protocol_repertoire.py`](src/mouse_control/protocol_repertoire.py)
for the auditable details and provenance.

### Safety model

- Observation comes first.
- Product names or VID:PID alone never authorize a hardware write.
- Descriptor shape and changing bytes are evidence, not semantics.
- Generic HID inspection does not send feature, output, or raw hidraw writes.
- Read-side DPI correlation cannot become write authority by implication.
- Ambiguous physical devices, interfaces, or protocol responders are refused.
- Writable DPI or polling requires operation-specific proof, safe ownership,
  verification/readback where available, and exact-device binding.
- A hardware backend failure must not stop ordinary evdev/uinput remapping.

Internally, evidence progresses through `OBSERVED`, `CORRELATED`, `VALIDATED`,
and `PROVEN`. Beginners do not need to understand those states; their practical
meaning is that Mouse Control says “not yet learned” instead of guessing.

## Everyday configuration

After setup, install the user service once if you want mappings restored when
you sign in:

```bash
mouse-control install-service
mouse-control start
mouse-control status
```

Other service commands are `mouse-control stop` and `mouse-control restart`.
`mouse-control run` is the explicit foreground/debug command.

Configuration is stored at:

```text
~/.config/mouse-control/config.toml
```

The TUI can create button mappings and basic sequential macros without manual
editing. Macros consist only of key, chord, mouse-button, and millisecond-delay
steps: they cannot execute commands, Python, loops, or hardware operations.

### Measure physical CPI

The installed, vendor-neutral ruler tool measures physical CPI and observed
polling from Linux motion events without sending vendor-protocol commands:

```bash
mouse-control cpi --help
mouse-control cpi --distance-mm 50.8
```

Stop the Mouse Control service first if it owns the selected event device.

### Permissions

Native packages install Mouse Control's udev rules. If a source installation
cannot access the mouse or `/dev/uinput`, install the supplied rule:

```bash
sudo install -Dm644 src/mouse_control/udev/71-mouse-control-uaccess.rules \
  /etc/udev/rules.d/71-mouse-control-uaccess.rules
sudo udevadm control --reload-rules
```

Reconnect the mouse or log out and back in, then run:

```bash
mouse-control check-permissions
```

## Developers and protocol researchers

Source development belongs here rather than in the beginner install path:

```bash
git clone https://github.com/DonGeronimo7/mouse-control.git
cd mouse-control
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
PYTHONPATH=src pytest -q
```

Technical starting points:

- [`docs/discovery-architecture.md`](docs/discovery-architecture.md) — discovery,
  identity, evidence, learning, and write-promotion boundaries.
- [`docs/CODE_HEALTH_AUDIT.md`](docs/CODE_HEALTH_AUDIT.md) — current production
  module and protocol inventory.
- [`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md) — evidence-backed hardware
  results rather than a speculative support list.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — hardware reports and pull requests.
- [`RELEASE_NOTES.md`](RELEASE_NOTES.md) and [`CHANGELOG.md`](CHANGELOG.md) —
  current and historical release details.

The complete v0.8.2 behavior contract remains the compatibility baseline:
remapping, uinput lifecycle, reconnect recovery, notifications, proven DPI and
polling paths, persistent learned behavior, service operation, and
configuration compatibility must not regress as discovery expands.

## Maintainer: GitHub About settings

Repository settings are not stored in Git. Recommended About description:

> Native Linux mouse configuration with multi-protocol hardware discovery,
> safe DPI/polling control, remapping, and guided device learning.

Recommended topics: `linux`, `linux-gaming`, `mouse`, `gaming-mouse`, `hid`,
`usb-hid`, `evdev`, `mouse-remapping`, `device-discovery`, `dpi`.

## Credits and provenance

Mouse Control builds on public Linux input and mouse-protocol research. Its
contribution is bringing that knowledge together with evidence-driven discovery
and strict write-safety boundaries—not claiming every protocol fact was
independently discovered here. See [CREDITS.md](CREDITS.md) for the projects and
sources represented in the repertoire, the distinction between cited research
and imported code, package visibility, and attribution items that still need
maintainer review.

## License

Mouse Control is licensed under the GNU General Public License, version 3 or
later. See [`LICENSE`](LICENSE).
