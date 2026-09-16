"""Read-only inspection of Automatic Discovery hypotheses for one selected mouse."""

from __future__ import annotations

import argparse
import sys

from .device_topology import TopologyError
from .discovery import get_mouse_devices, select_mouse_device
from .discovery_engine import DiscoveryEngine


def _pick(index: int | None):
    mice = get_mouse_devices()
    if not mice:
        raise SystemExit("No mouse devices found")
    if index is None:
        return select_mouse_device(mice)
    if index < 1 or index > len(mice):
        raise SystemExit(f"--device must be between 1 and {len(mice)}")
    return mice[index - 1]


def _identity(mouse) -> str:
    vendor = mouse.vendor if isinstance(mouse.vendor, int) else 0
    product = mouse.product if isinstance(mouse.product, int) else 0
    return f"{mouse.name} [{vendor:04x}:{product:04x}] [{mouse.path}]"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect read-only topology, descriptor, repertoire, and evidence hypotheses. "
            "This command never sends an unknown HID write."
        )
    )
    parser.add_argument("--device", type=int, metavar="N")
    args = parser.parse_args(argv)

    mouse = _pick(args.device)
    if mouse is None:
        return 0

    print("Mouse Control — Discovery Evidence Inspection")
    print("============================================")
    print(f"Selected device: {_identity(mouse)}")
    print("Unknown HID writes sent: NO")

    engine = DiscoveryEngine(detectors=(), save_profiles=False)
    try:
        result = engine.discover(mouse)
    except TopologyError as exc:
        print()
        print("Topology correlation: FAILED SAFELY")
        print(f"Reason: {exc}")
        print(
            "The selected evdev mouse remains identified, but Automatic Discovery could not "
            "correlate its HID/sysfs siblings strongly enough to continue."
        )
        print("No hardware authority changed and no HID write was sent.")
        return 1
    except PermissionError as exc:
        print()
        print("Topology/descriptor visibility: INCOMPLETE")
        print(f"Reason: {exc}")
        print(
            "This is an evidence-visibility failure, not permission to guess. "
            "No hardware authority changed and no HID write was sent."
        )
        return 1
    except OSError as exc:
        print()
        print("Discovery inspection: HARDWARE ACCESS FAILURE")
        print(f"Reason: {exc}")
        print("Reconnect the selected mouse and retry. No HID write was sent.")
        return 1
    except Exception as exc:
        # Inspection is a diagnostic surface. Preserve the selected device and
        # return the unexpected failure to the TUI instead of tearing curses down.
        print()
        print("Discovery inspection: INTERNAL FAILURE")
        print(f"{type(exc).__name__}: {exc}")
        print("No hardware authority changed and no HID write was sent.")
        return 1

    print(f"Physical identity ambiguous: {'yes' if result.device.ambiguous else 'no'}")
    print(
        f"Correlated interfaces: {len(result.device.evdev_nodes)} evdev / "
        f"{len(result.device.hidraw_nodes)} hidraw"
    )
    print(f"Parsed HID descriptors: {len(engine.descriptors)}")
    print(f"Feature-report snapshots: {len(engine.feature_snapshots)} interface(s)")

    candidates = engine.repertoire_candidates
    print()
    print("Protocol repertoire hypotheses:")
    if not candidates:
        print("  none matched strongly enough")
    for candidate in candidates:
        family = candidate.family
        print(
            f"  {family.name}/{family.revision}: score={candidate.score}, "
            f"exact_identity={'yes' if candidate.exact_identity else 'no'}, "
            f"write_authorized={'yes' if candidate.write_authorized else 'no'}"
        )
        if candidate.matched:
            print("    matched: " + ", ".join(candidate.matched))
        if candidate.missing:
            print("    missing: " + ", ".join(candidate.missing))
        if family.notes:
            print("    note: " + family.notes)

    print()
    print("Evidence ladder:")
    for evidence in result.evidence:
        print(f"  [{evidence.level.name}] {evidence.kind}: {evidence.description}")

    print()
    print("Unknown HID writes sent: NO")
    print("A structural family match is evidence only; it never grants write authority by itself.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
