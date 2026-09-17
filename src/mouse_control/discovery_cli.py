"""Dedicated CLI for automatic-hardware-discovery acceptance and learning.

Keeping this command separate from the normal setup/runtime path lets us test
real hardware without silently changing the behavior of ``mouse-control run``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .contrastive_inference import refine_teacher_free
from .device_topology import TopologyError
from .discovery import get_mouse_devices, select_mouse_device
from .discovery_engine import DiscoveryEngine
from .discovery_ui import render_discovery_result, result_to_dict
from .guided_discovery import (
    _full_access_preflight,
    run_guided_dpi_learning,
)
from .learning_session import ReadOnlyLearningSession
from .community_report import build_community_report, render_community_report
from . import __version__


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mouse-control-discover",
        description=(
            "Safety-first automatic mouse hardware discovery. Known protocol "
            "queries are validated; unknown HID inspection remains read-only."
        ),
    )
    parser.add_argument(
        "--device", type=int, metavar="N",
        help="select mouse N from the detected list instead of prompting",
    )
    parser.add_argument("--verbose", action="store_true", help="show discovery evidence")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument(
        "--community-report", metavar="FILE",
        help="write a deterministic privacy-conscious report suitable for an issue",
    )
    parser.add_argument(
        "--no-save", action="store_true",
        help="do not cache the path-independent discovery profile",
    )
    parser.add_argument(
        "--generic-only", action="store_true",
        help=(
            "skip known protocol detectors and exercise only topology, descriptor, "
            "repertoire and read-only learning paths"
        ),
    )
    parser.add_argument(
        "--full-access", action="store_true",
        help=(
            "require root hardware visibility and a complete passive-open preflight "
            "for every hidraw sibling correlated to the selected physical mouse; "
            "unknown HID writes remain forbidden"
        ),
    )
    parser.add_argument(
        "--learn-dpi-button", action="store_true",
        help=(
            "capture two negative controls plus three read-only DPI-button actions and "
            "infer action-specific report shapes, persistent state and momentary fields"
        ),
    )
    parser.add_argument(
        "--teacher", action="store_true",
        help=(
            "also read semantic ground truth before and after each guided action from a "
            "native protocol teacher such as HID++; packet details are not shared"
        ),
    )
    parser.add_argument(
        "--learn-window", type=float, default=1.5, metavar="SECONDS",
        help="capture window for each control/action sample (default: 1.5)",
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


def _render_guided_learning(learned) -> str:
    teacher_transitions = [
        {"before": dict(sample.teacher_before_state), "after": dict(sample.teacher_state)}
        for sample in learned.samples
        if sample.teacher_before_state or sample.teacher_state
    ]
    refinement = None if teacher_transitions else refine_teacher_free(learned)
    action_specific = (
        tuple(item.candidate for item in refinement.candidates)
        if refinement is not None
        else learned.discriminative_trigger_candidates
    )
    report_shapes = refinement.report_shapes if refinement is not None else ()
    refined_by_location = (
        {(item.candidate.report_key, item.candidate.offset): item for item in refinement.candidates}
        if refinement is not None else {}
    )
    hypotheses = refinement.hypotheses if refinement is not None else learned.hypotheses

    lines = [
        "", "Guided DPI-button learning", "==========================",
        f"Guided samples: {len(learned.samples)}",
        f"Negative-control samples: {len(learned.control_samples)}",
        f"Feature-field candidates: {len(learned.feature_candidates)}",
        f"Persistent raw-state candidates: {len(learned.report_candidates)}",
        f"Raw trigger candidates before controls: {len(learned.trigger_candidates)}",
        f"Raw trigger locations seen in controls: {len(learned.control_trigger_candidates)}",
        f"Action-specific report shapes: {len(report_shapes)}",
        f"Transition-specific raw-trigger candidates: {len(action_specific)}",
    ]
    if refinement is not None and refinement.suppressed_stage_locations:
        lines.append(
            "Control-active stage guesses suppressed: "
            f"{len(refinement.suppressed_stage_locations)}"
        )
    if report_shapes:
        lines.append("Action-specific report-shape evidence:")
        for shape in report_shapes:
            lines.append(
                f"  report={shape.report_key!r} guided_counts={shape.guided_counts!r} "
                f"control_counts={shape.control_counts!r}"
            )
        shape_keys = {shape.report_key for shape in report_shapes}
        associated_state = tuple(
            candidate for candidate in learned.report_candidates
            if candidate.report_key in shape_keys
        )
        if associated_state:
            lines.append("State fields carried by action-specific reports:")
            for candidate in associated_state:
                lines.append(
                    f"  report={candidate.report_key!r} byte={candidate.offset} "
                    f"observations={candidate.observations} values={candidate.values!r}"
                )
    if action_specific:
        lines.append("Action-specific raw transition evidence:")
        for candidate in action_specific:
            roles = learned.descriptor_roles.get(
                (candidate.report_key, candidate.offset), ("unknown",)
            )
            suffix = ""
            refined = refined_by_location.get((candidate.report_key, candidate.offset))
            if refined is not None:
                suffix = f" distinctive_transitions={refined.distinctive_transitions!r}"
            lines.append(
                f"  report={candidate.report_key!r} byte={candidate.offset} "
                f"observations={candidate.observations} descriptor={','.join(roles)}{suffix}"
            )
    if hypotheses:
        lines.append("Semantic hypotheses:")
        for hypothesis in hypotheses:
            location = (
                f" report={hypothesis.report_key!r}"
                + (f" byte={hypothesis.offset}" if hypothesis.offset is not None else "")
                if hypothesis.report_key is not None else ""
            )
            mapping = f" mapping={dict(hypothesis.mapping)}" if hypothesis.mapping else ""
            lines.append(
                f"  {hypothesis.confidence:10} {hypothesis.behavior.value}{location}{mapping}"
            )
            lines.append(f"               {hypothesis.reason}")
    else:
        lines.append(
            "Semantic hypotheses: none yet — no action-specific repeatable evidence was found."
        )
    if teacher_transitions:
        lines.append(f"Teacher transitions: {teacher_transitions}")
    else:
        lines.append("Teacher: unavailable/not requested — inference used Linux HID evidence only.")
    lines.append("Write status: forbidden — guided learning produces observations/correlations only.")
    return "\n".join(lines)


def _run_guided_learning(
    selected, result, engine, *, seconds: float, teacher: bool,
    require_complete_access: bool,
) -> None:
    print(
        "\nGuided learner is read-only. Native/onboard control is preserved. It will watch "
        "every readable correlated evdev/hidraw interface while you press the physical "
        "DPI button exactly once per sample."
    )
    if not teacher:
        print(
            "Native teacher is OFF. Inference uses Linux hidraw/evdev observations, "
            "HID descriptors, repeated transition signatures, and negative controls."
        )

    def prompt(step) -> bool:
        input(
            f"[{step.index}/5] {step.title}: {step.instructions} "
            f"Press Enter to capture {seconds:g}s... "
        )
        return True

    outcome = run_guided_dpi_learning(
        selected, result, engine,
        prompt=prompt,
        progress=lambda message: print("  " + message),
        seconds=seconds,
        teacher=teacher,
        require_complete_access=require_complete_access,
    )
    print(_render_guided_learning(outcome.learned))


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.learn_window <= 0:
        parser.error("--learn-window must be greater than zero")
    if args.json and args.learn_dpi_button:
        parser.error("--json cannot be combined with interactive --learn-dpi-button")
    if args.teacher and not args.learn_dpi_button:
        parser.error("--teacher requires --learn-dpi-button")
    if args.full_access and os.geteuid() != 0:
        print(
            "Full-access discovery requires root so every correlated mouse hidraw "
            "interface can be inspected. Re-run this same discovery command with sudo. "
            "Root visibility does not authorize unknown HID writes.",
            file=sys.stderr,
        )
        return 77

    selected, status = _pick_mouse(args.device)
    if selected is None:
        return status

    if not args.json:
        mode = (
            "Known protocol detectors are disabled; unknown HID remains read-only and native control is preserved."
            if args.generic_only
            else "Unknown HID is read-only and the normal mouse-control runtime is not being reconfigured."
        )
        if args.full_access:
            mode += " Root/full-evidence acquisition is required for all correlated HID siblings."
        print(f"Discovery test mode: {mode}\n")

    engine = DiscoveryEngine(
        detectors=() if args.generic_only else None,
        save_profiles=not args.no_save,
    )
    try:
        result = engine.discover(selected)
        if args.full_access:
            access_session = ReadOnlyLearningSession(result.device, engine.descriptors)
            readable = _full_access_preflight(access_session)
            if not args.json:
                print(
                    f"Full-access acquisition: {len(readable)}/{len(result.device.hidraw_nodes)} "
                    "correlated hidraw sibling(s) readable.\n"
                )
    except TopologyError as exc:
        print(f"Discovery could not correlate the physical mouse: {exc}", file=sys.stderr)
        return 1
    except PermissionError as exc:
        print(f"Discovery permission denied: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Discovery hardware error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nDiscovery cancelled.", file=sys.stderr)
        return 130

    if args.json:
        print(json.dumps(result_to_dict(result, profile_path=engine.profile_path), indent=2, sort_keys=True))
    else:
        print(render_discovery_result(result, profile_path=engine.profile_path, verbose=args.verbose))

    if args.community_report:
        report_text = render_community_report(
            build_community_report(result, version=__version__)
        )
        try:
            with open(args.community_report, "x", encoding="utf-8") as handle:
                handle.write(report_text)
        except FileExistsError:
            print("Community report destination already exists; refusing to overwrite it.", file=sys.stderr)
            return 1
        except OSError as exc:
            print(f"Could not write community report: {exc}", file=sys.stderr)
            return 1
        if not args.json:
            print(f"\nCommunity discovery report saved: {args.community_report}")

    if args.learn_dpi_button:
        try:
            _run_guided_learning(
                selected, result, engine,
                seconds=args.learn_window,
                teacher=args.teacher,
                require_complete_access=args.full_access,
            )
        except KeyboardInterrupt:
            print("\nGuided learning cancelled.", file=sys.stderr)
            return 130
        except (OSError, PermissionError) as exc:
            print(f"Guided learning hardware error: {exc}", file=sys.stderr)
            return 1

    if result.device.ambiguous:
        return 2
    if not result.device.hidraw_nodes:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
