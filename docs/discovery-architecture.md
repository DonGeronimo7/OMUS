# Automatic Hardware Discovery

Mouse Control discovery treats a mouse as a physical graph of evdev and hidraw
interfaces rather than as one `/dev` node. Device paths are live interfaces,
not persistent identities.

The long-term design goal is not a larger hard-coded device table. It is a
repeatable learning pipeline that can observe an unknown mouse, let the user
supply semantic demonstrations, validate those demonstrations with physical
behavior, persist only the evidence that was actually learned, and reuse that
knowledge at runtime.

## Core rule

**Discovery learns hardware; it does not guess hardware.**

Root access increases visibility only. It never increases semantic confidence
or write authority.

## Safety model

1. Enumerate evdev, hidraw, and sysfs identity.
2. Correlate interfaces into one physical-device graph.
3. Parse HID descriptors for report structure only.
4. Observe passive Input traffic and safe GET Feature traffic where available.
5. Collect negative controls for ordinary movement/click activity.
6. Ask the user to demonstrate a specific behavior such as a DPI-cycle press.
7. Physically calibrate the resulting state when a measurable behavior exists.
8. Correlate raw state with the independently validated semantic state.
9. Persist only path-independent read-side evidence.
10. Rebind learned report identities at runtime and expose only validated reads/events.
11. Promote writes only through a separate proof process.

Unknown hardware never gains writable support from descriptor shape, brand,
VID:PID, a changing byte, or a successful read-side correlation alone.
`ReadOnlyHidProbe` intentionally exposes no SET_REPORT or raw-write API.

## Evidence levels

Mouse Control keeps four evidence levels distinct:

- `OBSERVED`: a fact was directly seen.
- `CORRELATED`: a raw field/report repeatedly tracks a demonstrated behavior.
- `VALIDATED`: the semantic behavior was independently confirmed, for example by physical CPI calibration and cycle wrap.
- `PROVEN`: a protocol transaction is established strongly enough to authorize the specific operation it describes.

A read-side calibrated profile is intentionally unable to become write authority.
Its root object and every raw mapping carry `write_authorized: false`.

## Identity rules

- `/dev/hidrawN` and `/dev/input/eventN` are never persistent identities.
- VID:PID alone is insufficient when multiple physical candidates exist.
- Ambiguous physical or protocol matches forbid writes.
- A USB port/sysfs parent is a connection location, not an instance identity.
- A true HID unique identifier may identify one physical instance.
- Model fingerprints describe the stable interface/descriptor layout.
- Runtime rebind uses stable report facts such as bus, VID:PID, interface number,
  descriptor fingerprint, report length, and report ID.

## Physical semantic calibration

The packaged user entry point is `mouse-control cpi`. It delegates to the same
`mouse_control.sensor_calibration` API consumed directly by discovery and
qualification code, so installed packages do not depend on a repository helper
or shelling out to another command. The measurement path is observational: it
uses raw evdev relative motion and does not grant protocol write authority.

DPI learning uses the physical sensor as an independent oracle rather than
assuming a vendor register is available.

For a ruler pass, Mouse Control:

- exclusively captures the selected physical evdev stream;
- preserves kernel event timestamps for polling estimation;
- isolates the strongest deliberate motion segment;
- uses two-dimensional displacement rather than assuming Linux `REL_X` matches
  the user's physical ruler direction;
- estimates measured CPI internally from device units and the supplied physical
  distance;
- repeats passes and uses median/MAD plus worst-pass spread for confidence;
- automatically requests more evidence when the initial pass set is unstable;
- reports configured DPI labels separately from measured physical CPI instead
  of applying a correction factor.

The user may provide a configured DPI value as a semantic label. That label and
the physical CPI measurement are retained as separate facts.

## Contrastive HID learning

Ordinary ruler movement is recorded as a negative control. DPI-button captures
are recorded separately with the mouse still. This allows the learner to
separate pointer traffic from action-specific traffic.

A report may be classified as:

- `state-bearing`: a stable raw field maps across calibrated semantic states;
- `transition-only`: the report reliably appears for the demonstrated action but
  does not itself provide a durable calibrated state mapping.

Individual raw fields remain correlated evidence even when the overall semantic
DPI-cycle behavior is validated.

## Persisted read-side profiles

A successful calibrated run may persist:

- stable model/instance fingerprints;
- configured DPI cycle order;
- measured physical CPI and polling evidence;
- cycle-wrap confirmation;
- state-bearing and transition-only report identities;
- raw-to-configured-DPI lookup tables;
- raw-to-measured-CPI observations;
- descriptor roles and observation counts.

Volatile `/dev` paths are rejected from persisted profiles.

## Native protocol knowledge and discovery repertoire

Mouse Control's protocol knowledge has two deliberately different roles:

1. **Runtime protocol adapters** may execute operations after exact identity,
   responder ownership, operation semantics, and verification requirements are
   satisfied. The current native adapters are dynamic Logitech HID++ 2 and the
   exact-modeled Razer 90-byte RPC implementation.
2. **Discovery repertoire entries** describe reusable family structure,
   transports, report signatures, codecs, transaction facts, provenance, and
   safety limits. They help classify observations and select the next useful
   evidence; they do not automatically become runtime drivers.

The current repertoire records HID++ 2 and Razer knowledge alongside sourced
facts for ASUS ROG command-64, SteelSeries direct-command, Sinowealth/ODM
configuration blobs, Attack Shark X11 feature reports, AJAZZ AJ-series feature
reports, MCHOSE V3 block RPC, and a BITMOUSE-style `0x72` grammar. The source of
each fact, its verification strength, its transport, and its write scope are
declared in `protocol_repertoire.py`.

This list is not a vendor compatibility table. Some entries have only passive
structural or semantic discriminators; some intentionally set write scope to
`NEVER`; exact-model entries still require the matching evidence before an
operation can execute. A vendor ID or familiar packet shape alone is never
support and never write authority.

## Universal backend contract

Discovery is the one hardware-backend surface exposed to the rest of Mouse
Control. Callers do not select Logitech, Razer, generic HID, or future vendor
backends directly.

The runtime shape is:

```text
application
    |
    v
DiscoveryBackend
    |
    +-- passive topology / descriptor discovery
    +-- physically learned read-side grammar
    +-- proven protocol adapter: HID++ / Razer / future families
    +-- evdev/uinput software remapping when no hardware semantics are known
```

A proven vendor implementation is therefore a **protocol adapter behind
Discovery**, not a competing top-level backend. Adapters may contribute proven
reads, writes, battery state, report-rate control, or event streams. Learned
profiles may supplement validated read/event capabilities. Learned evidence can
never contribute write authority.

This stable contract is intended to make Discovery reusable: another Linux
project should be able to ask one backend for mouse capabilities without knowing
which vendor wire protocol, learned grammar, or protocol adapter supplied them.

## Runtime backend selection

The old inert `GenericBackend` is retired as a runtime concept. `get_backend()`
now always returns `DiscoveryBackend` for every selected mouse.

Discovery internally performs three jobs:

1. run the safe passive discovery path for every device;
2. load and rebind any physically calibrated learned profile;
3. bind an ordered proven protocol adapter when one confidently recognizes the
   device.

Native HID++ and Razer support therefore remain available, including their
already-proven write operations, but they are implementation details behind the
Discovery contract. `GenericBackend` remains only as a compatibility alias to
`DiscoveryBackend` so older imports do not break.

When Discovery has a matching calibrated profile, it re-finds the current hidraw
interface from stable identity facts and emits confirmed `DpiState` events from
the learned mapping. It does not expose a synchronous vendor GET-DPI transaction
that was never learned, and learned profiles do not expose DPI writes.

When no calibrated profile or proven adapter exists, Discovery still represents
the device and ordinary evdev/uinput remapping continues without guessed
hardware controls.

## G305 controlled proof

The Logitech G305 is the golden reference because its native HID++ behavior was
already independently mastered before the generic experiment.

For the controlled Discovery acceptance test, the HID++ teacher was disabled.
The learner used physical calibration plus read-only raw HID capture and learned
this five-stage mapping from the G305 state-bearing report:

```text
raw 0 ->  800 DPI
raw 1 -> 1500 DPI
raw 2 -> 2000 DPI
raw 3 -> 2500 DPI
raw 4 -> 3000 DPI
```

The complete cycle wrap back to raw `0` / 800 DPI was independently confirmed by
physical CPI measurement. Polling measured approximately 1000 Hz at every stage.

The persisted profile was then loaded by `DiscoveryBackend` with every
vendor/native backend explicitly bypassed. Repeated physical DPI-button presses
produced the live runtime sequence:

```text
800 -> 1500 -> 2000 -> 2500 -> 3000
```

The acceptance monitor uses the normal Freedesktop DPI notifier, so this proof
covers the path from learned raw state through `DpiState` into the existing Mouse
Control notification layer.

This proves the architecture on the G305. It does not by itself prove that every
mouse exposes a similarly simple state field; other devices may require wider
fields, encoded values, checksums, Feature reports, transition-only learning, or
other grammar patterns already represented by the discovery/repertoire system.

## Write promotion remains separate

Read-side success never authorizes SET-DPI.

A future write grammar must independently establish the exact writable protocol
through constrained evidence such as known repertoire grammar, reversible
candidate transactions, readback, physical behavioral verification, rollback,
and any required ownership transition. A failed or ambiguous proof leaves the
learned read-side profile intact and read-only.

Host/software-control takeover is post-discovery only.

## Phase 3 learned runtime ownership

Automatic Discovery's production learned path uses one protocol-neutral
`LearnedHidSession` per live hidraw interface. DPI transactions, promoted
report-rate transactions, and validated physical-action events share that
single reader. Transaction response matchers claim replies first; unmatched
packets become read-only event evidence.

Subscriber callbacks from `LearnedHidSession` execute on its reader thread.
Production watchers therefore decode packets on the reader thread but enqueue
semantic events for delivery from the DPI watcher thread. A physical
`DPI_CYCLE_TRIGGER` can consequently invoke the existing `DpiCycler`, perform a
PROVEN learned DPI write/readback, and emit the normal deliberate DPI
notification without re-entering `session.exchange()` from the reader thread.

Learned polling preserves control-ownership safety. Ordinary reconciliation may
write only when the learned state machine reports Host control; it never takes
Host ownership merely to reconcile startup state. An explicit user-requested
polling change may use the independently PROVEN reversible takeover branch.

Validated learned action profiles are permanently read-only
(`write_authorized=false`, `write_scope=never`). They only identify a physical
action. Any resulting hardware change still requires a separately PROVEN
exact-model writable operation.

The G305 hardware evidence collected during Phase 3 showed the Host-mode
physical DPI button as an exact 9-byte press/release stream on the same
interface used by learned DPI/polling transactions:

- press: `02 20 00 00 00 00 00 00 00`
- release: `02 00 00 00 00 00 00 00 00`

Those packets are structurally disjoint from the 20-byte learned transaction
replies. The generic runtime does not hard-code these bytes; they are persisted
only as exact-model learned action evidence.
