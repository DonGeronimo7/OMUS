# Discovery Lab

The Discovery Lab is the first-class TUI workspace for safe, evidence-driven
mouse protocol investigation. It composes Automatic Discovery's existing
selected-device capture, logical-record, dialogue, inference, physical
measurement, provenance, proof, and information-gain layers. It does not own a
second capture stack.

## TUI path

```text
Hardware Discovery
→ Open Discovery Lab
→ Run Full Automatic Lab
```

The first milestone runs the Differential Protocol Analyzer. Later Lab
instruments will use the same experiment model and page rather than becoming
separate normal-user command-line workflows.

## Canonical experiment model

`LabExperiment` retains:

- a stable exact-device context and connection generation;
- purpose, labelled human action, and repeat number;
- baseline, controlled-action, post-action, and negative-control intervals;
- path-independent HID observations and read-only Feature transitions;
- optional canonical USB observations, logical records, and dialogues;
- physical CPI and polling evidence;
- evidence-source provenance, confidence, and operation proof state;
- the differential analysis and next recommended experiment.

Evidence from different connection generations is rejected. Existing USB and
logical-record evidence is projected into an interval only when its timestamp
belongs to exactly one recorded interval. Incomplete or invalid logical records
remain contradictory evidence rather than being treated as semantics.

`replay_fixture()` emits deterministic local replay data. It excludes volatile
device/sysfs paths, diagnostic source paths, evdev event history, typed text,
clipboard content, and screen content.

## Differential Protocol Analyzer

The analyzer is deterministic and performs no I/O. For each stable stream and
field it identifies and ranks:

- constants and changed fields;
- controlled-action correlations separated from the negative control;
- counter/sequence, declared-length, and small-domain status candidates;
- bounded existing checksum/integrity candidates;
- trailing conventional padding/stale-region candidates;
- timing changes between baseline and action intervals;
- request/response echoes and transaction byte/length/timing differences;
- existing dependency-inference results when labelled scalar values exist;
- conservative labelled-action semantic hypotheses and contradictions.

The next observation is selected with the existing information-gain planner.
Recommendations in this milestone are read-only.

## Protocol Timing Profiler

The second Lab milestone turns already-established temporal relationships into
canonical timing evidence. It does not infer request ownership, burst
membership, push causality, or lifecycle state independently; those facts must
come from the existing dialogue, burst, pushed-state, freshness, or explicit
lifecycle evidence.

Each `LabTimingObservation` retains the experiment ID, stable physical context,
connection generation, source observation IDs, start/end timestamps, raw
duration, relationship, interval/repeat, confidence/proof state, classification,
and freshness where relevant. `ProtocolTimingProfile` remains attached to the
same `LabExperiment` and provides:

- request/response and request/ACK latency;
- busy/poll cadence, busy duration, time-to-ready, and poll count;
- trigger-to-first-response, inter-response gaps, bounded quiet completion,
  overall burst duration, response count, and completion reason;
- nudge-to-push, controlled-action-to-state-change, and periodic push cadence;
- stale/unknown immediate read to later fresh changed state;
- last-valid/commit to disconnect, disconnect to attachment, and attachment to
  first valid new-generation state;
- per-relationship count, minimum, median, maximum, spread, rejected outliers,
  classification, and evidence sufficiency;
- baseline-versus-action timing deltas and timing-aware next experiments.

All calculations use recorded nanosecond timestamps. Tests and replay perform
no sleeps. `IMMEDIATE`, `SHORT_DELAY`, `SETTLING_DELAY`, `PERIODIC`,
`BUSY_POLL`, `BURST`, and `RECONNECT_BOUND` are contextual classifications,
not universal millisecond thresholds. A lone ordinary transaction remains
`UNKNOWN` while its raw latency is retained.

Reconnect measurements use explicit lifecycle boundary records. Protocol
transactions themselves still cannot cross generations. Quiet completion is
measured only when the existing bounded-burst assembler retains an exact replay
completion boundary; explicit-end or generation-change completion remains
unknown when no completion timestamp exists.

## Controlled Action Matrix and automatic run

`LabExperimentPlan` is attached to, and produces, the existing
`LabExperiment`. The planner considers passive, physical-only, external-vendor,
bounded-engine, and unavailable actions. Automatic execution currently admits
the first three classes. A bounded-engine action is excluded unless separately
eligible under the experiment-authority model, and the plan never grants
runtime write authority.

The initial templates cover quiet baseline, ordinary movement, a generic
button, one DPI stage, a multi-stage DPI sequence, disconnect/reconnect,
charging transition, and an external vendor-setting demonstration. The planner:

1. partitions unresolved hypotheses with the existing information-gain model;
2. rejects unsafe/unavailable actions and uses human effort only to break
   equivalent-information ties;
3. chooses bounded question-specific repeats and a semantic negative control;
4. selects HID/Feature, USB/logical, dialogue, timing, differential, freshness,
   dependency, integrity, topology, CPI, and polling instruments as relevant;
5. derives baseline/action/post/control windows from retained timing evidence,
   or records bounded-default uncertainty;
6. executes baseline, prompted action, post-action, negative control, physical
   verification, analysis, hypothesis update, and information-gain recalculation;
7. records an explicit stop reason or retains the next best plan.

The CPI verifier is selected for DPI ambiguity and asks for one measured-guide
pass. The polling verifier is selected for polling ambiguity and measures
selected-device motion timestamps. These remain independent physical evidence;
neither assigns protocol semantics or authorizes a write.

Hypotheses are never silently discarded. Supported, strengthened, weakened,
rejected, conflicted, and unresolved states retain their positive and negative
evidence. Plan/result replay fixtures are deterministic and privacy-redacted.

## Safety and privacy

- Capture is restricted to the physical mouse selected by Automatic Discovery.
- Unknown-device acquisition uses existing read-only HID and Feature-report
  primitives.
- The Lab has no setter, output-report, feature-write, arbitrary HID-write, or
  fuzzing primitive.
- `LabExperiment.write_authorized` is always false. Recognition, correlation,
  physical measurement, and proof-state reporting do not grant write authority.
- Captures remain local. The Lab contains no network submission or telemetry.
- Ordinary evdev events may guide a live capture window but are not retained in
  the experiment or replay fixture.

## Deferred master-Lab milestones

The state/effect/persistence verifier,
receiver/child routing mapper, battery/charging investigator, vendor capture
importer,
`ProtocolKnowledgePackage`, automatic positive/negative contribution fixtures,
repository contribution pipeline, and blind-device v1 acceptance suite remain
bounded future milestones.
