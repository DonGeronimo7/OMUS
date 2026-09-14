# Mouse Control v0.7.11

## RPM updater reliability

RPM ownership detection now retains the stable package name. After DNF runs,
Mouse Control verifies the installed RPM version; warnings, noisy output, or a
nonzero DNF result cannot report a false failure when the target version is
installed.

If a native DNF upgrade leaves the old version installed, Mouse Control still
uses the validated GitHub RPM fallback and verifies the final installed version.

`mouse-control update --yes` now passes DNF `--assumeyes` for both native and
fallback installs. Updates without `--yes` keep their normal confirmation flow.
