"""Mouse discovery using python-evdev and stable /dev/input/by-id paths."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .performance import timed

from evdev import InputDevice, ecodes, list_devices


@dataclass(frozen=True)
class MouseDevice:
    """A discovered Linux input device that looks like a mouse."""

    name: str
    path: str
    phys: str = ""
    vendor: int | None = None
    product: int | None = None
    bustype: int | None = None

    @classmethod
    def from_input_device(cls, device: InputDevice, path: str | None = None) -> "MouseDevice":
        info = getattr(device, "info", None)
        return cls(
            name=device.name or "Unknown mouse",
            path=path or device.path,
            phys=getattr(device, "phys", "") or "",
            vendor=getattr(info, "vendor", None),
            product=getattr(info, "product", None),
            bustype=getattr(info, "bustype", None),
        )


def _iter_candidate_paths() -> Iterable[str]:
    by_id = Path("/dev/input/by-id")
    if by_id.is_dir():
        try:
            yield from (str(entry) for entry in sorted(by_id.iterdir()))
        except OSError:
            pass

    try:
        yield from list_devices()
    except OSError:
        return


def has_mouse_capabilities(device: InputDevice) -> bool:
    """Return True for devices exposing relative motion and mouse/keyboard keys."""
    try:
        caps = device.capabilities(verbose=False)
        return ecodes.EV_REL in caps and ecodes.EV_KEY in caps
    except (OSError, PermissionError):
        return False


@timed("device_enumeration")
def get_mouse_devices() -> list[MouseDevice]:
    """Discover mouse-like evdev devices, preferring stable by-id symlinks."""
    devices: list[MouseDevice] = []
    seen_realpaths: set[str] = set()

    for path in _iter_candidate_paths():
        try:
            realpath = os.path.realpath(path)
            if realpath in seen_realpaths:
                continue
            device = InputDevice(path)
            if not has_mouse_capabilities(device):
                device.close()
                continue
            seen_realpaths.add(realpath)
            devices.append(MouseDevice.from_input_device(device, path))
            device.close()
        except (OSError, PermissionError):
            continue

    return devices


def select_mouse_device(mice: list[MouseDevice]) -> MouseDevice | None:
    """Prompt the user to select one discovered mouse."""
    if not mice:
        print("No mouse devices found.")
        return None

    print("\nAvailable mouse devices:")
    for index, mouse in enumerate(mice, 1):
        identity = ""
        if mouse.vendor is not None and mouse.product is not None:
            identity = f" [{mouse.vendor:04x}:{mouse.product:04x}]"
        print(f"{index}. {mouse.name}{identity} [{mouse.path}]")

    while True:
        try:
            choice = input(f"\nSelect a mouse (1-{len(mice)} or 'q' to quit): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None

        if choice.lower() == "q":
            return None
        try:
            index = int(choice) - 1
        except ValueError:
            print("Please enter a number or 'q'.")
            continue
        if 0 <= index < len(mice):
            return mice[index]
        print(f"Please enter a number between 1 and {len(mice)}.")
