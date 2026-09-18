# Production code-health audit (2026-09-17)

Scope: every Python module under `src/mouse_control`, packaging entry points,
hardware backends, protocol repertoire records, and current user-facing docs.
Test modules and generated `*.egg-info` metadata are not production source.

## Removed or consolidated

| Item | Decision |
|---|---|
| `hardware/openrazer.py` | Removed. Native exact-model Razer framing and backend now provide the Mouse-Control-relevant DPI, polling, firmware, battery, and charging operations. OpenRazer remains provenance only. |
| `hardware.registry.BACKEND_FACTORIES` | Removed unused compatibility alias; the private factory tuple is the sole registry. |
| descriptor decoding split by report direction | Consolidated in `hid_report.decode_report`; input/output/feature helpers are intentionally thin typed entry points. |
| Razer `encode_read_request` compatibility alias | Removed; the sole read/write packet encoder is `native_razer.encode_request`. |
| legacy setup wizard | Removed in the preceding TUI-only checkpoint; not restored. |

No package entry point was obsolete. The seven scripts in `pyproject.toml` all
resolve to a current `main`: app/setup, discovery, sensor calibration, write
trace/promotion, discovery monitor, and polling promotion.

## Runtime and setup inventory

| Modules | Current active purpose |
|---|---|
| `__init__`, `branding`, `support` | Package identity, display metadata, and supported-device presentation. |
| `app`, `cli`, `setup_entry`, `setup_flow`, `setup_tui`, `setup_tui_curses`, `wizard` | One full-screen interactive setup dispatcher plus explicit noninteractive application operation. `wizard` is the current state model, not the removed prompt UI. |
| `config`, `device_profiles`, `permissions`, `updater` | Configuration/profile persistence, permission guidance, and explicit update workflow. |
| `service`, `remapper`, `keyboard_capture`, `notifications`, `battery`, `read_only_dpi_cycle` | Remapping lifecycle, input ownership, notifications, independent battery reporting, and read-only physical DPI event handling. |
| `doctor` | Installed-system diagnostics; reports native Razer rather than an optional OpenRazer dependency. |

## Device identity, discovery, and learning inventory

| Modules | Current active purpose |
|---|---|
| `discovery`, `discovery_models`, `device_topology` | Physical-device enumeration, exact identity, ambiguity refusal, and composite sibling topology. |
| `discovery_engine`, `discovery_research`, `guided_discovery`, `discovery_ui` | Orchestration, evidence aggregation, safe next-step planning, and setup presentation. |
| `event_correlation`, `learning_session`, `contrastive_inference`, `semantic_inference`, `information_gain` | Guided/control observations, repeated contrastive validation, semantic hypotheses, and minimum-interaction experiment choice. |
| `calibrated_discovery`, `calibrated_profiles`, `sensor_calibration` | Physical motion calibration kept separate from protocol write authority. |
| `learned_actions`, `learned_operations`, `learned_polling` | Persisted exact-model evidence with OBSERVED/CORRELATED/VALIDATED/PROVEN gating. |
| `learned_hid_session`, `learned_hid_transport`, `learned_polling_transport`, `transition_sources` | Exact-bound learned operation transport and read-side transition sources. |
| `backend_teacher`, `teacher_registry` | Converts proven backend facts into learning evidence without making vendor identity itself authority. |
| `research_probe` | Explicit, reversible research execution for DEMONSTRATED grammars; not a runtime fallback. |

## HID and protocol inventory

| Modules | Current active purpose |
|---|---|
| `hid_descriptor`, `hid_usage`, `hid_report`, `hid_semantics` | Canonical descriptor parse, HUT ontology, direction-aware field decoding, units/collections, and evdev semantics. |
| `hid_behavior`, `hid_semantic_candidates`, `hid_corpus` | Read-only behavioral evidence, candidate ranking, and sanitized repeatable corpus representation. These consume canonical descriptor/report identities rather than re-decoding reports. |
| `generic_hid`, `hid_probe`, `hid_session` | Read-only generic enumeration/probing and one-reader HID session ownership. |
| `protocol_grammar`, `protocol_codec`, `protocol_repertoire` | Vendor-neutral transport/frame/codec/semantic/evidence vocabulary and structural family matching. |
| `protocol_discovery`, `transaction_engine`, `transaction_inference`, `integrity_inference` | Proven handshake detection, authorization-gated state machines, repeated-frame role/grammar inference, and bounded checksums. |
| `hidpp`, `hidpp_driver`, `hidpp_debug` | Dynamic HID++ ROOT grammar/runtime and explicit diagnostics for the proven Logitech path. |
| `native_razer` | Protocol-only Razer 90-byte framing, exact model variants, and packet codecs; hardware access stays in the backend package. |
| `polling_measurement`, `polling_observation`, `polling_replay` | Protocol-neutral timing evidence, passive observation, and demonstrated replay grammar. |

## Hardware package inventory

| Modules | Current active purpose |
|---|---|
| `hardware/__init__`, `base`, `capabilities` | Stable backend contracts, errors, and independent capability models. |
| `hardware/registry`, `supervisor`, `generic`, `discovery_backend` | Backend selection, failure-isolated lifecycle, generic fallback, and discovery-backed operations. |
| `hardware/native_hid` | Proven native HID++ backend. |
| `hardware/native_razer` | Exact-model/single-responder native Razer backend with write readback verification. |

## Retained research and acceptance commands

These modules are intentionally not imported by normal runtime. They are
bounded operator tools, invoked directly with `python -m`, and preserve
physical acceptance workflows that automated tests cannot replace:

| Modules | Purpose |
|---|---|
| `calibrated_discovery_cli`, `hid_capture_cli`, `learned_action_capture_cli` | Teacher-free calibrated/corpus/action capture. |
| `dpi_generalization_cli` | Repeated numeric-codec generalization acceptance; its pure validator is regression-tested. |
| `polling_host_trace_cli`, `polling_trace_cli` | Host/raw polling trace acquisition and timing estimation; pure helpers are regression-tested. |
| `polling_replay_cli`, `polling_state_machine_cli`, `polling_verify_cli` | Explicitly authorized replay, consecutive-state, and physical timing laboratories. |
| `discovery_cli`, `discovery_runtime_cli`, `sensor_calibration_cli`, `polling_promotion_cli`, `write_trace_cli`, `write_promotion_cli` | Installed operator commands declared in `pyproject.toml`. |

Their direct-run status is intentional: adding general-user entry points would
advertise hardware research workflows as ordinary supported operations.

## Active protocol repertoire audit

Every retained record is consumed by `match_repertoire`, then by
`DiscoveryEngine` for classification and `discovery_research` for transport
observation planning. Bindings additionally seed semantic interpretation.

| Family | Active contribution |
|---|---|
| HID++ 2 | Proven backend classification/execution teacher; deliberately cannot match on VID alone. |
| Razer RPC90 | Native proven exact-model execution plus shared frame/provenance vocabulary. |
| ASUS ROG command64 | Exact-model classification and HID input/output observation plan. |
| SteelSeries direct command | Exact-model classification and HID input/output observation plan. |
| Sinowealth configuration blob | Strong buffered-feature shape classification and polling binding; write disabled. |
| Attack Shark X11 | Multi-report classification, semantic bindings, transport plan, and explicit dangerous-report boundary. |
| AJAZZ AJ feature64 | Feature-envelope classification and delayed-query transport planning. |
| MCHOSE V3 block RPC | Block/RPC classification, semantic bindings, and transport planning. |

Structural repertoire matches remain research hints. They do not set a
capability writable and cannot construct `TransactionAuthorization`.

## Documentation and generated artifacts

Current README, package descriptions, AppImage notes, and project status were
updated to describe native Razer and no OpenRazer runtime dependency. Historical
handoff/changelog references are retained as historical evidence. Generated
`src/mouse_control.egg-info/SOURCES.txt` is ignored build output and is not
edited or treated as authoritative source.
