%global python_sitelib %(/usr/bin/python3 -c "import sysconfig; print(sysconfig.get_path('purelib', vars={'base': '/usr', 'platbase': '/usr'}))")
%global python_version %(/usr/bin/python3 -c "import sys; print('%s.%s' % sys.version_info[:2])")

Name:           mouse-control
Version:        0.4.2
Release:        1%{?dist}
Summary:        Mouse remapping with optional hardware backends
# No license was declared in the supplied source; no redistribution grant is inferred.
License:        LicenseRef-Proprietary
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
BuildRequires:  python3-pytest
BuildRequires:  python3-evdev
Requires:       python3 >= 3.12
Requires:       python(abi) = %{python_version}
Requires:       python3-evdev >= 1.0.0
Requires:       systemd
Recommends:     libratbag-ratbagd

%description
A command-line mouse button remapper using evdev and uinput, with optional
hardware DPI and polling-rate configuration through Libratbag or OpenRazer. Includes an
interactive setup wizard and commands for managing a systemd user service.

%prep
%setup -q
# Compatibility shim: all package metadata remains in pyproject.toml.
printf 'from setuptools import setup\nsetup()\n' > setup.py

%build
/usr/bin/python3 setup.py build

%install
/usr/bin/python3 setup.py install --skip-build --root=%{buildroot} --prefix=%{_prefix}

%check
/usr/bin/python3 -m pytest -q tests
/usr/bin/python3 -m compileall -q src tests
PYTHONPATH=%{buildroot}%{python_sitelib} %{buildroot}%{_bindir}/mouse-control --help

%files
%doc README.md CHANGELOG.md
%{_bindir}/mouse-control
%{python_sitelib}/mouse_control/
%{python_sitelib}/mouse_control-*.egg-info/

%changelog
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
