# Mouse Control v0.7.5

## Universal updater

`mouse-control update` and `mouse-control update --check` are now included in
every documented release package. Mouse Control detects the running
installation and safely delegates to its owning installation mechanism:

- RPM/DNF installations
- DEB/APT installations
- AppImage
- Python/pip installations
- safe reporting for source, editable, and unsupported installations

`mouse-control update` supports Mouse Control's documented installation methods
and safely reports installations that cannot be updated automatically.

System-package-owned files are never manually overwritten. AppImage replacement
is atomic, release assets are validated by name and architecture, source
checkouts are not automatically modified, and `--check` is non-mutating. User
configuration and service state are preserved through supported updates.
