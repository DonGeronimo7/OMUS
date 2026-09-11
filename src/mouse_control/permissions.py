"""Report the narrowly scoped device access needed by the remapper."""

from __future__ import annotations

import os
from pathlib import Path

from .discovery import get_mouse_devices


UINPUT_PATH = Path("/dev/uinput")


def permission_report() -> int:
    """Show whether this logged-in session can use uinput and discovered mice."""
    missing: list[str] = []
    if not UINPUT_PATH.exists():
        missing.append("/dev/uinput is absent (load the uinput kernel module).")
    elif not os.access(UINPUT_PATH, os.R_OK | os.W_OK):
        missing.append("/dev/uinput is not readable and writable by this session.")

    mice = get_mouse_devices()
    if not mice:
        missing.append("No readable mouse event device was found.")

    if missing:
        for item in missing:
            print(item)
        print("Install the Fedora RPM or review the supplied udev rule, then log out and back in.")
        return 1

    print("Mouse event devices and /dev/uinput are accessible to this session.")
    return 0
