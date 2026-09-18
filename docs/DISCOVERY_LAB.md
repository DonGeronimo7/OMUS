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
→ Run Full Automatic Lab — Differential Analyzer milestone
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

## Automatic run

The current TUI run chooses the capture plan automatically:

1. untouched baseline;
2. three isolated repeats of the labelled physical control;
3. untouched post-action interval;
4. ordinary motion plus one left click as a negative control;
5. analysis, ranking, hypothesis generation, and next-experiment selection.

The user only performs the prompted physical actions. Mouse Control handles
capture windows, repeat count, field and packet differences, timing,
correlation, integrity analysis, ranking, and replay-fixture representation.

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

The protocol timing profiler, controlled action matrix, multi-instrument
information-gain orchestration, state/effect/persistence verifier,
receiver/child routing mapper, battery/charging investigator, vendor capture
importer, complete multi-instrument automatic orchestrator,
`ProtocolKnowledgePackage`, automatic positive/negative contribution fixtures,
repository contribution pipeline, and blind-device v1 acceptance suite remain
bounded future milestones.
