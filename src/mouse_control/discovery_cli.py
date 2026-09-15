"""Dedicated CLI for the first automatic-hardware-discovery acceptance cycle.

Keeping this command separate from the normal setup/runtime path lets us test
real hardware without silently changing the behavior of ``mouse-control run``.
"""

from __future__ import annotations

import argparse
import json
import sys

from .device_topology import TopologyError
from .discovery import get_mouse_devices, select_mouse_device
from .discovery_engine import DiscoveryEngine
from .discovery_ui import render_discovery_result, result_to_dict


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mouse-control-discover",
        description=(
            "Safety-first automatic mouse hardware discovery. Known protocol "
            "queries are validated; unknown HID inspection remains read-only."
        ),
    )
    parser.add_argument(
        "--device",
        type=int,
        metavar="N",
        help="select mouse N from the detected list instead of prompting",
    )
    parser.add_argument("--verbose", action="store_true", help="show discovery evidence")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="do not cache the path-independent discovery profile",
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


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    selected, status = _pick_mouse(args.device)
    if selected is None:
        return status

    if not args.json:
        print(
            "Discovery test mode: unknown HID is read-only and the normal "
            "mouse-control runtime is not being reconfigured.\n"
        )

    engine = DiscoveryEngine(save_profiles=not args.no_save)
    try:
        result = engine.discover(selected)
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
        print(render_discovery_result(
            result,
            profile_path=engine.profile_path,
            verbose=args.verbose,
        ))

    if result.device.ambiguous:
        return 2
    if not result.device.hidraw_nodes:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
