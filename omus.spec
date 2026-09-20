Name:           omus
Version:        1.0.3
Release:        1%{?dist}
Summary:        One Mouse Universal System for Linux
License:        GPL-3.0-or-later
URL:            https://github.com/DonGeronimo7/OMUS
%global python_version 1.0.3
Source0:        omus-%{python_version}.tar.gz
BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  python3-build
BuildRequires:  python3-setuptools >= 77.0.3
BuildRequires:  python3-wheel
BuildRequires:  python3-pytest
BuildRequires:  python3dist(pyyaml)
BuildRequires:  python3-evdev
BuildRequires:  python3-dbus-next
BuildRequires:  python3-packaging
BuildRequires:  pyproject-rpm-macros
BuildRequires:  systemd-rpm-macros
BuildRequires:  desktop-file-utils
# The wheel installer is kept from writing bytecode below; avoid recreating it
# during RPM's post-install processing so build-time caches are not shipped.
%undefine py_auto_byte_compile
Requires:       python3-evdev
Requires:       python3-dbus-next
Requires:       python3-packaging
Requires:       systemd-udev
Provides:       mouse-control = %{version}-%{release}
Obsoletes:      mouse-control < %{version}-%{release}

%description
OMUS discovers, configures, and remaps mice using evdev and uinput, with validated
hardware DPI configuration through native protocol drivers. Includes an
interactive setup wizard and commands for managing a systemd user service.

%prep
%autosetup -n omus-%{python_version}

%build
%pyproject_wheel

%install
export PYTHONDONTWRITEBYTECODE=1
export PIP_NO_COMPILE=1
%pyproject_install
install -Dpm 0644 src/mouse_control/udev/71-mouse-control-uaccess.rules \
  %{buildroot}%{_udevrulesdir}/71-mouse-control-uaccess.rules
install -Dpm 0644 packaging/appimage/omus.desktop \
  %{buildroot}%{_datadir}/applications/omus.desktop
for size in 512 256 128 64 48 32 24 16; do
  install -Dpm 0644 assets/icons/hicolor/${size}x${size}/apps/omus.png \
    %{buildroot}%{_datadir}/icons/hicolor/${size}x${size}/apps/omus.png
done
desktop-file-validate %{buildroot}%{_datadir}/applications/omus.desktop
install -Dpm 0644 packaging/omus.metainfo.xml \
  %{buildroot}%{_datadir}/metainfo/io.github.DonGeronimo7.OMUS.metainfo.xml
install -Dpm 0644 packaging/omus-autostart.desktop \
  %{buildroot}%{_sysconfdir}/xdg/autostart/omus.desktop
install -Dpm 0644 packaging/omus.service \
  %{buildroot}%{_userunitdir}/omus.service
%pyproject_save_files mouse_control
# pip records bytecode even when it is not a distributable source file.  Remove
# it only after the generated file manifest has been created, then omit it from
# that manifest as well.
find %{buildroot}%{python3_sitelib} -type d -name __pycache__ -prune -exec rm -rf {} +
sed -i '\|__pycache__|d' %{pyproject_files}

%check
/usr/bin/python3 -m pytest -q tests
/usr/bin/python3 -m compileall -q src tests
for command in omus mouse-control mouse-control-discover mouse-control-sensor-calibrate mouse-control-write-trace mouse-control-write-promote mouse-control-discovery-monitor mouse-control-polling-promote; do
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=%{buildroot}%{python3_sitelib} \
    %{buildroot}%{_bindir}/$command --help >/dev/null
done
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=%{buildroot}%{python3_sitelib} \
  %{buildroot}%{_bindir}/mouse-control cpi --help >/dev/null

%post
%systemd_user_post omus.service

%preun
%systemd_user_preun omus.service

%postun
%systemd_user_postun_with_restart omus.service

%files -f %{pyproject_files}
%{_userunitdir}/omus.service
%config(noreplace) %{_sysconfdir}/xdg/autostart/omus.desktop
%license LICENSE
%doc README.md CHANGELOG.md CREDITS.md SECURITY.md
%doc docs/COMPATIBILITY.md
%{_bindir}/mouse-control
%{_bindir}/omus
%{_bindir}/omus-launcher
%{_bindir}/mouse-control-launcher
%{_bindir}/mouse-control-discover
%{_bindir}/mouse-control-sensor-calibrate
%{_bindir}/mouse-control-write-trace
%{_bindir}/mouse-control-write-promote
%{_bindir}/mouse-control-discovery-monitor
%{_bindir}/mouse-control-polling-promote
%{_udevrulesdir}/71-mouse-control-uaccess.rules
%{_datadir}/applications/omus.desktop
%{_datadir}/icons/hicolor/*/apps/omus.png
%{_datadir}/metainfo/io.github.DonGeronimo7.OMUS.metainfo.xml
%changelog
* Sat Sep 19 2026 Marc-Anthony Geronimo - 1.0.3-1
- Add the OMUS-branded rounded purple-gradient battery tray indicator.

* Sat Sep 19 2026 Marc-Anthony Geronimo - 1.0.2-1
- Accept bounded HTTPS redirects to exact GitHub release-asset infrastructure.

* Sat Sep 19 2026 Marc-Anthony Geronimo - 1.0.1-1
- Preserve native evdev frames and isolate input from hardware management.
- Stabilize sleep, wake, reconnect, and synthetic-state recovery.
- Record the accepted final Python baseline before the planned Rust migration.

* Sat Sep 19 2026 Marc-Anthony Geronimo - 1.0.0-1
- Rebrand the public product as OMUS while preserving Mouse Control compatibility.

* Sat Sep 19 2026 Marc-Anthony Geronimo - 0.9.9-1
- Complete the canonical TUI, updater, service controls, and CLI capability parity.
- Add safe per-device, multi-zone lighting models with write authority unchanged.
- Add hardened VirusTotal scanning for the five primary release artifacts.

* Fri Sep 18 2026 Marc-Anthony Geronimo - 0.9.8-1
- Harden release security, provenance, dependency auditing, and workflow policy.
- Prevent shutdown wake/rebind races and repeated DPI or polling reconciliation.
- Preserve PROVEN-only hardware writes and the established compatibility contract.

* Fri Sep 18 2026 Marc-Anthony Geronimo - 0.9.7-2
- Render the interactive device-selection frame before live backend initialization.
- Preserve service-suspension ordering, full Rediscover, and exact evidence checks.

* Fri Sep 18 2026 Marc-Anthony Geronimo - 0.9.7-1
- Fix strict incremental-RPM asset selection across packaging version formats.
- Reduce cold imports, reuse immutable HID knowledge, and remove idle UI polling.
- Add repeatable timing and retained-memory performance validation.

* Fri Sep 18 2026 Marc-Anthony Geronimo - 0.9.6-2
- Restore the prior service state after every unsaved setup exit.
- Reuse exact-device discovery evidence when established users configure a mouse.
- Route every interactive launch through the canonical full-screen TUI.

* Fri Sep 18 2026 Marc-Anthony Geronimo - 0.9.6-1
- Require SHA-256 verification before direct release artifact installation.
- Pin release workflow actions and AppImage runtime/tool inputs.
- Harden user-service installation and document security/privacy boundaries.

* Thu Sep 17 2026 Marc-Anthony Geronimo - 0.9.5-1
- Add persistent known-device startup, progress reporting, and reconnect affinity.
- Add responsive TUI navigation, Vim controls, and basic sequential macros.
- Preserve evidence-driven discovery and PROVEN-only hardware writes.

* Thu Sep 17 2026 Marc-Anthony Geronimo - 0.9.4-1
- Add the pre-v1 temporal dialogue, proof-state, experiment, and report foundations.
- Keep generic discovery read-only and operation writes PROVEN-only.
- Preserve the v0.8.2 and v0.9.3 compatibility contracts.

* Thu Sep 17 2026 Marc-Anthony Geronimo - 0.9.3-1
- Release descriptor-backed Automatic Hardware Discovery acceptance.
- Preserve native HID++, remapping, polling, notifications, and v0.8.2 compatibility.
- Keep unknown-device discovery read-only and learned writes PROVEN-only.

* Wed Sep 16 2026 Marc-Anthony Geronimo - 0.9.1-1
- Add the keyboard-driven setup TUI and guided unknown-mouse discovery.
- Separate live DPI testing from explicit stage acceptance with rollback.
- Fix interactive updater input visibility and exclusive keyboard capture.
- Preserve the complete v0.9.0 runtime and safety contract.

* Wed Sep 16 2026 Marc-Anthony Geronimo - 0.9.0-1
- Release Automatic Discovery learned runtime integration.
- Preserve the v0.8.2 compatibility contract.

* Tue Sep 15 2026 Marc-Anthony Geronimo - 0.8.2-1
- Stabilize native hardware control and reconnect fallback behavior.
- Preserve remaps and setup configuration while hardware options are reviewed.

* Mon Sep 14 2026 Marc-Anthony Geronimo - 0.8.1-1
- Add revisitable wizard navigation, live numeric DPI testing, and safe rollback.
- Show readable polling rates and select only when writes are supported.
- Persist accepted DPI stages for runtime cycling.

* Mon Sep 14 2026 Marc-Anthony Geronimo - 0.8.0-1
- Add held keyboard chord bindings with shared-modifier and disconnect cleanup.
- Allow an explicit configuration file for isolated runtime testing.

* Mon Sep 14 2026 Marc-Anthony Geronimo - 0.7.11-1
- Verify RPM updates from the installed package version after DNF completes.
- Make `mouse-control update --yes` non-interactive for DNF upgrades and fallback installs.

* Mon Sep 14 2026 Marc-Anthony Geronimo - 0.7.10-1
- Keep the battery tray visible through transient HID++ read timeouts.
- Remove the redundant device name from the tray menu and refresh terminal branding.

* Mon Sep 14 2026 Marc-Anthony Geronimo - 0.7.9-1
- Bundle a self-contained Python 3.12 runtime in the AppImage.
- Prevent host Python ABI mismatches with native extensions such as evdev.

* Mon Sep 14 2026 Marc-Anthony Geronimo - 0.7.8-1
- Verify installed RPM and DEB versions before reporting updater success.
- Fall back to the validated GitHub package when native repositories do not
  actually upgrade a direct-release installation.

* Mon Sep 14 2026 Marc-A. Geronimo - 0.7.7-1
- Polish the terminal launcher mark and strengthen icon visibility at small sizes.

* Mon Sep 14 2026 Marc-A. Geronimo - 0.7.6-1
- Fix Arch build dependencies for the updater release.

* Sun Sep 13 2026 Marc-A. Geronimo - 0.7.5-1
- Add the safe cross-distribution update command and package its version
  comparison dependency.

* Sun Sep 13 2026 Marc-A. Geronimo - 0.7.4-1
- Release community hardware support reporting with a local, read-only workflow.

* Sun Sep 13 2026 Marc-A. Geronimo - 0.7.3-1
- Add the on-demand, read-only mouse-control support report workflow for
  community hardware testing. Reports remain local and include optional guided
  button capture plus selected-mouse HID descriptor topology only.
- Add the optional StatusNotifierItem battery monitor with a live icon,
  tooltip, and standards-based DBusMenu battery details.

* Sun Sep 13 2026 Marc-A. Geronimo - 0.7.2-1
- Release the native Logitech HID++ stabilization milestone.
- Add reconnect-safe backend rediscovery and service control commands.

* Sat Sep 12 2026 Marc-A. Geronimo - 0.6.9-1
- Prepare Linux-wide community hardware testing with doctor diagnostics,
  privacy-safe reports, Debian/Arch/AppImage packaging definitions, issue
  templates, and a compatibility matrix.
- Preserve the validated passive G305 HID++ implementation unchanged.

* Fri Sep 11 2026 Marc-A. Geronimo - 0.6.3-1
- Add controlled generic Logitech HID++ capability and device-name discovery.
- Keep normal runtime passive and preserve independent G305 DPI query/event routes.
- Validate notifications on Logitech G305 046d:4074 without changing firmware mappings.

* Fri Sep 11 2026 Marc-A. Geronimo - 0.5.0-1
- Synchronize the validated G305 HID++ DPI monitor and Freedesktop notifications.
- Preserve safe setup/service recovery, configurable DPI stages and maximum polling.
- Package the scoped G305 hidraw uaccess rule and current 89-test source tree.

* Fri Sep 11 2026 Marc-A. Geronimo - 0.4.2-3
- Notify through Freedesktop D-Bus when a hardware backend reports a DPI change.
- Submit one independent DPI notification per physical press and keep notification failures nonfatal.

* Fri Sep 11 2026 Marc-A. Geronimo - 0.4.2-2
- License the project under GPL-3.0-or-later.
- Install active-session uaccess rules for mouse event devices and uinput.
- Use the Fedora pyproject build macros.

* Thu Sep 10 2026 Marc-A. Geronimo - 0.4.2-1
- Add physical keyboard/media-key capture with manual-entry fallback.
- Add extensible hardware backend selection.
- Preserve G305 DPI stages, polling defaults, config and service behavior.
- Keep OpenRazer optional and hardware failures nonfatal to remapping.
- Include tuple-alias fix in source; remove redundant packaging patch.
- Synchronize Python version metadata; run 38 tests and compile checks.

* Thu Sep 10 2026 Marc-A. Geronimo - 0.3.3-1
- Update package and Python version metadata to 0.3.3.

* Thu Sep 10 2026 Marc-A. Geronimo - 0.2.5-1
- Package the existing utility, including its user service controls.
- Accept tuple button aliases returned by evdev.
