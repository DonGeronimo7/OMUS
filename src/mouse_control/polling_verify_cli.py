"""Physical polling-rate verifier for discovery promotion laboratories.

Uses an already-proven native backend only to establish/restore known polling
states. The measurement path is protocol-neutral evdev timing. No generic HID
polling write is performed and no learned write authority is modified.
"""
from __future__ import annotations

import argparse
import sys

from .device_topology import build_device_graph
from .discovery import get_mouse_devices, select_mouse_device
from .hardware.base import HardwareError
from .hardware.native_hid import NativeHidBackend
from .polling_measurement import (
    PollingMeasurement,
    analyze_polling_timestamps,
    summarize_polling_measurements,
)
from .sensor_calibration import (
    EV_REL,
    EV_SYN,
    REL_X,
    REL_Y,
    SYN_REPORT,
    capture_evdev_motion,
    normalize_event,
)

DEFAULT_RATES = (250, 500, 125)


def _positive_csv(value: str) -> tuple[int, ...]:
    try:
        result = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("rates must be comma-separated integers") from exc
    if not result or any(item <= 0 for item in result):
        raise argparse.ArgumentTypeError("rates must be positive")
    if len(set(result)) != len(result):
        raise argparse.ArgumentTypeError("rates must be unique")
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mouse-control-polling-verify",
        description=(
            "Repeat physical evdev timing measurements for proven polling states. "
            "This laboratory command never performs a generic polling write."
        ),
    )
    parser.add_argument("--device", type=int, metavar="N")
    parser.add_argument("--rates", type=_positive_csv, default=DEFAULT_RATES,
                        metavar="HZ,...", help="rates to verify (default: 250,500,125)")
    parser.add_argument("--passes", type=int, default=4,
                        help="physical passes per rate (default: 4)")
    parser.add_argument("--window", type=float, default=6.0,
                        help="seconds per physical pass (default: 6)")
    parser.add_argument("--i-understand-this-writes-hardware", action="store_true")
    return parser


def _pick(index: int | None):
    mice = get_mouse_devices()
    if not mice:
        raise HardwareError("no mouse devices found")
    if index is None:
        return select_mouse_device(mice)
    if index < 1 or index > len(mice):
        raise HardwareError(f"--device must be between 1 and {len(mice)}")
    return mice[index - 1]


def _motion_timestamps(events) -> tuple[int, ...]:
    timestamps = []
    motion = False
    for raw in events:
        event = normalize_event(raw)
        if event.event_type == EV_REL and event.code in (REL_X, REL_Y):
            motion = motion or event.value != 0
        elif event.event_type == EV_SYN and event.code == SYN_REPORT:
            if motion:
                timestamps.append(event.timestamp_ns)
            motion = False
    return tuple(timestamps)


def _ms(value: float | None) -> str:
    return "n/a" if value is None else f"{value / 1_000_000:.3f} ms"


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _print_measurement(index: int, measurement: PollingMeasurement) -> None:
    print(
        f"  pass {index}: frames={measurement.frame_count}, "
        f"intervals={measurement.interval_count}, confidence={measurement.confidence}"
    )
    print(
        f"    p10={_ms(measurement.p10_interval_ns)}  "
        f"p25={_ms(measurement.p25_interval_ns)}  "
        f"p50={_ms(measurement.p50_interval_ns)}  "
        f"mode={_ms(measurement.mode_interval_ns)}"
    )
    if measurement.inferred_hz is None:
        print(f"    inferred=n/a; {measurement.rejection_reason or 'rejected'}")
    else:
        standard = f"{measurement.standard_hz} Hz" if measurement.standard_hz else "no accepted standard"
        print(
            f"    inferred={measurement.inferred_hz:.1f} Hz -> {standard}; "
            f"error={_pct(measurement.error_fraction)}, jitter={_pct(measurement.jitter_fraction)}, "
            f"coverage={measurement.matched_fraction * 100:.1f}%, "
            f"direct={measurement.direct_fraction * 100:.1f}%"
        )
        if measurement.rejection_reason:
            print(f"    note: {measurement.rejection_reason}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.i_understand_this_writes_hardware:
        print("Refusing test without --i-understand-this-writes-hardware.", file=sys.stderr)
        return 2
    if args.passes <= 0 or args.window <= 0:
        print("--passes and --window must be positive", file=sys.stderr)
        return 2

    mouse = None
    backend = None
    original_rate = None
    original_mode = None
    all_summaries = []

    try:
        mouse = _pick(args.device)
        if mouse is None:
            return 0
        physical = build_device_graph(mouse)
        if physical.ambiguous:
            raise HardwareError("physical identity is ambiguous")

        backend = NativeHidBackend()
        if not backend.supports_device(mouse):
            raise HardwareError("selected device has no proven native polling verifier")
        supported = tuple(backend.get_polling_rates(mouse))
        missing = [rate for rate in args.rates if rate not in supported]
        if missing:
            raise HardwareError(f"requested rates are not proven supported: {missing}; supported={supported}")

        driver = backend._driver(mouse)
        original_mode = driver.get_control_mode()
        original_rate = driver.get_report_rate()

        print("OMUS — Polling Physical Verification")
        print("=============================================")
        print(f"Device: {mouse.name} [{(mouse.vendor or 0):04x}:{(mouse.product or 0):04x}]")
        print(f"Original polling/control state: {original_rate} Hz, mode 0x{original_mode:02x}")
        print("Actuator: proven native backend only")
        print("Measurement: protocol-neutral evdev interval distribution")
        print("Generic polling write authority: NONE")

        for target in args.rates:
            backend.set_polling_rate(mouse, target)
            readback = backend.get_polling_rate(mouse)
            if readback != target:
                raise HardwareError(f"native polling readback requested {target}, got {readback}")
            print(f"\nTarget {target} Hz — native readback confirmed")
            measurements = []
            for index in range(1, args.passes + 1):
                print(f"Pass {index}/{args.passes}: move rapidly and continuously for {args.window:g} seconds.")
                input("Press Enter, then begin moving immediately... ")
                captured = capture_evdev_motion(mouse.path, seconds=args.window, exclusive=True)
                measurement = analyze_polling_timestamps(_motion_timestamps(captured))
                measurements.append(measurement)
                _print_measurement(index, measurement)

            summary = summarize_polling_measurements(target, measurements)
            all_summaries.append(summary)
            print(
                f"  target summary: {summary.accepted_passes}/{len(summary.passes)} accepted; "
                f"confidence={summary.confidence}; "
                f"median inferred=" + (
                    f"{summary.median_inferred_hz:.1f} Hz" if summary.median_inferred_hz is not None else "n/a"
                )
            )
            if summary.rejection_reason:
                print(f"  target note: {summary.rejection_reason}")

        print("\nVerification result")
        print("-------------------")
        for summary in all_summaries:
            status = "PASS" if summary.confidence in {"high", "medium"} else "NOT PROVEN"
            print(f"{summary.target_hz} Hz: {status} ({summary.confidence})")
        if all(summary.confidence in {"high", "medium"} for summary in all_summaries):
            print("Physical timing is sufficiently repeatable for the next generic polling replay laboratory.")
            return 0
        print("At least one polling state remains physically unresolved. Do not promote generic polling writes.")
        return 1

    except KeyboardInterrupt:
        print("\nPolling verification cancelled.", file=sys.stderr)
        return 130
    except (HardwareError, OSError, PermissionError) as exc:
        print(f"Polling verification failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if backend is not None and mouse is not None:
            try:
                driver = backend._driver(mouse)
                if original_rate is not None:
                    backend.set_polling_rate(mouse, original_rate)
                if original_mode is not None and driver.get_control_mode() != original_mode:
                    driver.set_control_mode(original_mode)
                    restored = driver.get_control_mode()
                    if restored != original_mode:
                        raise HardwareError(f"control-mode restoration read 0x{restored:02x}")
                if original_rate is not None and original_mode is not None:
                    print(f"\nRestored polling/control state: {original_rate} Hz, mode 0x{original_mode:02x}")
            except Exception as exc:
                print(f"\nWARNING: polling restoration failed: {exc}", file=sys.stderr)
            backend.close()


if __name__ == "__main__":
    raise SystemExit(main())
