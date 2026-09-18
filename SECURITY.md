# Mouse Control security policy

## Reporting a vulnerability

Use GitHub's private vulnerability reporting for this repository when it is
available. Otherwise, open a minimal public issue asking the maintainer for a
private contact channel; do not include exploit details, device serials,
credentials, private traces, or other secrets in a public issue.

Security issues include unauthorized hardware writes, input capture outside an
explicit user workflow, privilege or device-permission expansion, updater or
release-integrity bypass, unsafe file replacement, sensitive-data disclosure,
and malformed-device/configuration input that crosses one of those boundaries.

## Supported versions

Security fixes are provided for the latest release. Older releases should be
upgraded before a report is treated as resolved. Distribution maintainers may
backport fixes under their own support policies.

## Update integrity

The updater obtains release metadata only from the official GitHub release API.
Native RPM and DEB repositories are tried first and may use their configured
package mirrors; pip-owned installations delegate to pip and its configured
index. A direct GitHub RPM, DEB, or AppImage
fallback is accepted only when its exact versioned filename is present once in
the official release, the release contains exactly one `SHA256SUMS` asset, and
the downloaded bytes match that manifest. Missing, malformed, duplicate,
unexpected, wrong-version, wrong-architecture, cross-origin, or mismatched
inputs fail closed before package installation or executable replacement.

AppImage updates are staged in the installation directory, verified before
execution, checked against the original non-symlink target identity, and
atomically replaced. This model relies on GitHub HTTPS/release-account
integrity; release checksums are not independently signed in v0.9.6.

Release CI pins third-party actions and the AppImage runtime/tool inputs to
immutable commits or SHA-256 digests. Publication generates `SHA256SUMS` from
the final five expected artifacts and refuses extra or missing files.

## Hardware-write model

Generic HID inspection and unsupported-device discovery are read-only. Known
protocol writes require exact transport, VID:PID, interface evidence, and the
driver's validated protocol semantics. Learned writes additionally require an
unambiguous current physical binding, exact model/interface fingerprints,
operation-level PROVEN evidence, bounded schema validation, and transaction
readback where the protocol permits it. Ambiguity or malformed evidence causes
abstention. A user-editable profile is not, by syntax alone, proof that a write
is authorized.

The shipped udev rules grant the active local session access to mouse-class
event devices, `/dev/uinput`, and the exact validated Logitech G305 HID++ child
interface. They do not grant blanket keyboard, USB, or hidraw access. Access to
these devices is powerful: a compromised process running as the logged-in user
could observe permitted mouse input or synthesize input through uinput.

## Privacy and network behavior

Normal remapping, discovery, notifications, macros, and hardware control do not
require network access. Mouse Control has no telemetry, analytics, crash-report
upload, credential access, browser/cookie access, or automatic trace/report
upload. Network access is limited to the explicit update command and to release
build/package-manager dependency retrieval. Support and discovery reports stay
local until the user deliberately shares them.

Normal runtime does not open arbitrary keyboards. Keyboard capture is limited
to explicit, user-initiated setup/remapping capture and raw key history is not
persisted. Macros are declarative synthetic key/button/delay sequences; they do
not execute commands, shells, or dynamic code.

Live usbmon capture is explicit and target-selected. The kernel usbmon stream
can contain traffic for other devices on the same bus; Mouse Control filters to
the selected bus/address immediately and does not persist, report, or transmit
unrelated records. Root or suitably privileged usbmon access remains inherently
sensitive.

## Service and persistence

`mouse-control install-service` creates only a per-user systemd service under
the user's configuration directory and enables it explicitly. It does not
install a root daemon or hidden persistence. The unit pins the resolved,
non-group/world-writable executable path, invokes no shell, injects no
environment values, and applies compatible process hardening. Package
installation separately supplies narrowly scoped udev rules.

## Limitations

Mouse Control handles device reports, configuration, and learned evidence as
untrusted input and aims to fail closed, but no claim of absolute security is
made. Physical validation applies only to the hardware named in the project
records. Report suspected parser denial of service, identity confusion, stale
rebind, permission broadening, or unexpected filesystem/network behavior even
when no hardware damage is demonstrated.
