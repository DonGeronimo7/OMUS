# Mouse Control Project Status

Last updated: 2026-09-12

## Current direction

Move hardware configuration gradually from daemon/library integrations to
validated native HID protocol drivers. Keep evdev/uinput as the universal
remapping path. Generic HID is a discovery and transport layer, not a universal
DPI or polling protocol; vendor-specific writes remain disabled until their
reports are understood and physically validated.

## Current release baseline

- Version: `0.6.9`
- Base branch at start of this work: `main`
- Base commit: `345bd4d` (`ci: verify RPM package output`)
- Validated before this branch: 108 tests, Python compileall, AppImage, DEB,
  sdist, wheel, and Fedora 44 RPM CI. Arch/AUR metadata exists but has not been
  validated by the current CI workflow.
- This feature branch does not change the package version and is not a release.

## Backend behavior

### evdev/uinput

- Discovers mouse-like input devices.
- Captures buttons and applies software remaps.
- Must continue even when hardware DPI or polling configuration is unavailable.

### Libratbag (legacy, retained)

- Currently performs the validated G305 DPI read/write, DPI-stage programming,
  active/default stage selection, and polling-rate read/write operations.
- It is not yet bypassed by the native HID++ implementation.

### Logitech HID++

- Exact G305 identity: `046d:4074`.
- Physically validated protocol: HID++ 4.2.
- Dynamically discovered G305 features include device name `0x0005` and
  adjustable DPI `0x2201`; feature-table indexes must never be hard-coded.
- Normal runtime uses cached metadata and read-only passive DPI notifications.
- `mouse-control debug-dpi` is the explicit active discovery workflow and
  coordinates with ratbagd.

### OpenRazer

- Optional existing backend; physical validation remains incomplete.

### Generic HID / evdev fallback

- `mouse-control debug-hid --seconds 10` selects an evdev mouse and matches its
  hidraw interfaces by bus type and exact VID:PID.
- It prints report descriptors and captures unique input reports for a bounded
  interval using read-only file access.
- It sends no HID feature or output reports.
- Unsupported hardware still receives normal evdev remapping.

## Zelotes F33 target

The target listing is the Zelotes F33 wireless trackball: 4800 DPI, eight
buttons, Bluetooth 5.0/3.0, and a 2.4 GHz USB receiver. Zelotes supplies a
Windows configuration utility, but no verified public DPI/polling protocol or
VID:PID is currently recorded in this repository.

Required physical evidence, preferably using the 2.4 GHz receiver first:

1. Run `mouse-control debug-hid --seconds 10` and record the selected VID:PID,
   matching hidraw interfaces, and report descriptors.
2. During each bounded capture, press the DPI control and every extra button.
3. Review the output for privacy before attaching it to an issue or development
   note.
4. If hidraw access is denied, use the discovered exact identity to design a
   narrow udev rule; do not grant access to all hidraw devices.
5. Reverse-engineer configuration writes separately, using the official
   Windows utility or controlled USB captures. Do not infer write packets only
   from ordinary input reports.

## Native backend roadmap

1. Collect and validate the F33 USB-receiver identity and descriptors.
2. Add a protocol-driver registry whose drivers explicitly claim supported
   transport/VID:PID/interface combinations.
3. Add read-only F33 capability probing if its protocol supports it.
4. Implement DPI/polling setters only after request and response formats are
   verified, with strict value validation and failure translation.
5. Implement native G305 HID++ DPI and report-rate operations.
6. Prefer each native driver ahead of Libratbag only after physical validation;
   remove Libratbag in a later, explicit compatibility change.

## Validation for this branch

- `113 passed`
- `python -m compileall -q src tests` passed
- `git diff --check` passed

No physical F33 validation has been performed yet.
