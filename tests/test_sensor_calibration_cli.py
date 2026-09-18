from dataclasses import replace

from mouse_control.sensor_calibration import (
    CalibrationEvent,
    EV_REL,
    EV_SYN,
    REL_X,
    SYN_REPORT,
    measure_sensor_state_auto,
    summarize_calibrations,
)
from mouse_control.sensor_calibration_cli import (
    _parser,
    _cpi_consistency,
    _polling_consensus,
    _robust_cpi_subset,
    _weaker_confidence,
)


def test_cpi_parser_supports_namespaced_public_program_name():
    parser = _parser(prog="mouse-control cpi")
    assert parser.prog == "mouse-control cpi"
    args = parser.parse_args(["--distance-mm", "254", "--passes", "4"])
    assert args.distance_mm == 254
    assert args.passes == 4


def _sample(*, rate: int | None):
    events = []
    timestamp = 1_000_000_000
    for _ in range(100):
        events.append(CalibrationEvent(timestamp, EV_REL, REL_X, 16))
        events.append(CalibrationEvent(timestamp, EV_SYN, SYN_REPORT, 0))
        timestamp += 1_000_000
    measured = measure_sensor_state_auto(events, distance_mm=50.8)
    return replace(measured, standard_polling_hz=rate)


def test_polling_consensus_is_high_only_when_all_three_passes_agree():
    rate, matches, confidence = _polling_consensus(
        (_sample(rate=1000), _sample(rate=1000), _sample(rate=1000))
    )

    assert rate == 1000
    assert matches == 3
    assert confidence == "high"


def test_polling_consensus_downgrades_mixed_three_pass_result():
    rate, matches, confidence = _polling_consensus(
        (_sample(rate=1000), _sample(rate=1000), _sample(rate=500))
    )

    assert rate == 1000
    assert matches == 2
    assert confidence == "medium"


def test_polling_consensus_is_low_without_standard_rate_evidence():
    rate, matches, confidence = _polling_consensus(
        (_sample(rate=None), _sample(rate=None), _sample(rate=None))
    )

    assert rate is None
    assert matches == 0
    assert confidence == "low"


def test_cpi_consistency_is_high_when_all_passes_cluster_tightly():
    base = _sample(rate=1000)
    results = (
        replace(base, estimated_dpi=1490.0),
        replace(base, estimated_dpi=1500.0),
        replace(base, estimated_dpi=1510.0),
    )
    summary = summarize_calibrations(results)

    worst, spread, confidence = _cpi_consistency(results, summary)

    assert worst < 0.01
    assert spread < 0.02
    assert confidence == "high"


def test_cpi_consistency_downgrades_one_outlier_hidden_by_small_mad():
    base = _sample(rate=1000)
    results = (
        replace(base, estimated_dpi=1412.0),
        replace(base, estimated_dpi=1528.6),
        replace(base, estimated_dpi=1562.0),
    )
    summary = summarize_calibrations(results)

    worst, spread, confidence = _cpi_consistency(results, summary)

    assert summary.confidence == "high"
    assert worst > 0.05
    assert spread > 0.08
    assert confidence == "medium"


def test_cpi_consistency_is_low_for_large_disagreement():
    base = _sample(rate=1000)
    results = (
        replace(base, estimated_dpi=800.0),
        replace(base, estimated_dpi=1000.0),
        replace(base, estimated_dpi=1300.0),
    )
    summary = summarize_calibrations(results)

    _, _, confidence = _cpi_consistency(results, summary)

    assert confidence == "low"


def test_three_passes_never_discard_a_possible_outlier():
    base = _sample(rate=1000)
    results = (
        replace(base, estimated_dpi=1628.0),
        replace(base, estimated_dpi=2035.0),
        replace(base, estimated_dpi=2042.0),
    )

    used, rejected = _robust_cpi_subset(results)

    assert used == results
    assert rejected == ()


def test_fourth_consistent_pass_can_confirm_and_reject_one_clear_outlier():
    base = _sample(rate=1000)
    results = (
        replace(base, estimated_dpi=1628.0),
        replace(base, estimated_dpi=2035.0),
        replace(base, estimated_dpi=2042.0),
        replace(base, estimated_dpi=2040.0),
    )

    used, rejected = _robust_cpi_subset(results)

    assert [round(sample.estimated_dpi) for sample in used] == [2035, 2042, 2040]
    assert [round(sample.estimated_dpi) for sample in rejected] == [1628]
    summary = summarize_calibrations(used)
    _, _, confidence = _cpi_consistency(used, summary)
    assert confidence == "high"


def test_robust_subset_does_not_hide_genuine_split_behavior():
    base = _sample(rate=1000)
    results = (
        replace(base, estimated_dpi=1600.0),
        replace(base, estimated_dpi=1650.0),
        replace(base, estimated_dpi=2000.0),
        replace(base, estimated_dpi=2050.0),
    )

    used, rejected = _robust_cpi_subset(results)

    assert used == results
    assert rejected == ()


def test_overall_confidence_uses_the_weaker_dimension():
    assert _weaker_confidence("high", "medium") == "medium"
    assert _weaker_confidence("low", "high") == "low"
    assert _weaker_confidence("high", "high") == "high"
