# SPDX-License-Identifier: AGPL-3.0-or-later
import random
import pytest

from mouse_control.polling_measurement import analyze_polling_timestamps


def timestamps_from_intervals(intervals, start=1_000_000_000):
    result = [start]
    for delta in intervals:
        result.append(result[-1] + delta)
    return result


@pytest.mark.parametrize("rate", [125, 250, 500, 1000, 2000, 4000, 8000])
def test_clean_standard_rates(rate):
    period = round(1_000_000_000 / rate)
    result = analyze_polling_timestamps(timestamps_from_intervals([period] * 100))
    assert result.standard_hz == rate
    assert result.confidence == "high"
    assert result.inferred_hz == pytest.approx(rate, rel=0.01)


def test_250_survives_3_4_5ms_timestamp_distribution_that_fooled_peak_estimator():
    # Fastest-quartile logic sees the 3 ms samples and reports ~333 Hz.
    # The distribution fundamental is nevertheless 4 ms / 250 Hz.
    intervals = [3_000_000] * 20 + [4_000_000] * 60 + [5_000_000] * 20
    result = analyze_polling_timestamps(timestamps_from_intervals(intervals))
    assert result.standard_hz == 250
    assert result.inferred_hz == pytest.approx(250.0, rel=0.01)
    assert result.p50_interval_ns == pytest.approx(4_000_000)
    assert result.mode_interval_ns == pytest.approx(4_000_000)
    assert result.confidence in {"high", "medium"}


def test_missing_motion_frames_are_treated_as_multiples_not_a_faster_harmonic():
    intervals = [4_000_000] * 55 + [8_000_000] * 30 + [12_000_000] * 15
    result = analyze_polling_timestamps(timestamps_from_intervals(intervals))
    assert result.standard_hz == 250
    assert result.direct_fraction > 0.5
    # 500 Hz would fit many intervals as 2x/4x/6x, but must lose for lack of direct support.
    score_by_rate = {candidate.rate_hz: candidate for candidate in result.candidates}
    assert score_by_rate[250].score > score_by_rate[500].score
    assert score_by_rate[250].direct_ratio > score_by_rate[500].direct_ratio


def test_125_not_misclassified_as_250_or_500_harmonic():
    intervals = [8_000_000] * 70 + [16_000_000] * 20 + [24_000_000] * 10
    result = analyze_polling_timestamps(timestamps_from_intervals(intervals))
    assert result.standard_hz == 125
    assert result.inferred_hz == pytest.approx(125.0, rel=0.01)


def test_realistic_jitter_and_dropped_frames():
    rng = random.Random(42)
    intervals = []
    for _ in range(250):
        multiple = 1 if rng.random() < 0.80 else rng.choice([2, 3])
        jitter = rng.randint(-180_000, 180_000)
        intervals.append(4_000_000 * multiple + jitter)
    result = analyze_polling_timestamps(timestamps_from_intervals(intervals))
    assert result.standard_hz == 250
    assert result.confidence in {"high", "medium"}
    assert abs(result.inferred_hz - 250) / 250 < 0.05


def test_insufficient_data_is_rejected():
    result = analyze_polling_timestamps(timestamps_from_intervals([4_000_000] * 5))
    assert result.standard_hz is None
    assert result.confidence == "rejected"
    assert "insufficient" in result.rejection_reason


def test_nonstandard_333hz_is_not_promoted_as_250_or_500():
    result = analyze_polling_timestamps(timestamps_from_intervals([3_000_000] * 100))
    assert result.standard_hz is None
    assert result.confidence == "rejected"


def test_long_idle_gap_does_not_destroy_fundamental():
    intervals = [4_000_000] * 50 + [500_000_000] + [4_000_000] * 50
    result = analyze_polling_timestamps(timestamps_from_intervals(intervals))
    assert result.standard_hz == 250
    assert result.interval_count == 100

from mouse_control.polling_measurement import summarize_polling_measurements


def test_summary_requires_repeated_agreement_for_high_confidence():
    good = analyze_polling_timestamps(timestamps_from_intervals([4_000_000] * 100))
    summary = summarize_polling_measurements(250, [good, good, good, good])
    assert summary.consensus_hz == 250
    assert summary.accepted_passes == 4
    assert summary.confidence == "high"


def test_summary_rejects_wrong_fundamental_even_when_repeatable():
    wrong = analyze_polling_timestamps(timestamps_from_intervals([2_000_000] * 100))
    summary = summarize_polling_measurements(250, [wrong, wrong, wrong])
    assert summary.consensus_hz is None
    assert summary.confidence == "rejected"
