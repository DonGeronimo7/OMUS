"""Guided, read-only promotion of a physical DPI-cycle action trigger."""

from __future__ import annotations

import argparse
import os
import select
import time

from .device_topology import build_device_graph
from .discovery import get_mouse_devices, select_mouse_device
from .learned_actions import LearnedActionStore, LearnedActionTrigger
from .learned_operations import (
    LearnedOperationStore,
    StableDeviceIdentity,
    StableInterfaceIdentity,
    matching_interface_node,
)
from .polling_replay import PacketPattern
from .protocol_grammar import SemanticBehavior


def _capture(node, seconds: float) -> list[bytes]:
    fd = os.open(os.fspath(node.path), os.O_RDONLY | os.O_NONBLOCK)
    packets: list[bytes] = []
    deadline = time.monotonic() + seconds
    try:
        while time.monotonic() < deadline:
            remaining = max(0.0, deadline - time.monotonic())
            readable, _, _ = select.select(
                [fd], [], [], min(0.25, remaining)
            )
            if not readable:
                continue
            try:
                data = os.read(fd, 4096)
            except BlockingIOError:
                continue
            if not data:
                raise RuntimeError("hidraw interface disconnected")
            packets.append(bytes(data))
    finally:
        os.close(fd)
    return packets


def _infer_alternating_pair(
    packets: list[bytes],
    *,
    minimum_presses: int,
) -> tuple[bytes, bytes, int]:
    transitions: list[bytes] = []
    for packet in packets:
        if not transitions or packet != transitions[-1]:
            transitions.append(packet)
    unique = set(transitions)
    if len(unique) != 2:
        raise RuntimeError(
            "guided action capture must contain exactly two alternating packet "
            f"states; observed {len(unique)} unique state(s)"
        )
    if len(transitions) < minimum_presses * 2:
        raise RuntimeError(
            f"need at least {minimum_presses} complete press/release cycles"
        )
    press = transitions[0]
    release = transitions[1]
    if len(press) != len(release):
        raise RuntimeError("press/release packet lengths differ")
    for index, packet in enumerate(transitions):
        expected = press if index % 2 == 0 else release
        if packet != expected:
            raise RuntimeError(
                "captured packets did not form a strict press/release alternation"
            )
    complete = len(transitions) // 2
    return press, release, complete


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Learn one exact read-only physical DPI-cycle trigger. "
            "No HID output or feature writes are sent."
        )
    )
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--presses", type=int, default=8)
    parser.add_argument(
        "--authorize-guided-capture",
        action="store_true",
        help="confirm that only the DPI-cycle physical action will be performed",
    )
    args = parser.parse_args(argv)
    if not args.authorize_guided_capture:
        parser.error("--authorize-guided-capture is required")
    if args.seconds <= 0 or args.presses < 5:
        parser.error("--seconds must be positive and --presses must be at least 5")

    mice = get_mouse_devices()
    if not mice:
        raise SystemExit("No mouse devices found")
    mouse = select_mouse_device(mice)
    if mouse is None:
        return 0
    physical = build_device_graph(mouse)
    if physical.ambiguous:
        raise SystemExit("Physical identity is ambiguous; refusing action learning")

    learned = LearnedOperationStore().find_for_physical(
        physical,
        behavior=SemanticBehavior.DPI_VALUE,
        proven_only=True,
    )
    if learned is None:
        raise SystemExit(
            "A PROVEN learned DPI writer is required before learning a cycle trigger"
        )
    _path, dpi_operation = learned
    node = matching_interface_node(dpi_operation, physical)

    print(f"Selected: {mouse.name}")
    print(f"Exact learned interface: {node.path}")
    print(
        "This capture is read-only. Do not move or click the mouse. "
        "Press only the physical DPI-cycle button."
    )
    print(
        f"After pressing Enter, press/release the DPI button at least "
        f"{args.presses} times during {args.seconds:g} seconds."
    )
    input("> ")

    packets = _capture(node, args.seconds)
    press, release, observations = _infer_alternating_pair(
        packets,
        minimum_presses=args.presses,
    )

    trigger = LearnedActionTrigger(
        behavior=SemanticBehavior.DPI_CYCLE_TRIGGER,
        identity=StableDeviceIdentity(
            bus=physical.bus,
            vendor_id=physical.vendor_id,
            product_id=physical.product_id,
            model_fingerprint=physical.model_fingerprint,
            instance_fingerprint=physical.instance_fingerprint,
        ),
        interface=StableInterfaceIdentity(
            bus=node.bus,
            vendor_id=node.vendor_id,
            product_id=node.product_id,
            interface_number=node.interface_number,
            descriptor_sha256=node.descriptor_sha256,
        ),
        press_pattern=PacketPattern(tuple(press)),
        release_pattern=PacketPattern(tuple(release)),
        observation_count=observations,
    )
    path = LearnedActionStore().save(trigger)

    print()
    print(f"Press packet:   {press.hex(' ')}")
    print(f"Release packet: {release.hex(' ')}")
    print(f"Validated cycles: {observations}")
    print(f"Saved: {path}")
    print("write_authorized=false")
    print("LEARNED DPI-CYCLE TRIGGER SUCCESS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
