# SPDX-License-Identifier: AGPL-3.0-or-later
"""Teacher-free raw polling replay laboratory.

The native backend is used only to establish the known initial state and to
restore the user's original state.  The tested polling transition itself is
rendered and executed solely from the saved raw demonstration corpus.

No generic polling write authority is persisted by this command.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .device_profiles import get_profile_directory
from .device_topology import build_device_graph
from .discovery import get_mouse_devices, select_mouse_device
from .hardware.base import HardwareError
from .hardware.native_hid import NativeHidBackend
from .hidpp_driver import ONBOARD_MODE
from .polling_measurement import (
    PollingMeasurement,
    analyze_polling_timestamps,
    summarize_polling_measurements,
)
from .polling_replay import (
    GenericPollingReplayAdapter,
    PollingReplayError,
    infer_polling_replay_grammar,
    load_polling_corpus,
    matching_interface_node,
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mouse-control-polling-replay",
        description=(
            "Replay one demonstrated polling transaction through inferred raw HID "
            "grammar, then require independent physical timing verification."
        ),
    )
    parser.add_argument("--device", type=int, metavar="N")
    parser.add_argument("--target", type=int, default=500, metavar="HZ")
    parser.add_argument("--passes", type=int, default=3)
    parser.add_argument("--window", type=float, default=6.0)
    parser.add_argument(
        "--authorize-generic-replay",
        action="store_true",
        help="required explicit authorization for the reversible raw polling experiment",
    )
    return parser


def _pick(index: int | None):
    mice = get_mouse_devices()
    if not mice:
        raise PollingReplayError("no mouse devices found")
    if index is None:
        return select_mouse_device(mice)
    if index < 1 or index > len(mice):
        raise PollingReplayError(f"--device must be between 1 and {len(mice)}")
    return mice[index - 1]


def _corpus_path(physical) -> Path:
    vendor = physical.vendor_id or 0
    product = physical.product_id or 0
    return (
        get_profile_directory()
        / "polling-demonstrations"
        / f"{vendor:04x}-{product:04x}-{physical.model_fingerprint[:16]}.json"
    )


def _validate_profile_identity(profile, physical) -> None:
    fingerprints = profile.get("fingerprints")
    identity = profile.get("identity")
    if not isinstance(fingerprints, dict) or not isinstance(identity, dict):
        raise PollingReplayError("polling corpus lacks stable device identity")
    if fingerprints.get("model") != physical.model_fingerprint:
        raise PollingReplayError("polling corpus model fingerprint does not match")
    for expected, actual, label in (
        (identity.get("bus"), physical.bus, "bus"),
        (identity.get("vendor_id"), physical.vendor_id, "vendor"),
        (identity.get("product_id"), physical.product_id, "product"),
    ):
        if expected is not None and actual is not None and expected != actual:
            raise PollingReplayError(f"polling corpus {label} identity does not match")


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
        standard = (
            f"{measurement.standard_hz} Hz"
            if measurement.standard_hz is not None
            else "no accepted standard"
        )
        print(
            f"    inferred={measurement.inferred_hz:.1f} Hz -> {standard}; "
            f"error={_pct(measurement.error_fraction)}, "
            f"jitter={_pct(measurement.jitter_fraction)}, "
            f"coverage={measurement.matched_fraction * 100:.1f}%, "
            f"direct={measurement.direct_fraction * 100:.1f}%"
        )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.authorize_generic_replay:
        print("Refusing test without --authorize-generic-replay.", file=sys.stderr)
        return 2
    if args.target <= 0 or args.passes <= 0 or args.window <= 0:
        print("--target, --passes, and --window must be positive", file=sys.stderr)
        return 2

    mouse = None
    adapter = None
    original_rate = None
    original_mode = None

    try:
        mouse = _pick(args.device)
        if mouse is None:
            return 0
        physical = build_device_graph(mouse)
        if physical.ambiguous:
            raise PollingReplayError("physical identity is ambiguous")

        corpus_path = _corpus_path(physical)
        profile = load_polling_corpus(corpus_path)
        _validate_profile_identity(profile, physical)
        grammar = infer_polling_replay_grammar(profile)
        grammar.raw_for_rate(args.target)
        node = matching_interface_node(profile, physical)

        print("OMUS — Generic Polling Replay Laboratory")
        print("=================================================")
        print(
            f"Device: {mouse.name} "
            f"[{(mouse.vendor or 0):04x}:{(mouse.product or 0):04x}]"
        )
        print(f"Raw corpus: {corpus_path}")
        print(f"Inferred transaction steps: {len(grammar.steps)}")
        print(f"Inferred polling write step: {grammar.write_step_index + 1}")
        print(f"Inferred polling readback step: {grammar.read_step_index + 1}")
        print(
            "Demonstrated rates only: "
            + ", ".join(f"{rate} Hz" for rate in grammar.demonstrated_rates)
        )
        print(
            "Inferred raw map: "
            + ", ".join(
                f"0x{raw:02x}->{rate} Hz"
                for raw, rate in sorted(grammar.raw_to_hz.items())
            )
        )
        print("Generic persisted polling write authority: NONE")
        print("Native backend role: establish known start + emergency/final restoration only")

        # Teacher establishes the same known initial state used by every raw
        # demonstration.  It is then closed before the generic transaction.
        native = NativeHidBackend()
        try:
            if not native.supports_device(mouse):
                raise PollingReplayError(
                    "proven native backend is required for laboratory rollback"
                )
            driver = native._driver(mouse)
            original_mode = driver.get_control_mode()
            original_rate = driver.get_report_rate()
            if driver.get_control_mode() != ONBOARD_MODE:
                driver.set_control_mode(ONBOARD_MODE)
                if driver.get_control_mode() != ONBOARD_MODE:
                    raise PollingReplayError(
                        "could not establish the demonstrated initial control state"
                    )
        finally:
            native.close()

        print(
            f"\nOriginal state recorded for restoration: "
            f"{original_rate} Hz, mode 0x{original_mode:02x}"
        )
        print("Known demonstrated initial control state established.")
        print("Native teacher closed. Beginning teacher-free raw replay...")

        adapter = GenericPollingReplayAdapter(node.path, grammar)
        readback = adapter.execute(args.target)
        print(f"Generic raw replay readback: {readback} Hz")
        if readback != args.target:
            raise PollingReplayError(
                f"generic replay requested {args.target}, read {readback}"
            )

        measurements = []
        for index in range(1, args.passes + 1):
            print(
                f"Pass {index}/{args.passes}: move rapidly and continuously "
                f"for {args.window:g} seconds."
            )
            input("Press Enter, then begin moving immediately... ")
            captured = capture_evdev_motion(
                mouse.path, seconds=args.window, exclusive=True
            )
            measurement = analyze_polling_timestamps(
                _motion_timestamps(captured)
            )
            measurements.append(measurement)
            _print_measurement(index, measurement)

        summary = summarize_polling_measurements(args.target, measurements)
        print("\nGeneric polling replay result")
        print("-----------------------------")
        print(
            f"Raw readback: {readback} Hz\n"
            f"Physical passes: {summary.accepted_passes}/{len(summary.passes)} accepted\n"
            f"Physical confidence: {summary.confidence}\n"
            f"Physical median: "
            + (
                f"{summary.median_inferred_hz:.1f} Hz"
                if summary.median_inferred_hz is not None
                else "n/a"
            )
        )

        if (
            summary.consensus_hz == args.target
            and summary.confidence in {"high", "medium"}
        ):
            print("\nGENERIC POLLING REPLAY SUCCESS")
            print("Teacher-free raw execution and independent physical timing agree.")
            print("Persisted generic polling write authority remains NONE.")
            return 0

        raise PollingReplayError(
            summary.rejection_reason
            or "physical timing did not prove the generic polling target"
        )

    except KeyboardInterrupt:
        print("\nGeneric polling replay cancelled.", file=sys.stderr)
        return 130
    except (PollingReplayError, HardwareError, OSError, PermissionError) as exc:
        print(f"Generic polling replay failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if adapter is not None:
            try:
                adapter.close()
            except Exception:
                pass

        if mouse is not None and original_rate is not None and original_mode is not None:
            native = NativeHidBackend()
            try:
                if not native.supports_device(mouse):
                    raise PollingReplayError(
                        "native restoration backend could not bind"
                    )
                driver = native._driver(mouse)
                native.set_polling_rate(mouse, original_rate)
                if driver.get_control_mode() != original_mode:
                    driver.set_control_mode(original_mode)
                restored_mode = driver.get_control_mode()
                if restored_mode != original_mode:
                    raise PollingReplayError(
                        f"restoration mode read 0x{restored_mode:02x}, "
                        f"expected 0x{original_mode:02x}"
                    )
                print(
                    f"\nRestored polling/control state: "
                    f"{original_rate} Hz, mode 0x{original_mode:02x}"
                )
            except Exception as exc:
                print(
                    f"\nWARNING: failed to restore original polling/control state: {exc}",
                    file=sys.stderr,
                )
            finally:
                native.close()


if __name__ == "__main__":
    raise SystemExit(main())
