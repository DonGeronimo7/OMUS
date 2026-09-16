"""Explicit hardware promotion of one DEMONSTRATED learned DPI operation.

Promotion is protocol-neutral.  A DEMONSTRATED exact-model operation may be
replayed only after the user has physically placed the mouse in a demonstrated
start state.  One persistent learned HID session is then held across active
readback, target replay, physical CPI verification, generic rollback, rollback
readback, and independent physical rollback verification.

A vendor/native backend is not required for authority.  If one happens to be
available it may be used only as an emergency restoration aid after a failed
generic rollback; it never supplies evidence used to promote the learned path.
"""

from __future__ import annotations

import argparse
import json
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
    learned_dpi_read_spec,
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
            "only after generic readback, independent physical CPI validation, "
            "and verified generic rollback."
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


def _measure_once(mouse, *, dpi: int, distance_mm: float, window: float, label: str):
    inches = distance_mm / 25.4
    input(
        f"{label}: position at the ruler start, press Enter, then move exactly "
        f"{distance_mm:g} mm ({inches:g} in) in one straight direction... "
    )
    events = capture_evdev_motion(mouse.path, seconds=window, exclusive=True)
    measured = measure_sensor_state_auto(events, distance_mm=distance_mm)
    deviation = (measured.estimated_dpi - dpi) / dpi
    print(
        f"  {label.lower()}: ~{measured.rounded_dpi} CPI "
        f"({deviation * 100:+.1f}%), straightness "
        f"{measured.straightness * 100:.1f}%"
    )
    return measured, deviation


def _generic_read(adapter: LearnedHidAdapter, authorization: TransactionAuthorization) -> int:
    context = TransactionEngine().run(
        learned_dpi_read_spec(),
        adapter,
        authorization=authorization,
        context=TransactionContext(),
    )
    return int(context.values["raw_readback"])


def _generic_write(
    adapter: LearnedHidAdapter,
    authorization: TransactionAuthorization,
    target: int,
) -> int:
    context = TransactionEngine().run(
        learned_dpi_transaction_spec(),
        adapter,
        authorization=authorization,
        context=TransactionContext(values={"target": int(target)}),
    )
    return int(context.values["raw_readback"])


def _emergency_native_restore(mouse, dpi: int) -> bool:
    """Best-effort safety aid only; never contributes promotion evidence."""
    backend = NativeHidBackend()
    try:
        if not backend.supports_device(mouse):
            return False
        state = backend.set_dpi(mouse, dpi)
        return state.x_dpi == dpi
    except Exception:
        return False
    finally:
        backend.close()


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.authorize_reversible_replay:
        print("Refusing replay without --authorize-reversible-replay.", file=sys.stderr)
        return 2
    if min(args.start_dpi, args.target_dpi, args.passes) <= 0:
        print("DPI values and passes must be positive.", file=sys.stderr)
        return 2
    if args.start_dpi == args.target_dpi:
        print("start and target DPI must differ.", file=sys.stderr)
        return 2
    if args.distance_mm <= 0 or args.window <= 0:
        print("distance and capture window must be positive.", file=sys.stderr)
        return 2

    mouse = None
    adapter: LearnedHidAdapter | None = None
    rollback_required = False
    rollback_verified = False

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
        authorization = TransactionAuthorization(
            active_queries=True,
            reversible_writes=True,
            reason=(
                f"explicit exact-model promotion replay "
                f"{args.start_dpi}->{args.target_dpi}->{args.start_dpi}"
            ),
        )
        adapter = LearnedHidAdapter(node.path, operation)

        print("Mouse Control — Learned Write Promotion")
        print("=======================================")
        print(
            f"Device: {mouse.name} "
            f"[{(mouse.vendor or 0):04x}:{(mouse.product or 0):04x}]"
        )
        print(f"Learned operation: {operation_path}")
        print(f"Calibrated read evidence: {calibrated_path}")
        print(f"Exact transport descriptor: {operation.interface.descriptor_sha256}")
        print(f"Replay: {args.start_dpi} -> {args.target_dpi} -> {args.start_dpi}")
        print("Authority source: demonstrated exact-model generic transaction only")
        print("Vendor/native protocol dependency: NONE")
        print("Session policy: one learned HID session stays open through target + rollback")
        print(
            f"\nBefore continuing, use the mouse's physical controls to place it at "
            f"{args.start_dpi} DPI. No generic write is used to manufacture the start state."
        )
        input("Press Enter when the physical start state is ready... ")

        start_readback = _generic_read(adapter, authorization)
        if start_readback != args.start_dpi:
            raise LearnedOperationError(
                f"generic learned readback reports {start_readback} DPI; expected the "
                f"physical start state {args.start_dpi} DPI"
            )
        start_measure, start_deviation = _measure_once(
            mouse,
            dpi=args.start_dpi,
            distance_mm=args.distance_mm,
            window=args.window,
            label="Start-state physical check",
        )
        if abs(start_deviation) > 0.15:
            raise LearnedOperationError(
                "generic start-state readback did not independently agree with physical CPI"
            )

        target_readback = _generic_write(adapter, authorization, args.target_dpi)
        rollback_required = True
        if target_readback != args.target_dpi:
            raise LearnedOperationError(
                f"generic write read back {target_readback}, expected {args.target_dpi}"
            )
        print(f"Generic target ACK/readback: confirmed {target_readback} DPI")
        print("Learned HID session remains OPEN during physical verification.")

        results = []
        for index in range(1, args.passes + 1):
            measured, _deviation = _measure_once(
                mouse,
                dpi=args.target_dpi,
                distance_mm=args.distance_mm,
                window=args.window,
                label=f"Target pass {index}/{args.passes}",
            )
            results.append(measured)

        summary = summarize_calibrations(results)
        deviation = (summary.estimated_dpi - args.target_dpi) / args.target_dpi
        print(f"\nMedian target physical CPI: {summary.estimated_dpi:.1f}")
        print(f"Calibration confidence: {summary.confidence}")
        print(f"Deviation from target: {deviation * 100:+.1f}%")
        if abs(deviation) > 0.15:
            raise LearnedOperationError(
                "generic target readback did not independently agree with physical CPI"
            )

        rollback_readback = _generic_write(adapter, authorization, args.start_dpi)
        if rollback_readback != args.start_dpi:
            raise LearnedOperationError(
                f"generic rollback read back {rollback_readback}, expected {args.start_dpi}"
            )
        rollback_measure, rollback_deviation = _measure_once(
            mouse,
            dpi=args.start_dpi,
            distance_mm=args.distance_mm,
            window=args.window,
            label="Rollback physical check",
        )
        if abs(rollback_deviation) > 0.15:
            raise LearnedOperationError(
                "generic rollback readback did not independently agree with physical CPI"
            )
        rollback_verified = True
        rollback_required = False

        promoted = promote_operation(
            operation,
            target_value=args.target_dpi,
            measured_value=summary.estimated_dpi,
            deviation_fraction=deviation,
            calibration_confidence=summary.confidence,
            raw_readback_value=target_readback,
            state_evidence={
                "calibrated_read_profile": True,
                "calibrated_values": sorted(calibrated_values),
                "start_generic_readback": start_readback,
                "start_physically_verified": True,
                "start_physical_cpi": float(start_measure.estimated_dpi),
                "transport_session_held_open": True,
                "generic_rollback_readback": rollback_readback,
                "generic_rollback_physically_verified": True,
                "rollback_physical_cpi": float(rollback_measure.estimated_dpi),
                "vendor_teacher_required_for_promotion": False,
            },
        )
        if not rollback_verified:
            raise LearnedOperationError("rollback was not verified; refusing promotion")
        destination = store.save(promoted)

        print("\nPROMOTION SUCCESS")
        print("-----------------")
        print("Status: PROVEN")
        print("Write authority: true")
        print("Scope: exact model + exact descriptor interface")
        print(f"Demonstrated values: {', '.join(map(str, promoted.demonstrated_values))}")
        print(f"Saved: {destination}")
        print("Target and rollback were executed through the generic learned transport.")
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
        if adapter is not None and rollback_required:
            try:
                authorization = TransactionAuthorization(
                    active_queries=True,
                    reversible_writes=True,
                    reason="promotion failure rollback",
                )
                restored = _generic_write(adapter, authorization, args.start_dpi)
                rollback_verified = restored == args.start_dpi
                if rollback_verified:
                    print(f"\nEmergency generic rollback readback: {restored} DPI")
            except Exception as exc:
                print(f"\nWARNING: generic rollback failed: {exc}", file=sys.stderr)
        if adapter is not None:
            adapter.close()
        if mouse is not None and rollback_required and not rollback_verified:
            if _emergency_native_restore(mouse, args.start_dpi):
                print(
                    f"WARNING: restored {args.start_dpi} DPI through an optional proven "
                    "vendor backend after generic rollback failed. Promotion remains denied.",
                    file=sys.stderr,
                )
            else:
                print(
                    "WARNING: automatic rollback could not be verified. Use the mouse's "
                    "physical DPI control to restore the previous state. No authority was promoted.",
                    file=sys.stderr,
                )


if __name__ == "__main__":
    raise SystemExit(main())
