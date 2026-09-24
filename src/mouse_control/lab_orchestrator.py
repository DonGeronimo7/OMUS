# SPDX-License-Identifier: AGPL-3.0-or-later
"""Safe information-gain orchestration for canonical Discovery Lab experiments.

Planning is pure and replayable.  Execution only observes the selected device
and requests physical or external-vendor actions; this module owns no hardware
write primitive and cannot grant write authority.
"""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from typing import Any, Callable, Iterable, Mapping, Sequence

from .discovery_lab import (
    ActionSafetyClass,
    ControlledAction,
    ControlledActionType,
    DiscoveryLabCancelled,
    FieldSignal,
    HypothesisDisposition,
    HypothesisUpdate,
    LabExperiment,
    LabExperimentPlan,
    LabHypothesis,
    LabInstrument,
    LabInterval,
    LabProgressEvent,
    LabProgressStage,
    LabStep,
    LabStopReason,
    ObservationWindowPlan,
    PhysicalEvidence,
    ProtocolTimingProfile,
    TimingRelationship,
    _interval_record,
    _sample_observations,
    _sample_transitions,
    analyze_differential_experiment,
)
from .information_gain import ExperimentHypothesis, choose_experiment
from .learning_session import LearningSample, ReadOnlyLearningSession


def _action(
    action_id: str,
    action_type: ControlledActionType,
    label: str,
    safety: ActionSafetyClass,
    instruction: str,
    *,
    effort: int = 1,
    duration: int = 1,
    risk: int = 0,
    equipment: int = 0,
    burden: int = 1,
    tags: tuple[str, ...] = (),
) -> ControlledAction:
    return ControlledAction(
        action_id, action_type, label, safety, instruction,
        effort, duration, risk, equipment, burden, tags,
    )


ACTION_TEMPLATES: Mapping[str, ControlledAction] = {
    "QUIET_BASELINE": _action(
        "QUIET_BASELINE", ControlledActionType.QUIET, "quiet baseline",
        ActionSafetyClass.PASSIVE, "Leave the selected mouse completely untouched.",
        effort=0, tags=("baseline", "periodic", "freshness"),
    ),
    "MOUSE_MOVEMENT": _action(
        "MOUSE_MOVEMENT", ControlledActionType.MOVE_MOUSE, "ordinary mouse movement",
        ActionSafetyClass.PHYSICAL_ONLY, "Move the selected mouse normally without pressing a button.",
        tags=("movement", "polling"),
    ),
    "GENERIC_BUTTON_PRESS": _action(
        "GENERIC_BUTTON_PRESS", ControlledActionType.MOUSE_BUTTON_PRESS, "one mouse-button press",
        ActionSafetyClass.PHYSICAL_ONLY, "Press the labelled mouse button exactly once when prompted.",
        tags=("button", "report"),
    ),
    "DPI_STAGE_CHANGE": _action(
        "DPI_STAGE_CHANGE", ControlledActionType.DPI_BUTTON_GENERIC, "one DPI-stage change",
        ActionSafetyClass.PHYSICAL_ONLY, "Press the physical DPI button exactly once when prompted.",
        tags=("dpi", "stage", "dependency"),
    ),
    "MULTI_DPI_STAGE_SEQUENCE": _action(
        "MULTI_DPI_STAGE_SEQUENCE", ControlledActionType.DPI_BUTTON_GENERIC,
        "three distinct DPI stages", ActionSafetyClass.PHYSICAL_ONLY,
        "Press the DPI button exactly once per action prompt.",
        effort=2, duration=2, burden=3, tags=("dpi", "stage", "dependency", "sequence"),
    ),
    "CONNECT_DISCONNECT": _action(
        "CONNECT_DISCONNECT", ControlledActionType.DISCONNECT_RECEIVER,
        "disconnect and reconnect the selected device", ActionSafetyClass.PHYSICAL_ONLY,
        "Disconnect and reconnect only the selected mouse or its receiver when prompted.",
        effort=3, duration=3, risk=1, equipment=1, burden=2,
        tags=("lifecycle", "receiver", "reconnect"),
    ),
    "CHARGING_TRANSITION": _action(
        "CHARGING_TRANSITION", ControlledActionType.CONNECT_CHARGING,
        "charging-state transition", ActionSafetyClass.PHYSICAL_ONLY,
        "Connect or disconnect the selected mouse's charging cable when prompted.",
        effort=2, duration=2, equipment=1, burden=2, tags=("charging", "power"),
    ),
    "VENDOR_SETTING_CHANGE": _action(
        "VENDOR_SETTING_CHANGE", ControlledActionType.VENDOR_CHANGE_PROFILE,
        "vendor-software setting demonstration", ActionSafetyClass.EXTERNAL_VENDOR_DEMONSTRATION,
        "Use the vendor application to make the requested setting change when prompted.",
        effort=2, duration=3, equipment=2, burden=2,
        tags=("vendor", "dpi", "polling", "profile"),
    ),
    "IDLE_PERSISTENCE": _action(
        "IDLE_PERSISTENCE", ControlledActionType.QUIET,
        "bounded idle persistence observation", ActionSafetyClass.PASSIVE,
        "Leave the selected mouse and its connection unchanged during the observation.",
        effort=0, duration=2, burden=1, tags=("persistence", "idle", "freshness"),
    ),
    "PROTOCOL_REREAD": _action(
        "PROTOCOL_REREAD", ControlledActionType.QUIET,
        "fresh protocol state re-read", ActionSafetyClass.PASSIVE,
        "Leave the selected mouse unchanged while OMUS waits for fresh state.",
        effort=0, duration=1, burden=1, tags=("persistence", "reread", "freshness"),
    ),
    "RECONNECT_PERSISTENCE": _action(
        "RECONNECT_PERSISTENCE", ControlledActionType.DISCONNECT_CABLE,
        "selected-device reconnect persistence test", ActionSafetyClass.PHYSICAL_ONLY,
        "Disconnect and reconnect the selected mouse when prompted.",
        effort=3, duration=3, risk=1, burden=1,
        tags=("persistence", "lifecycle", "reconnect"),
    ),
    "RECEIVER_RECONNECT_PERSISTENCE": _action(
        "RECEIVER_RECONNECT_PERSISTENCE", ControlledActionType.DISCONNECT_RECEIVER,
        "receiver reconnect persistence test", ActionSafetyClass.PHYSICAL_ONLY,
        "Disconnect and reconnect only the selected mouse receiver when prompted.",
        effort=4, duration=4, risk=1, equipment=1, burden=1,
        tags=("persistence", "lifecycle", "receiver", "reconnect"),
    ),
    "POWER_CYCLE_PERSISTENCE": _action(
        "POWER_CYCLE_PERSISTENCE", ControlledActionType.POWER_CYCLE,
        "device power-cycle persistence test", ActionSafetyClass.PHYSICAL_ONLY,
        "Turn the selected mouse off and back on when prompted.",
        effort=5, duration=5, risk=2, burden=1,
        tags=("persistence", "lifecycle", "power"),
    ),
    "MANUAL_RESTORE": _action(
        "MANUAL_RESTORE", ControlledActionType.CUSTOM_LABELLED_ACTION,
        "manual original-state restoration", ActionSafetyClass.PHYSICAL_ONLY,
        "Restore the original setting with the same physical or external tool used for the demonstration.",
        effort=2, duration=2, burden=1, tags=("restoration",),
    ),
    "OTHER_CHILD_ROUTE_CONTROL": _action(
        "OTHER_CHILD_ROUTE_CONTROL", ControlledActionType.CUSTOM_LABELLED_ACTION,
        "analogous action on another paired child", ActionSafetyClass.PHYSICAL_ONLY,
        "Leave the selected mouse idle and perform the prompted action only on the other paired device.",
        effort=2, duration=2, equipment=1, burden=2,
        tags=("routing", "other-child", "negative-control"),
    ),
    "VENDOR_POWER_STATE_CHANGE": _action(
        "VENDOR_POWER_STATE_CHANGE", ControlledActionType.CUSTOM_LABELLED_ACTION,
        "vendor-software power-state demonstration",
        ActionSafetyClass.EXTERNAL_VENDOR_DEMONSTRATION,
        "Use the vendor application only to display or demonstrate the requested power state.",
        effort=1, duration=2, equipment=2, burden=1,
        tags=("battery", "charging", "power", "vendor"),
    ),
}


SAFE_AUTOMATIC_CLASSES = {
    ActionSafetyClass.PASSIVE,
    ActionSafetyClass.PHYSICAL_ONLY,
    ActionSafetyClass.EXTERNAL_VENDOR_DEMONSTRATION,
}


def initial_lab_hypotheses() -> tuple[LabHypothesis, ...]:
    """Seed the first generic Lab question without claiming any byte semantics."""

    common = {
        "QUIET_BASELINE": "stable",
        "MOUSE_MOVEMENT": "movement-only",
        "GENERIC_BUTTON_PRESS": "button-only",
    }
    return (
        LabHypothesis(
            "dpi-direct", "Which field represents DPI?", "a candidate field contains direct DPI",
            "dpi", {**common, "DPI_STAGE_CHANGE": "numeric-step", "MULTI_DPI_STAGE_SEQUENCE": "numeric-series"},
        ),
        LabHypothesis(
            "dpi-stage", "Which field represents DPI?", "a candidate field contains a DPI stage index",
            "dpi", {**common, "DPI_STAGE_CHANGE": "index-step", "MULTI_DPI_STAGE_SEQUENCE": "small-cycle"},
        ),
        LabHypothesis(
            "button-report", "Which field represents DPI?", "the observed change is button metadata only",
            "dpi", {**common, "DPI_STAGE_CHANGE": "button-pulse", "MULTI_DPI_STAGE_SEQUENCE": "repeated-pulse"},
        ),
    )


def derive_observation_windows(profile: ProtocolTimingProfile | None) -> ObservationWindowPlan:
    if profile is None or not profile.summaries:
        return ObservationWindowPlan(
            1.5, 1.5, 1.5, 1.5, source="bounded conservative default",
            uncertainty="No timing profile was available; windows are conservative and bounded.",
        )
    durations = tuple(
        value
        for item in profile.summaries
        for value in (item.maximum_ns, item.median_ns)
        if value is not None and value > 0
    )
    if not durations:
        return ObservationWindowPlan(
            1.5, 1.5, 1.5, 1.5, source="bounded conservative default",
            uncertainty="Timing evidence had no usable duration estimate.",
        )
    longest = max(durations) / 1_000_000_000
    settling = min(5.0, max(0.05, longest * 1.25))
    capture = min(10.0, max(0.5, longest * 3.0))
    periodic = any(item.classification.value == "periodic" for item in profile.summaries)
    baseline = min(10.0, max(capture, longest * (4.0 if periodic else 2.0)))
    return ObservationWindowPlan(
        round(baseline, 6), round(capture, 6), round(max(capture, settling * 2), 6),
        round(baseline, 6), round(settling, 6), source="ProtocolTimingProfile",
    )


def _repeat_count(action: ControlledAction, hypotheses: Sequence[LabHypothesis]) -> int:
    topics = {item.topic.lower() for item in hypotheses}
    if "persistence" in action.semantic_tags:
        return 1
    if "timing" in topics or "periodic" in topics or "polling" in topics:
        return 5
    if action.action_id == "MULTI_DPI_STAGE_SEQUENCE":
        return 3
    if "lifecycle" in action.semantic_tags or "power" in action.semantic_tags:
        return 2
    return 2


def _negative_control(action: ControlledAction) -> ControlledAction:
    if "dpi" in action.semantic_tags:
        return replace(ACTION_TEMPLATES["MOUSE_MOVEMENT"], label="movement without a DPI press")
    if "button" in action.semantic_tags:
        return replace(ACTION_TEMPLATES["QUIET_BASELINE"], label="same interval without a button press")
    if "charging" in action.semantic_tags or "power" in action.semantic_tags:
        return replace(ACTION_TEMPLATES["QUIET_BASELINE"], label="leave the power state unchanged")
    if "lifecycle" in action.semantic_tags:
        return replace(ACTION_TEMPLATES["QUIET_BASELINE"], label="equivalent interval without disconnecting")
    return ACTION_TEMPLATES["QUIET_BASELINE"]


def _instruments(action: ControlledAction, hypotheses: Sequence[LabHypothesis]) -> tuple[LabInstrument, ...]:
    topics = {item.topic.lower() for item in hypotheses}
    selected = {
        LabInstrument.HID_OBSERVATION,
        LabInstrument.FEATURE_BASELINE,
        LabInstrument.TEMPORAL_DIALOGUE,
        LabInstrument.PROTOCOL_TIMING_PROFILER,
        LabInstrument.DIFFERENTIAL_ANALYZER,
        LabInstrument.FRESHNESS_ANALYSIS,
        LabInstrument.DEPENDENCY_INFERENCE,
        LabInstrument.INTEGRITY_INFERENCE,
    }
    tags = set(action.semantic_tags)
    if "dpi" in topics or "dpi" in tags:
        selected.add(LabInstrument.CPI_VERIFIER)
    if "polling" in topics or "polling" in tags:
        selected.add(LabInstrument.POLLING_VERIFIER)
    if "receiver" in tags or "lifecycle" in topics:
        selected.add(LabInstrument.RECEIVER_TOPOLOGY)
    if topics & {"battery", "charging", "power"} or tags & {"battery", "charging", "power"}:
        selected.add(LabInstrument.RECEIVER_TOPOLOGY)
    if "usb" in topics or "vendor" in tags:
        selected.update({LabInstrument.SELECTED_DEVICE_USBMON, LabInstrument.LOGICAL_RECORD_RECONSTRUCTION})
    return tuple(sorted(selected, key=lambda item: item.value))


def plan_next_experiment(
    hypotheses: Sequence[LabHypothesis],
    *,
    available_actions: Iterable[ControlledAction] | None = None,
    timing_profile: ProtocolTimingProfile | None = None,
    authorized_bounded_action_ids: Iterable[str] = (),
) -> LabExperimentPlan:
    """Choose the maximum-information safe action, using human cost only as a tie-breaker."""

    hypotheses = tuple(item for item in hypotheses if item.disposition not in {HypothesisDisposition.REJECTED})
    offered = tuple(ACTION_TEMPLATES.values() if available_actions is None else available_actions)
    authorized = set(authorized_bounded_action_ids)
    safe = tuple(
        action for action in offered
        if action.safety_class in SAFE_AUTOMATIC_CLASSES
        or (
            action.safety_class is ActionSafetyClass.BOUNDED_ENGINE_EXPERIMENT
            and action.action_id in authorized
        )
    )
    info_hypotheses = tuple(
        ExperimentHypothesis(item.hypothesis_id, item.predicted_outcomes, item.weight)
        for item in hypotheses
    )
    ranked: list[tuple[float, int, str, ControlledAction]] = []
    for action in safe:
        choice = choose_experiment(info_hypotheses, allowed_experiments=(action.action_id,))
        if choice is not None:
            ranked.append((-choice.information_gain_bits, action.human_cost, action.action_id, action))
    if ranked:
        inverse_gain, _cost, _identifier, selected = min(ranked)
        gain = -inverse_gain
    else:
        selected = None
        gain = 0.0
    if selected is None:
        relevant = [
            action for action in safe
            if any(item.topic.lower() in action.semantic_tags for item in hypotheses)
        ]
        if len(hypotheses) <= 1 and relevant:
            selected = min(relevant, key=lambda item: (item.human_cost, item.action_id))
    windows = derive_observation_windows(timing_profile)
    stop = LabStopReason.INSUFFICIENT_SAFE_ACTIONS if selected is None else None
    repeat = _repeat_count(selected, hypotheses) if selected else 0
    control = _negative_control(selected) if selected else None
    purpose = hypotheses[0].question if hypotheses else "Resolve the next protocol ambiguity"
    identity = repr((purpose, tuple(item.hypothesis_id for item in hypotheses), selected.action_id if selected else None)).encode()
    return LabExperimentPlan(
        plan_id="plan-" + sha256(identity).hexdigest()[:20],
        purpose=purpose,
        target_hypotheses=hypotheses,
        candidate_actions=tuple(sorted(safe, key=lambda item: item.action_id)),
        selected_action=selected,
        baseline_requirements=("selected-device read-only observation", "stable feature baseline"),
        action_capture_requirements=("label only the requested action", "retain exact connection generation"),
        post_action_requirements=("observe settling and fresh state",),
        negative_control_requirements=("same scope and duration without the target action",),
        negative_control=control,
        repeat_count=repeat,
        instruments=_instruments(selected, hypotheses) if selected else (),
        success_criteria=("repeatable action/control separation", "independent physical evidence when selected"),
        stop_criteria=("ambiguity resolved", "conflicting evidence", "no safe informative action remains"),
        expected_information_gain_bits=gain,
        safety_class=selected.safety_class if selected else ActionSafetyClass.UNAVAILABLE,
        human_instructions=(selected.human_instruction,) if selected else (),
        windows=windows,
        stop_reason=stop,
    )


def update_hypotheses(
    hypotheses: Sequence[LabHypothesis], experiment: LabExperiment,
) -> tuple[HypothesisUpdate, ...]:
    analysis = experiment.analysis
    if analysis is None:
        return tuple(
            HypothesisUpdate(item.hypothesis_id, item.disposition, HypothesisDisposition.UNRESOLVED, ())
            for item in hypotheses
        )
    updates: list[HypothesisUpdate] = []
    for item in hypotheses:
        fields = analysis.ranked_fields
        if item.candidate_field is not None:
            fields = tuple(
                field for field in fields
                if (field.stream_id, field.offset) == item.candidate_field
            )
        positives = tuple(
            f"{field.stream_id}:{field.offset} separated action from control"
            for field in fields if FieldSignal.ACTION_CORRELATED in field.signals
        )
        negatives = tuple(
            contradiction for field in fields for contradiction in field.contradictions
        )
        if positives and negatives:
            after = HypothesisDisposition.CONFLICTED
        elif positives:
            after = (
                HypothesisDisposition.SUPPORTED
                if item.disposition is HypothesisDisposition.STRENGTHENED
                else HypothesisDisposition.STRENGTHENED
            )
        elif negatives:
            after = HypothesisDisposition.REJECTED
        else:
            after = HypothesisDisposition.WEAKENED if item.candidate_field else HypothesisDisposition.UNRESOLVED
        updates.append(HypothesisUpdate(item.hypothesis_id, item.disposition, after, positives, negatives))
    return tuple(updates)


def _stop_reason(updates: Sequence[HypothesisUpdate]) -> LabStopReason | None:
    if any(item.after is HypothesisDisposition.CONFLICTED for item in updates):
        return LabStopReason.CONFLICT_FOUND
    viable = [item for item in updates if item.after not in {HypothesisDisposition.REJECTED, HypothesisDisposition.WEAKENED}]
    strong = [item for item in viable if item.after in {HypothesisDisposition.SUPPORTED, HypothesisDisposition.STRENGTHENED}]
    if len(strong) == 1 and len(viable) == 1:
        return LabStopReason.HYPOTHESIS_RESOLVED
    if len(updates) == 1 and strong:
        return LabStopReason.SEMANTIC_CORRELATION_CONFIRMED
    return None


Verifier = Callable[[LabExperimentPlan], Sequence[PhysicalEvidence]]
EffectVerifier = Callable[[LabExperiment], LabExperiment]
RouteMapper = Callable[[LabExperiment], LabExperiment]
PowerInvestigator = Callable[[LabExperiment], LabExperiment]


def _suggests_power_investigation(experiment: LabExperiment) -> bool:
    """Return whether retained evidence merits conservative power analysis."""

    power_tokens = ("battery", "charge", "charging", "power")
    if experiment.human_action and any(
        token in experiment.human_action.lower() for token in power_tokens
    ):
        return True
    if experiment.plan is not None and any(
        hypothesis.topic.lower() in power_tokens
        for hypothesis in experiment.plan.target_hypotheses
    ):
        return True
    if any(
        any(token in state.semantic_state_id.lower() for token in power_tokens)
        for state in (*experiment.state_reads, *experiment.pushed_states)
    ):
        return True
    routing = experiment.routing_analysis
    if routing is not None and any(
        any(
            token in str(value).lower()
            for token in power_tokens
            for value in (
                item.source_route.namespace,
                item.source_route.channel,
                item.destination_route.namespace if item.destination_route else None,
                item.destination_route.channel if item.destination_route else None,
            )
            if value is not None
        )
        for item in routing.evidence
    ):
        return True
    timing = experiment.timing_profile
    return bool(
        timing is not None
        and any(
            item.relationship is TimingRelationship.PERIODIC_PUSH_CADENCE
            for item in timing.summaries
        )
        and experiment.analysis is not None
        and any(
            FieldSignal.STATUS_CANDIDATE in item.signals
            for item in experiment.analysis.ranked_fields
        )
    )


def execute_lab_plan(
    physical: Any,
    descriptors: Mapping[Any, Any],
    plan: LabExperimentPlan,
    *,
    prompt: Callable[[LabStep], bool],
    progress: Callable[[LabProgressEvent], None] | None = None,
    connection_generation: int = 0,
    session_factory: Callable[..., ReadOnlyLearningSession] = ReadOnlyLearningSession,
    verifier_runners: Mapping[LabInstrument, Verifier] | None = None,
    effect_verifier: EffectVerifier | None = None,
    route_mapper: RouteMapper | None = None,
    power_investigator: PowerInvestigator | None = None,
) -> LabExperiment:
    """Produce one canonical experiment from a plan using read-only capture callbacks."""

    if plan.selected_action is None:
        raise ValueError("the Lab has no safe informative action to execute")
    if plan.safety_class not in SAFE_AUTOMATIC_CLASSES:
        raise PermissionError("bounded engine actions require a separate authorized executor")
    if getattr(physical, "ambiguous", False):
        raise PermissionError("physical identity is ambiguous; the Lab refuses capture")
    emit = progress or (lambda _event: None)
    session = session_factory(physical, descriptors)
    samples: list[tuple[LabInterval, int, LearningSample, str | None]] = []
    action = plan.selected_action
    control = plan.negative_control
    capture_plan = [
        (LabInterval.BASELINE, 0, LabProgressStage.BASELINE, "Baseline", ACTION_TEMPLATES["QUIET_BASELINE"].human_instruction, None, plan.windows.baseline_seconds),
        *[
            (LabInterval.ACTION, repeat, LabProgressStage.ACTION_CAPTURE, "Controlled action", action.human_instruction, action.label, plan.windows.action_seconds)
            for repeat in range(1, plan.repeat_count + 1)
        ],
        (LabInterval.POST_ACTION, 0, LabProgressStage.POST_ACTION, "Post-action", "Leave the selected mouse unchanged while fresh state settles.", None, plan.windows.post_action_seconds),
        (LabInterval.NEGATIVE_CONTROL, 0, LabProgressStage.NEGATIVE_CONTROL, "Negative control", control.human_instruction if control else "Leave the mouse unchanged.", control.label if control else None, plan.windows.negative_control_seconds),
    ]
    selected_verifiers = tuple(
        instrument for instrument in (verifier_runners or {})
        if instrument in plan.instruments
    )
    total = len(capture_plan) + max(0, plan.repeat_count - 1) + len(selected_verifiers) + 3
    completed = 0
    emit(LabProgressEvent(LabProgressStage.PLAN, f"Selected {action.label}", 0, total))
    for current, (interval, repeat, stage, title, instruction, label, seconds) in enumerate(capture_plan, 1):
        emit(LabProgressEvent(LabProgressStage.USER_PROMPT, instruction, completed, total))
        if not prompt(LabStep(current, len(capture_plan), title, instruction)):
            raise DiscoveryLabCancelled(LabStopReason.USER_CANCELLED.value)
        sample = session.observe_action(seconds=seconds)
        samples.append((interval, repeat, sample, label))
        completed += 1
        emit(LabProgressEvent(stage, f"Captured {title.lower()}", completed, total))
        if interval is LabInterval.ACTION and repeat < plan.repeat_count:
            completed += 1
            emit(LabProgressEvent(
                LabProgressStage.REPEAT,
                f"Action repeat {repeat}/{plan.repeat_count} complete",
                completed,
                total,
            ))

    observations = tuple(
        observation for interval, repeat, sample, _label in samples
        for observation in _sample_observations(sample, interval, repeat, connection_generation)
    )
    transitions = tuple(
        transition for interval, repeat, sample, _label in samples
        for transition in _sample_transitions(sample, interval, repeat)
    )
    intervals = tuple(
        _interval_record(sample, interval, repeat, label)
        for interval, repeat, sample, label in samples
    )
    context = {
        "bus": physical.bus,
        "vendor_id": physical.vendor_id,
        "product_id": physical.product_id,
        "model_fingerprint": physical.model_fingerprint,
        "instance_fingerprint": physical.instance_fingerprint,
    }
    identity = repr((sorted(context.items()), connection_generation, plan.plan_id, intervals[0].started_ns)).encode()
    cpi: list[PhysicalEvidence] = []
    polling: list[PhysicalEvidence] = []
    for instrument, runner in (verifier_runners or {}).items():
        if instrument not in plan.instruments:
            continue
        evidence = tuple(runner(plan))
        if instrument is LabInstrument.CPI_VERIFIER:
            cpi.extend(evidence)
        elif instrument is LabInstrument.POLLING_VERIFIER:
            polling.extend(evidence)
        completed += 1
        emit(LabProgressEvent(
            LabProgressStage.PHYSICAL_VERIFICATION,
            f"Completed {instrument.value.replace('_', ' ')}",
            completed,
            total,
        ))
    experiment = LabExperiment(
        experiment_id="lab-" + sha256(identity).hexdigest()[:20],
        physical_device_context=context,
        connection_generation=connection_generation,
        purpose=plan.purpose,
        human_action=action.action_type.value,
        intervals=intervals,
        observations=observations,
        feature_transitions=transitions,
        physical_cpi_evidence=tuple(cpi),
        physical_polling_evidence=tuple(polling),
        provenance=tuple(f"{item.source_id}:{item.sequence}" for item in observations),
        plan=plan,
    )
    completed += 1
    emit(LabProgressEvent(LabProgressStage.ANALYSIS, "Running automatic differential analysis", completed, total))
    analyzed = analyze_differential_experiment(experiment)
    if effect_verifier is not None:
        analyzed = effect_verifier(analyzed)
        if analyzed.write_authorized:
            raise PermissionError("effect verification cannot grant Lab write authority")
    if route_mapper is not None:
        analyzed = route_mapper(analyzed)
        if analyzed.write_authorized:
            raise PermissionError("routing analysis cannot grant Lab write authority")
    if power_investigator is not None:
        analyzed = power_investigator(analyzed)
        if analyzed.write_authorized:
            raise PermissionError("power-state analysis cannot grant Lab write authority")
    elif _suggests_power_investigation(analyzed):
        from .power_investigator import analyze_power_state

        analyzed = analyze_power_state(analyzed)
        if analyzed.write_authorized:
            raise PermissionError("power-state analysis cannot grant Lab write authority")
    updates = update_hypotheses(plan.target_hypotheses, analyzed)
    completed += 1
    emit(LabProgressEvent(LabProgressStage.HYPOTHESIS_UPDATE, "Updating retained hypotheses", completed, total))
    specialized_stop = analyzed.stop_reason
    specialized_next_plan = analyzed.next_plan
    stop = specialized_stop or _stop_reason(updates)
    next_plan = specialized_next_plan
    if stop is None and next_plan is None:
        dispositions = {item.hypothesis_id: item for item in updates}
        revised = tuple(
            replace(
                hypothesis,
                disposition=dispositions[hypothesis.hypothesis_id].after,
                evidence=(*hypothesis.evidence, *dispositions[hypothesis.hypothesis_id].evidence),
                negative_evidence=(
                    *hypothesis.negative_evidence,
                    *dispositions[hypothesis.hypothesis_id].negative_evidence,
                ),
            )
            for hypothesis in plan.target_hypotheses
        )
        next_plan = plan_next_experiment(
            revised,
            available_actions=(
                item for item in plan.candidate_actions
                if item.action_id != action.action_id
            ),
            timing_profile=analyzed.timing_profile,
        )
        if next_plan.selected_action is None:
            stop = LabStopReason.INSUFFICIENT_SAFE_ACTIONS
    result = replace(
        analyzed, hypothesis_updates=updates, stop_reason=stop, next_plan=next_plan,
    )
    completed += 1
    emit(LabProgressEvent(LabProgressStage.INFORMATION_GAIN_RECALCULATION, "Recalculating remaining information gain", completed, total))
    return result
