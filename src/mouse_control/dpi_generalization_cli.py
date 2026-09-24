# SPDX-License-Identifier: AGPL-3.0-or-later
"""Laboratory test for numeric DPI generalization.

This command deliberately tests values that were never part of the teacher
demonstration. It extends a PROVEN learned operation only in memory, keeps the
learned hidraw session alive, and requires physical CPI verification. It does
not widen persisted runtime write authority.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import sys

from .device_topology import build_device_graph
from .discovery import get_mouse_devices, select_mouse_device
from .hardware.native_hid import NativeHidBackend
from .learned_hid_transport import (
    LearnedHidAdapter,
    learned_dpi_transaction_spec,
)
from .learned_operations import (
    LearnedOperationError,
    LearnedOperationStore,
    matching_interface_node,
)
from .protocol_grammar import CodecKind
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
    TransactionError,
)


DIRECT_INTEGER_CODECS = frozenset(
    {CodecKind.U8, CodecKind.U16_LE, CodecKind.U16_BE}
)


def _positive_csv(value: str) -> tuple[int, ...]:
    try:
        result = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("values must be comma-separated integers") from exc
    if not result or any(item <= 0 for item in result):
        raise argparse.ArgumentTypeError("values must be positive integers")
    if len(set(result)) != len(result):
        raise argparse.ArgumentTypeError("values must be unique")
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mouse-control-dpi-generalize",
        description=(
            "Test unseen DPI values using only an already-PROVEN learned numeric "
            "grammar. No teacher demonstrates the candidate values."
        ),
    )
    parser.add_argument("--device", type=int, metavar="N")
    parser.add_argument("--baseline", type=int, default=1500)
    parser.add_argument(
        "--candidates",
        type=_positive_csv,
        default=(1600, 1550),
        metavar="DPI,...",
        help="unseen DPI values to generate (default: 1600,1550)",
    )
    parser.add_argument("--distance-mm", type=float, default=254.0)
    parser.add_argument("--passes", type=int, default=3)
    parser.add_argument("--window", type=float, default=8.0)
    parser.add_argument(
        "--authorize-generalization-test",
        action="store_true",
        help="required explicit authorization for bounded reversible unseen-value writes",
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


def validate_numeric_generalization(operation, baseline: int, candidates: tuple[int, ...]) -> None:
    if not operation.write_authorized:
        raise LearnedOperationError("numeric generalization requires a PROVEN operation")
    if operation.write_field.codec.kind not in DIRECT_INTEGER_CODECS:
        raise LearnedOperationError("write field is not a direct U8/U16 numeric codec")
    if operation.read_field.codec.kind is not operation.write_field.codec.kind:
        raise LearnedOperationError("write/readback codecs do not agree")
    if operation.read_field.width != operation.write_field.width:
        raise LearnedOperationError("write/readback widths do not agree")
    if baseline not in operation.demonstrated_values:
        raise LearnedOperationError("baseline must be one of the demonstrated values")

    demonstrated = set(operation.demonstrated_values)
    low, high = min(demonstrated), max(demonstrated)
    for candidate in candidates:
        if candidate in demonstrated:
            raise LearnedOperationError(
                f"candidate {candidate} was already demonstrated; it cannot prove generalization"
            )
        if not low < candidate < high:
            raise LearnedOperationError(
                f"candidate {candidate} is outside the demonstrated envelope {low}..{high}"
            )


def _physical_measure(mouse, *, distance_mm: float, window: float, passes: int, label: str):
    results = []
    inches = distance_mm / 25.4
    print(
        f"\n{label}: move exactly {distance_mm:g} mm ({inches:g} in) "
        "in one straight direction for each pass."
    )
    for index in range(1, passes + 1):
        input(f"Pass {index}/{passes}: position at start mark and press Enter... ")
        events = capture_evdev_motion(mouse.path, seconds=window, exclusive=True)
        measured = measure_sensor_state_auto(events, distance_mm=distance_mm)
        results.append(measured)
        print(
            f"  pass {index}: ~{measured.rounded_dpi} CPI, "
            f"straightness {measured.straightness * 100:.1f}%"
        )
    return summarize_calibrations(results)


def _execute(adapter, target: int):
    context = TransactionContext(values={"target": int(target)})
    return TransactionEngine().run(
        learned_dpi_transaction_spec(),
        adapter,
        authorization=TransactionAuthorization(
            reversible_writes=True,
            reason=f"bounded numeric DPI generalization laboratory target {target}",
        ),
        context=context,
    )


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
    if not args.authorize_generalization_test:
        print("Refusing test without --authorize-generalization-test.", file=sys.stderr)
        return 2
    if args.distance_mm <= 0 or args.window <= 0 or args.passes <= 0:
        print("distance, window, and passes must be positive", file=sys.stderr)
        return 2

    mouse = None
    original_dpi: int | None = None
    adapter = None

    try:
        mouse = _pick(args.device)
        physical = build_device_graph(mouse)
        if physical.ambiguous:
            raise LearnedOperationError("physical identity is ambiguous")

        found = LearnedOperationStore().find_for_physical(
            physical, proven_only=True
        )
        if found is None:
            raise LearnedOperationError(
                "exactly one PROVEN learned DPI operation is required"
            )
        operation_path, operation = found
        validate_numeric_generalization(operation, args.baseline, args.candidates)
        node = matching_interface_node(operation, physical)

        print("OMUS — Unseen DPI Numeric Generalization")
        print("================================================")
        print(
            f"Device: {mouse.name} "
            f"[{(mouse.vendor or 0):04x}:{(mouse.product or 0):04x}]"
        )
        print(f"PROVEN learned operation: {operation_path}")
        print(
            f"Learned codec: {operation.write_field.codec.kind.value}, "
            f"offset {operation.write_field.offset}, width {operation.write_field.width}"
        )
        print("Teacher demonstration of candidate values: NONE")
        print(f"Demonstrated values: {', '.join(map(str, operation.demonstrated_values))}")
        print(f"Generated unseen candidates: {', '.join(map(str, args.candidates))}")
        print("Persisted runtime authority will NOT be modified by this test.")

        # First confirm the known baseline physically with the proven native path.
        native = NativeHidBackend()
        try:
            if not native.supports_device(mouse):
                raise LearnedOperationError("native baseline verifier could not bind")
            initial = native.get_dpi_state(mouse)
            if initial is None:
                raise LearnedOperationError("could not read original DPI")
            original_dpi = initial.x_dpi
            start = native.set_dpi(mouse, args.baseline)
            print(f"\nNative baseline register readback: {start.x_dpi} DPI")
            baseline_summary = _physical_measure(
                mouse,
                distance_mm=args.distance_mm,
                window=args.window,
                passes=1,
                label="Baseline physical sanity check",
            )
            baseline_deviation = (
                baseline_summary.estimated_dpi - args.baseline
            ) / args.baseline
            print(
                f"Baseline physical CPI: {baseline_summary.estimated_dpi:.1f} "
                f"({baseline_deviation * 100:+.1f}%)"
            )
            if abs(baseline_deviation) > 0.15:
                raise LearnedOperationError(
                    "known baseline register readback does not match physical CPI"
                )
        finally:
            native.close()

        # Expand only the in-memory object so its existing renderer can encode
        # candidate values. The persisted profile remains unchanged.
        ephemeral = replace(
            operation,
            demonstrated_values=tuple(
                sorted(set(operation.demonstrated_values).union(args.candidates))
            ),
        )
        adapter = LearnedHidAdapter(node.path, ephemeral)

        # Re-establish the proven baseline on the exact persistent learned session.
        baseline_context = _execute(adapter, args.baseline)
        if int(baseline_context.values["raw_readback"]) != args.baseline:
            raise LearnedOperationError("generic baseline readback failed")
        print(
            f"Generic persistent-session baseline established: {args.baseline} DPI"
        )

        successful = []
        for candidate in args.candidates:
            context = _execute(adapter, candidate)
            raw = int(context.values["raw_readback"])
            print(f"\nGenerated {candidate} -> generic readback {raw}")
            if raw != candidate:
                raise LearnedOperationError(
                    f"candidate {candidate} read back as {raw}"
                )

            summary = _physical_measure(
                mouse,
                distance_mm=args.distance_mm,
                window=args.window,
                passes=args.passes,
                label=f"Physical verification for unseen {candidate} DPI",
            )
            deviation = (summary.estimated_dpi - candidate) / candidate
            print(f"Median physical CPI: {summary.estimated_dpi:.1f}")
            print(f"Calibration confidence: {summary.confidence}")
            print(f"Deviation from generated target: {deviation * 100:+.1f}%")
            if abs(deviation) > 0.15:
                raise LearnedOperationError(
                    f"unseen target {candidate} differs physically by more than 15%"
                )
            if summary.confidence not in {"high", "medium"}:
                raise LearnedOperationError(
                    f"unseen target {candidate} has insufficient physical confidence"
                )
            successful.append(candidate)

        print("\nNUMERIC DPI GENERALIZATION SUCCESS")
        print("----------------------------------")
        print(
            "Discovery generated and physically proved values that were never "
            "demonstrated by the teacher."
        )
        print(f"Unseen values proved: {', '.join(map(str, successful))}")
        if len(successful) >= 2:
            step = min(
                abs(a - b)
                for i, a in enumerate(successful)
                for b in successful[i + 1 :]
                if a != b
            )
            print(f"Local unseen-value spacing proved: {step} DPI")
        print(
            "Profile remains unchanged; this is evidence for the next "
            "range/step promotion stage."
        )
        return 0

    except KeyboardInterrupt:
        print("\nGeneralization test cancelled.", file=sys.stderr)
        return 130
    except (
        LearnedOperationError,
        CalibrationError,
        TransactionError,
        OSError,
        PermissionError,
    ) as exc:
        print(f"Generalization test failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if adapter is not None:
            adapter.close()
        if mouse is not None and original_dpi is not None:
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
