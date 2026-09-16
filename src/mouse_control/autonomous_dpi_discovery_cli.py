"""Teacher-free physical DPI-cycle discovery for genuinely unknown mice.

The mouse teaches Mouse Control its DPI states. No advertised/configured DPI
list and no native protocol teacher is required. Each state is independently
measured from physical travel while correlated HID streams are observed
read-only. The cycle ends only after a later physical state returns to the
starting CPI within the accepted calibration tolerance.

This module creates read-side evidence only. It never sends an unknown HID
write and can never authorize one.
"""

from __future__ import annotations

import argparse
import os
import sys

from .calibrated_discovery import (
    CalibratedDpiState,
    capture_calibrated_motion,
    infer_calibrated_raw_mappings,
)
from .calibrated_discovery_cli import _check_access
from .calibrated_profiles import calibrated_profile_data, save_calibrated_profile
from .contrastive_inference import refine_teacher_free
from .device_topology import TopologyError
from .discovery import get_mouse_devices, select_mouse_device
from .discovery_engine import DiscoveryEngine
from .learning_session import ReadOnlyLearningSession
from .protocol_grammar import SemanticBehavior
from .sensor_calibration import CalibrationError, measure_sensor_state_auto
from .sensor_calibration_cli import _evaluate, _polling_label


_DEFAULT_MAX_ADAPTIVE_PASSES = 5


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mouse-control-discover-dpi-cycle",
        description=(
            "Discover an unknown mouse's physical DPI cycle without configured DPI labels, "
            "a native teacher, or HID writes."
        ),
    )
    parser.add_argument("--device", type=int, metavar="N")
    parser.add_argument("--distance-mm", type=float, default=254.0, metavar="MM")
    parser.add_argument("--window", type=float, default=10.0, metavar="SECONDS")
    parser.add_argument("--passes", type=int, default=3, metavar="N")
    parser.add_argument("--learn-window", type=float, default=1.5, metavar="SECONDS")
    parser.add_argument("--max-states", type=int, default=12, metavar="N")
    parser.add_argument("--wrap-tolerance", type=float, default=0.15, metavar="FRACTION")
    parser.add_argument("--full-access", action="store_true")
    parser.add_argument("--no-save", action="store_true")
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


def _same_physical_state(left: float, right: float, tolerance: float) -> bool:
    scale = max(abs(left), abs(right), 1.0)
    return abs(left - right) / scale <= tolerance


def _calibrate_unlabelled_state(
    session: ReadOnlyLearningSession,
    *,
    evdev_path: str,
    distance_mm: float,
    seconds: float,
    minimum_passes: int,
    require_complete_access: bool,
):
    results = []
    motion_samples = []
    max_passes = max(minimum_passes, _DEFAULT_MAX_ADAPTIVE_PASSES)

    while len(results) < max_passes:
        if len(results) >= minimum_passes:
            evaluation = _evaluate(results)
            if evaluation[-1] == "high":
                break
            print("  confidence is not yet high; collecting one additional ruler pass")

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

    (
        _used,
        rejected,
        summary,
        polling_rate,
        polling_matches,
        polling_confidence,
        _worst,
        _cpi_range,
        _cpi_confidence,
        overall_confidence,
    ) = _evaluate(results)

    semantic_dpi = max(1, int(round(summary.estimated_dpi)))
    state = CalibratedDpiState(
        configured_dpi=semantic_dpi,
        measured_cpi=summary.estimated_dpi,
        polling_hz=polling_rate,
        confidence=overall_confidence,
    )
    print(
        f"  accepted physical state: ~{summary.estimated_dpi:.1f} CPI "
        f"(semantic label {semantic_dpi}), polling "
        f"~{polling_rate if polling_rate is not None else '?'} Hz, "
        f"confidence {overall_confidence}"
    )
    if rejected:
        print(f"  rejected {len(rejected)} inconsistent physical pass(es)")
    if polling_rate is not None:
        print(
            f"  polling agreement: {polling_matches}/{len(results)} passes at "
            f"~{polling_rate} Hz ({polling_confidence})"
        )
    return state, tuple(motion_samples)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if (
        args.distance_mm <= 0
        or args.window <= 0
        or args.passes <= 0
        or args.learn_window <= 0
        or args.max_states < 2
        or not 0 < args.wrap_tolerance <= 0.30
    ):
        print("invalid distance/window/passes/state/tolerance arguments", file=sys.stderr)
        return 2
    if args.full_access and os.geteuid() != 0:
        print(
            "Full-access discovery requires root for complete hidraw visibility. "
            "Root increases evidence visibility only; unknown HID writes remain forbidden.",
            file=sys.stderr,
        )
        return 77

    selected, status = _pick_mouse(args.device)
    if selected is None:
        return status

    print("Mouse Control — Autonomous Physical DPI-Cycle Discovery")
    print("=======================================================")
    print(f"Device: {selected.name} [{(selected.vendor or 0):04x}:{(selected.product or 0):04x}]")
    print("Configured/advertised DPI labels: NOT USED")
    print("Native protocol teacher: OFF")
    print("Unknown HID writes: FORBIDDEN")
    print(
        "Mouse Control will measure the current CPI, then repeatedly observe one physical "
        "DPI-button transition and re-measure CPI until the cycle returns to its start."
    )

    profile_path = None
    engine = DiscoveryEngine(detectors=(), save_profiles=False)
    try:
        result = engine.discover(selected)
        if result.device.ambiguous:
            raise TopologyError("physical identity is ambiguous")
        session = ReadOnlyLearningSession(result.device, engine.descriptors)
        readable, unreadable = session.hidraw_access_report()
        if args.full_access and unreadable:
            raise PermissionError(
                "full-access learning requires every correlated hidraw sibling to be readable: "
                + ", ".join(unreadable)
            )
        print(
            f"Read-only HID visibility: {len(readable)}/{len(result.device.hidraw_nodes)} "
            "correlated hidraw sibling(s) readable"
        )

        input("\nLeave the mouse at its current DPI state and press Enter to calibrate it... ")
        initial_state, initial_controls = _calibrate_unlabelled_state(
            session,
            evdev_path=selected.path,
            distance_mm=args.distance_mm,
            seconds=args.window,
            minimum_passes=args.passes,
            require_complete_access=args.full_access,
        )

        transition_samples = []
        resulting_states = []
        measured_cycle = [initial_state]
        motion_controls = list(initial_controls)
        distinct_states = [initial_state]
        wrap_confirmed = False

        for index in range(1, args.max_states + 1):
            input(
                f"\nTransition {index}: press Enter, then press the physical DPI button "
                f"exactly once within {args.learn_window:g}s... "
            )
            transition = session.observe_action(seconds=args.learn_window)
            _check_access(transition, require_complete_access=args.full_access)
            transition_samples.append(transition)
            print(
                f"  captured {len(transition.action.hid_reports)} HID report(s), "
                f"{len(transition.action.feature_changes)} Feature byte change(s)"
            )

            state, controls = _calibrate_unlabelled_state(
                session,
                evdev_path=selected.path,
                distance_mm=args.distance_mm,
                seconds=args.window,
                minimum_passes=args.passes,
                require_complete_access=args.full_access,
            )
            motion_controls.extend(controls)

            if len(distinct_states) >= 2 and _same_physical_state(
                state.measured_cpi,
                initial_state.measured_cpi,
                args.wrap_tolerance,
            ):
                # Preserve the exact semantic identity of the starting state so
                # the persisted profile can explicitly prove wrap-around while
                # retaining the newly measured CPI as independent evidence.
                state = CalibratedDpiState(
                    configured_dpi=initial_state.configured_dpi,
                    measured_cpi=state.measured_cpi,
                    polling_hz=state.polling_hz,
                    confidence=state.confidence,
                )
                resulting_states.append(state)
                measured_cycle.append(state)
                wrap_confirmed = True
                print(
                    f"  cycle wrap detected: physical CPI returned to the starting "
                    f"~{initial_state.measured_cpi:.1f} CPI state"
                )
                break

            duplicate = next(
                (
                    previous
                    for previous in distinct_states
                    if _same_physical_state(
                        state.measured_cpi, previous.measured_cpi, args.wrap_tolerance
                    )
                ),
                None,
            )
            if duplicate is not None:
                raise CalibrationError(
                    "a previously observed non-start DPI state repeated before wrap; "
                    "repeat the run and press the DPI button exactly once per transition"
                )

            distinct_states.append(state)
            resulting_states.append(state)
            measured_cycle.append(state)

        if not wrap_confirmed:
            raise CalibrationError(
                f"DPI cycle did not return to its starting physical state within {args.max_states} transitions"
            )

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

        configured_cycle = tuple(state.configured_dpi for state in distinct_states)
        if not args.no_save and mappings:
            profile = calibrated_profile_data(
                device=result.device,
                configured_cycle=configured_cycle,
                measured_cycle=measured_cycle,
                mappings=mappings,
                action_report_keys=action_specific_keys,
            )
            profile_path = save_calibrated_profile(profile)

    except KeyboardInterrupt:
        print("\nAutonomous DPI discovery cancelled.", file=sys.stderr)
        return 130
    except (TopologyError, CalibrationError, OSError, PermissionError, ValueError) as exc:
        print(f"Autonomous DPI discovery failed: {exc}", file=sys.stderr)
        return 1

    print("\nDiscovered physical DPI cycle")
    print("=============================")
    for index, state in enumerate(distinct_states, 1):
        print(
            f"  state {index}: ~{state.measured_cpi:.1f} CPI "
            f"(learned semantic {state.configured_dpi}), "
            f"polling ~{state.polling_hz if state.polling_hz is not None else '?'} Hz, "
            f"confidence {state.confidence}"
        )
    print("  wrap: CONFIRMED by independent physical CPI measurement")

    if mappings:
        print("\nCalibrated raw-state correlations:")
        for mapping in mappings:
            print(
                f"  report={mapping.report_key!r} byte={mapping.offset} "
                f"raw->physical DPI={dict(mapping.configured_mapping)}"
            )
    else:
        print(
            "\nNo unique persistent raw state field was isolated. The physical cycle is "
            "still valid evidence, but read-side HID semantics remain unresolved."
        )

    if profile_path is not None:
        print(f"\nSaved calibrated read-only profile: {profile_path}")
        print("Profile write authority: false")

    print("\nWrite status: FORBIDDEN — no unknown HID write was sent or authorized.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
