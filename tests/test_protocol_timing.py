from dataclasses import replace

from mouse_control.discovery_lab import (
    LabExperiment,
    LabInterval,
    LabIntervalRecord,
    LabLifecycleEvent,
    LifecycleEventKind,
    TimingClassification,
    TimingRelationship,
    analyze_differential_experiment,
)
from mouse_control.protocol_timing import profile_experiment_timing
from mouse_control.temporal_dialogue import (
    BurstDialogueSpec,
    DialogueAssembler,
    DialogueKind,
    DialogueObservation,
    DialogueRecord,
    Direction,
    PushedStateAssociation,
    PushedStateRecord,
    StateEvidence,
    StateFreshness,
)


def _obs(sequence, timestamp_ms, direction, payload=b"x", *, generation=1, status=None, grammar="rpc"):
    return DialogueObservation(
        source_id="selected-device", physical_id="physical", channel_id="feature",
        transport="hid", direction=direction, report_namespace="feature",
        report_id=7, generation=generation, timestamp_ns=timestamp_ms * 1_000_000,
        sequence=sequence, payload=payload, transaction_tag=sequence // 10,
        grammar=grammar, status=status,
    )


def _intervals():
    return (
        LabIntervalRecord(LabInterval.BASELINE, 0, 0, 999_000_000, 0),
        LabIntervalRecord(LabInterval.ACTION, 1, 1_000_000_000, 1_999_000_000, 0),
        LabIntervalRecord(LabInterval.POST_ACTION, 0, 2_000_000_000, 2_999_000_000, 0),
        LabIntervalRecord(LabInterval.NEGATIVE_CONTROL, 0, 3_000_000_000, 3_999_000_000, 0),
    )


def _experiment(**kwargs):
    return LabExperiment(
        experiment_id="timing-fixture",
        physical_device_context={"model_fingerprint": "model", "vendor_id": 1, "product_id": 2},
        connection_generation=1,
        purpose="timing fixture",
        human_action="press control",
        intervals=_intervals(),
        observations=(),
        **kwargs,
    )


def _reply(sequence, request_ms, duration_ms, *, kind=DialogueKind.RESPONSE, grammar="rpc"):
    request = _obs(sequence * 10, request_ms, Direction.OUT, grammar=grammar)
    response = _obs(sequence * 10 + 1, request_ms + duration_ms, Direction.IN, grammar=grammar)
    return DialogueRecord(kind, response, request=request, confidence="identifier")


def test_single_request_response_latency_is_retained_but_classification_is_unknown():
    profiled = profile_experiment_timing(_experiment(dialogues=(_reply(1, 100, 3),)))
    timing = profiled.timing_profile
    assert timing is not None
    observation = timing.observations[0]
    assert observation.relationship is TimingRelationship.REQUEST_RESPONSE_LATENCY
    assert observation.duration_ns == 3_000_000
    assert observation.experiment_id == profiled.experiment_id
    assert observation.connection_generation == 1
    summary = timing.summaries[0]
    assert summary.sample_count == 1
    assert summary.classification is TimingClassification.UNKNOWN
    assert summary.confidence == "insufficient-samples"


def test_repeated_summary_rejects_outlier_and_ranks_action_timing_delta():
    dialogues = tuple(
        _reply(index, request, duration)
        for index, (request, duration) in enumerate(
            ((100, 2), (200, 2), (300, 2), (400, 50),
             (1100, 18), (1200, 19), (1300, 17)),
            1,
        )
    )
    analyzed = analyze_differential_experiment(_experiment(dialogues=dialogues))
    profile = analyzed.timing_profile
    assert profile is not None
    baseline = next(
        item for item in profile.summaries
        if item.interval is LabInterval.BASELINE
    )
    assert baseline.sample_count == 4
    assert baseline.accepted_count == 3
    assert baseline.median_ns == 2_000_000
    assert baseline.rejected_durations_ns == (50_000_000,)
    delta = profile.differentials[0]
    assert delta.baseline_median_ns == 2_000_000
    assert delta.action_median_ns == 18_000_000
    assert delta.ratio == 9.0
    assert {
        item.classification for item in profile.observations
        if item.interval is LabInterval.BASELINE
    } == {TimingClassification.IMMEDIATE}
    assert {
        item.classification for item in profile.observations
        if item.interval is LabInterval.ACTION
    } == {TimingClassification.SETTLING_DELAY}
    assert analyzed.analysis is not None
    assert analyzed.analysis.timing_deltas == profile.differentials


def test_burst_timing_uses_existing_burst_result_and_quiet_completion():
    assembler = DialogueAssembler()
    request = DialogueObservation(
        "selected-device", "physical", "burst", "hid", Direction.OUT,
        "request", 0x20, 1, 0, 1, b"query", transaction_tag=9,
        grammar="burst",
    )
    spec = BurstDialogueSpec(
        "request", "response", quiet_interval_ms=10,
        absolute_deadline_ms=50, max_responses=8,
        request_report_id=0x20, response_report_id=0x21,
        response_channel_id="burst", response_grammar="burst",
    )
    assembler.begin_burst(request, spec)
    for sequence, timestamp_ms in ((2, 5), (3, 8), (4, 12)):
        assembler.observe_burst(DialogueObservation(
            "selected-device", "physical", "burst", "hid", Direction.IN,
            "response", 0x21, 1, timestamp_ms * 1_000_000, sequence, b"record",
            transaction_tag=9, grammar="burst",
        ))
    burst = assembler.advance_time(22_000_000)[0]
    assert burst.completion_timestamp_ns == 22_000_000
    assert burst.quiet_interval_ns == 10_000_000

    profile = profile_experiment_timing(_experiment(bursts=(burst,))).timing_profile
    assert profile is not None
    by_kind = {}
    for item in profile.observations:
        by_kind.setdefault(item.relationship, []).append(item.duration_ns)
    assert by_kind[TimingRelationship.BURST_TRIGGER_TO_FIRST_RESPONSE] == [5_000_000]
    assert by_kind[TimingRelationship.BURST_INTER_RESPONSE_GAP] == [3_000_000, 4_000_000]
    assert by_kind[TimingRelationship.BURST_QUIET_INTERVAL] == [10_000_000]
    assert by_kind[TimingRelationship.BURST_DURATION] == [22_000_000]
    retained = profile.burst_timings[0]
    assert retained.response_count == 3
    assert retained.completion_reason == "quiet_interval"
    assert retained.inter_response_gaps_ns == (3_000_000, 4_000_000)


def test_nudge_action_and_periodic_pushed_state_timing_are_extracted():
    nudge = _obs(1, 10, Direction.OUT, grammar="nudge")
    action = _obs(2, 20, Direction.IN, grammar="physical_action")
    first_observation = _obs(3, 50, Direction.IN, grammar="state")
    second_observation = _obs(4, 90, Direction.IN, grammar="state")
    first = PushedStateRecord(
        first_observation, "dpi", 1, StateFreshness.FRESH,
        ("nudge-precedes-asynchronous-push",),
        association=PushedStateAssociation.NUDGED, nudge=nudge,
        periodic_index=1, controlled_action=action,
    )
    second = PushedStateRecord(
        second_observation, "dpi", 2, StateFreshness.FRESH,
        ("known-periodic-push-cadence",), periodic_index=2,
    )
    profile = profile_experiment_timing(
        _experiment(pushed_states=(first, second))
    ).timing_profile
    assert profile is not None
    durations = {item.relationship: item.duration_ns for item in profile.observations}
    assert durations[TimingRelationship.NUDGE_TO_PUSH_LATENCY] == 40_000_000
    assert durations[TimingRelationship.ACTION_TO_STATE_CHANGE_LATENCY] == 30_000_000
    assert durations[TimingRelationship.PERIODIC_PUSH_CADENCE] == 40_000_000
    assert profile.next_recommended_experiment is not None
    assert profile.next_recommended_experiment.experiment == "repeat-without-nudge"
    assert profile.next_recommended_experiment.requires_hardware_write is False


def test_later_fresh_push_defines_stale_read_settling_window():
    read_observation = _obs(1, 0, Direction.IN, grammar="read")
    push_observation = _obs(2, 45, Direction.IN, grammar="state")
    read = StateEvidence(
        read_observation, "dpi", 1, StateFreshness.UNKNOWN,
        ("successful-read-does-not-prove-freshness",),
    )
    pushed = PushedStateRecord(
        push_observation, "dpi", 2, StateFreshness.FRESH,
        ("newer-pushed-state-disagrees-with-immediate-read",),
    )
    profile = profile_experiment_timing(
        _experiment(state_reads=(read,), pushed_states=(pushed,))
    ).timing_profile
    assert profile is not None
    evidence = next(
        item for item in profile.observations
        if item.relationship is TimingRelationship.READ_TO_FRESH_STATE_LATENCY
    )
    assert evidence.duration_ns == 45_000_000
    assert evidence.freshness is StateFreshness.STALE
    assert evidence.classification is TimingClassification.SETTLING_DELAY
    assert profile.next_recommended_experiment.experiment == "repeat-request-push-timing"


def test_busy_poll_ready_preserves_poll_count_cadence_and_time_to_ready():
    request = _obs(10, 0, Direction.OUT, grammar="rpc")
    records = (
        DialogueRecord(DialogueKind.BUSY_PENDING, _obs(11, 10, Direction.IN, status="busy"), request),
        DialogueRecord(DialogueKind.RESPONSE_POLL, _obs(12, 20, Direction.OUT, grammar="poll"), request),
        DialogueRecord(DialogueKind.BUSY_PENDING, _obs(13, 30, Direction.IN, status="busy"), request),
        DialogueRecord(DialogueKind.RESPONSE_POLL, _obs(14, 40, Direction.OUT, grammar="poll"), request),
        DialogueRecord(DialogueKind.RESPONSE, _obs(15, 60, Direction.IN, status="ok"), request),
    )
    profile = profile_experiment_timing(_experiment(dialogues=records)).timing_profile
    assert profile is not None
    cycle = profile.busy_poll_cycles[0]
    assert cycle.poll_count == 2
    assert cycle.poll_intervals_ns == (20_000_000,)
    assert cycle.busy_duration_ns == 50_000_000
    assert cycle.time_to_ready_ns == 60_000_000
    assert any(
        item.relationship is TimingRelationship.BUSY_TO_READY_LATENCY
        and item.classification is TimingClassification.BUSY_POLL
        for item in profile.observations
    )
    assert profile.next_recommended_experiment.experiment == "extend-busy-observation-window"


def test_generation_lifecycle_timing_never_forms_cross_generation_transaction():
    events = (
        LabLifecycleEvent(LifecycleEventKind.LAST_VALID_STATE, 100, 1, "old:last"),
        LabLifecycleEvent(LifecycleEventKind.DISCONNECT, 120, 1, "old:disconnect"),
        LabLifecycleEvent(LifecycleEventKind.ATTACH, 300, 2, "new:attach"),
        LabLifecycleEvent(LifecycleEventKind.FIRST_VALID_STATE, 450, 2, "new:first"),
    )
    commit = DialogueRecord(
        DialogueKind.COMMIT_APPLY,
        _obs(9, 0, Direction.OUT, grammar="commit"),
    )
    # Move the commit to 90 ns so this lifecycle fixture can use exact small values.
    commit = replace(commit, observation=replace(commit.observation, timestamp_ns=90))
    profile = profile_experiment_timing(
        _experiment(lifecycle_events=events, dialogues=(commit,))
    ).timing_profile
    assert profile is not None
    disconnects = [
        item for item in profile.observations
        if item.relationship is TimingRelationship.DISCONNECT_LATENCY
    ]
    assert {item.duration_ns for item in disconnects} == {20, 30}
    assert any(item.context == "commit-to-disconnect" for item in disconnects)
    values = {item.relationship: item for item in profile.observations if item not in disconnects}
    assert values[TimingRelationship.RECONNECT_DURATION].duration_ns == 180
    assert values[TimingRelationship.RECONNECT_DURATION].connection_generation == 2
    assert values[TimingRelationship.RECONNECT_TO_FIRST_VALID_STATE].duration_ns == 150
    assert all(
        item.classification is TimingClassification.RECONNECT_BOUND
        for item in profile.observations
    )


def test_timing_replay_is_deterministic_redacted_and_never_authorizes_writes():
    request = replace(_obs(10, 100, Direction.OUT), source_id="/dev/hidraw7")
    response = replace(_obs(11, 103, Direction.IN), source_id="/dev/hidraw7")
    experiment = _experiment(dialogues=(
        DialogueRecord(DialogueKind.RESPONSE, response, request),
    ))
    profiled = profile_experiment_timing(experiment)
    first = profiled.replay_fixture()
    second = profiled.replay_fixture()
    assert first == second
    assert "/dev/hidraw7" not in repr(first)
    assert "keyboard" not in repr(first).lower()
    assert profiled.write_authorized is False
