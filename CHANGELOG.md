# Changelog

## 0.4.2 — 2026-09-10

Includes both changes developed since the published 0.3.3 package.

### Physical keyboard-key capture

- Wizard option 3 captures a physical keyboard or media-key press and saves the
  existing `key:KEY_*` mapping format, including Super, function and volume keys.
- Listens across accessible keyboard interfaces, deduplicates paths, and filters
  queued events, held keys and autorepeat. Ctrl+C cancels capture.
- Preserves manual key-code entry as option 5 and restores terminal state.

### Hardware backends and OpenRazer

- Adds a capability-based interface and ordered Ratbag, OpenRazer and Generic
  backend selection. Future backends can be registered without vendor branches
  in the wizard or remapper.
- Migrates Libratbag code while preserving G305 USB identity matching, enabled DPI
  stages, active/default resolution selection, maximum polling setup and runtime
  active-DPI fallback. Existing TOML configuration remains compatible.
- Adds optional OpenRazer Python/daemon support for device-reported DPI and polling
  capabilities. Matches USB VID/PID, rejects ambiguous matches and avoids guessed
  polling-rate limits. OpenRazer applies active DPI, not programmable stages.
- Hardware discovery/query/write failures warn and allow generic remapping to
  continue. No mandatory OpenRazer dependency, lighting, profiles or macros.
- Documents optional Fedora OpenRazer installation and real-hardware limitations.

### Packaging and validation

- Synchronizes RPM, Python project metadata and `__version__` to 0.4.2.
- Includes the existing evdev tuple-alias fix directly in source; the old packaging
  patch is no longer applied.
- Retains the existing remapper and systemd service behavior. RPM installation
  does not start the remapper, enable services or change input permissions.
- Full suite: 38 tests passed; Python compile checks passed. Physical Razer/G305
  smoke tests and system-wide RPM installation have not been performed.

## 0.3.3 — 2026-09-10

- Published Fedora 44 / Python 3.14 RPMs from the existing utility with its setup
  wizard and systemd user-service commands.
- Updated package/Python version metadata and included the evdev tuple button-name
  compatibility fix. Six tests passed during that package build.

## 0.2.5 — 2026-09-10

- Initial local RPM packaging of the existing mouse-control utility.
- Included service controls and the evdev tuple-alias compatibility patch.
