# Automatic Discovery experiment handoff — 2026-09-16

Branch: `feat/automatic-hardware-discovery`
Known remote parent before this preservation commit: `5369106d335c8018080866b816129bb0484198ba`

This document is the durable handoff for the G305 Automatic Discovery experiment. It records what was actually proven on hardware, the safety boundaries that must remain intact, and the exact next work required for production integration.

## Permanent compatibility contract

v0.8.2 behavior is the release-blocking baseline for all future work. Do not ship a reduced generic mode. Preserve DPI read/write, configured stages and dpi-cycle, live reconciliation, physical DPI events and direct per-change notifications, polling where proven, battery/tray/notifications, evdev/uinput remapping, keyboard bindings and held chords, reconnect/late receiver recovery, setup rollback/preservation, service/runtime, updater/packaging, and existing public backend return contracts including X/Y DPI tuples from proven adapters.

## Safety model

Evidence remains `OBSERVED -> CORRELATED -> VALIDATED -> PROVEN`.

- HID++ is a teacher/reference, not the generic discovery backbone.
- Read evidence never grants write authority.
- Descriptor/family resemblance never grants write authority.
- Unknown writes are forbidden until an exact reversible transaction is demonstrated and independently verified.
- Initial learned writes are exact-model / exact-interface scoped.
- Stable identity is topology + descriptor based; never persist `/dev/hidrawN` or `/dev/input/eventN`.
- ACK/readback alone is insufficient; physical behavior must independently agree.
- Session lifetime can be protocol behavior. Keep the learned raw transport open when the experiment proved that requirement.
- Polling remains an enumerated demonstrated set. Do not synthesize arbitrary rates merely because a reciprocal codec is recognizable.
- Raw teacher corpora remain explicitly non-authoritative (`write_authorized=false`) until a separate promotion boundary persists PROVEN authority.

## Hardware teacher

Logitech G305 Lightspeed, mouse VID:PID `046d:4074`, receiver `046d:c53f`.

Teacher-side HID++ facts observed during the experiment: protocol 4.2, device index `0x01`, ONBOARD_PROFILES index `0x07`, REPORT_RATE index `0x09`, ADJUSTABLE_DPI index `0x1a`. Proven native DPI range was 200–12000 step 50; proven polling rates were 1000/500/250/125 Hz. These feature indexes are evidence from the teacher and must not become generic assumptions.

## DPI — PROVEN

Passive/read-side state report: report ID `0x02`, descriptor fingerprint `8ad51307a6bda2e23f88d90e890589fd063a81c09ca0aec457d89b5868886357`, byte 4 correlated with stage state. Observed stage map: 0->800, 1->1500, 2->2000, 3->2500, 4->3000. Passive evidence alone never granted writes.

Learned 20-byte DPI transaction:

- Write request prefix `11 01 1a 3a 00`; bytes 5–6 are U16 big-endian DPI; remaining payload zero.
- Write ACK prefix `11 01 1a 3a`; remaining payload zero.
- Read request prefix `11 01 1a 2a`; remaining payload zero.
- Read response prefix `11 01 1a 2a 00`; bytes 5–6 are current DPI U16 big-endian; bytes 7–8 observed as `03 20`.
- Teacher demonstrations: 800, 1500, 2000, 2500, 3000.

Persisted learned DPI operation observed at:
`~/.local/share/mouse-control/devices/learned-operations/046d-4074-68d6be33c2f016d9-dpi_value.json`

Critical session finding: an early generic promotion produced readback 1500 while physical CPI stayed around 820. Keeping the learned hidraw transport open through physical verification produced physical CPI around 1540 for requested/readback 1500. Session lifetime therefore became an explicit part of the proven behavior.

Teacher-free DPI execution succeeded through `PROVEN learned operation -> TransactionEngine -> raw HID`, with requested 1500, generic readback 1500, and independent learned read query 1500.

Numeric generalization also succeeded without teacher demonstrations of the candidate values:

- baseline 1500 -> physical ~1533.2 CPI (+2.2%)
- unseen 1600 -> readback 1600; physical ~1655/1655/1641, median ~1654.5 (+3.4%), high confidence
- unseen 1550 -> readback 1550; physical ~1569/1606/1571, median ~1571.1 (+1.4%), high confidence

The laboratory printed `NUMERIC DPI GENERALIZATION SUCCESS`. This proves the DPI field was learned as a numeric encoding rather than memorized packet replay. Do not yet widen persisted production authority to the whole sensor range; range/boundary discovery still needs explicit proof.

## Polling teacher corpus

Original corpus:
`~/.local/share/mouse-control/devices/polling-demonstrations/046d-4074-68d6be33c2f016d9.json`

It remains `write_authorized=false` and each demonstration intentionally began from Onboard mode.

Inferred Onboard-start state machine:

1. query control mode
2. enter Host mode
3. verify Host mode
4. write polling rate
5. read polling rate

Observed semantic encoding:

- `0x01` -> 1000 Hz
- `0x02` -> 500 Hz
- `0x04` -> 250 Hz
- `0x08` -> 125 Hz

Observed teacher request shapes were mode query `11 01 07 2a ...`, enter Host `11 01 07 1a 02 ...`, rate write `11 01 09 2a <raw> ...`, and rate read `11 01 09 1a ...`. These are learned evidence, not generic constants.

## Polling physical verifier

The old `sensor_calibration.estimate_peak_polling_hz()` estimates the fastest sustained event rate and was unsuitable as promotion evidence. Its ~333 Hz result at the 250 Hz teacher state was an estimator artifact caused by ~3 ms samples in the fastest quartile.

A dedicated fundamental analyzer was added for SYN_REPORT motion intervals. It handles missed frames as integer multiples, requires direct fundamental support, and rejects harmonic aliases.

Verified on hardware:

- 250 Hz: 4/4 accepted, high confidence, p50/mode 4.000 ms, inferred 250.0 Hz, 0.0% error, direct support roughly 87.0–98.6%.
- 500 Hz: 4/4 accepted, high confidence, p50/mode 2.000 ms, inferred 500.0 Hz, direct support about 99% on clean passes.
- 125 Hz: 4/4 accepted, high confidence, p50/mode 8.000 ms, inferred 125.0 Hz, direct support about 99.5–100%.

Conclusion: 250 Hz is physically correct; the old ~333 Hz result was not a real device state.

## First teacher-free generic polling write — PROVEN

The generic replay laboratory inferred its transaction from the raw corpus. For the target operation the native HID++ semantic backend was closed.

Known start: 1000 Hz / mode 0x01. Generic raw replay requested 500 Hz. Generic raw readback was 500 Hz. The raw session remained open during physical verification.

Physical passes: 500.0 Hz high, 500.0 Hz high, 500.0 Hz medium. Aggregate 3/3 accepted, high confidence, median 500.0 Hz. The program printed `GENERIC POLLING REPLAY SUCCESS`. Native was used only to establish/restore the safe boundary state.

## Host-start polling corpus

Second corpus:
`~/.local/share/mouse-control/devices/polling-host-demonstrations/046d-4074-68d6be33c2f016d9.json`

It remains `write_authorized=false`.

The corpus proved that once already in Host mode, polling changes reduce to a 3-step branch:

1. query control mode and observe Host (`0x02`)
2. write polling raw value
3. read polling raw value

There is no repeated Host-mode write.

Representative Host traces:

- query TX `11 01 07 2a ...`
- query RX `11 01 07 2a 02 ...`
- write TX `11 01 09 2a <01|02|04|08> ...`
- ACK RX `11 01 09 2a 00 ...`
- read TX `11 01 09 1a ...`
- read RX `11 01 09 1a <01|02|04|08> ...`

Teacher demonstrations covered Host 500->1000 and Host 1000->500/250/125.

## Decisive chained state-machine proof

One persistent generic raw HID session executed:

`Onboard -> 500 Hz / Host -> 250 Hz / Host`

No native backend was reopened between the two generic writes.

First transition, Onboard -> 500:

- generic readback 500 Hz
- three physical passes all high confidence
- p50/mode 2.000 ms
- aggregate 3/3 accepted, high confidence, median 500.0 Hz

Second transition, Host 500 -> 250:

The program explicitly printed `Native backend has NOT been reopened between generic writes.`

- generic readback 250 Hz
- pass 1: p50/mode 4.000 ms, inferred 250.0 Hz, 0.0% rate error, low confidence because coverage/direct was ~58.2%
- pass 2: 250.0 Hz, high confidence, ~98.0% direct
- pass 3: 250.0 Hz, high confidence, ~97.9% direct
- aggregate 2/3 accepted by threshold, medium confidence, median 250.0 Hz

The program printed `GENERIC POLLING STATE-MACHINE SUCCESS` and restored `1000 Hz, mode 0x01`.

This proves polling was learned as a stateful protocol, not a one-shot packet replay. Both Onboard-start and Host-start branches were executed generically on the same open transport.

## Current capability status

| Capability | Discover | Read | Write | Physical verify | Teacher-free target execution |
| --- | --- | --- | --- | --- | --- |
| DPI | YES | YES | YES | YES | YES |
| Polling | YES | YES | YES | YES | YES |
| Stateful polling transitions | YES | YES | YES | YES | YES |

The core Automatic Discovery research hypothesis succeeded on the G305. This does not yet mean arbitrary unknown mice are production-supported.

## Production work still required

### Polling promotion/persistence

The laboratories still print `Generic persisted polling write authority: NONE`. Do not bypass this boundary. Build a proper exact-model PROVEN polling-operation/state-machine representation containing both control-state branches, the demonstrated rate set, exact stable identity/interface, reversible safety, readback rules, and physical promotion evidence.

Do not overload the simple DPI transaction grammar. Polling is a state machine.

### Single-reader generic HID session

A production risk remains in learned DPI runtime: when a learned writer owns a hidraw stream, the competing learned event reader is suppressed to avoid reply/event races. That can suppress physical DPI event notifications on a learned-only device.

Production needs one protocol-neutral owner for the stream that can serialize requests, correlate replies, route unsolicited events, retain persistent session semantics, survive reconnect/rebind, and support DPI + polling + later battery queries/events. Native `HidSession` is the architectural teacher, but generic code must not hard-code HID++ parsing.

### Battery, reconnect, setup/runtime parity

Generic learned battery is not complete. Learned operations must re-resolve by stable identity after hidraw renumbering/disconnect. Learned polling must be exposed through DiscoveryEngine/DiscoveryBackend without changing proven adapter contracts or v0.8.2 behavior.

## Setup regressions repaired during the experiment

1. Setup review documented Enter=Finish but only accepted `s`; Enter was restored.
2. `merge_setup_config` used an obsolete positional call including `enable_service`; repaired to the current keyword-only API.
3. Finishing setup rewrote unchanged DPI/polling. Final gating now honors `choices.dpi_changed` and `choices.polling_changed`, while still applying defaults on first run and preserved preferences to a genuinely different selected device.

Latest full pytest output actually shown before the later Host/chained lab additions: `444 passed, 1 warning in 4.87s`. The warning is the existing PyGObject `GLib.unix_signal_add_full` deprecation. The Host-state and chained hardware tests later succeeded, but a later complete pytest output was not supplied in-chat. The next session MUST rerun the full suite before production integration; do not invent a final count.

## Exact next-session sequence

1. From `~/Mouse-control`, run `git status --short`, `git log -1 --oneline`, then `PYTHONPATH=src pytest -q`.
2. Confirm the two polling corpora and learned DPI operation still exist under `~/.local/share/mouse-control/devices/`.
3. Design a persisted polling learned-operation model with semantic behavior `REPORT_RATE_HZ`, exact identity/interface, demonstrated set `{125,250,500,1000}`, raw map `{1:1000,2:500,4:250,8:125}`, Onboard-start branch, Host-start branch, control prerequisites/results, reversible safety, readback verification, and exact-model scope.
4. Build an explicit promotion command that reruns a safe generic chain and persists PROVEN only after generic execution, generic readback, high/medium physical timing consensus, successful rollback, and exact identity/interface recording.
5. Build the protocol-neutral single-reader learned HID session/dispatcher before normal runtime integration.
6. Integrate learned polling into DiscoveryEngine/DiscoveryBackend while preserving native/vendor priority and contracts, demonstrated-rate restriction, reconnect/rebind, and v0.8.2 behavior.
7. Run final G305 acceptance: startup/restart, learned DPI read/write, dpi-cycle, every-press notifications, learned polling all four rates, repeated transitions, service restart, unplug/replug, late receiver insertion, no stuck uinput, battery/tray preserved, full pytest green.
8. Then move the scientific experiment to genuinely non-Logitech hardware (planned Zelotes high-DPI wireless trackball / generic MMO mouse). The next major question is whether the methodology transfers to a protocol the program did not already know.

## Reconstruction chronology

The local experimental line after remote parent `5369106` was built through these guarded installers, in order:

1. install-write-trace.py
2. install-write-discovery-pipeline.py
3. fix-discovery-adapter-dpi-contract.py
4. update-promotion-persistent-session-test.py
5. install-proven-learned-runtime.py
6. install-next-capability-tests.py
7. install-polling-verifier-stability.py
8. fix-setup-hardware-apply-gating.py
9. install-generic-polling-replay-lab.py
10. install-polling-host-state-lab.py
11. install-polling-chained-state-machine-lab.py

The complete checksumed installer bundle and a longer handoff were also preserved in the user's ChatGPT Library on 2026-09-16. These reconstruction assets are not a substitute for the user's current local working tree, but they make the experimental lineage auditable from the known remote parent.

## Decision record

We are no longer trying to prove that Automatic Discovery can learn a writable mouse capability. That has been demonstrated for DPI and polling, including polling control-state transitions.

The remaining problem is productionization: represent and execute the physically-proven learned operations in normal runtime with the same reliability, events, reconnect behavior, and feature parity as the v0.8.2 system.