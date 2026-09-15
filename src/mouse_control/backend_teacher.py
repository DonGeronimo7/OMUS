"""Read-only bridge from proven runtime backends to generic protocol learning.

A backend teacher supplies *semantic truth* only.  It does not reveal packet
indexes, feature IDs, report layouts or write commands to the learner.  That
keeps HID++/OpenRazer useful as labelled examples without making their protocol
implementations the backbone of automatic discovery.
"""

from __future__ import annotations

from typing import Mapping

from .discovery import MouseDevice


def read_backend_teacher_state(
    device: MouseDevice,
) -> Mapping[str, int | tuple[int, int] | None]:
    """Return safely readable state from the best already-proven backend.

    Generic HID deliberately contributes no teacher labels because it has no
    protocol semantics of its own.  Every backend is closed before returning so
    the subsequent raw capture has a single clear owner of each hidraw stream.
    """

    # Lazy imports preserve the discovery/HID++ import boundary.
    from .hardware import get_backend
    from .hardware.generic import GenericBackend

    backend = get_backend(device, log_failures=False)
    try:
        if isinstance(backend, GenericBackend):
            return {}

        caps = backend.get_capabilities(device)
        state: dict[str, int | tuple[int, int] | None] = {}

        if caps.dpi.readable:
            dpi_state = backend.get_dpi_state(device)
            if dpi_state is not None and dpi_state.confirmed:
                state["dpi"] = dpi_state.display_value
                if dpi_state.active_stage is not None:
                    state["dpi_stage"] = int(dpi_state.active_stage)

        if caps.report_rate.readable:
            rate = backend.get_polling_rate(device)
            if rate is not None:
                state["polling_rate"] = int(rate)

        if caps.battery.readable:
            battery = backend.get_battery_state(device)
            if battery is not None and battery.percentage is not None:
                state["battery"] = int(battery.percentage)

        return state
    finally:
        backend.close()
