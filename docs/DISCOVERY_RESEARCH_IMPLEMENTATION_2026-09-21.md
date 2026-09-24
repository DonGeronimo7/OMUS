# OMUS Discovery research implementation handoff — 2026-09-21

## Scope

This tree starts from the Codex Discovery snapshot derived from OMUS v1.0.4 and
implements the deterministic/offline-safe portion of the September 21 research.
It intentionally stops at physical-hardware, kernel-attachment, vendor-runtime,
and firmware-rehosting validation boundaries.

This work does **not** widen generic write authority. Public/static evidence is
knowledge, never proof. Runtime writes still require the existing exact-device,
exact-interface, generation-bound proof and transaction path.

## Implemented

### 1. Peripheral IR → bounded executable research experiment

`src/mouse_control/discovery_execution.py`

Adds the missing bridge from a demonstrated/proven exact-model learned DPI
operation into `PeripheralIR`, then into one operator-authorized reversible
experiment using the existing `ExperimentAuthority`, learned HID session, and
transaction engine.

Key invariants:

- exact physical identity required;
- exact bus/VID/PID/interface/descriptor binding required;
- valid EvidenceGraph ancestry required;
- current connection generation bound into the receipt;
- baseline readback and independent physical baseline verification before write;
- target readback and physical target verification after write;
- mandatory rollback/readback/physical restore;
- no rollback is attempted into a new connection generation;
- success remains research evidence and does not create runtime write authority;
- a fully restored same-generation result can be persisted as `experiment` +
  `verification` EvidenceGraph nodes, never as a capability promotion.

### 2. Mutation-safety map

`src/mouse_control/mutation_policy.py`

Adds evidence-derived bit-region classifications:

- unknown;
- independently mutable;
- restricted;
- immutable;
- coupled.

`peripheral_ir.patch_candidate_state()` can optionally require a
`MutationSafetyMap`, preventing an RMW proposal from touching fields not proven
safe for that mutation shape. Immutable classification cannot be inferred from a
failed mutation; it must be explicitly sourced.

### 3. HID++ 0x2202 extended DPI

`src/mouse_control/hidpp_driver.py`

Adds runtime support when 0x2201 is absent:

- dynamic ROOT discovery of `0x2202`;
- sensor count/capabilities;
- paged DPI-range decoding;
- independent X/Y capability;
- DPI-level count;
- current parameter reads;
- LOD-preserving setter;
- canonical readback verification;
- ParametersChanged event decoding without a second reader or redundant query.

The existing 0x2201 path remains preferred and unchanged for devices such as the
known G305 path.

### 4. Protocol repertoire additions

`src/mouse_control/protocol_repertoire.py`

Adds typed operation vocabulary for:

- HID++ 0x2202 extended DPI;
- HID++ 0x8061 extended report rate;
- exact Darmoshark M3 `dms` identity/signatures;
- exact WLMOUSE Beast X `36A7:A887` page protocol identity/signatures.

Darmoshark and Beast X are deliberately `WriteScope.NEVER` at this stage.
HID++ 0x8061 is modeled but not given a runtime writer until live connection
routing/type can be established without guessing.

### 5. Strict public protocol codecs

`src/mouse_control/public_protocols.py`

Pure parsers/builders only; this module never opens hardware and never grants
write authority.

Implemented vocabulary includes:

- Darmoshark `dms` receiver ACK, configuration snapshot, short DPI payload;
- RAWM/MiracleTek 12-bit logical-event framing, 64-byte physical/virtual chunks,
  query and semantic notifications;
- EWEADN H2 exact 33-byte checksum grammar, polling mapping, ic_type 17 DPI
  codec/table and setter packets;
- WLMOUSE Beast X CRC16/MODBUS report/page helpers and DPI transform.

Ambiguous or non-round-tripping values are rejected rather than normalized.

### 6. Source-attributed protocol priors

`src/mouse_control/protocol_prior.py`

Imports public protocol sources/families/operations into `EvidenceGraph` as
content-addressed `source` and `hypothesis` nodes. The importer cannot create
`verification` or `capability` evidence. Invalidating a source invalidates its
dependent hypotheses transitively through the existing EvidenceGraph behavior.

### 7. Incremental symbolic action alphabet

`src/mouse_control/action_alphabet.py`

Builds semantic query/action symbols directly from Peripheral IR. Setter symbols
are only synthesized when the IR already records volatile storage, rollback,
verification, and a legal baseline. Setters are limited to a nearest legal
neighbor instead of arbitrary values. Alphabets can be extended without
throwing away prior learned symbols.

### 8. Reactive ECA peripheral-state model

`src/mouse_control/reactive_model.py`

Adds explainable event-condition-action state hypotheses. Repeated deterministic
transitions can produce rules; multiple effects are emitted only when stable
pre-state fields unambiguously distinguish them. Hidden-state ambiguity causes
abstention rather than a guessed transition.

### 9. Virtual Peripheral Oracle core

`src/mouse_control/virtual_oracle.py`

Adds the transport-independent core needed for future UHID/USB-IP vendor-app
teaching:

- exact report definitions/state;
- GET/SET/OUTPUT transaction recording;
- explicit semantic vendor-action brackets;
- aligned differential write-byte analysis;
- EvidenceGraph experiment/frame emission.

No Wine, UHID, USB/IP, or physical-device adapter is claimed here. Those are
environmental adapters to this tested core.

### 10. HID-BPF observation contract

`src/mouse_control/hid_bpf_observation.py`

Adds a safety admission model and normalized provenance-rich observations for a
future loader:

- before-hook availability;
- request source IDs;
- descriptor metadata;
- synthetic self-test;
- explicit kernel-safety admission;
- exact device/interface/descriptor/generation binding;
- kernel-vs-userspace/hidraw provenance;
- EvidenceGraph frame/transaction emission only.

No BPF program is attached by this tree and no HID-BPF observation creates write
proof.

## Tests added/changed

New files:

- `tests/test_discovery_execution.py`
- `tests/test_mutation_policy.py`
- `tests/test_action_alphabet.py`
- `tests/test_reactive_model.py`
- `tests/test_public_protocols.py`
- `tests/test_protocol_prior.py`
- `tests/test_virtual_oracle.py`
- `tests/test_hid_bpf_observation.py`

Extended:

- `tests/test_native_hid.py`
- `tests/test_protocol_repertoire.py`
- `tests/test_peripheral_ir.py` indirectly exercises optional mutation policy

## Validation completed in the ChatGPT sandbox

The sandbox lacks the project runtime packages `evdev` and `dbus-next`, and has
no network access to install them. A temporary `evdev` import shim located
**outside this tree** was used only to make unrelated Linux input imports
collectable; it is not included in this source tree or deliverable.

Completed validation:

```text
python -m compileall -q src tests
    PASS

Focused new/relevant suites including native HID:
    202 passed

Existing Automatic Discovery/reconnect regression group:
    65 passed

Broad suite excluding only D-Bus-specific battery/tray/notification modules:
    1335 passed
```

The broad run excludes:

- `tests/test_battery.py`
- `tests/test_tray_private_bus.py`
- `tests/test_tray_session.py`
- `tests/test_notifications.py`

because `dbus-next` is not installed in this environment. These areas were not
modified by this implementation pass.

## Required Codex/workstation validation

Use the normal Fedora development environment with real dependencies installed.

1. Run the complete unmodified test suite:

   ```bash
   PYTHONPATH=src pytest -q
   python -m compileall -q src tests
   ```

2. Run the repository lint/package/security gates used by the current branch.

3. Confirm existing G305 behavior remains on HID++ 0x2201 and that no new path
   changes its polling/DPI/reconnect/notification behavior.

4. If an actual 0x2202 Logitech device is available, validate range discovery,
   current DPI, one reversible write/readback/rollback, and physical sensitivity.
   Until then label 0x2202 as protocol-implemented/tested, not physically
   validated by OMUS.

5. Keep Darmoshark, RAWM/MiracleTek, EWEADN H2 and Beast X public codecs as
   knowledge/read-side tooling until an OMUS-owned exact-device experiment
   reaches the normal physical verification/promotion path.

6. For HID-BPF, add a separate loader/instrument adapter only after the real
   target kernel passes the admission/self-test policy. Do not weaken the
   admission contract to make attachment succeed.

7. For the Virtual Peripheral Oracle, implement UHID or USB/IP as adapters to the
   tested transport-neutral core. Vendor software compatibility under Wine or
   native Windows is an environmental validation, not a unit-test claim.

## Intentionally not implemented as a claim

The following remain environment/hardware research tiers rather than fake
software-complete claims:

- physical unknown-device write validation;
- HID-BPF kernel attachment and reconnect behavior;
- native Windows/Wine vendor-app compatibility with a virtual peripheral;
- Cynthion physical-wire automation;
- firmware rehosting / coverage-as-state execution;
- firmware flashing;
- cross-model protocol-family write promotion;
- 0x8061 writes without proven live connection routing.

## Merge guidance

This tree is not a Git checkout. Treat the accompanying patch as a review aid
and the ZIP as a complete source snapshot. Apply/merge onto the active OMUS
branch, resolve any newer branch edits normally, then rerun the complete gates.
Do not infer a release/tag from this handoff.
