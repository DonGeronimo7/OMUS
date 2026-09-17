"""Read-only tracking for physically calibrated ordered DPI cycles.

This component deliberately has no hardware backend reference and therefore no
way to write DPI. It converts already-proven physical stage order plus read-side
transition evidence into confirmed observed DPI states.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence

from .hardware.capabilities import DpiState


class ReadOnlyDpiCycleTracker:
    """Track a physically proven DPI cycle without creating write authority.

    Trigger-only evidence is useful only while the current physical stage is
    genuinely known. Absolute observations may establish or restore that
    synchronization. A reconnect invalidates trigger-only certainty.
    """

    def __init__(self, cycle_order: Sequence[int], *, initial_dpi: int | None = None) -> None:
        order = tuple(int(value) for value in cycle_order)
        if len(order) < 2 or len(set(order)) < 2 or any(value <= 0 for value in order):
            raise ValueError("read-only DPI cycle requires at least two distinct positive stages")
        self._order = order
        self._lock = threading.Lock()
        self._stage_index: int | None = None
        self._trigger_armed = True
        if initial_dpi is not None:
            self.seed(initial_dpi)

    @property
    def cycle_order(self) -> tuple[int, ...]:
        return self._order

    @property
    def synchronized(self) -> bool:
        with self._lock:
            return self._stage_index is not None

    @property
    def active_stage(self) -> int | None:
        with self._lock:
            return self._stage_index

    @property
    def current_dpi(self) -> int | None:
        with self._lock:
            if self._stage_index is None:
                return None
            return self._order[self._stage_index]

    def _index_for(self, dpi: int) -> int:
        try:
            return self._order.index(int(dpi))
        except ValueError as exc:
            raise ValueError(f"{dpi} DPI is not in the calibrated cycle") from exc

    def seed(self, dpi: int) -> None:
        """Synchronize from legitimate current-stage evidence without emitting."""
        index = self._index_for(dpi)
        with self._lock:
            self._stage_index = index
            self._trigger_armed = True

    def observe_absolute(self, dpi: int) -> DpiState | None:
        """Synchronize/resynchronize from an absolute calibrated read source."""
        index = self._index_for(dpi)
        with self._lock:
            if self._stage_index == index:
                return None
            self._stage_index = index
            return DpiState(
                int(dpi),
                int(dpi),
                active_stage=None,
                confirmed=True,
                cycle_trigger=False,
            )

    def observe_trigger(self, pressed: bool) -> DpiState | None:
        """Advance once for one press; holds/echoes are ignored until release."""
        with self._lock:
            if not pressed:
                self._trigger_armed = True
                return None
            if not self._trigger_armed:
                return None
            self._trigger_armed = False
            if self._stage_index is None:
                return None
            self._stage_index = (self._stage_index + 1) % len(self._order)
            dpi = self._order[self._stage_index]
            return DpiState(
                dpi,
                dpi,
                active_stage=None,
                confirmed=True,
                cycle_trigger=False,
            )

    def invalidate_trigger_sync(self) -> None:
        """Forget unsupported trigger-only certainty after continuity is lost."""
        with self._lock:
            self._stage_index = None
            self._trigger_armed = True
