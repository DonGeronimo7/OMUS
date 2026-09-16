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
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mouse-control-sensor-calibrate",
        description=(
            "Measure current mouse DPI and polling from raw Linux evdev motion without "
            "using a vendor protocol backend."
        ),
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
        help="Linux relative axis to measure; default auto selects the dominant motion axis",
    )
    parser.add_argument(
        "--window",
        type=float,
        default=6.0,
        metavar="SECONDS",
        help="capture window after pressing Enter (default: 6 seconds)",
    )
    return parser


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


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.distance_mm <= 0 or args.window <= 0:
        print("distance and capture window must be greater than zero", file=sys.stderr)
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
    print("Mouse Control — Generic Sensor Calibration")
    print("==========================================")
    print(f"Device: {mouse.name} [{(mouse.vendor or 0):04x}:{(mouse.product or 0):04x}]")
    print(f"evdev source: {mouse.path} -> {resolved_path}")
    print(
        f"Place the mouse against a ruler. After pressing Enter, move it exactly "
        f"{args.distance_mm:g} mm ({inches:g} in) in one straight direction, then stop. "
        "Do not press the DPI button during this pass."
    )
    if args.axis == "auto":
        print("Mouse Control will determine which Linux relative axis carries the movement.")
    else:
        print(f"Diagnostic override: measuring REL_{args.axis.upper()} explicitly.")
    print(
        "Calibration will exclusively grab this physical evdev stream during the capture. "
        "If mouse-control is currently remapping it, stop the service first."
    )
    input("Press Enter when ready... ")

    try:
        events = capture_evdev_motion(mouse.path, seconds=args.window, exclusive=True)
        if args.axis == "auto":
            result = measure_sensor_state_auto(events, distance_mm=args.distance_mm)
        else:
            result = measure_sensor_state(
                events,
                distance_mm=args.distance_mm,
                axis=args.axis,
            )
    except (CalibrationError, OSError, PermissionError) as exc:
        print(f"Calibration failed: {exc}", file=sys.stderr)
        return 1

    print("\nMeasured sensor state")
    print("---------------------")
    print(f"Detected motion axis: REL_{result.axis.upper()}")
    print(f"Raw {result.axis.upper()} net counts: {result.net_counts}")
    print(f"Raw {result.axis.upper()} path counts: {result.path_counts}")
    other_axis = "Y" if result.axis == "x" else "X"
    print(f"Cross-axis {other_axis} path counts: {result.cross_axis_counts}")
    print(f"Movement straightness: {result.straightness * 100:.1f}%")
    print(f"Estimated DPI: {result.estimated_dpi:.1f} (~{result.rounded_dpi})")
    print(f"Motion report frames: {result.motion_frames}")
    if result.peak_polling_hz is None:
        print("Observed polling: insufficient motion frames")
    elif result.standard_polling_hz is None:
        print(f"Observed peak polling: {result.peak_polling_hz:.1f} Hz (no standard rate match)")
    else:
        print(
            f"Observed peak polling: {result.peak_polling_hz:.1f} Hz "
            f"(~{result.standard_polling_hz} Hz)"
        )
    print("Vendor protocol used: none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
