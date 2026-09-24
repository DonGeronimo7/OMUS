# HANDOFF — Discovery IR and evidence foundation

## Goal and delivered scope

Request: user attachment `Pasted text.txt` (62186559-888a-439e-85e3-d9f1e4e31bf0),
“OMUS Discovery Engine — Autonomous DPI/Polling Control Mission”.
Implement the first bounded foundation of that mission. This is an **offline
research implementation**, not completion of autonomous plug-in Discovery.

## Repository state

- Branch: `codex/autonomous-discovery-ir`.
- Starting HEAD: `912bdcc6e4d536abcf3df259228a0bfad82ec2bd`.
- Final HEAD: the commit containing this report (resolve with `git log -1`).
- Starting tree: clean. Intended final tree: clean after committing this report.
- Both `9b93b4a` and `4640054` are ancestors of starting HEAD. Their work and the
  subsequent recovery/release commits were retained without replay or rewriting.
- No push, merge, tag, release, install, service change, or hardware write.
- Remote verification before push: not applicable; no push requested or made.

## Files and architecture actually implemented

- `src/mouse_control/peripheral_ir.py`: exact USB/Bluetooth physical and interface
  identities, first-class DPI/report-rate capability descriptions, legal enum/range
  domains, reviewable differential proof-plan compilation, and offline RMW proposals.
  Reuses existing family, transaction, frame, field, codec and safety vocabulary.
  Reports missing canonical query, reversible setter, frame/transaction references,
  volatile storage, rollback, correlation, verification and evidence separately.
  Selects nearest legal control value without enumerating a large range.
- `src/mouse_control/evidence_graph.py`: content-addressed dependency DAG with source,
  identity, interface, report, transaction, hypothesis, experiment, verification and
  capability nodes. Supporting ancestry is explainable. Invalidation propagates to
  dependent claims; independent read-side knowledge survives a failed write claim.
  Bounded versioned JSON import rejects altered hashes, missing parents, duplicate
  nodes and malformed schema. Snapshot creation refuses to overwrite existing files.
- `src/mouse_control/kernel_knowledge.py`: offline source importer with commit and
  content-hash provenance; extracts HID transport/API vocabulary and explicit literal
  enum assignments. Masks comments and strings, retains line references, and refuses
  to guess symbolic C expressions. CLI: `python -m mouse_control.kernel_knowledge
  SOURCE --kernel-path drivers/hid/FILE --revision FULL_SHA --output NEW_FILE`.
- `docs/discovery-corpus/*.evidence.json`: three generated upstream evidence graphs.
- `tests/test_peripheral_ir.py`: 39 deterministic tests.
- This report, corpus README, project status and handoff log record scope/evidence.

IR references reuse existing ownership, prerequisite, frame, logical-record,
sequence/routing and integrity vocabulary through `ProtocolFamily`; they do not
implement a new transaction interpreter. Dedicated full IR JSON parsing,
normalization and runtime recipe compilation remain outstanding. Graph persistence
is implemented; executable learned-operation persistence is not added here.

## Kernel/protocol material mined

Pinned Linux v6.12 commit `adc218676eef25575469234709c2d87185ca223a`:

- `drivers/hid/hid-roccat-common.c`: 12 facts plus source identity.
- `drivers/hid/hid-roccat-koneplus.c`: 2 facts plus source identity.
- `drivers/hid/hid-roccat-koneplus.h`: 38 facts plus source identity.

Total: **52 extracted facts, 3 source nodes**. Full files were fetched to `/tmp`
for mining; only generated facts and provenance are committed. This is a small
seed, not a mine of the complete Linux tree. No C control-flow interpretation or
automatic source-to-capability inference is claimed. Report sizes/command enum
names do not establish volatile storage, a legal DPI domain, or safe setters.

The upstream common transport uses feature GET/SET_REPORT and status handling;
the Koneplus header provides literal command/report-size vocabulary. That is useful
research evidence, but insufficient authority for an autonomous DPI/polling write.

## Safety and behavior boundaries

- **No new hardware write path.** Plans always report runtime write authority false.
- A blocker-free plan is a reviewable proposal, not an authorization receipt.
  Its text references and caller-supplied evidence IDs are not proof predicates.
- RMW proposals preserve all untargeted bytes/bits; reject incomplete state,
  out-of-domain values, width mismatch and ambiguous enum inverses. They do not
  synthesize commands or checksums and cannot be sent through this module.
- Snapshot capture, unique live binding, current generation checks, ownership,
  timeouts, actual rollback and independent physical verification remain the
  responsibility of a future integration with the existing transaction owner.
- Graph hashes detect corruption, not malicious evidence. Loaded graphs never
  authorize runtime writes. Automatic firmware/binding comparison and revocation
  policy are not wired; explicit graph invalidation is available.
- No calibrated observer calls setters or updates desired hardware state.
- Existing runtime remains separate and is exercised by the full regression suite:
  remapping, G305 HID++, learned DPI/polling, reconnect, notifications and the
  v0.8.2 compatibility paths. No new physical compatibility claim.

## Automatic DPI/polling and Lab behavior

New **offline** behavior: construct a nearest-value differential proof plan for
DPI or configured host report rate, explain unresolved evidence, and construct a
byte-preserving candidate state using existing codecs. Enum polling codecs and
BE16 DPI are covered by synthetic fixtures.

No change to ordinary setup/runtime automatic DPI or polling acquisition, existing
hypothesis ranking, experiment authorization, Lab UI, or runtime fast-path routing.
Plans describe baseline/target/restore verification, but do not execute it.
No measured report-rate estimator changes or new device support.

## HID-BPF

Reviewed the official HID-BPF documentation at
https://docs.kernel.org/hid/hid-bpf.html, including request observation and userspace
ownership of interpretation. **No HID-BPF attachment, loader, tracing adapter,
firewall, or bounded request support implemented.** Existing runtime acquires no
new dependency. Platform capability detection and captured-traffic integration
remain separate work.

## Validation

- Unit-tested: `PYTHONPATH=src pytest -q tests/test_peripheral_ir.py` — **39 passed
  in 0.06s**.
- Full gate: `PYTHONPATH=src pytest -q` — **1,320 passed, 1 skipped, 1 warning in
  10.72s**. Existing GLib deprecation warning. The private D-Bus test skipped because
  the sandbox could not create its private socket.
- Integration-tested: `PYTHONPATH=src pytest -q tests/test_tray_private_bus.py`
  outside the sandbox — **1 passed, 1 warning in 0.31s**. It uses its own bus;
  it does not connect to the desktop session.
- `python3 -m compileall -q src tests` — passed.
- `git diff --check` — passed, including final staged changes before commit.
- Packaging: not run; no dependency, entry-point or package metadata changes.
- Physical hardware: **none performed; Unverified**. No mouse movement, polling
  changes, receiver unplug, or hardware writes were performed for this pass.

## Performance and resources

Two runs of `PYTHONPATH=src python3 benchmarks/run_performance.py --rounds 50 --json`
were made on this working tree. These are repeat measurements, not a controlled
before/after benchmark or evidence of a speedup:

| Fixture median | First run | Second run |
|---|---:|---:|
| Known-device startup | 38.953 µs | 35.076 µs |
| Explicit Rediscover | 496.454 µs | 448.303 µs |
| Application import | 16.472 ms | 13.882 ms |
| 1,000 HID decodes | 29.077 ms | 28.950 ms |

In 200-cycle memory fixtures, reconnect retained 88 bytes / peak growth 2,040
bytes in both runs; setup enter/exit retained zero / peak growth 15,572 bytes.
Rediscover retained 5,769/6,123 bytes with peak growth 185,522/185,994 bytes.

Additional synthetic warm native-owner proof timing using the existing
`test_capability_acceleration.binding` fixture and `hidpp_match`: **29.436 µs median,
1,000 calls, zero HID requests**. Not comparable as a physical measurement to the
previous installed G305 73.474 µs result. No live service thread/FD/RSS measurement
was made. The new offline modules are not imported into the existing runtime.

## Remaining gaps and next bounded task

Most of the broader mission remains: automatic evidence-to-IR semantics,
source-backed capability recipe compilation, exact live candidate binding,
autonomous experiment execution through one-reader ownership, independent DPI and
polling physical verification, evidence-driven promotion to existing learned
operations, broad kernel mining, HID-BPF instruments, Workbench/Lab integration,
firmware/rebind invalidation, generalization, and physical acceptance.

**Next highest-value bounded task:** implement one source-backed exact-device
capability compiler adapter that converts a demonstrated learned DPI operation
into this IR and validates every required fact against its existing transaction
and current binding. Produce a generation-bound executable plan through the
existing research-probe/transaction owner, with deterministic baseline/readback/
rollback failures covered before any operator-supervised physical trial.
