"""Protocol-neutral lighting validation and shared-record preservation.

This module contains no transport. Backends retain exact-device binding and
write authority; callers cannot turn repertoire knowledge into a hardware write.
"""

from __future__ import annotations

from dataclasses import replace
import re
from typing import Callable

from .hardware import HardwareError
from .hardware.capabilities import (
    LightingMode,
    LightingState,
    LightingWriteScope,
    LightingZoneCapabilities,
)

_RGB24 = re.compile(r"^#[0-9A-Fa-f]{6}$")


def normalize_color(value: str) -> str:
    if not isinstance(value, str) or not _RGB24.fullmatch(value):
        raise ValueError("lighting color must use #RRGGBB")
    return value.upper()


def validate_lighting_state(
    state: LightingState, capability: LightingZoneCapabilities
) -> LightingState:
    if state.zone_id != capability.zone_id:
        raise ValueError("lighting state does not match the selected zone")
    if state.mode not in capability.modes:
        raise ValueError(f"{state.mode.value} is unsupported for {capability.name}")
    color = state.color
    if state.mode in {LightingMode.STATIC, LightingMode.BREATHING}:
        if not capability.rgb24:
            raise ValueError("this zone does not expose full RGB color")
        if color is None:
            raise ValueError("this lighting mode requires a color")
        color = normalize_color(color)
    elif color is not None:
        color = normalize_color(color)
    for label, value, bounds in (
        ("brightness", state.brightness, capability.brightness_range),
        ("speed", state.speed, capability.speed_range),
    ):
        if value is not None and (bounds is None or not bounds[0] <= value <= bounds[1]):
            raise ValueError(f"{label} is outside the supported range")
    if state.persistence not in capability.persistence:
        raise ValueError("requested lighting persistence is unsupported")
    return replace(state, color=color)


def patch_shared_configuration(
    baseline: bytes | None,
    patch: Callable[[bytearray], None],
    *,
    write_scope: LightingWriteScope,
    integrity: Callable[[bytearray], None] | None = None,
) -> bytes:
    """Patch a trustworthy whole-device record while preserving unrelated bytes."""
    if write_scope is not LightingWriteScope.SHARED_DEVICE_CONFIG:
        raise ValueError("shared-record patching requires SHARED_DEVICE_CONFIG")
    if baseline is None or not baseline:
        raise HardwareError("lighting write refused: no trustworthy configuration baseline")
    result = bytearray(baseline)
    patch(result)
    if len(result) != len(baseline):
        raise HardwareError("lighting write refused: configuration record size changed")
    if integrity is not None:
        integrity(result)
    return bytes(result)
