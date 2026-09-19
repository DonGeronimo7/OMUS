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

## State, effect, and persistence verification

An observed packet transition is not treated as device success. Canonical
`EffectEvidence` separately retains request acceptance, protocol readback,
freshness, physical behavior, verification method, source observations, proof
state, and contradictions. A fresh later state dominates a stale immediate read
for conclusions, while both remain in replay and advanced evidence.

`PersistenceEvidence` compares stable state facts—not transactions—across an
explicit ladder:

0. immediate effect;
1. settling or idle;
2. fresh protocol reread;
3. selected-device reconnect;
4. receiver reconnect;
5. physical power cycle;
6. host or session restart evidence.

Protocol transactions and temporal relationships still cannot span connection
generations. Cross-generation state comparison is allowed only in explicit
persistence evidence carrying the same experiment and exact physical identity,
old/new generations, freshness, verification methods, and source IDs.

Persistence classifications include volatile, session/reconnect/receiver/
power-cycle/host-restart persistence, device- or host-stored state, unknown
storage, commit/apply required, volatile-until-commit, reverted, and unknown.
No level implies an untested stronger level. A host restart alone does not prove
device storage; independently observed power-cycle survival may do so.

The verifier uses the timing profile for freshness and settling windows,
preserves protocol/physical and stale/fresh contradictions, detects observed
automatic reversion, and can identify a commit/apply requirement without
inventing the command. It selects the next safe high-value idle, reread,
reconnect, receiver-reconnect, or power-cycle plan, or records why disruptive
testing stopped. Changed original state produces a manual restoration request;
the Lab never broadens write authority for cleanup.

The normal Lab page renders physical effect, persistence classifications,
strongest tested level, contradiction count, restoration needs, and the next
experiment. Deterministic replay retains effect and persistence findings while
hashing source identifiers and omitting live device paths and unrelated human
activity.

## Receiver and child routing

Routing evidence remains attached to `LabExperiment` and reuses its exact
physical identity and connection generation. The receiver/child graph keeps the
physical USB/HID receiver separate from logical child candidates, receiver-local
ownership, interfaces, endpoints, channels, namespaces, reports, logical record
types, internal targets, and route tags.

The mapper projects existing selected-device USB observations, logical records,
dialogues, pushed-state associations, timing, persistence, and differential
findings. It supports:

- one or multiple children behind one receiver;
- many interfaces for one child or several routed children on one interface;
- mouse-local and receiver-local namespaces with otherwise similar grammar;
- shared VID:PID where an observed internal target is required;
- asymmetric Output/Feature request to Input response routes;
- controlled action to asynchronous state on another interface.

An internal target candidate requires repeated controlled cross-child contrast.
A constant byte is not a child ID. Timing can strengthen an already justified
dialogue but cannot establish ownership. USB routes without logical evidence
stay `UNMAPPED`; weaker evidence stays `CANDIDATE_ROUTE`; collisions become
`AMBIGUOUS_ROUTE`; only repeated discriminating evidence becomes
`CONFIRMED_ROUTE`.

Route evidence cannot cross a connection generation. Old and newly rediscovered
graphs may be compared for stable, remapped, missing, or new routes, but old
ownership is never automatically carried forward. Persistence observations may
support a mouse-versus-receiver hypothesis without proving either route or
storage location.

Routing ambiguity feeds the same information-gain planner. Depending on
available evidence, the next experiment may keep the selected mouse idle while
another paired child acts, repeat a selected-child control, or power-cycle only
the mouse to distinguish mouse-local from receiver-local state. No arbitrary
target IDs are transmitted and no receiver slots are scanned.

The Lab page provides a concise receiver/device routing summary, confirmed route
count, unresolved ownership count, and next routing experiment. Advanced replay
retains interfaces, endpoints, report IDs, internal targets, asymmetric edges,
generation, contradictions, and redacted source IDs.

## Battery, charging, and power-state investigation

Power evidence is attached to the same `LabExperiment`; there is no additional
capture or authority model. Each observation keeps raw and decoded values
separate and records the exact selected-device context, connection generation,
source IDs, candidate semantic, optional proven units, charging/source/battery
state, freshness, timestamp, cadence, routed owner, confidence, proof state,
and contradictions.

An integer in `0..100` is only a percentage candidate. A percentage is confirmed
only by established protocol semantics, agreement with an independent source,
or repeated directional evidence at distinct levels during charging/discharge.
One plausible value and cadence alone are insufficient. Discrete buckets,
ADC-like values, and voltage-like values retain exact raw form; an unknown
conversion is reported as raw level known and percentage unknown.

The investigator consumes existing differential fields, Feature/Input reports,
async state, temporal freshness, timing profiles, and confirmed routing facts.
A power-related plan or semantic state, power-labelled routed namespace, or
periodic status candidate causes the automatic orchestrator to run it; users do
not select a separate investigator.
A repeated binary transition across baseline and a controlled cable action may
support charging or not-charging state. Merely performing a cable action does
not label every changing field. Explicit external power, battery power, full,
charge-complete, and low-battery evidence remain independent facts.

Fresh telemetry supersedes a conflicting stale cache for the current conclusion
without deleting either observation. Periodic cadence is reported but never
assigns semantics. Confirmed logical ownership is distinct from transport via a
receiver, and mouse/receiver disagreements and equally supported candidate
fields remain explicit contradictions.

Slow trends may be compared across sessions only when stable device-unique
identity is present. The replay fixture stores only scoped power/protocol facts
and hashes session, source, independent-reference, and routed-owner identifiers.
There is no evdev, keyboard, clipboard, screen, unrelated USB, or network
history. Normal runtime passive collection is intentionally deferred; the
pending-candidate model is the extension point if a later selected-device,
allowlisted design can satisfy the privacy boundary.

Power uncertainty reuses the information-gain planner. It prefers one cable
transition, or a mouse-only power-cycle experiment when receiver cache ownership
is ambiguous. It never proposes forced discharge or a long wait. A candidate
may remain pending for evidence gathered during normal future use. The Lab TUI
shows the useful interpretation, cadence, contradictions, passive follow-up,
and next bounded experiment without packet detail.

## LAMZU Aurora family knowledge

The repertoire contains two explicitly separate LAMZU families. The modern
family uses a 64-byte Feature Report 0 control grammar plus Input Report 4
asynchronous events. The legacy VID `3554` family uses report 8, a 16-byte
packet, its sourced checksum relation, and separate flash-layout semantics.
Neither family is a runtime backend and neither grants write authority.

Modern response normalization accepts the two vendor-observed command
alignments before semantic matching. Status `a1` and the vendor-observed `02`
are terminal evidence; lower/pending and higher/resend statuses map into the
existing busy/poll temporal vocabulary with explicit bounds. The 15/20/30/100
ms values remain vendor timing priors and are never substituted for measured
Protocol Timing Profiler evidence.

The catalog retains Thorn, Thorn V2, and 54H20 identities and capabilities as
`VENDOR_DECLARED`. It does not call a matching product physically proven.
Bootloader identities are excluded before normal selection and refused at the
Discovery entry point. Receiver USB PID `0032` and routed/internal PID `002e`
remain unresolved identity layers.

Input Report 4 recipes cover DPI, profile reread, battery/charging, connection,
LOD, polling, and joint performance state. They project into existing
`PushedStateRecord` evidence rather than creating a notification subsystem.
Battery events therefore use the ordinary Power Investigator, and observed
routed identity replies use candidate-level Routing Mapper evidence.

All vendor-described commands—including Rapid Trigger and Scroll Bhop—are data
records and pure deterministic codecs. Current-family Feature requests are not
eligible automatic experiments because even a read requires an unverified
outgoing Feature transaction. Both families remain `WriteScope.NEVER`.
Factory/profile reset, identity/descriptor mutation, pairing, DFU, flash erase,
firmware control, arbitrary target enumeration, and unknown command probing are
explicitly non-experimentable.

## Vendor Capture Importer

The Lab can ingest legitimate public/vendor protocol observations offline from
the normal `Discovery Lab → Import Vendor Capture` action. Importing never opens
a HID device, transmits a captured frame, contacts a network service, or changes
runtime capabilities. It is an evidence-staging path, not packet replay.

Version 1 supports the canonical `mouse-control-vendor-capture:1` JSON form and
an equivalent JSONL stream with a `capture_header` followed by `record` objects.
Adapters implement deterministic `detect` and `parse` behavior; a future vendor
or trace exporter can add an adapter without changing normalization, evidence,
persistence, or the TUI. Ambiguous detection abstains. Raw PCAP/PCAPNG is not
claimed by v1 and can be added later through the same bounded adapter boundary.

Each source retains its SHA-256 digest, basename, source/provenance category,
optional vendor/model/VID:PID/receiver/family/version/date/reference metadata,
notes, import date, and importer version. Allowed provenance includes official
public vendor packages, public documentation, open-source implementations, and
personally recorded captures. Material represented as private, leaked,
exfiltrated, NDA-restricted, or authentication-bypassed is refused. Unknown
metadata remains unknown.

Normalization preserves the physical frame, original length and sequence,
normalized order, known direction and timestamp, report/transport/interface/
endpoint/channel/control metadata, transaction relationship, parser warnings,
and source reference. Unknown frames remain evidence. Known repertoire grammar
may additionally supply a normalized payload and decoded fields, but never
replaces the raw bytes. The Aurora fixture uses its existing family module for
Feature-0 alignment/status, Input-4 events, routed identity, battery/power, and
dangerous-operation classification; no LAMZU-specific import side channel was
added.

Imported records are wrapped around the existing `DiscoveryEvidence` type and
projected into existing `ProtocolObservation`, `DialogueRecord`,
`PushedStateRecord`, timing, Routing Mapper, and Power Investigator structures
when the capture has sufficient facts. The review lifecycle is
`IMPORTED_UNREVIEWED`, `ACCEPTED`, or `REJECTED`. Acceptance means only that the
prior knowledge may be consulted; evidence remains `OBSERVED` or `DECODED` and
can never become `PROVEN`, experiment-eligible, or write-authorizing through
this pipeline.

The local content-addressed store keeps one JSON staging document per source
digest under the OMUS discovery data directory. It retains the
manifest, provenance, normalized records, warnings, conflicts, review state,
and stable relationships to generated evidence. Exact duplicate imports are
recognized by source digest. Exact duplicate observations within one source are
collapsed, temporally distinct repeats remain, and identical bytes from an
independent source remain separate corroboration. Conflicting meanings,
families, and report lengths are retained as conflict evidence rather than
resolved by import order.

Capture files are untrusted input. File size, record count, frame size, nesting,
node count, timestamps, byte values, and stored paths are bounded and checked.
Persistence filenames are derived only from validated SHA-256 digests. The
importer does not evaluate scripts, execute vendor JavaScript, load pickles, or
make external requests.

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

The vendor capture importer, `ProtocolKnowledgePackage`, automatic
positive/negative contribution fixtures,
repository contribution pipeline, and blind-device v1 acceptance suite remain
bounded future milestones.
