# SPDX-License-Identifier: AGPL-3.0-or-later
"""Acceptance CLI for physically calibrated, teacher-free DPI-state discovery."""

from __future__ import annotations

import argparse
import os
import sys

from .calibrated_discovery import (
    CalibratedDpiState,
    calibrated_cycle_hypothesis,
    capture_calibrated_motion,
    infer_calibrated_raw_mappings,
)
from .calibrated_profiles import (
    CalibratedProfileError,
    calibrated_profile_data,
    save_calibrated_profile,
)
from .contrastive_inference import refine_teacher_free
from .device_topology import TopologyError
from .discovery import get_mouse_devices, select_mouse_device
from .discovery_engine import DiscoveryEngine
from .learning_session import ReadOnlyLearningSession
from .protocol_grammar import SemanticBehavior
from .sensor_calibration import CalibrationError, measure_sensor_state_auto
from .sensor_calibration_cli import _evaluate, _polling_label


_DEFAULT_MAX_ADAPTIVE_PASSES = 5


def _dpi_values(value: str) -> tuple[int, ...]:
    try:
        result = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("DPI values must be comma-separated integers") from exc
    if len(result) < 2:
        raise argparse.ArgumentTypeError("provide at least two DPI stages")
    if any(item <= 0 for item in result):
        raise argparse.ArgumentTypeError("DPI values must be greater than zero")
    if len(set(result)) != len(result):
        raise argparse.ArgumentTypeError("DPI stage labels must be unique")
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mouse-control-discover-dpi-states",
        description=(
            "Teacher-free DPI-state discovery using physical CPI/polling calibration plus "
            "simultaneous read-only hidraw observation. Unknown HID writes are forbidden."
        ),
    )
    parser.add_argument("--device", type=int, metavar="N")
    parser.add_argument(
        "--dpi-values",
        type=_dpi_values,
        required=True,
        metavar="DPI,...",
        help=(
            "configured DPI cycle in physical-button order, starting with the current stage; "
            "example: 800,1500,2000,2500,3000"
        ),
    )
    parser.add_argument(
        "--distance-mm",
        type=float,
        default=254.0,
        metavar="MM",
        help="physical ruler travel per calibration pass (default: 254 mm / 10 inches)",
    )
    parser.add_argument(
        "--window",
        type=float,
        default=10.0,
        metavar="SECONDS",
        help="maximum capture window for each ruler pass (default: 10 seconds)",
    )
    parser.add_argument(
        "--passes",
        type=int,
        default=3,
        metavar="N",
        help="minimum ruler passes per DPI state (default: 3; adaptive retry may add two)",
    )
    parser.add_argument(
        "--learn-window",
        type=float,
        default=1.5,
        metavar="SECONDS",
        help="capture window for each single DPI-button transition (default: 1.5 seconds)",
    )
    parser.add_argument(
        "--full-access",
        action="store_true",
        help="require every correlated hidraw sibling to remain readable throughout learning",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="do not persist the path-independent calibrated read-only profile",
    )
    return parser


def _pick_mouse(index: int | None):
    mice = get_mouse_devices()
    if not mice:
        print("No mouse devices found. Check input permissions.", file=sys.stderr)
        return None, 1
    if index is None:
        return select_mouse_device(mice), 0
    if index < 1 or index > len(mice):
        print(f"--device must be between 1 and {len(mice)}", file=sys.stderr)
        return None, 2
    return mice[index - 1], 0


def _check_access(sample, *, require_complete_access: bool) -> None:
    if require_complete_access and sample.unreadable_hidraw_paths:
        raise PermissionError(
            "a correlated hidraw sibling became unavailable during full-access learning: "
            + ", ".join(sample.unreadable_hidraw_paths)
        )


def _calibrate_state(
    session: ReadOnlyLearningSession,
    *,
    evdev_path: str,
    configured_dpi: int,
    distance_mm: float,
    seconds: float,
    minimum_passes: int,
    require_complete_access: bool,
):
    """Calibrate one unchanged DPI state while collecting ordinary-motion HID controls."""

    results = []
    motion_samples = []
    max_passes = max(minimum_passes, _DEFAULT_MAX_ADAPTIVE_PASSES)

    while len(results) < max_passes:
        if len(results) >= minimum_passes:
            evaluation = _evaluate(results)
            if evaluation[-1] == "high":
                break
            print(
                "  confidence is not yet high; collecting one additional ruler pass "
                "before accepting this state"
            )

        pass_index = len(results) + 1
        input(
            f"  CPI pass {pass_index}: position at the ruler start, press Enter, then move "
            f"exactly {distance_mm:g} mm in one straight direction... "
        )
        capture = capture_calibrated_motion(
            session,
            evdev_path=evdev_path,
            seconds=seconds,
        )
        _check_access(capture.sample, require_complete_access=require_complete_access)
        measured = measure_sensor_state_auto(
            capture.calibration_events,
            distance_mm=distance_mm,
        )
        results.append(measured)
        motion_samples.append(capture.sample)
        print(
            f"    ~{measured.rounded_dpi} measured CPI, {_polling_label(measured)}, "
            f"straightness {measured.straightness * 100:.1f}%"
        )
        if measured.segment_count > 1:
            print(
                f"    isolated strongest motion segment from {measured.segment_count} observed segments"
            )

    (
        _used,
        rejected,
        summary,
        polling_rate,
        polling_matches,
        polling_confidence,
        _worst,
        _cpi_range,
        cpi_confidence,
        overall_confidence,
    ) = _evaluate(results)

    deviation = (summary.estimated_dpi - configured_dpi) / configured_dpi
    print(
        f"  accepted state: configured {configured_dpi} DPI -> measured "
        f"{summary.estimated_dpi:.1f} CPI ({deviation * 100:+.1f}%), "
        f"polling ~{polling_rate if polling_rate is not None else '?'} Hz, "
        f"confidence {overall_confidence}"
    )
    if rejected:
        print(f"  adaptive retry rejected {len(rejected)} clearly inconsistent physical pass(es)")
    if polling_rate is not None:
        print(
            f"  polling agreement: {polling_matches}/{len(results)} passes at "
            f"~{polling_rate} Hz ({polling_confidence})"
        )

    return (
        CalibratedDpiState(
            configured_dpi=configured_dpi,
            measured_cpi=summary.estimated_dpi,
            polling_hz=polling_rate,
            confidence=overall_confidence,
        ),
        tuple(motion_samples),
        cpi_confidence,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.distance_mm <= 0 or args.window <= 0 or args.passes <= 0 or args.learn_window <= 0:
        print("distance, capture windows, and passes must be greater than zero", file=sys.stderr)
        return 2
    if args.full_access and os.geteuid() != 0:
        print(
            "Full-access calibrated discovery requires root for complete hidraw visibility. "
            "Root increases evidence visibility only; unknown HID writes remain forbidden.",
            file=sys.stderr,
        )
        return 77

    selected, status = _pick_mouse(args.device)
    if selected is None:
        return status

    print("OMUS — Physically Calibrated DPI Discovery")
    print("===================================================")
    print(f"Device: {selected.name} [{(selected.vendor or 0):04x}:{(selected.product or 0):04x}]")
    print("Native protocol teacher: OFF")
    print("Unknown HID writes: FORBIDDEN")
    print(f"Configured cycle: {', '.join(str(value) for value in args.dpi_values)} DPI")
    print(
        "Each ruler pass captures physical evdev motion and every readable correlated hidraw "
        "stream simultaneously. DPI-button transitions are captured separately with the mouse still."
    )

    profile_path = None
    engine = DiscoveryEngine(detectors=(), save_profiles=False)
    try:
        result = engine.discover(selected, force=True)
        session = ReadOnlyLearningSession(result.device, engine.descriptors)
        readable, unreadable = session.hidraw_access_report()
        if args.full_access and unreadable:
            raise PermissionError(
                "full-access learning requires every correlated hidraw sibling to be readable; "
                "unavailable: " + ", ".join(unreadable)
            )
        print(
            f"Read-only HID visibility: {len(readable)}/{len(result.device.hidraw_nodes)} "
            "correlated hidraw sibling(s) readable"
        )

        first_dpi = args.dpi_values[0]
        input(
            f"\nSet the mouse to the first configured stage ({first_dpi} DPI), keep the normal "
            "onboard/native mode unchanged, then press Enter... "
        )

        initial_state, initial_controls, _initial_cpi_confidence = _calibrate_state(
            session,
            evdev_path=selected.path,
            configured_dpi=first_dpi,
            distance_mm=args.distance_mm,
            seconds=args.window,
            minimum_passes=args.passes,
            require_complete_access=args.full_access,
        )

        transition_samples = []
        resulting_states = []
        motion_controls = list(initial_controls)
        measured_cycle = [initial_state]

        for index in range(len(args.dpi_values)):
            target_dpi = args.dpi_values[(index + 1) % len(args.dpi_values)]
            input(
                f"\nTransition {index + 1}/{len(args.dpi_values)}: press Enter, then press the "
                f"physical DPI button exactly once to enter the {target_dpi} DPI stage "
                f"within {args.learn_window:g}s... "
            )
            transition = session.observe_action(seconds=args.learn_window)
            _check_access(transition, require_complete_access=args.full_access)
            transition_samples.append(transition)
            print(
                f"  transition captured {len(transition.action.hid_reports)} HID report(s), "
                f"{len(transition.action.evdev_events)} evdev event(s), "
                f"{len(transition.action.feature_changes)} Feature byte change(s)"
            )

            state, controls, _cpi_confidence = _calibrate_state(
                session,
                evdev_path=selected.path,
                configured_dpi=target_dpi,
                distance_mm=args.distance_mm,
                seconds=args.window,
                minimum_passes=args.passes,
                require_complete_access=args.full_access,
            )
            resulting_states.append(state)
            measured_cycle.append(state)
            motion_controls.extend(controls)

        learned = session.analyze(
            transition_samples,
            trigger_behavior=SemanticBehavior.DPI_CYCLE_TRIGGER,
            control_samples=motion_controls,
        )
        refinement = refine_teacher_free(learned)
        action_specific_keys = frozenset(shape.report_key for shape in refinement.report_shapes)
        descriptor_roles = {
            (candidate.report_key, candidate.offset): session.descriptor_roles_for_candidate(candidate)
            for candidate in learned.report_candidates
        }
        mappings = (
            infer_calibrated_raw_mappings(
                transition_samples,
                resulting_states,
                allowed_report_keys=set(action_specific_keys),
                descriptor_roles=descriptor_roles,
            )
            if action_specific_keys
            else ()
        )
        cycle_hypothesis = calibrated_cycle_hypothesis(resulting_states)

        if (
            not args.no_save
            and mappings
            and cycle_hypothesis is not None
            and cycle_hypothesis.confidence == "validated"
        ):
            profile = calibrated_profile_data(
                device=result.device,
                configured_cycle=args.dpi_values,
                measured_cycle=measured_cycle,
                mappings=mappings,
                action_report_keys=action_specific_keys,
            )
            profile_path = save_calibrated_profile(profile)

    except KeyboardInterrupt:
        print("\nCalibrated discovery cancelled.", file=sys.stderr)
        return 130
    except TopologyError as exc:
        print(f"Could not correlate the physical mouse: {exc}", file=sys.stderr)
        return 1
    except (CalibrationError, OSError, PermissionError, ValueError, CalibratedProfileError) as exc:
        print(f"Calibrated discovery failed: {exc}", file=sys.stderr)
        return 1

    print("\nCalibrated DPI-state evidence")
    print("=============================")
    for index, state in enumerate(measured_cycle):
        suffix = " (wrap confirmation)" if index == len(measured_cycle) - 1 else ""
        print(
            f"  configured {state.configured_dpi:5d} DPI -> measured {state.measured_cpi:7.1f} CPI; "
            f"polling ~{state.polling_hz if state.polling_hz is not None else '?'} Hz; "
            f"confidence {state.confidence}{suffix}"
        )

    if cycle_hypothesis is not None:
        print(
            f"\nSemantic DPI-cycle evidence: {cycle_hypothesis.confidence} — "
            f"{cycle_hypothesis.reason}"
        )

    state_keys = {mapping.report_key for mapping in mappings}
    print(f"Action-specific report shapes absent from ruler-motion controls: {len(action_specific_keys)}")
    for shape in refinement.report_shapes:
        role = "state-bearing" if shape.report_key in state_keys else "transition-only"
        print(
            f"  [{role}] report={shape.report_key!r} guided_counts={shape.guided_counts!r} "
            f"control_counts={shape.control_counts!r}"
        )

    if mappings:
        print("\nCalibrated raw-state correlations:")
        for mapping in mappings:
            print(
                f"  correlated report={mapping.report_key!r} byte={mapping.offset} "
                f"descriptor={','.join(mapping.descriptor_roles)}"
            )
            print(f"    raw -> configured DPI: {dict(mapping.configured_mapping)}")
            print(f"    raw -> measured CPI:   {dict(mapping.measured_cpi_mapping)}")
    else:
        print(
            "\nCalibrated raw-state correlations: none yet — physical DPI changes were measured, "
            "but no persistent raw field was both repeated across the full cycle and isolated "
            "to an action-specific report shape."
        )

    if profile_path is not None:
        print(f"\nSaved calibrated read-only profile: {profile_path}")
        print("Profile write authority: false")

    print(
        "\nWrite status: FORBIDDEN — calibrated discovery validates read-side behavior and "
        "correlations only. No raw field, codec, or packet observed here authorizes SET-DPI."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
