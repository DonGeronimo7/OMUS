"""Robust, protocol-neutral polling-rate analysis from evdev motion timestamps.

This module intentionally does not replace sensor_calibration.estimate_peak_polling_hz().
DPI calibration asks for the highest sustained event frequency; polling-rate
verification instead needs to identify the fundamental report period and reject
harmonics caused by missed/coalesced motion frames.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor
from statistics import median
from typing import Iterable, Literal

STANDARD_POLLING_RATES_HZ = (125, 250, 500, 1000, 2000, 4000, 8000)
MIN_INTERVAL_NS = 50_000
MAX_INFORMATIVE_GAP_NS = 100_000_000
MAX_PERIOD_MULTIPLE = 16
MATCH_TOLERANCE_PERIODS = 0.22


@dataclass(frozen=True)
class PollingCandidate:
    rate_hz: int
    period_ns: float
    matched_intervals: int
    direct_intervals: int
    coverage: float
    direct_ratio: float
    direct_period_ns: float | None
    direct_jitter_fraction: float | None
    direct_error_fraction: float | None
    score: float


@dataclass(frozen=True)
class PollingMeasurement:
    frame_count: int
    interval_count: int
    median_interval_ns: float | None
    mode_interval_ns: float | None
    p10_interval_ns: float | None
    p25_interval_ns: float | None
    p50_interval_ns: float | None
    inferred_hz: float | None
    standard_hz: int | None
    error_fraction: float | None
    jitter_fraction: float | None
    matched_fraction: float
    direct_fraction: float
    confidence: Literal["high", "medium", "low", "rejected"]
    rejection_reason: str | None
    candidates: tuple[PollingCandidate, ...]


def _percentile(values: tuple[int, ...], fraction: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lo = floor(position)
    hi = ceil(position)
    if lo == hi:
        return float(ordered[lo])
    weight = position - lo
    return float(ordered[lo] * (1.0 - weight) + ordered[hi] * weight)


def _mad_fraction(values: tuple[float, ...], center: float) -> float | None:
    if not values or center <= 0:
        return None
    mad = float(median(abs(value - center) for value in values))
    return mad / center


def _histogram_mode(values: tuple[int, ...]) -> float | None:
    if not values:
        return None
    center = float(median(values))
    # Keep enough resolution for high-rate mice while avoiding 1 us-scale
    # timestamp noise from fragmenting the common 1/2/4/8 ms clusters.
    bin_width = int(max(25_000, min(250_000, center * 0.08)))
    buckets: dict[int, list[int]] = {}
    for value in values:
        key = int(round(value / bin_width))
        buckets.setdefault(key, []).append(value)
    # Prefer the lower-time bucket on exact count ties; it is less likely to be
    # a missed-frame multiple of the fundamental period.
    best_key, best_values = max(
        buckets.items(), key=lambda item: (len(item[1]), -item[0])
    )
    del best_key
    return float(median(best_values))


def _candidate(intervals: tuple[int, ...], rate_hz: int) -> PollingCandidate:
    period = 1_000_000_000.0 / rate_hz
    matched: list[tuple[int, int]] = []
    direct: list[float] = []
    for interval in intervals:
        ratio = interval / period
        multiple = max(1, int(round(ratio)))
        if multiple > MAX_PERIOD_MULTIPLE:
            continue
        residual = abs(interval - multiple * period) / period
        if residual <= MATCH_TOLERANCE_PERIODS:
            matched.append((interval, multiple))
            if multiple == 1:
                direct.append(float(interval))

    total = len(intervals)
    coverage = len(matched) / total if total else 0.0
    direct_ratio = len(direct) / total if total else 0.0
    direct_period = float(median(direct)) if direct else None
    jitter = _mad_fraction(tuple(direct), direct_period) if direct_period else None
    error = (
        abs((1_000_000_000.0 / direct_period) - rate_hz) / rate_hz
        if direct_period and direct_period > 0
        else None
    )

    # Coverage acknowledges dropped/coalesced frames. Direct support is weighted
    # more heavily so a slow rate is not mistaken for a faster harmonic whose
    # period merely divides the observed deltas.
    stability = 0.0 if jitter is None else max(0.0, 1.0 - min(jitter, 1.0))
    score = coverage * 0.35 + direct_ratio * 0.55 + stability * 0.10
    return PollingCandidate(
        rate_hz=rate_hz,
        period_ns=period,
        matched_intervals=len(matched),
        direct_intervals=len(direct),
        coverage=coverage,
        direct_ratio=direct_ratio,
        direct_period_ns=direct_period,
        direct_jitter_fraction=jitter,
        direct_error_fraction=error,
        score=score,
    )


def analyze_polling_timestamps(
    frame_timestamps_ns: Iterable[int],
    *,
    standards: Iterable[int] = STANDARD_POLLING_RATES_HZ,
) -> PollingMeasurement:
    """Identify a fixed polling fundamental from motion-frame timestamps.

    Long idle gaps are excluded from rate inference. Short integer multiples of
    a candidate period remain useful evidence because evdev sees only frames
    containing motion; a report with no REL_X/REL_Y does not appear in this
    motion-only stream.
    """
    timestamps = tuple(int(value) for value in frame_timestamps_ns)
    intervals = tuple(
        delta
        for before, after in zip(timestamps, timestamps[1:])
        if MIN_INTERVAL_NS <= (delta := after - before) <= MAX_INFORMATIVE_GAP_NS
    )

    p10 = _percentile(intervals, 0.10)
    p25 = _percentile(intervals, 0.25)
    p50 = _percentile(intervals, 0.50)
    mode = _histogram_mode(intervals)

    standard_rates = tuple(sorted({int(rate) for rate in standards if int(rate) > 0}))
    candidates = tuple(
        sorted((_candidate(intervals, rate) for rate in standard_rates),
               key=lambda item: (-item.score, -item.direct_ratio, item.rate_hz))
    )

    if len(intervals) < 8:
        return PollingMeasurement(
            frame_count=len(timestamps), interval_count=len(intervals),
            median_interval_ns=p50, mode_interval_ns=mode,
            p10_interval_ns=p10, p25_interval_ns=p25, p50_interval_ns=p50,
            inferred_hz=None, standard_hz=None, error_fraction=None,
            jitter_fraction=None, matched_fraction=0.0, direct_fraction=0.0,
            confidence="rejected",
            rejection_reason="insufficient motion intervals; need at least 8",
            candidates=candidates,
        )

    best = candidates[0] if candidates else None
    if best is None or best.direct_period_ns is None:
        return PollingMeasurement(
            frame_count=len(timestamps), interval_count=len(intervals),
            median_interval_ns=p50, mode_interval_ns=mode,
            p10_interval_ns=p10, p25_interval_ns=p25, p50_interval_ns=p50,
            inferred_hz=None, standard_hz=None, error_fraction=None,
            jitter_fraction=None,
            matched_fraction=best.coverage if best else 0.0,
            direct_fraction=best.direct_ratio if best else 0.0,
            confidence="rejected",
            rejection_reason="no standard rate has direct fundamental support",
            candidates=candidates,
        )

    inferred = 1_000_000_000.0 / best.direct_period_ns
    error = abs(inferred - best.rate_hz) / best.rate_hz
    jitter = best.direct_jitter_fraction or 0.0

    minimum_direct = max(6, ceil(len(intervals) * 0.12))
    if best.direct_intervals < minimum_direct:
        confidence: Literal["high", "medium", "low", "rejected"] = "rejected"
        reason = (
            f"only {best.direct_intervals}/{len(intervals)} intervals support the "
            f"{best.rate_hz} Hz fundamental directly"
        )
        standard = None
    elif best.coverage >= 0.80 and best.direct_ratio >= 0.45 and error <= 0.08 and jitter <= 0.12:
        confidence = "high"
        reason = None
        standard = best.rate_hz
    elif best.coverage >= 0.60 and best.direct_ratio >= 0.20 and error <= 0.15 and jitter <= 0.25:
        confidence = "medium"
        reason = None
        standard = best.rate_hz
    elif best.coverage >= 0.45 and error <= 0.20:
        confidence = "low"
        reason = "timing cluster is plausible but too sparse or jittery for write promotion"
        standard = best.rate_hz
    else:
        confidence = "rejected"
        reason = "no stable standard-rate fundamental dominates the interval distribution"
        standard = None

    return PollingMeasurement(
        frame_count=len(timestamps), interval_count=len(intervals),
        median_interval_ns=p50, mode_interval_ns=mode,
        p10_interval_ns=p10, p25_interval_ns=p25, p50_interval_ns=p50,
        inferred_hz=inferred, standard_hz=standard, error_fraction=error,
        jitter_fraction=jitter, matched_fraction=best.coverage,
        direct_fraction=best.direct_ratio, confidence=confidence,
        rejection_reason=reason, candidates=candidates,
    )


@dataclass(frozen=True)
class PollingVerificationSummary:
    target_hz: int
    passes: tuple[PollingMeasurement, ...]
    accepted_passes: int
    consensus_hz: int | None
    median_inferred_hz: float | None
    median_error_fraction: float | None
    confidence: Literal["high", "medium", "low", "rejected"]
    rejection_reason: str | None


def summarize_polling_measurements(
    target_hz: int,
    measurements: Iterable[PollingMeasurement],
) -> PollingVerificationSummary:
    """Aggregate repeated physical passes for one configured polling target."""
    samples = tuple(measurements)
    if target_hz <= 0:
        raise ValueError("target_hz must be positive")
    if not samples:
        raise ValueError("at least one polling measurement is required")

    accepted = tuple(
        sample for sample in samples
        if sample.standard_hz == target_hz and sample.confidence in {"high", "medium"}
    )
    inferred = tuple(
        sample.inferred_hz for sample in accepted if sample.inferred_hz is not None
    )
    median_hz = float(median(inferred)) if inferred else None
    median_error = (
        abs(median_hz - target_hz) / target_hz if median_hz is not None else None
    )
    ratio = len(accepted) / len(samples)

    if len(samples) >= 3 and len(accepted) >= 3 and ratio >= 0.75 and median_error is not None and median_error <= 0.08:
        confidence: Literal["high", "medium", "low", "rejected"] = "high"
        reason = None
        consensus = target_hz
    elif len(accepted) >= 2 and ratio >= 0.60 and median_error is not None and median_error <= 0.15:
        confidence = "medium"
        reason = None
        consensus = target_hz
    elif accepted:
        confidence = "low"
        reason = "some passes matched, but repeatability is insufficient for write promotion"
        consensus = target_hz
    else:
        confidence = "rejected"
        reason = "no repeated pass established the configured polling fundamental"
        consensus = None

    return PollingVerificationSummary(
        target_hz=target_hz,
        passes=samples,
        accepted_passes=len(accepted),
        consensus_hz=consensus,
        median_inferred_hz=median_hz,
        median_error_fraction=median_error,
        confidence=confidence,
        rejection_reason=reason,
    )
