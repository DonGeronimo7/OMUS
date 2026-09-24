# SPDX-License-Identifier: AGPL-3.0-or-later
"""Interactive vendor-neutral DPI/polling calibration for discovery work."""

from __future__ import annotations

import argparse
import os
import sys

from .discovery import get_mouse_devices, select_mouse_device
from .sensor_calibration import (
    CalibrationError,
    capture_evdev_motion,
    measure_sensor_state,
    measure_sensor_state_auto,
    summarize_calibrations,
)


_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
_DEFAULT_MAX_ADAPTIVE_PASSES = 5
_CPI_OUTLIER_THRESHOLD = 0.05


def configure_parser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Add the installed CPI interface to a OMUS argument parser."""

    parser.description = (
        "Measure current mouse CPI/DPI and polling from raw Linux evdev motion without "
        "using a vendor protocol backend."
    )
    parser.add_argument("--device", type=int, metavar="N")
    parser.add_argument(
        "--distance-mm",
        type=float,
        default=50.8,
        metavar="MM",
        help="known physical travel distance (default: 50.8 mm / 2 inches)",
    )
    parser.add_argument(
        "--axis",
        choices=("auto", "x", "y"),
        default="auto",
        help="diagnostic Linux relative-axis override; default auto uses vector motion",
    )
    parser.add_argument(
        "--window",
        type=float,
        default=6.0,
        metavar="SECONDS",
        help="maximum capture window for each pass (default: 6 seconds)",
    )
    parser.add_argument(
        "--passes",
        type=int,
        default=3,
        metavar="N",
        help=(
            "minimum ruler passes before confidence is evaluated (default: 3); "
            "OMUS may request up to two extra passes when needed"
        ),
    )
    parser.add_argument(
        "--known-dpi",
        type=int,
        metavar="DPI",
        help=(
            "optional configured DPI stage label; used only to report physical CPI "
            "deviation and never to calculate the measurement"
        ),
    )
    return parser


def _parser(*, prog: str = "mouse-control-sensor-calibrate") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
    )
    return configure_parser(parser)


def _pick(index: int | None):
    mice = get_mouse_devices()
    if not mice:
        print("No mouse devices found.", file=sys.stderr)
        return None
    if index is None:
        return select_mouse_device(mice)
    if index < 1 or index > len(mice):
        raise ValueError(f"--device must be between 1 and {len(mice)}")
    return mice[index - 1]


def _polling_label(result) -> str:
    if result.standard_polling_hz is not None:
        return f"~{result.standard_polling_hz} Hz"
    if result.peak_polling_hz is not None:
        return f"{result.peak_polling_hz:.1f} Hz"
    return "insufficient data"


def _polling_consensus(results) -> tuple[int | None, int, str]:
    """Return modal standard rate, matching-pass count, and confidence."""

    rates = [result.standard_polling_hz for result in results]
    known = [rate for rate in rates if rate is not None]
    if not known:
        return None, 0, "low"

    rate = max(
        sorted(set(known)),
        key=lambda candidate: (known.count(candidate), -candidate),
    )
    matches = sum(candidate == rate for candidate in rates)
    fraction = matches / len(results)
    if len(results) >= 3 and matches == len(results):
        confidence = "high"
    elif len(results) >= 2 and fraction >= 2 / 3:
        confidence = "medium"
    else:
        confidence = "low"
    return rate, matches, confidence


def _cpi_consistency(results, summary) -> tuple[float, float, str]:
    """Score repeated CPI passes without letting a single outlier hide behind MAD."""

    if not results or summary.estimated_dpi <= 0:
        return 1.0, 1.0, "low"

    relative_errors = [
        abs(result.estimated_dpi - summary.estimated_dpi) / summary.estimated_dpi
        for result in results
    ]
    worst_relative_deviation = max(relative_errors)
    dpis = [result.estimated_dpi for result in results]
    relative_range = (max(dpis) - min(dpis)) / summary.estimated_dpi

    if (
        len(results) >= 3
        and summary.confidence == "high"
        and worst_relative_deviation <= 0.05
        and relative_range <= 0.08
    ):
        confidence = "high"
    elif (
        summary.confidence != "low"
        and worst_relative_deviation <= 0.12
        and relative_range <= 0.20
    ):
        confidence = "medium"
    else:
        confidence = "low"

    return worst_relative_deviation, relative_range, confidence


def _robust_cpi_subset(results):
    """Return a defensible CPI cluster and any explicitly rejected passes.

    Three samples are never enough evidence to discard one of them. Once at
    least four passes exist, a pass may be excluded only when at least three
    samples and at least 75% of all samples lie within 5% of the all-pass
    median. This lets one obvious ruler/capture mistake be retried without
    silently hiding genuine device instability.
    """

    samples = tuple(results)
    if len(samples) < 4:
        return samples, ()

    all_summary = summarize_calibrations(samples)
    center = all_summary.estimated_dpi
    if center <= 0:
        return samples, ()

    inliers = tuple(
        sample
        for sample in samples
        if abs(sample.estimated_dpi - center) / center <= _CPI_OUTLIER_THRESHOLD
    )
    outliers = tuple(sample for sample in samples if sample not in inliers)
    if len(inliers) >= 3 and len(inliers) / len(samples) >= 0.75:
        return inliers, outliers
    return samples, ()


def _weaker_confidence(first: str, second: str) -> str:
    return min((first, second), key=lambda value: _CONFIDENCE_RANK[value])


def _evaluate(results):
    cpi_results, rejected = _robust_cpi_subset(results)
    summary = summarize_calibrations(cpi_results)
    polling_rate, polling_matches, polling_confidence = _polling_consensus(results)
    worst_cpi_deviation, cpi_range, cpi_confidence = _cpi_consistency(cpi_results, summary)
    overall_confidence = _weaker_confidence(cpi_confidence, polling_confidence)
    return (
        cpi_results,
        rejected,
        summary,
        polling_rate,
        polling_matches,
        polling_confidence,
        worst_cpi_deviation,
        cpi_range,
        cpi_confidence,
        overall_confidence,
    )


def run_calibration(args: argparse.Namespace) -> int:
    """Run one parsed CPI session for CLI and discovery callers."""

    if args.distance_mm <= 0 or args.window <= 0 or args.passes <= 0:
        print("distance, capture window, and passes must be greater than zero", file=sys.stderr)
        return 2
    if args.known_dpi is not None and args.known_dpi <= 0:
        print("--known-dpi must be greater than zero", file=sys.stderr)
        return 2
    try:
        mouse = _pick(args.device)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    if mouse is None:
        return 1

    inches = args.distance_mm / 25.4
    resolved_path = os.path.realpath(mouse.path)
    print("OMUS — Generic Sensor Calibration")
    print("==========================================")
    print(f"Device: {mouse.name} [{(mouse.vendor or 0):04x}:{(mouse.product or 0):04x}]")
    print(f"evdev source: {mouse.path} -> {resolved_path}")
    print(
        f"For each pass, start at the ruler mark and move the mouse exactly "
        f"{args.distance_mm:g} mm ({inches:g} in) in one straight direction, then stop."
    )
    print("OMUS isolates the deliberate motion segment and performs all CPI/DPI math internally.")
    if args.axis == "auto":
        print("Linux X/Y orientation is detected automatically from two-dimensional motion.")
    else:
        print(f"Diagnostic override: measuring REL_{args.axis.upper()} explicitly.")
    print(
        "Calibration exclusively grabs the physical evdev stream during each capture. "
        "If OMUS is currently remapping it, stop the service first."
    )
    if args.known_dpi is not None:
        print(f"Configured DPI stage label for comparison: {args.known_dpi} DPI")

    results = []
    max_passes = max(args.passes, _DEFAULT_MAX_ADAPTIVE_PASSES)
    try:
        while len(results) < max_passes:
            if len(results) >= args.passes:
                evaluation = _evaluate(results)
                if evaluation[-1] == "high":
                    break
                print(
                    "\nConfidence is not yet high; collecting one additional pass "
                    "to distinguish a physical outlier from real device variation."
                )

            pass_index = len(results) + 1
            minimum_label = args.passes if pass_index <= args.passes else max_passes
            prompt = (
                f"\nPass {pass_index}/{minimum_label}: press Enter when positioned "
                "at the start mark... "
            )
            input(prompt)

            events = capture_evdev_motion(mouse.path, seconds=args.window, exclusive=True)
            if args.axis == "auto":
                result = measure_sensor_state_auto(events, distance_mm=args.distance_mm)
            else:
                result = measure_sensor_state(
                    events,
                    distance_mm=args.distance_mm,
                    axis=args.axis,
                )
            results.append(result)
            print(
                f"  pass {pass_index}: ~{result.rounded_dpi} measured CPI, {_polling_label(result)}, "
                f"straightness {result.straightness * 100:.1f}%"
            )
            if result.segment_count > 1:
                print(
                    f"  isolated strongest motion segment from {result.segment_count} observed segments"
                )
    except KeyboardInterrupt:
        print("\nCalibration cancelled.", file=sys.stderr)
        return 130
    except (CalibrationError, OSError, PermissionError) as exc:
        print(f"Calibration failed on pass {len(results) + 1}: {exc}", file=sys.stderr)
        return 1

    (
        cpi_results,
        rejected,
        summary,
        polling_rate,
        polling_matches,
        polling_confidence,
        worst_cpi_deviation,
        cpi_range,
        cpi_confidence,
        overall_confidence,
    ) = _evaluate(results)
    representative = min(
        cpi_results,
        key=lambda item: abs(item.estimated_dpi - summary.estimated_dpi),
    )

    print("\nMeasured sensor state")
    print("---------------------")
    print(f"Calibration passes captured: {len(results)}")
    if rejected:
        print(
            f"CPI passes used: {len(cpi_results)}; rejected {len(rejected)} clearly inconsistent "
            "physical pass(es) after adaptive retry"
        )
    print(f"Detected motion axis: REL_{representative.axis.upper()} (diagnostic only)")
    print(f"Representative net displacement: {representative.net_counts} device units")
    print(f"Representative path: {representative.path_counts} device units")
    print(f"Movement straightness: {representative.straightness * 100:.1f}%")
    print(f"Measured physical CPI: {summary.estimated_dpi:.1f} (~{summary.rounded_dpi})")
    print(
        f"Pass consistency: median absolute deviation {summary.median_absolute_deviation:.1f} CPI "
        f"({summary.relative_mad * 100:.1f}%)"
    )
    print(
        f"Worst-used-pass CPI deviation from median: {worst_cpi_deviation * 100:.1f}%; "
        f"used-pass range: {cpi_range * 100:.1f}%"
    )
    if polling_rate is not None:
        print(f"Observed polling: ~{polling_rate} Hz")
        print(
            f"Polling agreement: {polling_matches}/{len(results)} passes matched "
            f"~{polling_rate} Hz ({polling_confidence})"
        )
    else:
        print(f"Observed polling: {_polling_label(representative)}")
        print("Polling agreement: insufficient repeated standard-rate observations (low)")
    print(f"CPI repeatability confidence: {cpi_confidence}")
    print(f"Overall calibration confidence: {overall_confidence}")

    if args.known_dpi is not None:
        deviation = (summary.estimated_dpi - args.known_dpi) / args.known_dpi
        print(f"Configured DPI stage label: {args.known_dpi} DPI")
        print(
            f"Physical CPI deviation from configured label: {deviation * 100:+.1f}% "
            "(reported, not corrected)"
        )

    print("Vendor protocol used for measurement: none")
    return 0


def main(argv: list[str] | None = None) -> int:
    return run_calibration(_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
