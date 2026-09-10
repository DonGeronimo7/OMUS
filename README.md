# Mouse Control

A command-line mouse utility for Linux that remaps buttons with evdev and uinput and configures hardware DPI and polling rates through Libratbag on supported mice.

## Download v0.3.3

Download from the [v0.3.3 release](https://github.com/DonGeronimo7/mouse-control/releases/tag/v0.3.3).

- **mouse-control-0.3.3-1.fc44.noarch.rpm** — installable package for Fedora 44 and Python 3.14.
- **mouse-control-0.3.3-1.fc44.src.rpm** — source package containing the source snapshot, RPM spec and compatibility patch.
- **SHA256SUMS** — checksums for both RPMs.

## Install

Run these commands in the directory containing your download:

```bash
sudo dnf install ./mouse-control-0.3.3-1.fc44.noarch.rpm
/usr/bin/mouse-control --help
```

The package requires Python 3.14, evdev and systemd. It recommends `libratbag-ratbagd` for hardware DPI control. This is a locally built, unsigned RPM.

## Use

```bash
/usr/bin/mouse-control setup
/usr/bin/mouse-control run
```

The interactive wizard discovers a mouse, captures button presses and saves mappings in `~/.config/mouse-control/config.toml`. Supported actions include passthrough, disabling a button, mapping to another mouse button and mapping to a keyboard key.

For supported hardware, the wizard attempts to initialize DPI stages of 800, 1500, 2000, 2500 and 3000, with 800 active/default, and selects the highest reported polling rate. Hardware capabilities may limit the settings applied. Unsupported mice can still use generic button remapping.

The utility also includes `install-service`, `start`, `stop`, `restart` and `status` commands for its systemd user service. Installing the RPM does not activate the remapper or enable a service. The setup wizard may offer to enable it.

Access to the physical input device and `/dev/uinput` is required. This RPM preserves the existing permission model; it does not configure device permissions. If an earlier pip installation shadows the command, use `/usr/bin/mouse-control` explicitly. A previously generated user service may still reference that earlier installation; inspect its `ExecStart` before switching it over.

## Release details

Version 0.3.3 packages the existing 0.2.5 working source, including its user-service controls, with package and Python version metadata updated to 0.3.3. It includes a compatibility patch accepting tuple aliases returned by evdev when resolving button names. Without this patch, the existing left-button test reports `BTN_272` instead of `BTN_LEFT`.

All six existing tests and the build's command-line help check passed. Both RPMs passed digest verification. Hardware remapping and system-wide installation were not tested as part of packaging.

## Rebuild on Fedora 44

```bash
sudo dnf install rpm-build python3-devel python3-setuptools python3-pytest python3-evdev
rpmbuild --rebuild mouse-control-0.3.3-1.fc44.src.rpm
```

For the original build, RPM tools were downloaded and extracted into a local workspace. Build dependency checking was bypassed because some available Python modules were not registered as RPMs; the build and test steps still ran successfully.

## License status

No software license has been selected for this project. The RPM spec uses `LicenseRef-Proprietary` as a placeholder; this publication does not add an open-source license.
