"""Explicit hardware promotion of one DEMONSTRATED learned DPI operation.

The native backend is used only to establish/restore a known safe starting
state. The candidate target transition itself is executed exclusively through
the protocol-neutral learned transaction engine.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .calibrated_profiles import (
    CalibratedProfileError,
    get_calibrated_profile_directory,
    validate_calibrated_profile,
)
from .device_topology import build_device_graph
from .discovery import get_mouse_devices, select_mouse_device
from .hardware.native_hid import NativeHidBackend
from .learned_hid_transport import (
    LearnedHidAdapter,
    LearnedHidTransportError,
    learned_dpi_transaction_spec,
)
from .learned_operations import (
    LearnedOperationError,
    LearnedOperationState,
    LearnedOperationStore,
    matching_interface_node,
    promote_operation,
)
from .sensor_calibration import (
    CalibrationError,
    capture_evdev_motion,
    measure_sensor_state_auto,
    summarize_calibrations,
)
from .transaction_engine import (
    TransactionAuthorization,
    TransactionContext,
    TransactionEngine,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mouse-control-write-promote",
        description=(
            "Replay one already-demonstrated learned DPI transaction and promote it "
            "only after generic readback plus independent physical CPI validation."
        ),
    )
    parser.add_argument("--device", type=int, metavar="N")
    parser.add_argument("--start-dpi", type=int, default=800)
    parser.add_argument("--target-dpi", type=int, default=1500)
    parser.add_argument("--distance-mm", type=float, default=254.0)
    parser.add_argument("--passes", type=int, default=3)
    parser.add_argument("--window", type=float, default=8.0)
    parser.add_argument(
        "--authorize-reversible-replay",
        action="store_true",
        help="required explicit authorization for one reversible demonstrated replay",
    )
    return parser


def _pick(index: int | None):
    mice = get_mouse_devices()
    if not mice:
        raise LearnedOperationError("no mouse devices found")
    if index is None:
        return select_mouse_device(mice)
    if index < 1 or index > len(mice):
        raise LearnedOperationError(f"--device must be between 1 and {len(mice)}")
    return mice[index - 1]


def _load_calibrated_profile(physical):
    directory = get_calibrated_profile_directory()
    matches = []
    if not directory.is_dir():
        return None
    for path in sorted(directory.glob("*.json")):
        try:
            profile = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(profile, dict):
                continue
            validate_calibrated_profile(profile)
        except (OSError, json.JSONDecodeError, CalibratedProfileError):
            continue
        identity = profile.get("identity") or {}
        fingerprints = profile.get("fingerprints") or {}
        if fingerprints.get("model") != physical.model_fingerprint:
            continue
        if any(
            expected is not None and actual is not None and expected != actual
            for expected, actual in (
                (identity.get("bus"), physical.bus),
                (identity.get("vendor_id"), physical.vendor_id),
                (identity.get("product_id"), physical.product_id),
            )
        ):
            continue
        matches.append((path, profile))
    return matches[0] if len(matches) == 1 else None


def _calibrated_values(profile) -> set[int]:
    values: set[int] = set()
    if not profile:
        return values
    for mapping in profile.get("raw_mappings") or []:
        lookup = mapping.get("raw_to_configured_dpi") if isinstance(mapping, dict) else None
        if isinstance(lookup, dict):
            for value in lookup.values():
                try:
                    values.add(int(value))
                except (TypeError, ValueError):
                    pass
    return values


def _restore_native(mouse, dpi: int) -> None:
    backend = NativeHidBackend()
    try:
        if not backend.supports_device(mouse):
            raise LearnedOperationError("native restoration backend could not bind")
        state = backend.set_dpi(mouse, dpi)
        if state.x_dpi != dpi:
            raise LearnedOperationError(
                f"native restoration read {state.x_dpi}, expected {dpi}"
            )
    finally:
        backend.close()


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.authorize_reversible_replay:
        print(
            "Refusing replay without --authorize-reversible-replay.",
            file=sys.stderr,
        )
        return 2
    if min(args.start_dpi, args.target_dpi, args.passes) <= 0:
        print("DPI values and passes must be positive.", file=sys.stderr)
        return 2
    if args.distance_mm <= 0 or args.window <= 0:
        print("distance and capture window must be positive.", file=sys.stderr)
        return 2

    mouse = None
    original_dpi: int | None = None
    restore_needed = False
    learned_adapter: LearnedHidAdapter | None = None

    try:
        mouse = _pick(args.device)
        physical = build_device_graph(mouse)
        if physical.ambiguous:
            raise LearnedOperationError("physical identity is ambiguous")

        store = LearnedOperationStore()
        found = store.find_for_physical(physical, proven_only=False)
        if found is None:
            raise LearnedOperationError(
                "exactly one learned operation was not found for this physical model"
            )
        operation_path, operation = found
        if operation.state is LearnedOperationState.PROVEN:
            print(f"Operation is already PROVEN: {operation_path}")
            return 0
        if not operation.accepts(args.start_dpi) or not operation.accepts(args.target_dpi):
            raise LearnedOperationError(
                "start and target must both be values in the demonstrated training set"
            )

        calibrated = _load_calibrated_profile(physical)
        if calibrated is None:
            raise LearnedOperationError(
                "exactly one calibrated read-only profile is required before promotion"
            )
        calibrated_path, calibrated_profile = calibrated
        calibrated_values = _calibrated_values(calibrated_profile)
        if args.start_dpi not in calibrated_values or args.target_dpi not in calibrated_values:
            raise LearnedOperationError(
                "start/target are not both present in the physically calibrated DPI mapping"
            )

        node = matching_interface_node(operation, physical)

        print("Mouse Control — Learned Write Promotion")
        print("=======================================")
        print(
            f"Device: {mouse.name} "
            f"[{(mouse.vendor or 0):04x}:{(mouse.product or 0):04x}]"
        )
        print(f"Learned operation: {operation_path}")
        print(f"Calibrated read evidence: {calibrated_path}")
        print(f"Exact transport descriptor: {operation.interface.descriptor_sha256}")
        print(f"Replay: {args.start_dpi} -> {args.target_dpi}")
        print("Candidate target write path: learned generic HID only")
        print("Native backend use: establish start + emergency/final restoration only")

        native = NativeHidBackend()
        try:
            if not native.supports_device(mouse):
                raise LearnedOperationError(
                    "a proven native actuator is required for this first promotion laboratory"
                )
            original = native.get_dpi_state(mouse)
            if original is None:
                raise LearnedOperationError("could not read original DPI")
            original_dpi = original.x_dpi
            started = native.set_dpi(mouse, args.start_dpi)
            if started.x_dpi != args.start_dpi:
                raise LearnedOperationError("failed to establish promotion start state")
            restore_needed = True
            print(f"Native register readback for start state: {started.x_dpi} DPI")

            inches = args.distance_mm / 25.4
            print(
                f"\nStart-state physical sanity check: move exactly {args.distance_mm:g} mm "
                f"({inches:g} in) once."
            )
            input("Start check: position at start mark and press Enter... ")
            start_events = capture_evdev_motion(
                mouse.path,
                seconds=args.window,
                exclusive=True,
            )
            start_measure = measure_sensor_state_auto(
                start_events,
                distance_mm=args.distance_mm,
            )
            start_deviation = (
                start_measure.estimated_dpi - args.start_dpi
            ) / args.start_dpi
            print(
                f"  physical start state: ~{start_measure.rounded_dpi} CPI "
                f"({start_deviation * 100:+.1f}%), "
                f"straightness {start_measure.straightness * 100:.1f}%"
            )
            if abs(start_deviation) > 0.15:
                raise LearnedOperationError(
                    "native start-state register readback did not match physical CPI"
                )
        finally:
            native.close()

        authorization = TransactionAuthorization(
            reversible_writes=True,
            reason=(
                f"explicit exact-model promotion replay "
                f"{args.start_dpi}->{args.target_dpi}"
            ),
        )
        learned_adapter = LearnedHidAdapter(node.path, operation)
        context = TransactionContext(values={"target": int(args.target_dpi)})
        context = TransactionEngine().run(
            learned_dpi_transaction_spec(),
            learned_adapter,
            authorization=authorization,
            context=context,
        )
        raw_readback = int(context.values["raw_readback"])
        print(f"Generic transaction ACK/readback: confirmed {raw_readback} DPI")
        print("Generic learned hidraw transport remains OPEN during physical verification.")

        results = []
        inches = args.distance_mm / 25.4
        print(
            f"\nPhysical verification: move exactly {args.distance_mm:g} mm "
            f"({inches:g} in) in one straight direction for each pass."
        )
        for index in range(1, args.passes + 1):
            input(f"Pass {index}/{args.passes}: position at start mark and press Enter... ")
            events = capture_evdev_motion(
                mouse.path,
                seconds=args.window,
                exclusive=True,
            )
            measured = measure_sensor_state_auto(
                events,
                distance_mm=args.distance_mm,
            )
            results.append(measured)
            print(
                f"  pass {index}: ~{measured.rounded_dpi} CPI, "
                f"straightness {measured.straightness * 100:.1f}%"
            )

        summary = summarize_calibrations(results)
        deviation = (
            summary.estimated_dpi - args.target_dpi
        ) / args.target_dpi
        print(f"\nMedian physical CPI: {summary.estimated_dpi:.1f}")
        print(f"Calibration confidence: {summary.confidence}")
        print(f"Deviation from target: {deviation * 100:+.1f}%")

        promoted = promote_operation(
            operation,
            target_value=args.target_dpi,
            measured_value=summary.estimated_dpi,
            deviation_fraction=deviation,
            calibration_confidence=summary.confidence,
            raw_readback_value=raw_readback,
            state_evidence={
                "calibrated_read_profile": True,
                "calibrated_values": sorted(calibrated_values),
                "start_physically_verified": True,
                "start_physical_cpi": float(start_measure.estimated_dpi),
                "transport_session_held_open": True,
                "passive_stage_event_required": False,
            },
        )
        destination = store.save(promoted)

        print("\nPROMOTION SUCCESS")
        print("-----------------")
        print("Status: PROVEN")
        print("Write authority: true")
        print("Scope: exact model + exact descriptor interface")
        print(f"Demonstrated values: {', '.join(map(str, promoted.demonstrated_values))}")
        print(f"Saved: {destination}")
        print(
            "The target transition was executed without the native semantic DPI setter."
        )
        return 0

    except KeyboardInterrupt:
        print("\nPromotion cancelled.", file=sys.stderr)
        return 130
    except (
        LearnedOperationError,
        LearnedHidTransportError,
        CalibrationError,
        OSError,
        PermissionError,
    ) as exc:
        print(f"Promotion failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if learned_adapter is not None:
            learned_adapter.close()
        if mouse is not None and restore_needed and original_dpi is not None:
            try:
                _restore_native(mouse, original_dpi)
                print(f"\nRestored original DPI: {original_dpi}")
            except Exception as exc:
                print(
                    f"\nWARNING: failed to restore original DPI {original_dpi}: {exc}",
                    file=sys.stderr,
                )


if __name__ == "__main__":
    raise SystemExit(main())
