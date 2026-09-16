"""Read-only inspection of Automatic Discovery hypotheses for one selected mouse."""

from __future__ import annotations

import argparse

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

    engine = DiscoveryEngine(detectors=(), save_profiles=False)
    result = engine.discover(mouse)

    print("Mouse Control — Discovery Evidence Inspection")
    print("============================================")
    print(f"Device: {mouse.name} [{(mouse.vendor or 0):04x}:{(mouse.product or 0):04x}]")
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
