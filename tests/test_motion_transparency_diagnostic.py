from pathlib import Path
from unittest.mock import patch

from evdev import ecodes

from mouse_control import cli
from mouse_control.motion_transparency import (
    MotionFrame,
    MotionTransparencyDiagnostic,
    analyze_motion_transparency,
)


def frame(events, timestamp, arrival=None):
    return MotionFrame(tuple(events), timestamp, timestamp if arrival is None else arrival)


def test_exact_frames_report_all_required_zero_loss_metrics() -> None:
    physical = (
        frame(((ecodes.REL_X, 7), (ecodes.REL_Y, -3)), 1_000_000, 10_000_000),
        frame(((ecodes.REL_X, 2),), 2_000_000, 20_000_000),
    )
    virtual = (
        frame(((ecodes.REL_X, 7), (ecodes.REL_Y, -3)), 11_000_000),
        frame(((ecodes.REL_X, 2),), 21_000_000),
    )

    result = analyze_motion_transparency(physical, virtual)

    assert result["pass"] is True
    assert result["physical_motion_frames"] == 2
    assert result["virtual_motion_frames"] == 2
    assert result["matched_frames"] == 2
    assert result["dropped_frames"] == 0
    assert result["duplicated_frames"] == 0
    assert result["modified_rel_events"] == 0
    assert result["dropped_motion_events"] == 0
    assert result["duplicated_motion_events"] == 0
    assert result["ordering_violations"] == 0
    assert result["framing_violations"] == 0
    assert result["forwarding_latency_ms"] == {
        "minimum": 1.0, "median": 1.0, "p95": 1.0, "p99": 1.0, "maximum": 1.0,
    }


def test_identical_motion_with_changed_boundaries_fails_framing_and_coalescing() -> None:
    physical = (
        frame(((ecodes.REL_X, 7),), 1),
        frame(((ecodes.REL_Y, -3),), 2),
    )
    virtual = (frame(((ecodes.REL_X, 7), (ecodes.REL_Y, -3)), 3),)

    result = analyze_motion_transparency(physical, virtual)

    assert result["pass"] is False
    assert result["dropped_motion_events"] == 0
    assert result["duplicated_motion_events"] == 0
    assert result["unexpected_coalescing"] == 1
    assert result["framing_violations"] == 1


def test_modified_reordered_dropped_and_duplicated_events_fail() -> None:
    physical = (frame(((ecodes.REL_X, 1), (ecodes.REL_Y, 2),
                       (ecodes.REL_X, 3)), 1),)
    virtual = (frame(((ecodes.REL_Y, 2), (ecodes.REL_X, 4),
                      (ecodes.REL_Y, 9)), 2),)

    result = analyze_motion_transparency(physical, virtual, syn_dropped=1)

    assert result["pass"] is False
    assert result["syn_dropped"] == 1
    assert any(result[name] for name in (
        "modified_rel_events", "dropped_motion_events",
        "duplicated_motion_events", "ordering_violations",
    ))


def test_reordered_events_are_reported_as_ordering_not_loss() -> None:
    physical = (
        frame(((ecodes.REL_X, 1), (ecodes.REL_Y, 2)), 1),
        frame(((ecodes.REL_X, 3),), 2),
    )
    virtual = (
        frame(((ecodes.REL_Y, 2), (ecodes.REL_X, 1)), 3),
        frame(((ecodes.REL_X, 3),), 4),
    )

    result = analyze_motion_transparency(physical, virtual)

    assert result["ordering_violations"] == 1
    assert result["dropped_motion_events"] == 0
    assert result["duplicated_motion_events"] == 0


def test_collector_writes_json_report_with_workload_label(tmp_path: Path) -> None:
    output = tmp_path / "motion.json"
    diagnostic = MotionTransparencyDiagnostic(output, "C")
    events = [(ecodes.EV_REL, ecodes.REL_X, 5),
              (ecodes.EV_REL, ecodes.REL_Y, -2)]
    diagnostic.physical_frame(events, 1_000_000, 2_000_000)
    for event in events:
        diagnostic.virtual_event(*event)
    diagnostic.virtual_frame(3_000_000)
    diagnostic.physical_frame(events, 4_000_000, 5_000_000)
    for event in events:
        diagnostic.virtual_event(*event)
    diagnostic.virtual_frame(6_000_000)

    summary = diagnostic.write_report()

    content = output.read_text()
    assert summary["pass"] is True
    assert '"workload": "C"' in content
    assert '"measurement_boundary"' in content


def test_run_motion_diagnostic_dispatches_production_remapper_path(tmp_path: Path) -> None:
    output = tmp_path / "motion.json"
    with patch.object(cli, "run_from_config", return_value=0) as run:
        assert cli.main([
            "run", "--motion-diagnostic", str(output), "--motion-workload", "B"
        ]) == 0

    diagnostic = run.call_args.kwargs["motion_diagnostic"]
    assert diagnostic.output == output
    assert diagnostic.workload == "B"
