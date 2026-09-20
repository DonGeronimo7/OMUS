# Discovery proof acceleration — local review handoff

## Goal and repository state

Reuse established, capability-specific protocol knowledge without granting writes
from a backend name, a family score, or a persisted discovery report.

- Phase 1 completed through issue [#19](https://github.com/DonGeronimo7/OMUS/issues/19)
  and protected PR [#20](https://github.com/DonGeronimo7/OMUS/pull/20).
- Stable local/remote `main`: `9b93b4a8453d675f84cb7d407cc5105efde8c062`.
  Its tree exactly matched persistence head `3940afd`; accepted runtime code is
  unchanged from `bdf260c`. All eight required PR checks passed. The user approved
  publishing the integration summary and reported successful actual cold boot.
- Phase 2 branch: `codex/discovery-proof-acceleration`, starting clean at that
  main commit. Final implementation commit is the commit containing this handoff;
  its hash and final working-tree state are recorded in the delivery message.
- Phase 2 is local only. No installation, push, PR, merge, tag, release, or reboot.
  Brief source-runtime benchmarks restored the installed service in `finally`.

## Architecture and files

`proof_state.py` retains the existing experiment `ProofState`, `OperationProof`,
and orthogonal `OperationEvidence`. `CapabilityProof` adds a frozen, derived
receipt, not another persisted promotion state machine. Its projected stages are
UNKNOWN, READ_PROVEN, WRITE_SEMANTICS_KNOWN, WRITE_BOUNDED, WRITE_VERIFIED, and
PERSISTENCE_PROVEN. A trusted existing implementation can supply independent
PROVEN operation evidence; Discovery need not issue a ceremonial write.

Every ordinary write receipt requires all of: proven read semantics, identified
capability, known command semantics, legal bounds, known packet, safe shared
state, authoritative confirmation, understood failure handling, unambiguous
routing, explicit compatibility, volatile operation, and satisfied runtime
policy. Missing predicates appear as named blockers. Persistence additionally
requires save/commit, profile/bank, power-cycle, flash, mode, wear, and recovery
facts plus demonstrated reconnect/power-cycle persistence and recovery. There
is no newly authorized persistence operation.

`protocol_repertoire.py` converts existing native code into structured
`ProtocolOperation` recipes for HID++ sensor DPI, HID++ report rate, and Razer
XY DPI. These recipes carry source references and prerequisites, not generic
executable packets or permission to experiment. Existing backend-only scopes
and automatic-experiment restrictions remain intact.

`protocol_discovery.py` derives per-capability receipts from the live driver's
ROOT-resolved feature identities, revisions, and enumerated legal values.
Automatic DPI promotion is limited to the existing 0x2201 sensor implementation,
feature revisions 0/1, and tested HID++ envelopes 2.0/4.2. G305 USB 046d:4074 is
reported as exact; another unambiguous device with those same verified feature
semantics is a family match, not a newly physically validated model. Unknown
versions and 0x2202 do not inherit authority. No receiver slot or feature index
is guessed. Report-rate knowledge is retained, but its current control-ownership
policy remains a blocker for Discovery promotion.

`hardware/base.py`, `native_hid.py`, `native_razer.py`, `discovery_backend.py`, and
`supervisor.py` expose an optional `discovery_protocol` receipt from the current
owner. Export does not select a backend, send a query, open another reader, or
load a profile. Native owners retain the descriptor hash already read at binding
and reject changed/missing descriptors, closed sessions, mismatched identities,
and ambiguous routes. Supervisor export uses its existing ownership lock.
A failed native DPI transaction revokes that binding's DPI discovery receipt;
setters still reject unconfirmed results through their existing readback policy.
Successful DPI cycling gains no request, readback, file access, or new worker.

`discovery_engine.py` accepts a current-owner callback. If it refuses a receipt,
the engine reports missing current proof without probing around that owner.
Without an owner, cold known-protocol discovery uses the existing validated
handshake before generic descriptor inference. Descriptors remain available
lazily for explicit guided/full-access workflows; unknown devices keep the
existing conservative descriptor/observation path.

`guided_discovery.py`, `setup_tui_curses.py`, and `setup_tui.py` connect this to
setup's actual bound native adapter and retain that adapter after successful
reuse. This removes both duplicate discovery and the subsequent redundant
backend selection. Fresh learned-operation discoveries still rebind normally.
The ordinary runtime's already-fast startup does not start this deeper discovery.

`device_profiles.py` keeps schema-v1 static knowledge and physical rebinding, but
never restores live write permission from disk. Historical operation receipts
are labeled as cached knowledge; current proof requires a current owner. Missing
current identity fields no longer satisfy a recorded exact identity. Existing
PROVEN learned-operation/polling stores remain separate and unchanged.
`discovery_ui.py` explains the stage, established predicates, blockers, and
persistence boundary in verbose reports.

## Proof reuse and invalidation

Compiled immutable recipes are reused across sessions. A cold native bind still
resolves current ROOT routing, features and bounds. Warm proof uses that current
owner and its descriptor snapshot without more traffic. Saved reports retain
protocol/feature/layout/identity signatures and legal ranges as historical facts,
never a live receiver slot, current DPI, polling setting, battery value, or lighting
state. They cannot become write authority just by being loaded.

Changed layouts/identity, ambiguous or closed bindings, unknown protocol/feature
revisions, and failed DPI confirmation prevent promotion/reuse. Features and
bounds come from the new owner after reconnect. A same-version firmware semantic
change cannot be predicted from a version string: canonical runtime confirmation
is still mandatory, and mismatch revokes the receipt. No cached firmware/version
claim bypasses those checks. Failure does not erase unrelated capabilities.

## Accelerated and intentionally restricted capabilities

| Knowledge | Result and boundary |
| --- | --- |
| Native HID++ 0x2201 DPI | Exact/family structural proof from the current owner; zero extra queries/writes; existing setter confirms every write. |
| HID++ report rate | Command/range knowledge reused; live Host/Onboard policy remains required. No automatic takeover or persistence promotion. |
| Native Razer | Exact owner and command/bounds reused without traffic. Storage-selecting DPI is not promoted as a volatile operation; existing backend policy remains intact. |
| LAMZU/Aurora | Existing structured frame, operation, dependency and dangerous-operation corpus reused by conservative discovery; unresolved shared configuration remains blocked. |
| Keychron/Vial | Existing paired namespace/source corpus remains recognition evidence, not proof that an unimplemented writer is safe. |
| ClickSync/vendor captures | Existing import/repertoire path remains source evidence; no invented packet or executable write permission. |
| OpenRGB-derived lighting | Existing exact-fingerprint/source records remain write-disabled unless their independent runtime policy proves the operation; no shared configuration zero-fill. |
| Learned-device corpus | Existing exact-model PROVEN DPI/polling stores and executor gates unchanged; physical calibration/read correlation grants no writes. |

There is no new generic HID write path, flash experiment, persistent write,
lighting writer, or observed-event call to `set_dpi`/`DpiCycler`. Observations do not
change desired hardware state. Optional backend failure still leaves remapping
independent. The v0.8.2 behavior contract, accepted G305 behavior, polling policy,
notifications, tray recovery, configuration, updater, service and package identity
remain covered by the complete regression suite.

## Tests and validation

`tests/test_capability_acceleration.py` adds 37 cases covering exact/family reuse,
every predicate independently, unknown revisions, unresolved shared state,
persistence separation, native read-only refusal, static cache downgrade,
identity/layout/protocol changes, live DPI after restart, closed/ambiguous routes,
readback failure, two-transaction successful cycles, lazy descriptor access,
Razer storage refusal, supervisor forwarding, competing-reader refusal, and setup
owner retention. `test_discovery_core.py` now requires cached reports to be
non-authoritative instead of preserving their old writable flag.

- **Code-reviewed / Unit-tested / Integration-tested** on Python 3.14.
- Focused: `PYTHONPATH=src pytest -q tests/test_capability_acceleration.py
  tests/test_calibrated_profiles.py tests/test_deep_stage_learning.py
  tests/test_transition_sources.py tests/test_discovery_backend.py
  tests/test_hardware_supervisor.py tests/test_remapper_reconnect.py
  tests/test_notifications.py tests/test_dpi_cycle.py tests/test_setup_tui.py
  tests/test_guided_discovery.py`: **158 passed**, one existing GLib warning,
  **4.37 s**.
- Source: `PYTHONPATH=src pytest -q`: **1,281 passed**, one existing GLib warning,
  **15.64 s**.
- `python3 -m compileall -q src tests scripts fuzz`: passed.
- `/tmp/omus-review-tools/bin/python -m ruff check src tests scripts fuzz`: passed.
- `python3 scripts/validate_workflows.py`: passed.
- `python3 scripts/verify_dependency_locks.py`: passed.
- `git diff --check`: passed.
- `python3 -m build --no-isolation`: wheel and source archive built.
- `PATH=/tmp/omus-review-tools/bin:$PATH scripts/check-wheel-reproducibility.sh`:
  this script archives HEAD, so it is rerun after the local commit. The candidate
  sdist also underwent two clean wheel builds before commit; exact digests are
  recorded in the reproducibility logs.
- Final RPM `%check`: **1,281 passed**, one existing GLib warning,
  **17.38 s**, plus compile and all packaged CLI-help checks. Built with
  `rpmbuild -ba omus.spec --define '_topdir /tmp/omus-discovery-rpm'
  --define '_tmppath /tmp'`; no installation.

## Measurements and evidence limits

Read-only G305 measurements used exclusive native ownership: installed OMUS was
stopped, the measurement owner closed before another opened, and installed OMUS
was restored. DPI was **3000 before and after**. No DPI/polling/flash configuration
write was used to prove Discovery. Queries used the existing validated driver.

| Metric | Merged baseline | Candidate |
| --- | ---: | ---: |
| Cold known discovery, topology already built | 1,241.902 ms | 1,239.592 ms |
| Cold discovery requests | 18 serial requests + one 7-slot probe batch | same |
| Generic descriptors parsed for known proof | 4 | 0 (available on explicit request) |
| Proof after a current native owner exists | no reuse interface; separate discovery repeats cold work | 71.686 µs median / 1,000 calls, **zero requests** |
| Exact/family fixture proof | no reuse interface | 37.140 / 37.000 µs median / 5,000 calls; **zero requests** |
| Static profile knowledge restore | previously could restore writable claims | 144.148 µs median / 500 calls; **zero requests, no write authority** |
| Source runtime DPI readiness | 2,225.359 ms | 2,227.829 ms |
| Settled source threads | 8 | 8 |
| Settled descriptors, external sampler | 17 | 17 |
| Input-counted 25-second idle CPU sample | 2 ticks, zero events | 1 tick, zero events |

Cold/readiness differences are measurement noise, not a claimed speedup.
The improvement is removal of redundant proof/selection work with an existing
owner. Timing values are local observations, not CI thresholds. Deterministic
traffic/selection assertions protect the improvement. The idle sampler itself
ran once per second; it counted 18 descriptors while inspecting its own fd
directory, versus 17 from the external sampler. Both versions were identical in
resource shape. The earlier unqualified 20-second sample had 1/19 CPU ticks and
no input counters; it is not evidence of an idle regression.

The accepted physical normal-cycle result remains about **20 ms / two HID
transactions**. This branch's tests verify the same two transactions and mandatory
readback; it did not repeat physical setting changes for ceremony. USB recovery
has deterministic lifecycle coverage; no new physical unplug/reinsert or reboot
trial was performed. The accepted baseline remains 109 ms remapping recovery and
5,074 ms management recovery. Do not relabel those as new candidate measurements.

Evidence logs are local, uncommitted `/tmp/omus-discovery-{source-gate,focused,rpm,
wheel-repro}.log`, `/tmp/omus-proof-{baseline,candidate-final}.log`, and
`/tmp/omus-idle-{baseline,candidate}.json`. No raw USB captures, device serials,
config files or build products are committed.

**Physically validated:** prior persistence cold-boot/button/reconnect behavior,
as reported by the user before integration. **Observed on hardware in Phase 2:**
read-only G305 binding/proof timing, unchanged DPI, and bounded source-runtime
readiness/resources. **Unverified (pending physical validation):** candidate physical button
presentation, USB reconnect/reboot, non-G305 family hardware, and native Razer.

## Next bounded task and Git discipline

Review this local commit and its capability/ownership boundaries. Only after
explicit authorization, install a reviewed candidate and repeat G305 button plus
USB-reconnect acceptance. No new device support or persistent capability is
claimed from fixtures or source research.

Phase 1 retained all intentional history and merged through protected review.
Phase 2 leaves main at the verified baseline and is committed locally only, with
no push, merge, installation, tag or release. The final delivery records the
actual commit hash and clean working-tree check.
