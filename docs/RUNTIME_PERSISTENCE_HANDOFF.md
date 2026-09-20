# Runtime persistence handoff — 2026-09-20

## Goal and repository state

Make enabled runtime behavior reconstruct from persisted configuration and current
session/hardware readiness, particularly the approved purple battery tray.

- Branch: `codex/runtime-persistence`.
- Starting HEAD: `057a5f336b331b58f1ff5b48a2e67d32a715868e`.
- Final HEAD: the commit containing this report (resolve with `git log -1`).
- Starting working tree: clean. Final working tree is reported in the task response.
- No merge, push, tag, release, history rewrite, or reboot was authorized/performed.

## Root causes established

1. The tray made one watcher registration attempt, ignored D-Bus error replies,
   and never subscribed to watcher ownership changes or bus disconnection.
   Late/restarted watchers therefore could leave a healthy process invisible.
   Private-bus and deterministic lifecycle tests reproduce those failure cases;
   the precise watcher ordering during the originally reported boot was not logged.
2. Live cold-start testing reproduced a second failure: initial Native HID probing
   temporarily failed, the G305 selected a PROVEN learned fallback, and the
   supervisor treated that fallback as final. It had no battery provider, so no
   tray started and native/battery recovery was never attempted.
3. Boot logs contained `DpiMonitor._run() takes 1 positional argument but 2 were
   given`. The supervisor passed a readiness callback to the polling fallback,
   provoking repeated rebinds. Polling also needed to relinquish control when
   the backend generation changed so a promoted event watcher could take over.
4. The enabled per-user unit belonged to `default.target`, without graphical
   session teardown/restart coupling. The RPM shipped no user unit or login
   bootstrap. A service existed only because an earlier setup installed it.
5. Reconciliation wrote DPI/rate even when live readback already matched desired
   state, and equivalent discovery candidates were reconciled before being
   discarded. Retry paths could therefore cause unnecessary writes.

The renderer itself was already deterministic and entirely packaged Python:
no repository image, temporary asset, font, or previous rendered file is needed.
The approved `battery_pixmap` implementation and palette are unchanged.

## Lifecycle architecture

Before: one-shot bus/watcher setup was coupled to successful battery samples;
three read failures destroyed the tray. Some initial learned bindings never
retried a temporarily unavailable protocol adapter.

After:

- One systemd `omus.service` owns the runtime. Vendor and generated units share
  `WantedBy=graphical-session.target`, `PartOf=graphical-session.target`, ordering
  after graphical-session preparation, `Restart=on-failure`, a three-second
  restart backoff, no permanent start-limit exhaustion, and 15-second teardown.
  Existing process hardening and legacy-unit conflict remain.
- An XDG autostart entry invokes an isolated packaged Python login helper. It
  requires existing configuration, installs a missing per-user unit, migrates
  only the exact former generated unit, preserves custom/disabled units, and
  asks systemd to start the enabled runtime. It launches no mouse worker itself.
  Old `default.target` links are removed during service installation.
- An advisory kernel lock in the user runtime directory rejects simultaneous
  production `run` instances before hardware initialization; stale file contents
  and PIDs never determine ownership. Process exit releases the lock.
- `TraySession` exclusively owns the tray bus connection and watcher subscription.
  It subscribes before querying the current owner, handles error replies, directs
  registration to the unique owner, and uses owner revisions to handle even a
  release/reacquisition in one dispatch turn. Retries back off to 30 seconds;
  healthy operation waits for events. Bus loss reconnects/reexports the retained
  item/menu without a fresh battery sample. Teardown cancels all child tasks.
- Battery monitoring publishes unknown state when a provider is pending, retains
  the item through missing readings, and recovers on a real reading. Definitively
  unsupported devices still do not invent a battery capability. Failed discovery
  uses capped backoff and existing wake signals.
- Protocol adapters report a pending eligible probe separately from capability
  success. A learned fallback does not erase that retry intent. No new protocol,
  semantic guess, device write permission, or discovery training is introduced.
- Equivalent candidates are closed before reconciliation. DPI/rate readback skips
  matching writes; needed writes retain existing capability and verification gates.
- Polling notification fallback accepts readiness and exits on generation changes
  so the supervisor can select event monitoring after native promotion.

## Feature audit and safety boundaries

Configuration is loaded on every fresh construction. Device identity resolution,
remaps/macros, DPI stages/active setting, polling, notifications, and volatile
lighting flow through the existing runtime constructors. A new file-backed test
covers repeated constructions with representative persisted preferences.

Existing exact model/instance/profile matching, cached discovery reuse, native and
learned protocol authorization, observer ownership, generation checks, and wake
coordination remain authoritative. Generic discovery is read-only; calibrated
observations gain no write authority and do not mutate desired state. Lighting
shared-packet policy and independent capability failures are unchanged. No new HID
write operation, udev permission, updater trust change, or RGB path was added.

The full regression suite covers retained v0.8.2 behavior, G305 HID++, PROVEN
learned DPI/polling, remapping, wake/reconnect, and notifications. This is automated
compatibility evidence, not new physical qualification for other hardware.

The installed user configuration was preserved byte-for-byte. Its actual stages
are `1000/1500/2000/2500/3000`, active 1000, polling 1000 Hz, DPI notifications
enabled, and `BTN_FORWARD = "dpi-cycle"`. The request's `800/...` sequence was
not silently substituted for these saved preferences.

## Packaging and resources

RPM and Debian manifests ship the vendor user unit and XDG login bootstrap.
RPM uses standard systemd user-unit install/removal/upgrade macros. The existing
per-user unit shadows the vendor file under the same unit name, never a second
service. Python wheel and AppImage contain the same self-contained renderer and
recovery modules. AppImage service installation now selects the persistent image
path from its launcher environment rather than a temporary mounted executable.

Wheel/sdist and Fedora RPM builds were executed. A wheel installed in an isolated
system-site virtual environment rendered pixmaps while running from `/tmp`.
`desktop-file-validate` and `systemd-analyze --user verify` passed (the latter
reported sandbox socket-option warnings). Native Debian build and AppImage image
build tools are unavailable here; those artifact builds remain unverified.
Their shared implementation, manifests, and persistent AppImage service path are
code-reviewed/unit-tested, not claimed as newly built artifacts.

## Validation and installed acceptance

Exact final counts, final installation parity, and final service state are recorded
below after the last gate. All runs retain the existing external GLib deprecation
warning. Source compileall and `git diff --check` are mandatory final checks.

Private D-Bus integration exports the real item/menu on an isolated bus, verifies
battery property updates, replaces the watcher, and repeats three tray lifetimes
with joined workers. Deterministic tests additionally cover missing/failed bus,
error replies, bus replacement, delayed watcher, owner churn, shutdown, unknown
battery/recovery, duplicate exclusion, config restoration, and adapter promotion.

Installed Fedora/niri/DMS checks performed before the final cold-start correction:

- DMS restart: the same OMUS PID re-registered; one item, battery 90%.
- Three service restarts: each returned one item at 90%, eight threads and
  18 descriptors (no accumulation).
- OMUS started while DMS was stopped: exported state remained accessible; starting
  DMS registered the item without restarting OMUS.
- SIGKILL of the service: systemd restarted it after its three-second backoff,
  and one item returned. The crash-recovery sample had seven threads/17 descriptors
  during initialization, not growth.
- A second packaged `omus run` returned an already-running error before hardware
  initialization.
- A stripped-environment login helper started the service, but a sleeping/late
  native adapter exposed the initial learned-fallback defect described above.
  That failed acceptance was not counted as a pass; it led to additional fixes.

Validation levels: **Code-reviewed**, **Unit-tested**, **Integration-tested**
(including installed desktop/session integration and real battery telemetry).
**Physically validated** button/remap/notification appearance and unplug/replug
remain pending operator observation for this patch. The user's real session bus
and compositor were never killed; bus interruption is covered on controlled buses.

## Remaining acceptance and next bounded task

After one real reboot, without opening the TUI or running a recovery command:

1. Confirm the purple OMUS icon appears and reports battery.
2. Confirm pointer and saved button remaps work.
3. Cycle DPI slowly, then rapidly: each press should produce one ordered popup.
4. Unplug/replug the G305 receiver and confirm remaps, battery, and notifications
   recover without extra icons or false reconnect popups.

If anything fails, retain the boot journal for `omus.service` before restarting
it. A real reboot/logout was deliberately not simulated by stopping niri or the
user bus. The next bounded task is this operator-observed reboot/reconnect gate.

## Final automated gate

- `PYTHONPATH=src pytest -q`: **1,217 passed**, one existing GLib warning.
- `python3 -m compileall -q src tests`: passed.
- `git diff --check`: passed.
- `python3 -m build --no-isolation`: wheel and sdist built.
- `rpmbuild -ba omus.spec --define '_topdir /tmp/omus-persistence-rpm'
  --define '_tmppath /tmp'`: passed; RPM `%check` **1,217 passed**, including
  private D-Bus integration outside the socket-restricted sandbox.
- Focused battery/notification/hardware/persistence run: **76 passed** before
  the final generation-handoff regression; that regression also passes in the
  final full gate.

## Files changed

- `src/mouse_control/tray_session.py`: connection/watcher recovery owner.
- `src/mouse_control/battery.py`: retained unknown state and shutdown-safe tray.
- `src/mouse_control/runtime_lock.py`, `app.py`: runtime exclusion.
- `src/mouse_control/session_start.py`, `service.py`: login/systemd lifecycle.
- `src/mouse_control/notifications.py`: polling readiness and generation handoff.
- `src/mouse_control/hardware/{discovery_backend,native_hid,native_razer,supervisor}.py`:
  retryable native probing and non-redundant reconciliation.
- `src/mouse_control/cli.py`: startup/shutdown diagnostics.
- `packaging/omus.service`, `packaging/omus-autostart.desktop`, `omus.spec`,
  `debian/install`: installed session integration.
- `tests/test_{tray_session,tray_private_bus,runtime_persistence,battery,
  hardware_supervisor,dpi_cycle,mouse_control,terminal_app}.py`: lifecycle,
  persistence, resource, ownership, and updated behavior regressions.
- This report, `docs/PROJECT_STATUS.md`, and `docs/AI_HANDOFF_LOG.md`:
  architecture and acceptance evidence.

## Final installed cold-start evidence

The final RPM was installed through the desktop administrator authentication
prompt. All changed production modules were byte-compared with the working tree
and matched. The enabled generated unit had migrated from `default.target` to
`graphical-session.target`.

On 2026-09-20 at 01:00:13 local time, the service was stopped and reconstructed by
`env -i` with only HOME, PATH, XDG_RUNTIME_DIR, and the session-bus address, invoking
`/usr/bin/python3 -I -m mouse_control.session_start` from the installed package.
No terminal display, source path, remembered Python state, TUI, or battery refresh
command was provided.

- At 01:00:19 the actual G305 again initially selected the PROVEN learned fallback.
  This time its tray registered immediately with an unknown (`?`) battery label.
- At 01:00:27 it automatically promoted to Native HID generation 1; battery
  recovered to 90% on the same tray identity. The service PID stayed 55937.
- The polling monitor returned after promotion; its existing supervisor logged
  one stopped/retrying transition while rebuilding event monitoring.
- One OMUS entry was present in the real DMS watcher. The configuration SHA-256
  stayed `e3cefec05ba6b90cffc78f6af4f7b39e7b9642f336ccaaa2ca3539f3f11bce6b`.
- The RPM upgrade itself also restarted the prior runtime through the package's
  standard systemd lifecycle hooks before the explicit cold reconstruction.

This final test closes the previously failed boot-equivalent software gate.
It does not substitute for an actual reboot or operator-observed mouse testing.
