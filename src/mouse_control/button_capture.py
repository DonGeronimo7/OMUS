"""Resilient evdev selection and filtering for setup button capture.

A selected MouseDevice is an identity/topology anchor, not necessarily the
composite evdev sibling that carries button events.  This module resolves the
actual mouse-capable sibling without persisting volatile event paths.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from evdev import InputDevice, ecodes

from .device_topology import TopologyError, build_device_graph
from .wizard import ButtonCaptureError


# Linux input-event-codes.h reserves 0x110..0x11f for ordinary mouse buttons.
# Keep keyboard KEY_* and joystick/gamepad BTN_* siblings out of mouse mapping.
_MOUSE_BUTTON_MIN = int(ecodes.BTN_MOUSE)
_MOUSE_BUTTON_MAX = int(ecodes.BTN_JOYSTICK) - 1


def is_mouse_button_code(code: int) -> bool:
    """Return True only for the Linux mouse-button code range."""

    try:
        value = int(code)
    except (TypeError, ValueError):
        return False
    return _MOUSE_BUTTON_MIN <= value <= _MOUSE_BUTTON_MAX


def _same_path(left: str | Path, right: str | Path) -> bool:
    try:
        return os.path.realpath(os.fspath(left)) == os.path.realpath(os.fspath(right))
    except OSError:
        return os.fspath(left) == os.fspath(right)


def _mouse_capability_score(device: InputDevice) -> int:
    capabilities = device.capabilities(verbose=False)
    key_codes = capabilities.get(ecodes.EV_KEY, ())
    rel_codes = capabilities.get(ecodes.EV_REL, ())
    mouse_buttons = sum(1 for code in key_codes if is_mouse_button_code(code))
    has_xy = ecodes.REL_X in rel_codes and ecodes.REL_Y in rel_codes
    if mouse_buttons == 0:
        return -1
    # Prefer a conventional pointer sibling but still allow button-only mouse
    # interfaces used by some composite gaming devices/receivers.
    return mouse_buttons + (100 if has_xy else 0)


def resolve_button_capture_path(
    selected,
    *,
    topology_builder: Callable = build_device_graph,
    input_device_factory: Callable = InputDevice,
) -> str:
    """Choose the correlated evdev sibling that actually carries mouse buttons.

    The currently selected path wins only when it is itself mouse-capable.
    Otherwise all correlated evdev siblings are inspected and the strongest
    mouse interface is selected.  Volatile event paths are returned only for
    this live capture session; they are never persisted as device identity.
    """

    try:
        physical = topology_builder(selected)
    except (TopologyError, OSError, PermissionError) as exc:
        raise ButtonCaptureError(
            f"Could not correlate mouse interfaces for button capture: {exc}"
        ) from exc

    candidates = list(physical.evdev_nodes)
    if not candidates:
        raise ButtonCaptureError(
            "No correlated evdev interface is available for button capture."
        )

    scored: list[tuple[int, int, str]] = []
    failures: list[str] = []
    for node in candidates:
        device = None
        try:
            device = input_device_factory(str(node.path))
            score = _mouse_capability_score(device)
        except (OSError, PermissionError) as exc:
            failures.append(f"{node.path}: {exc}")
            continue
        finally:
            if device is not None:
                try:
                    device.close()
                except OSError:
                    pass
        if score < 0:
            continue
        selected_bonus = 1 if _same_path(node.path, selected.path) else 0
        scored.append((score, selected_bonus, str(node.path)))

    if not scored:
        detail = f" ({'; '.join(failures)})" if failures else ""
        raise ButtonCaptureError(
            "No correlated evdev sibling exposes mouse-button events" + detail
        )

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return scored[0][2]
