# Deep-research baseline — Mouse Control v0.9.7-2

This document records the released implementation baseline for the next
research phase. `v0.9.7-2` is the immutable behavioral reference. It is not a
proposal for a rewrite, protocol expansion, or new peripheral class.

## A. Current architecture

| Area | Authoritative implementation |
|---|---|
| Entrypoints and command dispatch | `src/mouse_control/app.py`, `cli.py`, `__main__.py`, `pyproject.toml` |
| Desktop launcher and foreground ownership | `graphical_launcher.py`, `foreground_session.py`, `service.py` |
| Canonical full-screen TUI | `setup_entry.py`, `setup_tui.py`, `setup_tui_curses.py` |
| Configuration and saved preferences | `config.py`, `setup_flow.py` |
| Device enumeration and physical topology | `discovery.py`, `device_topology.py`, `discovery_models.py` |
| Discovery orchestration and UI integration | `discovery_engine.py`, `discovery_integration.py`, `guided_discovery.py` |
| Runtime backend selection | `hardware/registry.py`, `hardware/discovery_backend.py`, `hardware/supervisor.py` |
| HID transport, descriptors, and reports | `hid_session.py`, `hid_descriptor.py`, `hid_report.py`, `hid_probe.py` |
| HID++ | `hidpp.py`, `hidpp_driver.py`, `hardware/native_hid.py` |
| Protocol knowledge and decoding | `protocol_repertoire.py`, `protocol_grammar.py`, `protocol_codec.py`, `protocol_discovery.py` |
| Evidence and learned operations | `knowledge_provenance.py`, `device_profiles.py`, `calibrated_profiles.py`, `learned_operations.py`, `learned_polling.py`, `learned_actions.py` |
| Remapping and input ownership | `remapper.py`, `keyboard_capture.py` |
| DPI, polling, battery, notifications, tray | `read_only_dpi_cycle.py`, `notifications.py`, `battery.py`, `polling_*.py` |
| Updating and release-version mapping | `updater.py`, `release_version.py` |
| Packaging | `mouse-control.spec`, `debian/`, `PKGBUILD`, `packaging/appimage/`, `.github/workflows/` |

The normal path is: desktop entry → `mouse-control-launcher` → terminal →
`mouse-control` → transient foreground supervisor → canonical curses TUI.
The TUI owns interactive hardware use; the persistent user service owns normal
remapping/runtime use. Foreground suspension/restoration preserves exclusive
ownership rather than relying on concurrent readers.

## B. Discovery-engine architecture

`DiscoveryEngine` receives a selected evdev mouse, builds current physical
topology, and first attempts an exact, path-independent persisted-evidence
rebind. Ambiguous, corrupt, changed, or unbindable evidence abstains. The
known-device path is a performance optimization only; explicit Rediscover runs
the full pipeline.

The full pipeline interprets HID descriptors, reads only through
`ReadOnlyHidProbe` for generic devices, records descriptor/report observations,
matches conservative repertoire signatures, and constructs capability/evidence
results. Known protocol detectors may use their established validated read
paths. Structural resemblance, byte changes, and a descriptor shape are not
semantic proof and do not authorize writes.

Discovery output feeds `DiscoveryBackend`, which exposes a universal backend
surface. Internally it can bind a proven native adapter (notably HID++),
validated exact-model learned operations, or a read-only calibrated source.
When none applies, ordinary evdev/uinput remapping remains available. Failures
are reported as hardware/discovery failures and do not block basic remapping.

## C. Current protocol knowledge

- Logitech G305 (`046d:4074`) is the physically validated native HID++
  reference. HID++ feature IDs are dynamically resolved through ROOT; it is
  not a claim about arbitrary Logitech receivers or models.
- `protocol_repertoire.py` stores source-attributed, declarative family facts
  for known shapes including HID++, Razer, SteelSeries, Sinowealth/ODM, Attack
  Shark, AJAZZ, MCHOSE, Redragon M724, Ryunix Kyu Pro MX1, and BITMOUSE-style
  grammars. This is recognition/read-side knowledge, not a compatibility list.
- `protocol_grammar.py` separates transport, report signatures, codecs,
  semantic behaviors, safety classes, provenance trust, and write scope.
  `protocol_codec.py` implements bounded value conversions.
- Descriptor parsing and HID report decoding are generic structural tools.
  Usage interpretation and changing-byte correlations are evidence, not
  vendor semantics.
- Persisted calibrated profiles cache path-independent read-side observations;
  learned DPI/polling operations cache only exact-model operations independently
  promoted to `EvidenceLevel.PROVEN`. Neither calibration nor read-side
  correlation grants write authority.

## D. Hardware-support truth

| Status | Evidence |
|---|---|
| Physically validated | Logitech G305 `046d:4074`: remapping, native HID++ DPI and polling, DPI events/notifications, reconnect, battery/tray, service lifecycle; see `docs/COMPATIBILITY.md` and handoff log. |
| Physically validated packaging/UI | Fedora 44 desktop launcher for the accepted v0.9.7-2 performance implementation. |
| Automated only | Discovery grammar/repertoire entries, generic HID decoding, learned-operation paths, protocol codecs, and most non-G305 hardware behavior. |
| Read-only recognition only | Redragon M724 and Ryunix Kyu Pro MX1 repertoire facts; both have `WriteScope.NEVER`. |
| Unknown/unsupported | Any model without exact physical identity plus independently proven operation evidence; generic HID standardized DPI/polling control; RGB/profile-suite control. |

No test fixture, descriptor, VID:PID, product name, or acknowledgement alone
establishes physical support or write authority.

## E. Performance baseline

The final accepted Fedora/G305 launcher figures are recorded in
`docs/PERFORMANCE.md`. Key observed changes from the performance pass are:

| Metric | Before | After |
|---|---:|---:|
| Evdev enumeration | 536.06 ms | 273.55 ms |
| Warm known-device first frame, median | 676.22 ms | 504.15 ms |
| Warm observed maximum, five runs | 777.43 ms | 647.61 ms |
| Cold/transitional first frame | 6,347.09 ms | 464.83 ms |

The 500-round controlled fixture recorded cold app import at 15.655 ms,
known-device restore at 0.0342 ms, and explicit Rediscover at 0.4171 ms after
the pass. Hardware measurements and fixture measurements are separate.

## F. Compatibility contract

Future work must preserve or explicitly re-prove: the canonical full-screen
TUI and launcher; foreground/service ownership and restoration; evdev/uinput
remapping and reconnect recovery; known-device fast path plus complete explicit
Rediscover; exact identity binding; configuration and persisted-evidence
survival; G305 HID++; PROVEN-only learned operations; generic-HID no-write
policy; DPI/polling/battery/notification/tray paths; updater checksum and
artifact validation; and RPM, DEB, wheel/sdist, and AppImage delivery.

The first frame may precede live backend initialization, but no hardware
navigation may proceed until the owned initializer has completed service
suspension and backend/evidence checks. Performance changes must not erase
validation work; they may only move or remove demonstrably duplicate work.

## G. Known architectural limitations

- Measured: live backend handshakes can be multi-second on transitional device
  states, so they are intentionally outside first-frame critical path.
- Measured: Python import and descriptor/report work has bounded caches and
  documented benchmarks, but absolute timings remain host-dependent.
- Capability gap: many mice expose no safe host-visible DPI/polling state and
  are remapping-only.
- Knowledge gap: repertoire matches and descriptor correlations do not imply
  transactions or writable semantics; model-specific evidence remains sparse.
- Scaling concern: broader device families require curated provenance, exact
  identity binding, sanitized fixtures, and physical confirmation—not merely
  larger lookup tables.

These are observations and research constraints, not justification for an
architecture rewrite.

## H. Prioritized research questions

1. Which Linux/kernel/HID interfaces expose reliable, portable identity and
   topology facts for multi-interface USB and Bluetooth peripherals?
2. Which maintained upstream projects provide auditable, license-compatible
   protocol facts and validation practices for additional mouse families?
3. How can descriptor and passive-report evidence be represented more
   reproducibly without turning correlation into semantic/write authority?
4. Which repeatable experiments safely establish read-side state, transitions,
   and independent physical confirmation on unknown devices?
5. What evidence is required to generalize a protocol grammar across exact
   models, receiver slots, wired/wireless modes, or firmware revisions?
6. Which performance constraints become material as the knowledge base grows,
   and which are demonstrably unsuitable for selective native components?
7. What peripheral classes, if any, share enough safety and topology properties
   with mice to warrant future study?

## I. Evidence requirements

Prefer USB/HID specifications, Linux kernel source, established maintained
drivers, mature open-source hardware projects, source-attributed protocol
documentation, sanitized captured behavior, and repeatable experiments.
Record provenance, exact identity/transport/interface constraints, readback,
failure behavior, rollback, and independent physical confirmation.

External evidence informs hypotheses; it does not itself prove a local device
operation. A write claim requires independently `EvidenceLevel.PROVEN`
protocol evidence and runtime enforcement of its write policy. Generic HID
inspection remains read-only: no output/feature/raw write operations are
introduced without a narrow tested, device-evidenced driver.

## J. Future architecture decision framework

Evaluate retaining Python, selective native/Rust components, broader Rust
migration, generated protocol data, knowledge-base expansion, or broader
peripheral classes against evidence rather than fashion. A proposal must show:

1. a concrete measured bottleneck, safety/maintainability limitation, or
   capability gap in the released baseline;
2. a design that preserves every compatibility contract above;
3. an identity, ownership, read/write-authority, failure, and rollback model;
4. deterministic regression coverage plus appropriate physical validation;
5. migration, packaging, updater, and operator-impact costs; and
6. a reason the smallest additive alternative is insufficient.

No future direction is selected by this document.
