# Skill: Mouse Control Automatic Discovery

## When to use

Use this skill for work involving any of the following:

- unknown mouse discovery,
- generic HID observation,
- DPI-stage discovery,
- CPI/ruler calibration,
- polling observation,
- calibrated profiles,
- transition-source inference,
- read-only DPI runtime events,
- learned HID behavior,
- device identity and rebinding,
- Titan / Venustech / non-Logitech hardware experiments,
- promotion from observation to PROVEN hardware control.

This skill is about architecture and evidence, not one specific mouse.

## Goal

Automatic Discovery should make unsupported mice progressively useful without requiring vendor-specific support while preserving strict write safety.

The desired progression is:

```text
identify hardware
→ observe behavior
→ physically calibrate behavior
→ infer stable read-side representation
→ reuse that knowledge at runtime
→ only later promote separately proven write operations
```

Never collapse these stages.

## The three-authority model

### Physical authority

Physical calibration may prove:

- a DPI change occurred,
- an ordered cycle exists,
- wraparound exists,
- measured CPI corresponds to a stage,
- polling behavior changed or stayed constant.

Physical authority does **not** reveal how to write firmware state.

### Observation authority

A calibrated runtime source may prove:

- current absolute DPI state,
- one physical transition occurred,
- a stable runtime input field or event corresponds to known calibrated behavior.

Examples:

- `hid_state`
- `feature_state`
- `evdev_absolute_stage`
- `hid_cycle_trigger`
- `evdev_cycle_trigger`

Observation authority remains read-only.

### Write authority

Write authority exists only through an independent PROVEN implementation.

Examples:

- native HID++ behavior with readback,
- exact-model learned operation promoted through the project’s existing proof path.

A calibrated transition source can coexist with a PROVEN writer, but it must never become that writer by implication.

## DPI cycle semantics

There are two distinct cycling mechanisms.

### Writable software cycle

Existing `DpiCycler` semantics:

```text
software/user mapping
→ choose configured next DPI
→ call set_dpi()
→ verify/read back
→ update desired state
→ notify
```

`cycle_trigger=True` belongs to this writable path where already intentionally supported.

Do not change these semantics.

### Read-only physical cycle

For trigger-driven unknown hardware:

```text
physical mouse firmware changes DPI itself
→ Mouse Control observes one calibrated transition
→ read-only tracker advances from a genuinely synchronized stage
→ emit confirmed DpiState
→ notify
```

This path must:

- use `cycle_trigger=False`,
- never call `set_dpi()`,
- never invoke `DpiCycler`,
- never update desired hardware state as though Mouse Control performed the write.

## ReadOnlyDpiCycleTracker rules

The tracker stores a physically proven ordered cycle.

It may:

- synchronize from a legitimate known state,
- advance exactly one stage per genuine trigger,
- wrap modulo the cycle,
- resynchronize from absolute state,
- suppress press/hold/release duplicates,
- preserve rapid ordered presses.

It must not:

- assume configured desired DPI equals hardware DPI,
- invent a starting stage,
- retain unsupported certainty after reconnect/power loss,
- call hardware setters,
- grant write authority.

### Legitimate synchronization sources

Examples:

- calibrated absolute state,
- another defensible live current-state mechanism,
- final known physical stage from the same active calibration session.

The last item is ephemeral session evidence, not persistent hardware truth.

### Reconnect rule

For trigger-only devices:

```text
disconnect/reconnect
→ invalidate stage certainty
→ ignore future triggers until resynchronized
```

For absolute sources:

```text
disconnect/reconnect
→ next valid absolute observation may resynchronize
```

Do not weaken this rule just to make hardware acceptance pass.

## Physical calibration persistence

Physical calibration and runtime source inference are independent successes.

Once all of the following are true:

- at least two distinct stages are physically proven,
- wraparound is physically confirmed,
- the cycle hypothesis reaches validated confidence,

persist the exact-device schema-v2 calibrated read-only profile even when:

```text
transition_sources == []
```

The profile should retain:

- exact identity/fingerprints,
- configured cycle order,
- measured CPI states,
- polling observations,
- confidence,
- wraparound proof,
- semantic evidence,
- `transition_sources: []`,
- `write_authorized: false`.

A later setup must reuse that physical calibration and must not repeat the ruler/wrap experiment solely because runtime-source inference was unresolved.

Reject corrupt, malformed, ambiguous, or different-device profiles.

Preserve schema-v1 compatibility.

## Runtime transition binding

When consuming schema-v2 transition sources:

- resolve persisted stable interface identity against current `PhysicalDevice`,
- never persist volatile event/hidraw node paths,
- refuse ambiguous matches,
- distinguish absolute state from ordered triggers,
- preserve legacy `raw_mappings`.

### `hid_state`

- decode the learned report field,
- map raw value to calibrated DPI,
- emit confirmed read-side state,
- absolute state may synchronize/resynchronize,
- suppress duplicate identical observations.

### `feature_state`

- use only existing safe read primitives,
- do not introduce feature writes,
- keep any polling conservative and bounded,
- if clean runtime observation is not yet possible, fail conservatively and test the limitation.

### `evdev_absolute_stage`

- observe through the existing remapper-owned input stream,
- map raw stage to calibrated DPI,
- use it as absolute synchronization evidence.

### `hid_cycle_trigger`

- detect one real press,
- press/hold/repeat echoes must not double-advance,
- release rearms,
- rapid distinct presses remain ordered.

### `evdev_cycle_trigger`

- observe through the existing remapper-owned stream,
- advance once per genuine press,
- never open a competing grabbed evdev reader.

## evdev ownership

`MouseRemapper` owns the selected evdev device through EVIOCGRAB.

Do not create another runtime reader for calibrated evdev sources.

Preferred architecture:

```text
MouseRemapper reads physical event
→ lightweight observer callback receives (type, code, value)
→ calibrated runtime source may inspect it
→ normal remapping continues unchanged
```

Observation:

- must not consume the event,
- must not block latency-sensitive input,
- must survive event-node renumbering,
- must preserve mapping/passthrough behavior,
- should receive reconnect/disconnect lifecycle notification where needed.

Keep remapping logic inside the remapper, not the hardware backend.

## HID ownership

Respect one-reader ownership.

If an interface is already owned by `LearnedHidSession`, use that session’s subscription/routing mechanism instead of opening a competing reader.

Where event and reply patterns share a session, prove they are disjoint or refuse ambiguous routing.

Do not break PROVEN exact-model transactions.

## Notifications

Confirmed physical read-only states should use the normal observed-state notification path.

Requirements:

- one genuine physical transition → one notification,
- slow presses work,
- rapid presses remain ordered,
- wraparound still notifies,
- duplicate packet echoes do not duplicate one transition,
- a DPI value may legitimately recur after wraparound.

Do not globally deduplicate merely by DPI history.

Preserve the current Freedesktop behavior including independent notifications (`replaces_id=0`).

## DesiredHardwareState boundary

A read-only observed hardware transition is not a Mouse Control write.

Do not update `DesiredHardwareState` merely because a calibrated read-only event reports a new DPI.

Writable software cycling may continue to update desired state according to existing behavior.

## Supervisor binding signature

A Discovery rebind should notice meaningful changes in:

- transition source kind,
- stable source/interface identity,
- live bound node,
- report shape,
- offset,
- raw mapping,
- press/release pattern,
- cycle order,
- absolute vs trigger semantics.

Runtime live node paths may participate in the in-memory signature to detect node renumbering.

They must not become persisted device identity.

## Setup UX

Once setup enters curses, keep discovery/setup UI in curses.

Do not describe absence of an absolute HID stage field as physical-learning failure.

Preferred outcome language:

- `Physical DPI cycle learned`
- `Runtime DPI transition source learned`
- `Physical calibration saved; runtime source unresolved`

For normal 254 mm ruler calibration wording, prefer:

`10 in (254 mm)`

Keep the comprehensive evidence-gathering process. Do not reduce methodology merely to shorten setup.

## Generalization rule

Never optimize the architecture around one Titan/G305 trace.

A successful new abstraction should explain:

- why Titan works,
- why another trigger-only mouse could work,
- why an absolute-state mouse could resynchronize,
- why ambiguous hardware is refused,
- why existing HID++ behavior remains unchanged.

## Definition of success

The read-only Automatic Discovery runtime is successful when:

- a physically calibrated unknown mouse can report its DPI transitions,
- no generic DPI write occurs,
- remapping is unaffected,
- reconnect behavior is honest,
- notifications remain correct,
- existing PROVEN writable paths still work unchanged.
