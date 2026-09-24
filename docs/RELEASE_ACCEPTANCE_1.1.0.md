# OMUS 1.1.0 Release Acceptance

Date: 2026-09-24

Branch: `codex/autonomous-discovery-ir`

Starting commit: `2fcd588e2675412c28737b176e42a33c16df678e`

## Scope and interpretation

This is the local pre-release acceptance record for OMUS 1.1.0. `PASS` means
the named local check was actually executed. Offline fixtures and mocks do not
constitute physical validation. `NOT EXECUTED`, `HARDWARE UNAVAILABLE`, and
`HOSTED CI REQUIRED` are deliberately distinct from failure.

The workstation's installed OMUS service was left running and unchanged. It
already owned the attached receiver, so the candidate did not perform live
HID++ writes, reconnects, remapping, or notification tests. Existing service
logs are useful context but are not candidate acceptance evidence.

## Acceptance matrix

| Capability | Implementation path | Offline tests | Physical test | Result | Evidence / command | Limitation |
|---|---|---|---|---|---|---|
| G305 identification | Native HID topology and exact interface binding | HID++/native HID regression included in full suite | Read-only host enumeration found Logitech receiver `046d:c53f` on USB hidraw interface 02 | PASS | `lsusb`; udev/sysfs inspection of `/dev/hidraw7` | The attached receiver identity was confirmed; candidate ownership was not taken and the paired slot was not re-probed. |
| HID++ read | `NativeHidBackend` and dynamically resolved HID++ features | PASS | Not run by the candidate | NOT EXECUTED | `tests/test_hidpp.py`, `tests/test_hidpp_debug.py`; focused gate below | The active installed service was not disturbed. Its prior DPI logs are not attributed to this candidate. |
| HID++ DPI write/readback | Proven G305 native operation | PASS | No candidate write | NOT EXECUTED | Full suite and focused HID++ tests | The 800/1500/2000/2500/3000 live sequence and restoration require an isolated acceptance window. |
| Report-rate read/write | Native HID++ polling path | PASS | No candidate read or write | NOT EXECUTED | Full suite | Original value was not changed; therefore no restoration was necessary. |
| Reconnect | Hardware supervisor generation/rebind path | PASS | Receiver was not disconnected | NOT EXECUTED | Full suite includes reconnect and stale-generation regressions | Avoided interrupting the active installation. |
| Remapping | evdev/uinput `MouseRemapper` | PASS | Candidate was not installed or substituted for the service | NOT EXECUTED | Full suite | Production configuration and service were not changed. |
| DPI notifications | Native event subscription through notification path | PASS | Candidate notification path not run | NOT EXECUTED | Full suite | Could not be isolated from the active installed service safely. |
| Native Razer | Native Razer protocol/backend | PASS | No supported Razer device present | HARDWARE UNAVAILABLE | `tests/test_native_razer.py`; focused gate below | Offline regression only; no physical Razer claim. |
| Discovery pipeline | Quarantine → identity → Genome → fingerprint → Advice → inference → proof/Lab | PASS | Not required for deterministic offline gate | PASS | Focused gate below; full suite | Corpus recognition never grants write authority. |
| Unknown-device safe inference | Read-only inference and bounded escalation | PASS | No safe candidate-owned unknown-device run | NOT EXECUTED | Discovery integration/hardening tests | No unknown writes were authorized. |
| Lab escalation | Canonical EvidenceGraph and missing-evidence action | PASS | No physical Lab exercise | PASS | Lab/orchestrator tests in focused gate | Professional/manual proof remains outside automatic authority. |
| Recipe persistence/invalidation | Atomic, identity/generation/evidence-bound compact recipes | PASS | Not applicable | PASS | Discovery hardening tests and full suite | Invalid, stale, symlinked, or malformed recipes fail closed. |
| TUI release surfaces | Canonical setup controller and curses renderer | PASS | Live interactive terminal session not run | PASS | TUI tests in focused gate; About license regression added | Offline coverage includes navigation, pages, resize/small terminal, long/no-device, known-device, and error states. |
| Licensing consistency | PEP 639/package/repository metadata checker | PASS | Not applicable | PASS | `python3 scripts/check_license_consistency.py` | Current tree is AGPL-3.0-or-later; historical releases retain their licenses. |
| Python package build | setuptools sdist and wheel | PASS | Not applicable | PASS | `python3 -m build --no-isolation` | Artifacts were not installed or uploaded. |
| Fedora RPM build | `omus.spec` with RPM `%check` | PASS | Package not installed | PASS | `rpmbuild -ba`; embedded gate: 1437 passed, 1 skipped | Built in an isolated `/tmp` topdir. |
| Arch package | `PKGBUILD` / `.SRCINFO` metadata | Metadata PASS | `makepkg` unavailable | NOT EXECUTED | Version/license consistency checks | Hosted or suitable Arch environment required. |
| Debian package | Debian metadata | Metadata PASS | `dpkg-buildpackage` unavailable | NOT EXECUTED | Version/license consistency checks | Suitable Debian build environment required. |
| AppImage | Repository AppImage recipe | Desktop/AppStream validation PASS | `appimagetool` unavailable | NOT EXECUTED | `desktop-file-validate`; `appstreamcli validate --no-net` | Suitable AppImage build environment required. |
| Wheel reproducibility | Clean committed-tree double build | Pending final commit | Not applicable | PASS | `scripts/check-wheel-reproducibility.sh` after the release-preparation commit | Claim is limited to the wheel. |
| SBOM | CycloneDX hosted release job and finalizer | Finalizer tests/workflow validation PASS | `cyclonedx-py` unavailable locally | HOSTED CI REQUIRED | `tests/test_release_sbom.py`; release workflow static validation | LOCAL SBOM GENERATION NOT EXECUTED. |
| Security workflow validation | Pinned actions, workflow policy, dependency locks | PASS | Hosted jobs not triggered | PASS | `scripts/verify_dependency_locks.py`; `scripts/validate_workflows.py`; security tests | CodeQL, Scorecard, provenance, signing, and hosted release jobs still require their protected hosts. |

## Local environment and physical evidence

- Fedora Linux 44, kernel `7.2.5-200.fc44.x86_64`.
- USB enumeration exposed Logitech receiver `046d:c53f`.
- `/dev/hidraw7` resolved to USB interface 02 with Logitech USB Receiver
  metadata. Live path numbers are locations, not persistent identities.
- `omus.service` was active throughout inspection. It was not restarted,
  replaced, or reconfigured.
- No physical write was sent by the candidate. No firmware, bootloader,
  arbitrary report, or unknown-device experiment was attempted.

## Focused offline gate

The focused HID++, native Razer, Discovery, Lab, TUI, release, SBOM, and
security suite was run with:

```bash
PYTHONPATH=src python3 -m pytest -q \
  tests/test_hidpp.py tests/test_hidpp_debug.py tests/test_native_razer.py \
  tests/test_discovery_core.py tests/test_discovery_execution.py \
  tests/test_discovery_integration.py \
  tests/test_discovery_integration_hardening.py \
  tests/test_deferred_discovery.py tests/test_discovery_lab.py \
  tests/test_lab_orchestrator.py tests/test_lab_expert_tools.py \
  tests/test_tui_presentation.py tests/test_setup_tui.py \
  tests/test_setup_tui_entry.py tests/test_setup_tui_polished.py \
  tests/test_cli_tui_parity.py tests/test_release_metadata.py \
  tests/test_release_sbom.py tests/test_security_invariants.py \
  tests/test_workflow_security.py
```

Result: **303 passed in 1.05 seconds**.

## Artifact record

| Artifact | Size | SHA-256 | Metadata / content result |
|---|---:|---|---|
| `omus-1.1.0-py3-none-any.whl` | 584,963 bytes | `8441695a2f3e04702542a96126541d89f6f5f8d4170ec6fb4788891300c29e50` | `omus` 1.1.0, Python `py3-none-any`, AGPL-3.0-or-later expression and required license/provenance files present |
| `omus-1.1.0.tar.gz` | 1,335,620 bytes | `723b1e2c5f810c65d71dd502ff8de99348474f1830650cf090ba2d380554ef3d` | Source archive includes `.SRCINFO`, package recipes, tests, application data, and required license/provenance files |
| `omus-1.1.0-1.fc44.noarch.rpm` | 737,490 bytes | `b63ef9855de6bae7fad5712d789bbecde3c50180a7befcd504f49be7f1d09aae` | `omus` 1.1.0-1.fc44, noarch, AGPL-3.0-or-later; desktop, AppStream, udev, and license/provenance files present |
| `omus-1.1.0-1.fc44.src.rpm` | 1,377,875 bytes | `39af64f789644d1430d3faf8cb6eb5829b183db58c475218b96837a2ecc9e744` | Fedora source package built successfully |

Artifact member-name inspection found no `.git`, caches, bytecode, personal
environment files, private keys, or token-shaped credentials. References to
`/tmp` and `/home/mgeronimo` in the sdist are confined to historical handoff
documentation and test fixtures/assertions; the wheel contains no such paths.

## Licensing and administrative follow-up

- The release candidate and its package metadata are
  `AGPL-3.0-or-later`. Separate commercial licensing remains available;
  historical releases retain their applicable historical licenses.
- No CLA or DCO mechanism grants future outside contributions for commercial
  dual licensing. Contribution documentation continues to gate such code
  pending legal review. No outside core-code contribution requiring that grant
  was identified in this release.
- The `bitmouse-72` fixture remains research-only, write-disabled, and excluded
  from first-party provenance assertions.
- Icon provenance remains the documented repository-history evidence; no new
  authorship assertion is made.

## Remaining release gates

The local source, package, license, safety, and workflow-readiness checks pass.
Protected hosted CI must still generate/validate the CycloneDX SBOM and execute
the configured CodeQL, Scorecard, checksums, provenance/SLSA, artifact, and
signing/verification jobs. Candidate physical G305 operations remain
unexecuted because taking ownership would have disturbed the active installed
service. Razer hardware was unavailable.

These are documented non-blocking limitations for beginning hosted release
gates; they are not represented as executed acceptance.

## Hosted gate correction

The first protected CI run for pull request #24 failed the
`repository-security` job because Ruff found two unused imports in test files.
All licensing, dependency-lock, workflow-policy, Python 3.12/3.13/3.14, and RPM
steps that completed in that run passed; the reproducible-wheel step was
skipped after the lint failure. The two imports were removed without changing
test behavior or runtime code. This correction requires a new release-candidate
commit and a complete rerun of local and hosted gates; commit `589ceaed` and
its local artifact hashes are superseded for publication.

The first tagged artifact run then failed before publication because Ubuntu
24.04's system setuptools rejected the modern PEP 639 SPDX-string license
metadata. Python, AppImage, RPM, and the three Python test jobs passed, while
the Debian failure correctly skipped publish, SBOM, provenance, and
VirusTotal. The Debian job now creates a system-site-aware virtual environment
and installs the repository's hash-locked build backend before invoking
`dpkg-buildpackage`; reverting to legacy license metadata was rejected because
it would remove the required wheel `License-Expression` contract.
