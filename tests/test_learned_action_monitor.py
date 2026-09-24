# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from mouse_control.hardware.capabilities import DpiState
from mouse_control.notifications import DpiEventMonitor


class Cycler:
    def __init__(self):
        self.calls = 0
        self.backend = None

    def cycle(self):
        self.calls += 1
        return True


class Backend:
    pass


def test_cycle_trigger_invokes_software_cycler_without_fake_dpi():
    cycler = Cycler()
    backend = Backend()
    monitor = DpiEventMonitor(
        backend,
        object(),
        [],
        0,
        dpi_cycler=cycler,
    )
    monitor.handle_state(
        DpiState(
            0,
            0,
            confirmed=True,
            cycle_trigger=True,
        )
    )
    assert cycler.calls == 1
    assert cycler.backend is backend


def test_cycle_trigger_without_cycler_does_not_notify_as_zero_dpi():
    class Notifier:
        def __init__(self):
            self.values = []
        def notify_dpi(self, value):
            self.values.append(value)

    notifier = Notifier()
    monitor = DpiEventMonitor(
        Backend(),
        object(),
        [],
        0,
        notifier=notifier,
    )
    monitor.handle_state(
        DpiState(
            0,
            0,
            confirmed=True,
            cycle_trigger=True,
        )
    )
    assert notifier.values == []
