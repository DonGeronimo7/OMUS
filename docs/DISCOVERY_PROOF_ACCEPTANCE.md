# Discovery proof acceleration — installed G305 acceptance

## Goal and review anchors

Persist capability knowledge, never stale hardware state. Starting candidate:
`4640054ceb36f8923401ce5203edba8c03994e41`, over verified main
`9b93b4a8453d675f84cb7d407cc5105efde8c062`. Work remains on
`codex/discovery-proof-acceleration`; the acceptance commit contains this report.
The earlier implementation/design report is
[DISCOVERY_PROOF_ACCELERATION_HANDOFF.md](DISCOVERY_PROOF_ACCELERATION_HANDOFF.md).
Its “uninstalled / pending physical validation” statements describe that earlier
checkpoint, not this acceptance.

## Result and scope

**PASS: installed G305 acceptance and local gates.** Publication/merge is gated
separately on hosted checks. No release/version metadata changed; no tag or
release was created. This is Fedora 44, niri and DankMaterialShell evidence for
this USB G305 only. No non-G305 or Razer hardware validation is implied.

The user explicitly retained the current OMUS stages
**1000 / 1500 / 2000 / 2500 / 3000**. Configuration stayed byte-identical. The
mouse's onboard native sequence remains **800 / 1500 / 2000 / 2500 / 3000**.
An OMUS write of 1000 followed by a native press selecting 800 is correct: a
volatile software DPI write does not rewrite or advance the onboard stage list.

## Acceptance correction

Investigation of variable reconnect latency uncovered an existing supervisor
error: non-forced recovery could discard a newly selected native backend because
its static topology signature equaled the old backend's. Matching paths and
layout are not evidence of a usable session. The optimization now applies only
to non-native discovery settling; native replacement advances the generation,
closes the old backend and causes consumers to reacquire current hardware state.
Native-adapter affinity and stale-generation suppression remain enforced.

The new regression failed before the correction, then passed. It verifies that
same-signature native recovery retains the replacement, performs no restoration
write, suppresses a second stale replacement, and cycles from the replacement's
live 1500 DPI to 2000 rather than from historical 3000 or saved preference 1000.
Files: `hardware/supervisor.py`, `tests/test_hardware_supervisor.py`.

This is a demonstrated correctness defect found during timing investigation;
the measurements do not isolate it as the sole cause of every delayed trial.
No sleeps, polling worker, protocol packet, write authority or hot-path query
was added. Existing non-native pending-discovery regression coverage still passes.

## Physical evidence

**Physically validated**, user observations corroborated by runtime logs:

- Native slow/rapid presses: initial ten transitions had ten corresponding
  notifications and no software-cycle writes. Repeated on the corrected RPM;
  user confirmed values and actual sensitivity, including rapid presses.
- Configured software stages: all five written and canonically read back, with
  user-confirmed sensitivity and notifications. Repeated after correction.
- Mixed ownership: native 800 → OMUS 1000 → native 1500 → OMUS 2000, then further
  native/software alternation after reconnect and power-cycle. Canonical live
  reads and cycler state agreed; observations never performed a second write.
- Receiver removal/reinsertion: remapping and battery returned. A temporary
  acceptance hook requested exactly one ordinary `DpiCycler.cycle()` immediately
  after the existing monitor's readiness signal. Corrected-build readback and
  notification were 1000; subsequent native stages reflected real hardware.
- Mouse off/on with receiver attached: user confirmed recovery, native events,
  software stages, remaps and battery; repeated on corrected RPM.
- Service restart: original 3000 was read without applying saved 1000. Final
  corrected ordinary service read live 1000, restored one 90% battery tray item,
  and retained normal remapping. No final instrumentation remains in the service.

No physical button on this configuration emitted the configured BTN_FORWARD
software-cycle action. Software-cycle acceptance therefore used the **installed
normal DpiCycler, supervisor, native driver and notification monitor**, via a
local temporary control hook while the ordinary service was stopped. It did not
change mappings, add a second evdev reader, or open a competing HID owner. Do not
represent this as physical BTN_FORWARD validation. Temporary instrumentation
added one control thread; all reported final resource counts exclude it.

## Knowledge, live state and invalidation

**Observed on hardware:** fresh owner binding resolved current protocol 4.2,
feature revision 1, routing and bounds. An isolated temporary profile store saved
that real receipt, restored capability values without live write authority, and
refused a simulated descriptor mismatch. The mismatch changed a copy of the
physical graph, not firmware, real descriptors or the user's profiles. Those
cache/invalidation checks issued zero HID requests. Warm proof also issued zero
requests. Live DPI was independently read as 1000 before and after the benchmark.

**Unit-tested / Integration-tested:** static cache never restores current DPI,
receiver slot or write authority; changed identity/layout/revision, ambiguous or
closed owner, malformed reports, failed confirmation and independent capability
failure remain covered. No dangerous firmware mismatch or flash experiment was
performed. Cached recipes cannot authorize persistence. Learned writable
operations retain their independent exact-model PROVEN gates. Read-only discovery
and calibrated observations cannot call setters or update desired hardware state.

## Timing and resources

Local observations, not universal latency guarantees or CI timing thresholds.
Probe/cycle counts are deterministic assertions; physical presentation timing is
operator-observed, not independently instrumented at the compositor.

| Measurement | Baseline/reference | Final corrected candidate |
| --- | ---: | ---: |
| Warm proof after live owner exists | no owner-reuse API | 73.474 µs median / 1,000 calls; **0 HID requests** |
| Cold known Discovery, topology already built | 1,241.902 ms | 1,243.041 ms |
| Cold discovery traffic | 18 requests + one 7-slot query batch | unchanged |
| Native bind | approximately 974 ms prior trial | 978.280 ms |
| Service start to remapping | 2,428 ms accepted persistence | 2,646 ms final ordinary restart; 2,444 ms from application start log |
| Initial live DPI read | approximately 10 ms | 10.910 ms |
| Settled software cycle | approximately 20 ms / 2 requests | 19.984 ms median across seven measured cycles; synchronized cycles **2 requests** |
| First software cycle after wake epoch | live resynchronization required | 54.488 ms / **3 requests**: sync, write, confirmation |
| Receiver return to remapping | 108.840 ms prior acceptance | 86.921 ms |
| Receiver return to DPI management | 5,074.202 ms prior acceptance | 5,001.211 ms |
| Readiness to confirmed deliberate cycle | not previously measured | 64.932 ms; cycle itself 15.586 ms / 2 requests |
| Ordinary-service threads / descriptors | 8 / 18 installed baseline | 8 / 18 |
| Settled CPU sample | prior source 1–2 ticks / 25 s | 3 ticks / 25 s; no persistent acceptance worker |

The pre-correction candidate had 3.00, 9.10 and 9.24-second management trials.
Fresh baseline comparisons measured 1.13 and 2.09 seconds with different unplug
intervals, so the earlier variability was investigated rather than averaged away.
A separate unattended trial only recovered after mouse activity resumed and is
not a clean awake reconnect measurement. The corrected physical trial had two
unanswered bounded probe batches followed by one successful batch, then no
continuing rediscovery loop. Recovery still waits for real receiver/mouse replies;
this change does not promise an instantaneous cold wireless handshake.

The final resource sample was external and did not count input events; it is a
settled low-activity observation, not an assertion of precisely zero input. Three
CPU ticks are 30 ms on this host (100 Hz), approximately 0.12% of one core over
25 seconds. No meaningful thread/descriptor increase was observed. No new
Python-level work was added to the synchronized DPI hot path.

## Exact validation

**Code-reviewed / Unit-tested / Integration-tested:**

- New regression, before fix: **1 failed, 12 deselected**, demonstrating refusal
  to replace the old same-signature native backend.
- Focused supervisor/proof/notification/reconnect/cycle suites: **106 passed**,
  one existing external GLib deprecation warning, **4.34 s**.
- Final post-physical `PYTHONPATH=src pytest -q -rs`: **1,282 passed**, no skips,
  one existing GLib warning, **15.93 s**.
- Final post-physical RPM `%check`: **1,282 passed**, no skips, one existing GLib
  warning, **17.71 s**, plus compileall and packaged CLI smoke checks.
- `python3 -m compileall -q src tests scripts fuzz`: passed.
- `git diff --check`: passed.
- Ruff, workflow security policy and dependency lock validation: passed.
- Wheel/sdist built with `python3 -m build --no-isolation`.
- RPM built with `rpmbuild -ba omus.spec --define '_topdir
  /tmp/omus-acceptance-rpm' --define '_tmppath /tmp'`.
- `rpm -V omus`: passed on host; installed changed Python files match source.
- Intermediate sandbox runs had **1,281 passed / 1 skipped** because a private
  D-Bus socket was disallowed. The final permitted runs above exercised that test.

Installed corrected RPM SHA-256:
`133530e1ab93f0a0c7e7ceb9f106bcbb0a3ea56784d782c913a5251c2a225130`.
Its runtime sources match this acceptance commit; subsequent documentation does
not alter installed behavior. Build artifacts and raw local evidence are not
committed. DNF invalidated a pending offline update transaction during local
reinstall; this was disclosed and was not rescheduled automatically.

Evidence is local `/tmp/omus-acceptance-*`: native/mixed journal snapshots,
`runtime-{first,edge,baseline,diagnostic,fixed}.log`, `proof-final.log`,
`service-final.log`, `idle-final.json`, `final-source.log`, `final-rpm.log`.
No serial-bearing hardware captures or user configuration are published.

## Git handoff and next bounded task

The acceptance commit includes the narrowly scoped correction, its regression,
this report and coordination-document updates. Intentional implementation history
is retained. Main is changed only through the authorized protected PR after all
required hosted checks pass; the final delivery records actual branch/main hashes
and PR URL. No tag, release or version change is authorized by this acceptance.

Next bounded task: review the recorded G305-only evidence and hosted checks for
integration. Broader HID-BPF / multi-instrument Discovery remains out of scope.
