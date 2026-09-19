# Post-v0.9.8 unified addendum audit

Baseline: `v0.9.8` at `e3c48c56f67c00568de0052228adb6832180c37b`
(the annotated tag resolves to release commit `e3c48c5`). The starting tree was
clean on `main`; implementation continues on
`codex/post-v0.9.8-unified-addendum`.

## Parallel updater reconciliation

The canonical-TUI updater implementations at unified-addendum commit
`bd22e158847f49a934f5f5eeb2e1e6b2d2f019c1` and dedicated-updater commit
`d3bb3bbc198a33825df2e716a431dcf47d3c4d4e` were compared component by
component before reconciliation. The result has one Updates route, one setup
controller, one updater UI state, and one updater authority.

| Overlap | Retained implementation | Reason |
|---|---|---|
| navigation and screen integration | unified addendum | preserves the broader canonical surface and parity inventory |
| controller/state location | unified addendum, strengthened in place | avoids a second controller or updater model; remains outside `SetupChoices` |
| check and compatibility result | dedicated updater behavior in `updater.py` | structured source/unknown/package-source/AppImage protection is updater-owned |
| network timing | dedicated updater behavior | only the explicit Check action calls the inspector; open/redraw/back are inert |
| action visibility and status/error rendering | dedicated updater behavior adapted to the unified screen | update is offered only after a successful compatible check |
| execution and approval | dedicated updater behavior | existing updater is called with interactive semantics while curses is suspended |
| download, checksum, origin, package, and service operations | existing shared `updater.py` paths | preserves the mature single source of truth and package ownership |

The final canonical order is exactly: Device; Hardware Discovery; Discovery
Lab; DPI; Polling; Buttons; Lighting; Service; Updates; Tools / Advanced;
About; Review / Save. The enforced capability inventory confirms that no mature
top-level CLI capability lost its canonical application route.

## CLI / TUI parity

The executable inventory is enforced by `product_capabilities.CAPABILITIES`.
Parser-only switches (`--json`-style formatting where present, `--yes`,
`--check`, paths, durations, and debugging serialization) are not product
capabilities and do not receive separate controls.

| CLI capability | Canonical TUI route | Shared implementation | Status |
|---|---|---|---|
| setup / tui | application itself | setup entry/controller | implemented |
| run | Service | runtime config path | implemented route |
| show-config | Tools / Configuration | config service | implemented route |
| check-permissions | Tools / Permissions | permissions service | implemented route |
| debug-dpi / debug-hid | Discovery / Tools | existing read-only inspectors | implemented route |
| research | Discovery Lab / Advanced Tools | existing corpus/Lab services | implemented |
| doctor / support | Tools | existing diagnostic/support services | implemented route |
| discover / rediscover | Hardware Discovery | existing automatic discovery | implemented |
| cpi | Discovery Lab / CPI investigator | existing calibration service | implemented |
| install/start/stop/restart/status | Service | existing service module | implemented route |
| update | Updates | canonical updater | implemented |
| standalone discovery/research entry points | Discovery Lab / Advanced Tools | their existing modules | implemented route |

Machine-oriented CLI argument entry remains available for scripting. A TUI
route may explain and route to an existing guarded workflow rather than expose
raw packet or promotion controls directly.

## Requirement classification

- Canonical full-screen curses TUI: **ALREADY_IMPLEMENTED**, expanded here with
  Lighting, Updates, Tools, and About.
- Discovery Lab, differential analysis, timing, controlled actions,
  persistence verification, receiver/child routing, power analysis, and vendor
  capture import: **ALREADY_IMPLEMENTED**.
- Canonical report identity, descriptor fidelity, integrity relationships,
  temporal dialogue, generation isolation, conflicts/provenance, structured
  effect/persistence evidence, and LAMZU fixtures: **ALREADY_IMPLEMENTED** or
  **PARTIALLY_IMPLEMENTED** in the existing architecture; no parallel engine
  was introduced.
- Basic protocol-neutral lighting capability, zones, persistence, write scope,
  validation, per-device configuration, reconnect restoration, and TUI:
  **MISSING** in v0.9.8; implemented additively in this milestone.
- Vendor lighting execution: **RESEARCH_ONLY / HARDWARE_REQUIRED**. Source
  knowledge is retained, but runtime write authority remains disabled.
- Raw PCAP/PCAPNG ingestion: **PARTIALLY_IMPLEMENTED**; the adapter architecture
  and JSON/JSONL importer exist, while native packet-capture parsing remains a
  bounded future adapter.

## Research ledger

| Item | v0.9.8 status | Result now | Runtime authority / remaining gate |
|---|---|---|---|
| OpenRGB lighting knowledge | missing | normalized source-backed detector/effect records | write-disabled; exact hardware qualification |
| ClickSync / WebHID | vendor-import architecture present | repertoire/capture-import target retained | source evidence only |
| Keychron Launcher / M6 | repertoire research | ledgered, not generalized | exact collection/transport hardware required |
| LAMZU Aurora / Thorn V2 | first-class repertoire + fixtures | already present | read-only/vendor evidence; physical qualification |
| modern CompX | grammar phenomena present | retained as research target | exact model/context required |
| Areson / Redragon / M724 | source-backed repertoire fragments | exact Redragon lighting fingerprint retained | write-disabled; conflict/session cleanup unresolved per model |
| Wraith / Lofree / Incott | source-backed candidates | retained in corpus/repertoire backlog | hardware required |
| Pulsar / Sonix / Nordic | family separation present | no brand-wide promotion | exact model/connection required |
| BITMOUSE | declarative asymmetric grammar | already present | recognition only |
| Finalmouse ULX | bounded burst dialogue model | already present | exact hardware required |
| GearHub-V5 / MicLink | routing/whole-record phenomena | routing mapper already present | internal identity and RMW proof required |
| Holtek Venus | accepted/stored/effective distinction | persistence architecture already present | physical commit semantics required |
| SinoWealth | whole-config family knowledge | shared-config lighting refusal/RMW primitive added | trustworthy baseline and exact layout required |
| Corsair | ownership/no-ACK/asymmetric evidence | transaction model retained | model-specific proof required |
| SteelSeries | generation-specific repertoire | already present | generation/exact device proof required |
| extended HID++ | dynamic HID++ architecture present | lighting feature knowledge retained | dynamic enumeration + hardware proof |
| MCHOSE generations | unresolved family candidates | not collapsed | exact identity/codec required |
| Razer variants | native backend + source evidence | source-backed lighting record; streamed breathing excluded | exact matrix/mode proof |
| Ryunix telemetry | decoder present | already present | read-only telemetry |
| receiver/child routing | full mapper present | already present | physical route qualification |
| capture/import pipeline | JSON/JSONL adapter present | already present | PCAP adapter remains |
| persistence evidence | seven-level verifier present | lighting persistence uses same vocabulary | hardware lifecycle checks |
| structured outcome evidence | effect/persistence models present | already present | operation-specific population |
| temporal dialogue | dialogue/burst/pushed state present | already present | family-specific fixtures continue |

No item above grants a setter merely because source code, a capture, or a
transport acknowledgement exists.

## Lighting safety boundary

Lighting is optional and independent of core mouse support. Generic discovery
still has no write primitive. A backend must expose an exact zone as writable;
the shared validator rejects unsupported modes, malformed RGB, and out-of-range
brightness/speed. `SHARED_DEVICE_CONFIG` writes require a non-empty trustworthy
baseline, byte-preserving same-length modification, integrity recomputation,
and backend verification. Without that baseline, the operation is refused.
Host-streamed animation is intentionally unsupported.
