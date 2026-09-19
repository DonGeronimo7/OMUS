"""Explicit physical promotion of a learned polling state machine.

The raw polling corpora remain non-authoritative. This command infers one
exact-model two-branch state machine, closes the native teacher, executes every
demonstrated rate through one persistent generic HID session, physically verifies
each resulting rate from evdev timing, restores the exact original polling/control
state, and only then persists PROVEN write authority.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys

from .device_profiles import get_profile_directory
from .device_topology import build_device_graph
from .discovery import get_mouse_devices, select_mouse_device
from .hardware.base import HardwareError
from .hardware.native_hid import NativeHidBackend
from .hidpp_driver import ONBOARD_MODE
from .learned_operations import StableDeviceIdentity, StableInterfaceIdentity
from .learned_polling import (
    LearnedPollingOperationError,
    LearnedPollingOperationStore,
    PollingControlState,
    infer_learned_polling_operation,
    promote_polling_operation,
)
from .polling_measurement import (
    PollingMeasurement,
    analyze_polling_timestamps,
    summarize_polling_measurements,
)
from .polling_replay import (
    GenericPollingReplayAdapter,
    PollingReplayError,
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


DEFAULT_PROMOTION_ORDER = (500, 250, 125, 1000)


def _parse_rates(value: str) -> tuple[int, ...]:
    try:
        rates = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("rates must be comma-separated integers") from exc
    if len(rates) < 2 or any(rate <= 0 for rate in rates):
        raise argparse.ArgumentTypeError("rates must contain at least two positive values")
    if len(set(rates)) != len(rates):
        raise argparse.ArgumentTypeError("rates must not contain duplicates")
    return rates


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mouse-control-polling-promote",
        description=(
            "Promote an exact-model learned polling state machine only after "
            "every demonstrated rate is generically written/read back, physically "
            "verified, and the original device state is restored."
        ),
    )
    parser.add_argument("--device", type=int, metavar="N")
    parser.add_argument(
        "--rates",
        type=_parse_rates,
        default=DEFAULT_PROMOTION_ORDER,
        metavar="HZ,...",
        help="promotion order; must cover the complete demonstrated rate set",
    )
    parser.add_argument("--baseline-rate", type=int, default=1000, metavar="HZ")
    parser.add_argument("--passes", type=int, default=3)
    parser.add_argument("--window", type=float, default=6.0)
    parser.add_argument(
        "--authorize-polling-promotion",
        action="store_true",
        help=(
            "required explicit authorization for the reversible, physically "
            "verified exact-model promotion sequence"
        ),
    )
    return parser


def _pick(index: int | None):
    mice = get_mouse_devices()
    if not mice:
        raise LearnedPollingOperationError("no mouse devices found")
    if index is None:
        return select_mouse_device(mice)
    if index < 1 or index > len(mice):
        raise LearnedPollingOperationError(
            f"--device must be between 1 and {len(mice)}"
        )
    return mice[index - 1]


def _corpus_path(physical, directory: str) -> Path:
    vendor = physical.vendor_id or 0
    product = physical.product_id or 0
    return (
        get_profile_directory()
        / directory
        / f"{vendor:04x}-{product:04x}-{physical.model_fingerprint[:16]}.json"
    )


def _validate_profile_identity(profile, physical, *, label: str) -> None:
    fingerprints = profile.get("fingerprints")
    identity = profile.get("identity")
    interface = profile.get("interface")
    if not isinstance(fingerprints, dict) or not isinstance(identity, dict):
        raise LearnedPollingOperationError(
            f"{label} corpus lacks stable device identity"
        )
    if not isinstance(interface, dict):
        raise LearnedPollingOperationError(
            f"{label} corpus lacks stable interface identity"
        )
    if fingerprints.get("model") != physical.model_fingerprint:
        raise LearnedPollingOperationError(
            f"{label} corpus model fingerprint does not match"
        )
    if (
        fingerprints.get("instance")
        and physical.instance_fingerprint
        and fingerprints.get("instance") != physical.instance_fingerprint
    ):
        raise LearnedPollingOperationError(
            f"{label} corpus instance fingerprint does not match"
        )
    for expected, actual, field in (
        (identity.get("bus"), physical.bus, "bus"),
        (identity.get("vendor_id"), physical.vendor_id, "vendor"),
        (identity.get("product_id"), physical.product_id, "product"),
    ):
        if expected is not None and actual is not None and expected != actual:
            raise LearnedPollingOperationError(
                f"{label} corpus {field} identity does not match"
            )


def _stable_node_key(node) -> tuple[object, ...]:
    return (
        node.bus,
        node.vendor_id,
        node.product_id,
        node.interface_number,
        node.descriptor_sha256,
    )


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


def _measure_target(mouse, target: int, *, passes: int, window: float):
    measurements = []
    for index in range(1, passes + 1):
        print(
            f"Pass {index}/{passes}: move rapidly and continuously "
            f"for {window:g} seconds."
        )
        input("Press Enter, then begin moving immediately... ")
        captured = capture_evdev_motion(
            mouse.path,
            seconds=window,
            exclusive=True,
        )
        measurement = analyze_polling_timestamps(_motion_timestamps(captured))
        measurements.append(measurement)
        _print_measurement(index, measurement)
    return summarize_polling_measurements(target, measurements)


def _require_summary(target: int, summary) -> None:
    if (
        summary.consensus_hz != target
        or summary.confidence not in {"high", "medium"}
    ):
        raise LearnedPollingOperationError(
            summary.rejection_reason
            or f"physical timing did not prove {target} Hz"
        )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _restore_original(mouse, *, original_rate: int, original_mode: int) -> dict[str, object]:
    backend = NativeHidBackend()
    try:
        if not backend.supports_device(mouse):
            raise LearnedPollingOperationError(
                "native restoration backend could not bind"
            )
        driver = backend._driver(mouse)
        backend.set_polling_rate(mouse, int(original_rate))
        if driver.get_control_mode() != int(original_mode):
            driver.set_control_mode(int(original_mode))
        restored_mode = int(driver.get_control_mode())
        restored_rate = int(driver.get_report_rate())
        success = (
            restored_mode == int(original_mode)
            and restored_rate == int(original_rate)
        )
        if not success:
            raise LearnedPollingOperationError(
                "restoration readback does not equal the recorded original state"
            )
        return {
            "success": True,
            "original_rate_hz": int(original_rate),
            "restored_rate_hz": restored_rate,
            "original_control_raw": int(original_mode),
            "restored_control_raw": restored_mode,
        }
    finally:
        backend.close()


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    rates = tuple(args.rates)

    if not args.authorize_polling_promotion:
        print(
            "Refusing promotion without --authorize-polling-promotion.",
            file=sys.stderr,
        )
        return 2
    if args.baseline_rate <= 0 or args.passes <= 0 or args.window <= 0:
        print(
            "--baseline-rate, --passes and --window must be positive",
            file=sys.stderr,
        )
        return 2

    mouse = None
    adapter: GenericPollingReplayAdapter | None = None
    original_rate: int | None = None
    original_mode: int | None = None
    rollback_complete = False

    try:
        mouse = _pick(args.device)
        if mouse is None:
            return 0
        physical = build_device_graph(mouse)
        if physical.ambiguous:
            raise LearnedPollingOperationError("physical identity is ambiguous")

        onboard_path = _corpus_path(physical, "polling-demonstrations")
        host_path = _corpus_path(physical, "polling-host-demonstrations")
        onboard_profile = load_polling_corpus(onboard_path)
        host_profile = load_polling_corpus(host_path)
        _validate_profile_identity(
            onboard_profile, physical, label="Onboard-start"
        )
        _validate_profile_identity(
            host_profile, physical, label="Host-start"
        )

        onboard_node = matching_interface_node(onboard_profile, physical)
        host_node = matching_interface_node(host_profile, physical)
        if _stable_node_key(onboard_node) != _stable_node_key(host_node):
            raise LearnedPollingOperationError(
                "Onboard and Host corpora resolve to different stable interfaces"
            )
        if onboard_node.path != host_node.path:
            raise LearnedPollingOperationError(
                "Onboard and Host corpora resolve to different live hidraw nodes"
            )

        identity = StableDeviceIdentity(
            bus=physical.bus,
            vendor_id=physical.vendor_id,
            product_id=physical.product_id,
            model_fingerprint=physical.model_fingerprint,
            instance_fingerprint=physical.instance_fingerprint,
        )
        interface = StableInterfaceIdentity(
            bus=onboard_node.bus,
            vendor_id=onboard_node.vendor_id,
            product_id=onboard_node.product_id,
            interface_number=onboard_node.interface_number,
            descriptor_sha256=onboard_node.descriptor_sha256,
        )
        operation = infer_learned_polling_operation(
            onboard_profile,
            host_profile,
            identity=identity,
            interface=interface,
        )

        if set(rates) != set(operation.demonstrated_rates):
            raise LearnedPollingOperationError(
                "--rates must cover every demonstrated polling rate exactly once; "
                f"demonstrated={operation.demonstrated_rates}, requested={rates}"
            )
        if args.baseline_rate not in operation.demonstrated_rates:
            raise LearnedPollingOperationError(
                "baseline rate must be part of the demonstrated polling set"
            )

        store = LearnedPollingOperationStore()
        existing = store.find_for_physical(physical, proven_only=True)
        if existing is not None:
            path, existing_operation = existing
            print(f"Polling operation is already PROVEN: {path}")
            print(
                "Authorized rates: "
                + ", ".join(map(str, existing_operation.demonstrated_rates))
            )
            return 0

        onboard_grammar = operation.replay_grammar(PollingControlState.ONBOARD)
        host_grammar = operation.replay_grammar(PollingControlState.HOST)

        print("OMUS — Polling State-Machine Promotion")
        print("================================================")
        print(
            f"Device: {mouse.name} "
            f"[{(mouse.vendor or 0):04x}:{(mouse.product or 0):04x}]"
        )
        print(f"Onboard corpus: {onboard_path}")
        print(f"Host corpus:    {host_path}")
        print(
            f"Exact interface: if#{onboard_node.interface_number}, "
            f"descriptor={onboard_node.descriptor_sha256}"
        )
        print(
            "Promotion rates: " + " -> ".join(f"{rate} Hz" for rate in rates)
        )
        print(
            "Authority before this run: NONE (teacher corpora remain write_authorized=false)"
        )
        print(
            "Boundary: every rate requires generic readback + independent physical "
            "timing; exact rollback must succeed before PROVEN is saved."
        )

        native = NativeHidBackend()
        try:
            if not native.supports_device(mouse):
                raise LearnedPollingOperationError(
                    "a proven native teacher is required to establish/restore "
                    "the first G305 production promotion boundary"
                )
            driver = native._driver(mouse)
            original_mode = int(driver.get_control_mode())
            original_rate = int(driver.get_report_rate())

            native.set_polling_rate(mouse, int(args.baseline_rate))
            if int(driver.get_report_rate()) != int(args.baseline_rate):
                raise LearnedPollingOperationError(
                    "could not establish the known baseline polling rate"
                )
            if int(driver.get_control_mode()) != ONBOARD_MODE:
                driver.set_control_mode(ONBOARD_MODE)
            established_mode = int(driver.get_control_mode())
            established_rate = int(driver.get_report_rate())
            if established_mode != ONBOARD_MODE:
                raise LearnedPollingOperationError(
                    "could not establish the demonstrated Onboard start state"
                )
            if established_rate != int(args.baseline_rate):
                raise LearnedPollingOperationError(
                    "baseline polling rate changed while establishing Onboard state"
                )
        finally:
            native.close()

        print(
            f"\nOriginal state recorded: {original_rate} Hz, "
            f"control raw 0x{original_mode:02x}"
        )
        print(
            f"Known start established: {args.baseline_rate} Hz / Onboard; "
            "native teacher CLOSED."
        )
        print("Opening ONE persistent generic raw HID session...")

        adapter = GenericPollingReplayAdapter(
            onboard_node.path,
            onboard_grammar,
        )
        rate_evidence: list[dict[str, object]] = []

        for index, target in enumerate(rates):
            state = (
                PollingControlState.ONBOARD
                if index == 0
                else PollingControlState.HOST
            )
            grammar = (
                onboard_grammar
                if state is PollingControlState.ONBOARD
                else host_grammar
            )
            if index:
                print(
                    "\nNative backend has NOT been reopened between generic writes."
                )
            print(
                f"\n[{index + 1}/{len(rates)}] Generic "
                f"{state.value}-start transition -> {target} Hz"
            )
            readback = adapter.execute_with_grammar(grammar, target)
            if readback != target:
                raise LearnedPollingOperationError(
                    f"generic polling readback requested {target} Hz, "
                    f"decoded {readback} Hz"
                )
            print(f"Generic raw readback: {readback} Hz")

            summary = _measure_target(
                mouse,
                target,
                passes=args.passes,
                window=args.window,
            )
            _require_summary(target, summary)
            print(
                f"Physical result: {summary.accepted_passes}/"
                f"{len(summary.passes)} accepted, {summary.confidence}, "
                f"median {summary.median_inferred_hz:.1f} Hz"
            )
            rate_evidence.append(
                {
                    "target_hz": int(target),
                    "branch": state.value,
                    "generic_readback_hz": int(readback),
                    "physical_consensus_hz": int(summary.consensus_hz),
                    "confidence": str(summary.confidence),
                    "accepted_passes": int(summary.accepted_passes),
                    "total_passes": len(summary.passes),
                    "median_inferred_hz": float(summary.median_inferred_hz),
                    "median_error_fraction": float(
                        summary.median_error_fraction or 0.0
                    ),
                }
            )

        # End generic ownership before reopening the proven native restorer.
        adapter.close()
        adapter = None

        rollback = _restore_original(
            mouse,
            original_rate=int(original_rate),
            original_mode=int(original_mode),
        )
        rollback_complete = True
        print(
            f"\nRollback verified: {rollback['restored_rate_hz']} Hz, "
            f"control raw 0x{int(rollback['restored_control_raw']):02x}"
        )

        promoted = promote_polling_operation(
            operation,
            rate_evidence=rate_evidence,
            rollback_evidence=rollback,
            state_evidence={
                "persistent_generic_session": True,
                "native_reopened_between_generic_writes": False,
                "first_branch": PollingControlState.ONBOARD.value,
                "subsequent_branch": PollingControlState.HOST.value,
                "baseline_rate_hz": int(args.baseline_rate),
                "corpus_sha256": {
                    "onboard": _sha256(onboard_path),
                    "host": _sha256(host_path),
                },
            },
        )
        destination = store.save(promoted)

        print("\nPOLLING PROMOTION SUCCESS")
        print("-------------------------")
        print("Status: PROVEN")
        print("Write authority: true")
        print("Scope: exact model + exact descriptor interface")
        print(
            "Authorized demonstrated rates: "
            + ", ".join(map(str, promoted.demonstrated_rates))
        )
        print("Both Onboard-start and Host-start branches are persisted.")
        print("All authorized rates were independently physically verified.")
        print(f"Saved: {destination}")
        return 0

    except KeyboardInterrupt:
        print("\nPolling promotion cancelled.", file=sys.stderr)
        return 130
    except (
        LearnedPollingOperationError,
        PollingReplayError,
        HardwareError,
        OSError,
        PermissionError,
    ) as exc:
        print(f"Polling promotion failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if adapter is not None:
            try:
                adapter.close()
            except Exception:
                pass
        if (
            mouse is not None
            and not rollback_complete
            and original_rate is not None
            and original_mode is not None
        ):
            try:
                rollback = _restore_original(
                    mouse,
                    original_rate=original_rate,
                    original_mode=original_mode,
                )
                print(
                    f"\nEmergency rollback verified: "
                    f"{rollback['restored_rate_hz']} Hz, "
                    f"control raw 0x{int(rollback['restored_control_raw']):02x}"
                )
            except Exception as exc:
                print(
                    "\nWARNING: exact polling/control rollback failed: "
                    f"{exc}",
                    file=sys.stderr,
                )


if __name__ == "__main__":
    raise SystemExit(main())
