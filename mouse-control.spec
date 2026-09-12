Name:           mouse-control
Version:        0.6.9
Release:        1%{?dist}
Summary:        Mouse remapping with optional hardware backends
License:        GPL-3.0-or-later
Source0:        mouse_control-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  python3-build
BuildRequires:  python3-setuptools >= 77.0.3
BuildRequires:  python3-wheel
BuildRequires:  python3-pytest
BuildRequires:  python3-evdev
BuildRequires:  python3-dbus-next
BuildRequires:  pyproject-rpm-macros
BuildRequires:  systemd-rpm-macros
# The wheel installer is kept from writing bytecode below; avoid recreating it
# during RPM's post-install processing so build-time caches are not shipped.
%undefine py_auto_byte_compile
Requires:       python3-evdev
Requires:       python3-dbus-next
Requires:       systemd-udev
Recommends:     libratbag-ratbagd

%description
A command-line mouse button remapper using evdev and uinput, with optional
hardware DPI and polling-rate configuration through Libratbag or OpenRazer. Includes an
interactive setup wizard and commands for managing a systemd user service.

%prep
%autosetup -n mouse_control-%{version}

%build
%pyproject_wheel

%install
export PYTHONDONTWRITEBYTECODE=1
export PIP_NO_COMPILE=1
%pyproject_install
install -Dpm 0644 src/mouse_control/udev/71-mouse-control-uaccess.rules \
  %{buildroot}%{_udevrulesdir}/71-mouse-control-uaccess.rules
%pyproject_save_files mouse_control
# pip records bytecode even when it is not a distributable source file.  Remove
# it only after the generated file manifest has been created, then omit it from
# that manifest as well.
find %{buildroot}%{python3_sitelib} -type d -name __pycache__ -prune -exec rm -rf {} +
sed -i '\|__pycache__|d' %{pyproject_files}

%check
/usr/bin/python3 -m pytest -q tests
/usr/bin/python3 -m compileall -q src tests
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=%{buildroot}%{python3_sitelib} \
  %{buildroot}%{_bindir}/mouse-control --help

%files -f %{pyproject_files}
%license LICENSE
%doc README.md CHANGELOG.md
%doc docs/COMPATIBILITY.md
%{_bindir}/mouse-control
%{_udevrulesdir}/71-mouse-control-uaccess.rules

%changelog
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
- Replace rapid DPI notifications and keep notification failures nonfatal.

* Fri Sep 11 2026 Marc-A. Geronimo - 0.4.2-2
- License the project under GPL-3.0-or-later.
- Install active-session uaccess rules for mouse event devices and uinput.
- Use the Fedora pyproject build macros.

* Thu Sep 10 2026 Marc-A. Geronimo - 0.4.2-1
- Add physical keyboard/media-key capture with manual-entry fallback.
- Add extensible Ratbag/OpenRazer/Generic hardware backend selection.
- Preserve G305 DPI stages, polling defaults, config and service behavior.
- Keep OpenRazer optional and hardware failures nonfatal to remapping.
- Include tuple-alias fix in source; remove redundant packaging patch.
- Synchronize Python version metadata; run 38 tests and compile checks.

* Thu Sep 10 2026 Marc-A. Geronimo - 0.3.3-1
- Update package and Python version metadata to 0.3.3.

* Thu Sep 10 2026 Marc-A. Geronimo - 0.2.5-1
- Package the existing utility, including its user service controls.
- Accept tuple button aliases returned by evdev.
