# Mouse Control v0.7.8

## Updater verification fix

The RPM/DEB updater now verifies the installed Mouse Control version after
DNF/APT runs. A successful package-manager exit no longer counts as an update
when it leaves the installed version behind the requested release.

This fixes direct-GitHub RPM/DEB installations where the distribution package
manager can return success with “nothing to do.” In that case, Mouse Control
downloads the validated GitHub release package through the existing secure
path, installs it through the native package manager, and verifies the version
again. The updater reports success only when the installed version reaches the
requested release.
