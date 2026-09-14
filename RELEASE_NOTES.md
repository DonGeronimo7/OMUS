# Mouse Control v0.7.6

## Universal updater

`mouse-control update` and `mouse-control update --check` are available in the
published RPM, DEB, AppImage, and Python packages. Mouse Control detects the
running installation and safely delegates to its owner.

This release also includes the terminal-native launcher, Mouse Control icon,
and corrected native package dependencies, including the Arch build fix. It
supersedes the unpublished v0.7.5 tag.

System-package-owned files are never manually overwritten, AppImage replacement
is atomic, release assets are validated by name and architecture, source
checkouts are not automatically modified, and `--check` is non-mutating.
