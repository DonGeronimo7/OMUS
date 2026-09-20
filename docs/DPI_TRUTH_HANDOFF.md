# Hardware-authoritative DPI handoff — 2026-09-20

## Goal and repository state

Keep configured stage choices separate from current hardware DPI, without adding
redundant transactions to ordinary switching. Continue runtime persistence work
on `codex/runtime-persistence`, starting at clean `2f4d162`. The final commit is
the commit containing this report; the final task response records its hash and
working-tree state. No push, merge, tag, release, reboot, or history rewrite.

Requests: user attachments
`781408e8-31f2-4379-9ce8-9304d4115242/Pasted text.txt` (DPI correctness) and
`c91f7ad3-185e-45f9-b010-c47d80a66e78/Pasted text.txt` (performance).

## Root cause and state flow

The faulty cycler seed and native-event-to-software-cycle routing were already
present in `2bd6208` (`Stabilize hardware control and reconnect lifecycle`), before
the persistence changes. This is a pre-existing defect exposed by reboot
acceptance, not evidence that the tray patch changed mouse sensitivity.

Before: saved active DPI seeded the cursor; startup reconciliation restored it;
an onboard stage event read hardware and then advanced the independent software
cursor/wrote another DPI. A legacy setter without readback could notify its
requested value, and a failed learned read could return cached DPI as confirmed.
The boot journal also shows learned fallback followed by native promotion and a
1000-DPI restoration. The saved stage list still started at 1000, unlike the
user-requested 800. Fixture reproduction initially failed 10 of 11 truth tests.

After:

- Runtime reconciliation preserves live DPI and stage programming. The existing
  explicit supervisor restore policy remains available to management callers;
  ordinary runtime passes `restore_dpi=False`. Polling safety gates are unchanged.
- A new cycler starts unknown and silently reads authoritative DPI. A saved
  active value is never evidence. An unready first press cannot guess.
- Backend/wake generations invalidate the cursor. Software cycling serializes
  cursor selection, write, and confirmation against backend replacement.
- A confirmed setter result is reused; a legacy setter gets one readback.
  An unchanged failed transition emits no requested-value popup. Confirmed
  quantized results use the actual accepted value. Exceptions resynchronize
  without inventing success.
- Native stage events update observed state and notify hardware truth, with no
  second write and no desired-state mutation. Learned explicit cycle triggers
  retain their separate, independently authorized write path.
- Reconnect resynchronization is silent. Polling observations also update the
  cursor. Failed learned reads clear stale truth and raise `HardwareError`.
- Existing notifier queues, D-Bus connection reuse, `replaces_id=0`, and serialized
  per-press software notifications remain. There are no new sleeps, polling loops,
  per-press config loads, resource searches, or subprocesses.
- The battery item caches its five rendered pixmaps until percentage changes;
  identical snapshots do not enqueue refreshes. Artwork and tray recovery logic
  are unchanged.

## Files and tests

Runtime: `remapper.py`, `notifications.py`, `cli.py`,
`hardware/supervisor.py`, `hardware/discovery_backend.py`, `battery.py`.
Tests: new `tests/test_dpi_truth.py`; updated DPI-cycle, hardware, supervisor, and
battery tests. Documentation: this report, project status, and handoff log.

Coverage includes opposite saved/live values, off-list DPI, unknown startup,
first ready press, unchanged/error/quantized writes, rapid serialized presses,
native observation without writes, silent reconnect, generation/wake invalidation,
legacy one-read confirmation, no backend reselection, stale learned read rejection,
and battery render/refresh reuse. Updated old tests no longer assert the removed
double-cycle or unconfirmed-success behavior.

## Validation

**Unit-tested / Integration-tested**:

- `git diff --check`: pass.
- `python3 -m compileall -q src tests`: pass.
- `PYTHONPATH=src pytest -q`: **1234 passed, 1 warning in 18.20s**.
- `python3 -m build --no-isolation`: sdist and wheel built.
- `rpmbuild -ba omus.spec --define '_topdir /tmp/omus-dpi-rpm' --define '_tmppath /tmp'`:
  **1234 passed, 1 warning in 16.95s** in RPM %check; RPM built successfully.
- Warning: existing GLib signal API deprecation. Full gates ran with local socket
  access so private D-Bus integration was executed, not skipped.

## Physical hardware and performance

Device: exact selected USB Logitech G305, transport 3, 046d:4074. Measurements use
the existing native driver/session and canonical ADJUSTABLE_DPI readback.
Programmatic tests stop the runtime first, restore the initial DPI, close their
session, and restart the service; there is no competing input/HID reader.

Baseline installed persistence build:
- Native binding: 4782.987 ms; authoritative initial read: 19.963 ms.
- Ten immediate software changes: approximately 19.956–20.010 ms each, two HID
  transactions per change (write plus canonical read), all confirmed values equal
  the values delivered to a test notifier.
- Initial hardware DPI was 2500. The baseline subsequent service start restored
  saved 1000, demonstrating the unwanted startup mutation.
- Fresh service process to configuration: 206.377 ms; native/device ready:
  5745.906 ms; workers: 5808.266 ms; tray registration: 5865.403 ms.
  The baseline did not separately log successful evdev grab or truthful DPI sync.
- Settled baseline: eight threads, 18 descriptors, 44,260 KiB RSS; ps cumulative
  CPU 0.3% over 440 seconds (includes initialization, not an idle-only interval).

The maintained timing logs measure cycle entry to canonical confirmation, plus
evdev action enqueue to result/notification enqueue. They exclude compositor
presentation, physical switch debounce, and movement-sensitivity perception.
New tests assert operation counts instead of brittle CI time thresholds.

Corrected installed build (same-version local RPM replacement, no release):
- Installation via Fedora graphical authentication completed; `rpm -V omus`
  returned no differences. Saved choices now start at 800; polling remains
  1000 Hz and BTN_FORWARD/other remaps remain unchanged.
- Native binding: 4730.132 ms; initial standalone read: 19.959 ms; cycler silent
  synchronization: 9.966 ms.
- Ten immediate changes: 19.927–20.068 ms, median **19.991 ms** versus baseline
  **19.991 ms**; total 199.935 versus 199.868 ms. Exactly **two HID transactions**
  per synchronized change both before and after. No measurable hot-path penalty
  in this small sample; it is not a statistical latency guarantee.
- Hardware/readback/test-notifier sequence:
  **800 → 1500 → 2000 → 2500 → 3000**, twice. Starting/restored DPI was 3000.
- Two installed fresh-service starts silently synchronized **3000**, despite
  persisted active=800. Neither produced startup DPI notifications or DPI
  reconciliation writes; polling logs explicitly report preserved native mode
  and no automatic polling write. Tests additionally assert no DPI/stage writes
  on runtime construction or rebind.
- Representative fresh-process start to configuration: **201.239 ms**; selected
  mouse: **5985.566 ms**; native ready: **5985.958 ms**; DPI synchronized:
  **6015.444 ms** (read itself **9.877 ms**); workers ready: **6019.000 ms**;
  tray registered: **6091.359 ms**; evdev/uinput operational: **6169.980 ms**.
  The preceding corrected start took 6293.410 ms to remapping operational.
  These are fresh process/service initialization samples, not a new system boot.
  Native discovery dominates the variation; there is no broad startup redesign.
- Settled corrected runtime: **eight threads, 18 descriptors**, matching baseline.

**Physically validated (instrumented G305)**: actual canonical reads/writes and
the programmatic sequence above, plus startup preservation of non-default DPI.
Live journal also shows slow and rapid onboard transitions with matching
hardware-confirmed values and `replaces_id=0` notifications. These passive native
events have no requested software DPI and intentionally produce no extra write.
Operator sensitivity/reconnect acceptance is tracked separately below.

## Safety, compatibility, and limits

No new write path, HID feature guess, protocol packet, host-mode takeover, udev
permission, or generic write is introduced. Exact identity, ambiguity refusal,
PROVEN learned-operation authorization, canonical native readback, and one-reader
session ownership remain enforced by existing backends. Observed/calibrated
transitions do not gain write authority or update desired hardware state.

The full automated gate covers the v0.8.2 compatibility surface, native HID++,
PROVEN learned DPI/polling, ordinary remapping, reconnect, notification, runtime
persistence, packaging, and security tests. This is automated coverage, not a
claim of newly physically validated hardware or every device backend.

Known performance floor: current cold native probing scans receiver slots and
features, taking seconds; ordinary synchronized cycles reuse the bound session
and cached capabilities. No speculative discovery redesign was included.
Physical sensitivity, slow/rapid real-button acceptance, receiver reconnect,
and actual reboot timing require separately observed evidence.


## Acceptance follow-up at the correctness checkpoint

The user reported no popups immediately after USB reconnect and slow popups on
restart, then clarified this occurs **only during initial recovery/startup**.
The journal confirms subsequent five-stage notifications resumed. This is not
full performance acceptance: reconnect management readiness took **16041.523 ms**
after device-return, while remapping resumed at **71.546 ms**. A 72.334-second
sample including reconnect used 0.19 CPU seconds (0.263% of one core), retaining
eight threads, 18 descriptors, and 43,996 KiB RSS. This is not idle-only CPU.

Next bounded task: profile the existing HID++ probe/recovery delay, preserve exact
identity/ambiguity checks, and remove only demonstrated unnecessary waits.
Physical button-to-visible timing, settled idle CPU, and reboot acceptance are
not established by the transaction benchmark.

## Recovery performance correction after checkpoint afdc25b

The user clarified that absent/mistimed popups occur only in the initial
startup/reconnect window. Existing sequential ROOT version probes waited up to
750 ms for each of seven candidate receiver slots; a nonresponsive pass measured
approximately 755 ms per query. This is independent of the 20 ms DPI write path.

`HidSession.probe_protocol_versions` now overlaps **only these existing read-only
ROOT version queries** within one unchanged timeout window. The sole reader
routes replies by complete device/feature/function/software identity, routes
matching protocol errors, and wakes every pending probe on disconnect.
Normal requests keep their existing serialized path. No additional thread,
reader, persistent route cache, generic write API, timeout reduction, fixed G305
slot, or early return after finding one responder is introduced.

`connect_hidpp20` still evaluates every slot and rejects multiple responders,
reusing the verified version response rather than querying it again. Feature IDs
still resolve dynamically through ROOT on each new session. Compatibility
transports without the optional probe operation keep their serial API.

Tests cover out-of-order responses, issuing all probes before waiting, exact
reply identity, errors, disconnect, invalid/duplicate slots, zero/multiple/single
responders, and no duplicate version read. Full source gate: **1244 passed,
1 warning in 13.41s**. RPM %check: **1244 passed, 1 warning in 15.52s**.
Compileall and diff checks pass.

A bounded source runtime using the complete production discovery path selected
Native HID at 1654.553 ms, synchronized 3000 at 1674.453 ms, registered the tray
at 1752.189 ms, and became remapping-operational at 1832.639 ms (logging-relative
process milestones). A complete-route G305 benchmark bound in 1608.335 ms and
again confirmed **800 → 1500 → 2000 → 2500 → 3000**, twice, with exactly two HID
transactions per change. This route includes passive Discovery overhead, unlike
the earlier direct-native binding measurement.

Direct-native diagnostic attempts after the USB reinsert received no responses;
they are not passed hardware tests. The production-route measurements above are
the successful evidence. An error-decoding hypothesis was inspected against
[Logitech's public HID++ specification](https://lekensteyn.nl/files/logitech/logitech_hidpp10_specification_for_Unifying_Receivers.pdf),
but no observed packet evidence justified changing error decoding; it is unchanged.


## Final installed acceptance

The second local RPM installation completed, and `rpm -V omus` reported no
differences. Installed service process start to configuration was 201.770 ms;
native/device selection 2269.805 ms; silent hardware synchronization 2289.691 ms
(read itself 9.920 ms); watcher ready 2292.966 ms; workers 2293.152 ms; tray
2349.381 ms; remapping operational **2428.494 ms**. Startup preserved live 3000
DPI despite saved active=800, with no restoration burst or startup DPI popup.

The user explicitly reported **“Timing and sensitivity now agree”** after the
faster build, then performed a separate requested USB unplug/reinsert trial.
That final instrumented trial recorded:
- device-return → remapping: **108.840 ms**;
- device-return → management/DPI watcher ready: **5074.202 ms**, versus the earlier
  **16041.523 ms** trial;
- silent synchronization to **3000**, with an **8.960 ms** hardware read;
- subsequent confirmed/readback/native-notification sequence:
  **800 → 1500 → 2000 → 2500 → 3000**, twice, all `replaces_id=0`;
- no native-observation software write. A native onboard press has no requested
  software DPI; the separate ten-cycle software benchmark verifies request =
  readback = notifier value with two transactions each.

**Physically validated on this G305**: post-readiness slow/rapid popup and
sensitivity agreement (operator report), automatic USB recovery (journal and
operator trial), non-default restart preservation, and native canonical
readback/software-cycle transaction counts. No other mouse model is newly
claimed physically validated.

The remaining startup/reconnect readiness window is explicit: this is faster
bounded protocol initialization, not instant hardware readiness. The measured
5.07-second reconnect sample includes existing discovery/retry/device response
behavior; it is not a guaranteed upper bound. Events before an authoritative
observer exists cannot be reconstructed into truthful historical DPI popups.
No arbitrary sleeps, reduced timeout, fixed receiver slot, cached volatile DPI,
or skipped ambiguity checks were used to hide this limitation.

Physical switch-to-presentation latency was not instrumented. The approximately
20 ms figures measure software cycle/confirmation (and test notifier enqueue),
not desktop animation. Actual cold system reboot was not repeated; the user had
already confirmed persistence after reboot, and reboot remains user-controlled.

Next bounded task: user-controlled cold-boot acceptance of this exact installed
candidate, checking live DPI, native readiness, remapping, and the purple tray.
The earlier profiling follow-up is complete for this scoped correction.

Final settled resource sample after acceptance: **eight threads, 18 descriptors,
44,416 KiB RSS**, and **zero additional CPU ticks over 44.080 seconds** at the
host's /proc accounting resolution. This is a bounded observation of essentially
idle behavior, not proof of literally zero CPU consumption. No duplicate worker,
descriptor growth, or repeated retry activity was observed after recovery.

Commits: `afdc25b` (DPI truth checkpoint), `68a042c` (bounded protocol probing),
and the documentation-only evidence commit containing this final paragraph.
Starting tree was clean; final tree/hash are verified in the task response.
`main` is untouched; all earlier intentional commits retained; feature branch
not pushed, remote not needed for a push check; no merge, tag, release, or reboot.
