"""Presentation-only inventory for the Discovery Lab expert dashboard.

Every entry maps to existing Discovery/Lab state or to one of the two existing
safe TUI actions.  This module deliberately owns no capture, transport, write,
or experiment-authority implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .discovery_models import EvidenceLevel
from .discovery_lab import LabInstrument
from .lab_orchestrator import ACTION_TEMPLATES, initial_lab_hypotheses, plan_next_experiment


class ExpertToolAction(Enum):
    INSPECT = "inspect"
    RUN_AUTHORIZED_PLAN = "run_authorized_plan"
    IMPORT_VENDOR_CAPTURE = "import_vendor_capture"


@dataclass(frozen=True, slots=True)
class ExpertTool:
    tool_id: str
    group: str
    title: str
    description: str
    implementation: str
    action: ExpertToolAction = ExpertToolAction.INSPECT


GROUPS = (
    "Inspect & Evidence",
    "Protocol Analysis",
    "Hardware Investigators",
    "Routing & Persistence",
    "Experiment Planning",
    "Capture & Corpus",
)


TOOLS = (
    ExpertTool("topology", GROUPS[0], "Device topology & descriptors",
               "Inspect the exact physical-device graph, interfaces, and parsed HID descriptors.",
               "device_topology + DiscoveryEngine.descriptors"),
    ExpertTool("raw_observations", GROUPS[0], "Raw HID / report observations",
               "Inspect retained read-only protocol observations without transmitting reports.",
               "LabExperiment.observations + DiscoveryEngine.feature_snapshots"),
    ExpertTool("feature_baseline", GROUPS[0], "Feature-report baseline",
               "Inspect bounded read-only feature snapshots captured during discovery.",
               "FEATURE_BASELINE + DiscoveryEngine.feature_snapshots"),
    ExpertTool("usb_observations", GROUPS[0], "Selected-device USB observations",
               "Inspect retained USB observations already scoped to the selected physical device.",
               "SELECTED_DEVICE_USBMON + LabExperiment.usb_observations"),
    ExpertTool("evidence", GROUPS[0], "Evidence browser / review",
               "Review discovery, capability, device, protocol, and imported evidence by proof level.",
               "DiscoveryEvidence + StagedEvidenceRecord"),
    ExpertTool("conflicts", GROUPS[0], "Contradictions & conflicts",
               "Inspect retained contradictions instead of collapsing them into a preferred meaning.",
               "DifferentialAnalysis + routing/power/import conflicts"),
    ExpertTool("repertoire", GROUPS[1], "Protocol repertoire / grammar / codec",
               "Inspect known-family candidates, recognized grammar, and codec evidence.",
               "protocol_repertoire + protocol_grammar + protocol_codec"),
    ExpertTool("logical_records", GROUPS[1], "Logical-record reconstruction",
               "Inspect higher-level records reconstructed from bounded observed traffic.",
               "LOGICAL_RECORD_RECONSTRUCTION + LabExperiment.logical_records"),
    ExpertTool("differential", GROUPS[1], "Differential Analyzer",
               "Inspect action-versus-control field rankings and semantic recommendations.",
               "analyze_differential_experiment"),
    ExpertTool("dialogue", GROUPS[1], "Temporal dialogue analysis",
               "Inspect request/response, burst, and asynchronous pushed-state relationships.",
               "DialogueAssembler + LabExperiment.dialogues"),
    ExpertTool("timing", GROUPS[1], "Protocol Timing Profiler",
               "Inspect bounded latency, cadence, stability, freshness, and lifecycle timing evidence.",
               "profile_experiment_timing"),
    ExpertTool("dependency", GROUPS[1], "Dependency inference",
               "Inspect observed state dependencies without treating correlation as authority.",
               "DEPENDENCY_INFERENCE + differential evidence"),
    ExpertTool("integrity", GROUPS[1], "Integrity / checksum inference",
               "Inspect bounded integrity and checksum candidates derived from observed frames.",
               "INTEGRITY_INFERENCE + protocol_codec"),
    ExpertTool("dpi", GROUPS[2], "DPI / CPI investigator",
               "Inspect independent physical CPI evidence and calibrated DPI-cycle state.",
               "CPI_VERIFIER + calibrated discovery"),
    ExpertTool("polling", GROUPS[2], "Polling investigator",
               "Inspect read-only motion-timing measurements and physical polling evidence.",
               "POLLING_VERIFIER + polling observation"),
    ExpertTool("power", GROUPS[2], "Battery / charging / power-state",
               "Inspect conservative battery, charging, source, cadence, and contradiction analysis.",
               "analyze_power_state"),
    ExpertTool("freshness", GROUPS[2], "Pushed-state / freshness",
               "Inspect pushed state, state reads, and stale-versus-fresh relationships.",
               "DialogueAssembler pushed-state + freshness analysis"),
    ExpertTool("routing", GROUPS[3], "Routing Mapper",
               "Inspect receiver/child ownership, route candidates, graphs, and ambiguity.",
               "analyze_receiver_child_routing"),
    ExpertTool("persistence", GROUPS[3], "Persistence Verifier",
               "Inspect effect and persistence evidence across bounded lifecycle checkpoints.",
               "verify_state_effect_persistence"),
    ExpertTool("reconnect", GROUPS[3], "Reconnect / rebind evidence",
               "Inspect generation-scoped disconnect, reconnect, and first-valid-state evidence.",
               "LabExperiment.lifecycle_events + routing rediscovery"),
    ExpertTool("restoration", GROUPS[3], "Restoration state",
               "Inspect whether original state restoration is required, complete, or still manual.",
               "PersistenceAssessment.restoration"),
    ExpertTool("experiment", GROUPS[4], "LabExperiment / LabExperimentPlan",
               "Inspect the canonical experiment, current plan, instruments, criteria, and stop state.",
               "LabExperiment + LabExperimentPlan"),
    ExpertTool("actions", GROUPS[4], "Controlled Action Matrix",
               "Inspect the implemented passive, physical, vendor-demonstration, and restoration actions.",
               "ACTION_TEMPLATES"),
    ExpertTool("information_gain", GROUPS[4], "Information-gain planner",
               "Inspect the selected action, alternatives, expected gain, and bounded observation windows.",
               "choose_experiment + plan_next_experiment"),
    ExpertTool("authorized", GROUPS[4], "Bounded authorized experiment",
               "Run the current plan through the existing selected-device safety and authorization gates.",
               "execute_lab_plan", ExpertToolAction.RUN_AUTHORIZED_PLAN),
    ExpertTool("vendor_import", GROUPS[5], "Vendor Capture Importer",
               "Stage a bounded local JSON/JSONL capture; packets are never replayed or transmitted.",
               "VendorCaptureStore + import_vendor_capture", ExpertToolAction.IMPORT_VENDOR_CAPTURE),
    ExpertTool("import_review", GROUPS[5], "Imported evidence review / staging",
               "Inspect the current import manifest, review state, warnings, conflicts, and suppression.",
               "VendorCaptureImport + CaptureReviewStatus"),
    ExpertTool("corpus", GROUPS[5], "Corpus / protocol knowledge",
               "Inspect matched repertoire candidates and local corpus/provenance knowledge.",
               "hid_corpus + protocol repertoire + trace corpus"),
)

TOOL_BY_ID = {tool.tool_id: tool for tool in TOOLS}

# Auditable coverage of every instrument the canonical planner can select.
LAB_INSTRUMENT_TO_TOOL = {
    LabInstrument.HID_OBSERVATION: "raw_observations",
    LabInstrument.FEATURE_BASELINE: "feature_baseline",
    LabInstrument.SELECTED_DEVICE_USBMON: "usb_observations",
    LabInstrument.LOGICAL_RECORD_RECONSTRUCTION: "logical_records",
    LabInstrument.TEMPORAL_DIALOGUE: "dialogue",
    LabInstrument.PROTOCOL_TIMING_PROFILER: "timing",
    LabInstrument.DIFFERENTIAL_ANALYZER: "differential",
    LabInstrument.CPI_VERIFIER: "dpi",
    LabInstrument.POLLING_VERIFIER: "polling",
    LabInstrument.FRESHNESS_ANALYSIS: "freshness",
    LabInstrument.DEPENDENCY_INFERENCE: "dependency",
    LabInstrument.INTEGRITY_INFERENCE: "integrity",
    LabInstrument.RECEIVER_TOPOLOGY: "routing",
}


def tools_for_group(group: str) -> tuple[ExpertTool, ...]:
    return tuple(tool for tool in TOOLS if tool.group == group)


def _experiment(controller: Any) -> Any | None:
    return getattr(controller, "lab_experiment", None)


def _plan(controller: Any) -> Any:
    experiment = _experiment(controller)
    return (
        getattr(experiment, "next_plan", None)
        or getattr(experiment, "plan", None)
        or plan_next_experiment(initial_lab_hypotheses())
    )


def _engine(controller: Any) -> Any | None:
    return getattr(controller, "discovery_engine", None)


def _result(controller: Any) -> Any | None:
    return getattr(controller, "discovery_result", None)


def _imported(controller: Any) -> Any | None:
    return getattr(controller, "vendor_capture_import", None)


def _count(value: Any, field: str) -> int:
    return len(getattr(value, field, ()) or ()) if value is not None else 0


def _statuses(controller: Any, tool_id: str) -> tuple[str, ...]:
    experiment = _experiment(controller)
    result = _result(controller)
    engine = _engine(controller)
    imported = _imported(controller)
    read_only = ("READ ONLY",)
    if tool_id == "topology":
        return (("READY",) if result else ("NO EVIDENCE",)) + read_only
    if tool_id == "raw_observations":
        observed = _count(experiment, "observations") or bool(
            getattr(engine, "feature_snapshots", {}) if engine else {}
        )
        return (("OBSERVED",) if observed else ("NO EVIDENCE",)) + read_only
    if tool_id == "feature_baseline":
        snapshots = getattr(engine, "feature_snapshots", {}) if engine else {}
        return (("OBSERVED",) if snapshots else ("NO EVIDENCE",)) + read_only
    if tool_id == "usb_observations":
        return (("OBSERVED",) if _count(experiment, "usb_observations") else ("NO EVIDENCE",)) + read_only
    if tool_id == "evidence":
        evidence = list(getattr(result, "observations", ()) or ()) if result else []
        if result:
            evidence += list(getattr(result.device, "evidence", ()) or ())
            evidence += list(getattr(result.protocol, "evidence", ()) or ()) if result.protocol else []
            for capability in result.capabilities.values():
                evidence += list(capability.evidence)
        if any(getattr(item, "level", None) is EvidenceLevel.PROVEN for item in evidence):
            state = "PROVEN"
        else:
            state = "OBSERVED" if evidence or imported else "NO EVIDENCE"
        return (state,) + read_only
    if tool_id == "conflicts":
        return (("OBSERVED",) if _conflict_count(controller) else ("NO EVIDENCE",)) + read_only
    if tool_id == "repertoire":
        candidates = tuple(getattr(engine, "repertoire_candidates", ()) or ()) if engine else ()
        return (("DECODED",) if candidates or getattr(result, "protocol", None) else ("NO EVIDENCE",)) + read_only
    if tool_id == "logical_records":
        return (("DECODED",) if _count(experiment, "logical_records") else ("NO EVIDENCE",)) + read_only
    if tool_id == "differential":
        return (("OBSERVED",) if getattr(experiment, "analysis", None) else ("NO EVIDENCE",)) + read_only
    if tool_id == "dialogue":
        return (("OBSERVED",) if _count(experiment, "dialogues") or _count(experiment, "bursts") else ("NO EVIDENCE",)) + read_only
    if tool_id == "timing":
        return (("OBSERVED",) if getattr(experiment, "timing_profile", None) else ("NO EVIDENCE",)) + read_only
    if tool_id in {"dependency", "integrity"}:
        return (("OBSERVED",) if getattr(experiment, "analysis", None) else ("NO EVIDENCE",)) + read_only
    if tool_id == "dpi":
        observed = _count(experiment, "physical_cpi_evidence") or bool(
            getattr(getattr(controller, "observed_hardware", None), "calibrated_dpi_cycle", ())
        )
        return (("OBSERVED", "READ ONLY") if observed else ("NEEDS HARDWARE", "READ ONLY"))
    if tool_id == "polling":
        observed = _count(experiment, "physical_polling_evidence") or getattr(
            getattr(controller, "choices", None), "measured_polling_rate", None
        ) is not None
        return (("OBSERVED", "READ ONLY") if observed else ("NEEDS HARDWARE", "READ ONLY"))
    if tool_id == "power":
        return (("OBSERVED",) if getattr(experiment, "power_analysis", None) else ("NO EVIDENCE",)) + read_only
    if tool_id == "freshness":
        return (("OBSERVED",) if _count(experiment, "pushed_states") or _count(experiment, "state_reads") else ("NO EVIDENCE",)) + read_only
    if tool_id == "routing":
        return (("OBSERVED",) if getattr(experiment, "routing_analysis", None) else ("NO EVIDENCE",)) + read_only
    if tool_id == "persistence":
        return (("OBSERVED",) if getattr(experiment, "persistence_assessment", None) else ("NO EVIDENCE",)) + read_only
    if tool_id == "reconnect":
        return (("OBSERVED",) if _count(experiment, "lifecycle_events") else ("NO EVIDENCE",)) + read_only
    if tool_id == "restoration":
        return (("READY",) if getattr(experiment, "persistence_assessment", None) else ("NO EVIDENCE",)) + read_only
    if tool_id in {"experiment", "information_gain"}:
        return ("READY", "READ ONLY")
    if tool_id == "actions":
        return ("READY", "READ ONLY")
    if tool_id == "authorized":
        plan = _plan(controller)
        ready = bool(
            result is not None
            and engine is not None
            and not getattr(result.device, "ambiguous", False)
            and getattr(plan, "selected_action", None) is not None
        )
        return ("READY",) if ready else ("DISABLED",)
    if tool_id == "vendor_import":
        return ("READY", "READ ONLY")
    if tool_id == "import_review":
        return (("OBSERVED",) if imported else ("NO EVIDENCE",)) + read_only
    if tool_id == "corpus":
        candidates = tuple(getattr(engine, "repertoire_candidates", ()) or ()) if engine else ()
        return (("DECODED",) if candidates else ("READY",)) + read_only
    raise KeyError(tool_id)


def tool_status(controller: Any, tool: ExpertTool) -> tuple[str, ...]:
    return _statuses(controller, tool.tool_id)


def _conflict_count(controller: Any) -> int:
    experiment = _experiment(controller)
    imported = _imported(controller)
    count = len(getattr(getattr(experiment, "analysis", None), "contradictions", ()) or ())
    count += len(getattr(getattr(experiment, "routing_analysis", None), "ambiguities", ()) or ())
    count += len(getattr(getattr(experiment, "power_analysis", None), "contradictions", ()) or ())
    count += len(getattr(getattr(experiment, "persistence_assessment", None), "contradictions", ()) or ())
    count += len(getattr(getattr(imported, "manifest", None), "conflicts", ()) or ())
    return count


def _lines(controller: Any, tool_id: str) -> tuple[str, ...]:
    experiment = _experiment(controller)
    result = _result(controller)
    engine = _engine(controller)
    imported = _imported(controller)
    plan = _plan(controller)
    if tool_id == "topology":
        if result is None:
            return ("Run Automatic Discovery to establish exact topology and descriptors.",)
        device = result.device
        descriptors = getattr(engine, "descriptors", {}) if engine else {}
        return (
            f"Physical mouse: {device.name}",
            f"Interfaces: {len(device.evdev_nodes)} evdev · {len(device.hidraw_nodes)} hidraw",
            f"Parsed descriptors: {len(descriptors)} · ambiguous: {'yes' if device.ambiguous else 'no'}",
        )
    if tool_id == "raw_observations":
        snapshots = getattr(engine, "feature_snapshots", {}) if engine else {}
        observations = tuple(getattr(experiment, "observations", ()) or ())
        samples = tuple(
            f"{item.stream_id[-18:]} · {len(item.payload)} B · {item.payload.hex(' ')}"
            for item in observations[:5]
        )
        return (f"Lab observations: {len(observations)}",
                f"Read-only feature snapshot interfaces: {len(snapshots)}",
                *samples,
                "No output or feature report can be transmitted from this view.")
    if tool_id == "feature_baseline":
        snapshots = getattr(engine, "feature_snapshots", {}) if engine else {}
        reports = sum(len(items) for items in snapshots.values())
        return (f"Snapshot interfaces: {len(snapshots)}", f"Feature reports retained: {reports}",
                "Snapshots are read-only discovery evidence.")
    if tool_id == "usb_observations":
        return (f"Selected-device USB observations: {_count(experiment, 'usb_observations')}",
                "No live USB capture is started from this evidence view.")
    if tool_id == "evidence":
        evidence = list(getattr(result, "observations", ()) or ()) if result else []
        if result:
            evidence += list(getattr(result.device, "evidence", ()) or ())
            evidence += list(getattr(result.protocol, "evidence", ()) or ()) if result.protocol else []
        observations = len(evidence)
        capability = sum(len(item.evidence) for item in result.capabilities.values()) if result else 0
        staged = _count(imported, "evidence_records")
        return (f"Discovery evidence: {observations}", f"Capability evidence: {capability}",
                f"Imported staged evidence: {staged}",
                *(f"{item.level.name}: {item.code} — {item.message}" for item in evidence[:5]))
    if tool_id == "conflicts":
        conflicts = []
        conflicts += list(getattr(getattr(experiment, "analysis", None), "contradictions", ()) or ())
        conflicts += list(getattr(getattr(experiment, "routing_analysis", None), "ambiguities", ()) or ())
        conflicts += list(getattr(getattr(experiment, "power_analysis", None), "contradictions", ()) or ())
        conflicts += list(getattr(getattr(experiment, "persistence_assessment", None), "contradictions", ()) or ())
        conflicts += list(getattr(getattr(imported, "manifest", None), "conflicts", ()) or ())
        return (f"Retained contradictions / conflicts: {len(conflicts)}",
                *(str(item) for item in conflicts[:6]),
                "Conflicts remain explicit and cannot authorize a write.")
    if tool_id == "repertoire":
        candidates = tuple(getattr(engine, "repertoire_candidates", ()) or ()) if engine else ()
        protocol = getattr(getattr(result, "protocol", None), "name", None)
        return (f"Known protocol: {protocol or 'none'}", f"Repertoire candidates: {len(candidates)}",
                *(f"{item.family.name} · {getattr(item, 'score', 'candidate')}" for item in candidates[:5]),
                "Grammar and codec knowledge is descriptive unless independently PROVEN.")
    if tool_id == "logical_records":
        return (f"Reconstructed logical records: {_count(experiment, 'logical_records')}",
                "Record reconstruction retains the source connection generation.")
    if tool_id == "differential":
        analysis = getattr(experiment, "analysis", None)
        return (f"Ranked fields: {_count(analysis, 'ranked_fields')}",
                f"Contradictions: {_count(analysis, 'contradictions')}",
                f"Recommendation: {getattr(getattr(analysis, 'next_recommended_experiment', None), 'experiment', 'none')}",
                *(f"{item.stream_id[-16:]} byte {item.offset} · score {item.score:g}"
                  for item in (getattr(analysis, "ranked_fields", ()) or ())[:5]))
    if tool_id == "dialogue":
        return (f"Dialogues: {_count(experiment, 'dialogues')}", f"Bursts: {_count(experiment, 'bursts')}",
                f"Pushed states: {_count(experiment, 'pushed_states')}")
    if tool_id == "timing":
        timing = getattr(experiment, "timing_profile", None)
        return (f"Timing summaries: {_count(timing, 'summaries')}",
                f"Timing differentials: {_count(timing, 'differentials')}",
                f"Busy/poll cycles: {_count(timing, 'busy_poll_cycles')}",
                *(f"{item.relationship.value.replace('_', ' ')} · median {item.median_ns} ns"
                  for item in (getattr(timing, "summaries", ()) or ())[:5]))
    if tool_id == "dependency":
        analysis = getattr(experiment, "analysis", None)
        dependencies = getattr(analysis, "dependencies", None)
        return (f"Ranked fields available: {_count(analysis, 'ranked_fields')}",
                f"Dependency candidates: {_count(dependencies, 'candidates')}",
                f"Unexplained offsets: {_count(dependencies, 'unexplained_offsets')}",
                "Dependency correlation never grants write authority.")
    if tool_id == "integrity":
        analysis = getattr(experiment, "analysis", None)
        return (f"Integrity streams inspected: {_count(analysis, 'integrity')}",
                f"Transaction differences: {_count(analysis, 'transaction_differences')}",
                "Checksum candidates remain descriptive until independently established.")
    if tool_id == "dpi":
        cycle = tuple(getattr(getattr(controller, "observed_hardware", None), "calibrated_dpi_cycle", ()) or ())
        return (f"Physical CPI evidence: {_count(experiment, 'physical_cpi_evidence')}",
                "Calibrated cycle: " + (" → ".join(map(str, cycle)) if cycle else "unavailable"),
                "Physical observation does not grant DPI write authority.")
    if tool_id == "polling":
        measured = getattr(getattr(controller, "choices", None), "measured_polling_rate", None)
        return (f"Physical polling evidence: {_count(experiment, 'physical_polling_evidence')}",
                f"Current read-only measurement: {str(measured) + ' Hz' if measured else 'unavailable'}")
    if tool_id == "power":
        analysis = getattr(experiment, "power_analysis", None)
        return (f"Power evidence: {_count(experiment, 'power_evidence')}",
                f"Power findings: {_count(analysis, 'summary')}",
                f"Contradictions: {_count(analysis, 'contradictions')}",
                *(str(item) for item in (getattr(analysis, "summary", ()) or ())[:6]))
    if tool_id == "freshness":
        return (f"Pushed states: {_count(experiment, 'pushed_states')}",
                f"Explicit state reads: {_count(experiment, 'state_reads')}",
                "Stale observations remain separate from fresh state.")
    if tool_id == "routing":
        analysis = getattr(experiment, "routing_analysis", None)
        return (f"Routing evidence: {_count(experiment, 'routing_evidence')}",
                f"Graph nodes: {_count(getattr(analysis, 'graph', None), 'nodes')}",
                f"Unresolved ambiguities: {_count(analysis, 'ambiguities')}",
                *(str(item) for item in (getattr(analysis, "summary", ()) or ())[:6]))
    if tool_id == "persistence":
        assessment = getattr(experiment, "persistence_assessment", None)
        strongest = getattr(getattr(assessment, "strongest_confirmed_level", None), "name", "none")
        return (f"Effect evidence: {_count(experiment, 'effect_evidence')}",
                f"Persistence evidence: {_count(experiment, 'persistence_evidence')}",
                f"Strongest confirmed level: {strongest.lower().replace('_', ' ')}",
                "Classifications: " + " · ".join(
                    item.value.replace("_", " ")
                    for item in (getattr(assessment, "classifications", ()) or ())
                ))
    if tool_id == "reconnect":
        return (f"Lifecycle events: {_count(experiment, 'lifecycle_events')}",
                f"Connection generation: {getattr(experiment, 'connection_generation', 'none')}",
                "Relationships never cross generations without explicit lifecycle evidence.")
    if tool_id == "restoration":
        restoration = getattr(getattr(experiment, "persistence_assessment", None), "restoration", None)
        return (f"Restoration required: {'yes' if getattr(restoration, 'required', False) else 'no'}",
                f"Restoration verified: {'yes' if getattr(restoration, 'verified', False) else 'no'}",
                f"Instruction: {getattr(restoration, 'instruction', None) or 'not recorded'}")
    if tool_id == "experiment":
        return (f"Experiment: {getattr(experiment, 'experiment_id', 'not run')}",
                f"Plan: {getattr(plan, 'plan_id', 'none')}",
                f"Instruments: {', '.join(item.value for item in plan.instruments) or 'none'}")
    if tool_id == "actions":
        classes = sorted({item.safety_class.value.replace("_", " ") for item in ACTION_TEMPLATES.values()})
        return (f"Implemented actions: {len(ACTION_TEMPLATES)}",
                "Safety classes: " + " · ".join(classes),
                *(f"{item.label} · {item.safety_class.value.replace('_', ' ')}"
                  for item in tuple(ACTION_TEMPLATES.values())[:8]),
                "Unknown and dangerous commands are absent from the matrix.")
    if tool_id == "information_gain":
        selected = getattr(plan, "selected_action", None)
        return (f"Selected: {getattr(selected, 'label', 'none')}",
                f"Candidate actions: {len(plan.candidate_actions)}",
                f"Expected information gain: {plan.expected_information_gain_bits:.2f} bits")
    if tool_id == "authorized":
        selected = getattr(plan, "selected_action", None)
        return (f"Current action: {getattr(selected, 'label', 'none')}",
                f"Safety class: {plan.safety_class.value.replace('_', ' ')}",
                "Execution uses existing identity, ambiguity, action-class, and verifier gates.")
    if tool_id == "vendor_import":
        return ("Accepted formats: canonical OMUS JSON / JSONL",
                "Local parsing only · no packet replay · no hardware access",
                "Imported evidence cannot become PROVEN or enable writes.")
    if tool_id == "import_review":
        manifest = getattr(imported, "manifest", None)
        return (f"Review state: {getattr(getattr(manifest, 'review_status', None), 'value', 'no import')}",
                f"Accepted records: {getattr(manifest, 'accepted_records', 0)}",
                f"Warnings: {_count(manifest, 'warnings')} · conflicts: {_count(manifest, 'conflicts')}",
                *(f"Warning: {item}" for item in (getattr(manifest, "warnings", ()) or ())[:4]),
                *(f"Conflict: {item}" for item in (getattr(manifest, "conflicts", ()) or ())[:4]))
    if tool_id == "corpus":
        candidates = tuple(getattr(engine, "repertoire_candidates", ()) or ()) if engine else ()
        families = tuple(getattr(item.family, "name", "unknown") for item in candidates)
        return (f"Matched repertoire families: {len(families)}",
                "Families: " + (" · ".join(families) if families else "none"),
                "Corpus and vendor knowledge remain evidence, not write authority.")
    raise KeyError(tool_id)


def tool_context(controller: Any, tool: ExpertTool) -> tuple[str, ...]:
    return _lines(controller, tool.tool_id)


def tool_row(controller: Any, tool: ExpertTool) -> str:
    return f"{tool.title}  [{' · '.join(tool_status(controller, tool))}]"
