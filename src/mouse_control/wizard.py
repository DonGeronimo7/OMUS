# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared setup button-capture primitives."""

from __future__ import annotations

from evdev import ecodes


class ButtonCaptureError(RuntimeError):
    """Raised when the setup wizard cannot capture the physical mouse."""


def get_button_name(code: int) -> str:
    """Resolve a Linux input code to its symbolic name."""
    name = ecodes.bytype.get(ecodes.EV_KEY, {}).get(code)
    if isinstance(name, (list, tuple)):
        name = name[0]
    if isinstance(name, str) and (name.startswith("BTN_") or name.startswith("KEY_")):
        return name
    return f"BTN_{code}"
