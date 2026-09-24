# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hardware state, software cursor and persisted choices are independent."""
import threading
from unittest.mock import Mock

import pytest

from mouse_control.discovery import MouseDevice
from mouse_control.hardware import HardwareBackend, HardwareError, DpiState, HardwareSupervisor, DesiredHardwareState
from mouse_control.remapper import DpiCycler
from mouse_control.notifications import DpiEventMonitor

DEVICE = MouseDevice('Test', '/dev/input/test')
STAGES = [800, 1500, 2000, 2500, 3000]


class LiveBackend(HardwareBackend):
    name = 'live fixture'
    def __init__(self, dpi):
        self.dpi = dpi
        self.writes = []
        self.reads = []
        self.accept = None
    def supports_device(self, device): return True
    def supports_dpi(self, device): return True
    def get_dpi(self, device):
        self.reads.append(self.dpi)
        return self.dpi
    def set_dpi(self, device, dpi):
        self.writes.append(dpi)
        self.dpi = self.accept if self.accept is not None else dpi
        return DpiState(self.dpi, confirmed=True)


@pytest.mark.parametrize('saved,live,expected', [(3000,800,1500),(800,3000,800),(800,2000,2500),(3000,1200,800)])
def test_startup_reads_hardware_silently_and_first_press_uses_live_cursor(saved, live, expected):
    backend, notifier = LiveBackend(live), Mock()
    cycler = DpiCycler(backend, DEVICE, STAGES, saved, notifier=notifier)
    assert cycler.current_dpi == live and cycler.current_dpi_confirmed
    notifier.notify_dpi.assert_not_called()
    assert backend.writes == []
    assert cycler.cycle()
    assert backend.writes == [expected]
    assert cycler.current_dpi == backend.dpi == expected
    notifier.notify_dpi.assert_called_once_with(expected)


def test_unknown_startup_refuses_to_guess_then_recovers_on_first_ready_press():
    backend, notifier = LiveBackend(None), Mock()
    cycler = DpiCycler(backend, DEVICE, STAGES, 3000, notifier=notifier)
    assert cycler.current_dpi is None
    assert not cycler.cycle()
    assert not backend.writes
    notifier.notify_dpi.assert_not_called()
    backend.dpi = 800
    assert cycler.cycle()
    notifier.notify_dpi.assert_called_once_with(1500)


def test_unchanged_hardware_after_write_never_notifies_requested_value():
    backend, notifier = LiveBackend(1500), Mock()
    cycler = DpiCycler(backend, DEVICE, STAGES, 800, notifier=notifier)
    backend.accept = 1500
    assert not cycler.cycle()
    assert backend.writes == [2000]
    assert cycler.current_dpi == 1500
    notifier.notify_dpi.assert_not_called()


def test_quantized_confirmed_state_is_used_for_popup_and_runtime():
    backend, notifier = LiveBackend(1500), Mock()
    cycler = DpiCycler(backend, DEVICE, STAGES, 800, notifier=notifier)
    backend.accept = 2050
    assert cycler.cycle()
    assert backend.writes == [2000]
    assert cycler.current_dpi == 2050
    notifier.notify_dpi.assert_called_once_with(2050)


def test_write_error_resynchronizes_without_a_popup():
    backend, notifier = LiveBackend(1500), Mock()
    cycler = DpiCycler(backend, DEVICE, STAGES, 800, notifier=notifier)
    backend.set_dpi = Mock(side_effect=HardwareError('failed'))
    assert not cycler.cycle()
    assert cycler.current_dpi == 1500
    notifier.notify_dpi.assert_not_called()


def test_reconnect_and_same_generation_wake_use_new_hardware_value():
    backend, notifier = LiveBackend(2500), Mock()
    cycler = DpiCycler(backend, DEVICE, STAGES, 800, notifier=notifier)
    backend.dpi = 800  # receiver/mouse reset, including same-node wake
    cycler.invalidate()
    assert cycler.cycle()
    assert backend.writes == [1500]
    notifier.notify_dpi.assert_called_once_with(1500)


def test_rapid_presses_have_one_verified_write_and_popup_each():
    backend, notifier = LiveBackend(800), Mock()
    cycler = DpiCycler(backend, DEVICE, STAGES, 3000, notifier=notifier)
    threads = [threading.Thread(target=cycler.cycle) for _ in range(5)]
    for thread in threads: thread.start()
    for thread in threads: thread.join(1)
    expected = [1500,2000,2500,3000,800]
    assert backend.writes == expected
    assert [c.args[0] for c in notifier.notify_dpi.call_args_list] == expected
    assert backend.dpi == cycler.current_dpi == 800


def test_native_stage_event_observes_confirmed_hardware_and_never_cycles_again():
    backend, notifier = LiveBackend(800), Mock()
    cycler = DpiCycler(backend, DEVICE, STAGES, 3000, notifier=notifier)
    monitor = DpiEventMonitor(backend, DEVICE, STAGES, 3000, notifier, dpi_cycler=cycler)
    backend.dpi = 2000
    monitor.handle_state(DpiState(2000, active_stage=2, confirmed=True))
    assert backend.writes == []
    assert cycler.current_dpi == 2000
    notifier.notify_dpi.assert_called_once_with(2000)
    monitor.handle_state(DpiState(800, confirmed=True, reconnect_resync=True))
    assert cycler.current_dpi == 800
    assert notifier.notify_dpi.call_count == 1


def test_synchronized_hot_path_reuses_confirmation_and_never_reselects_backend():
    backend, notifier = LiveBackend(800), Mock()
    factory = Mock(side_effect=AssertionError("hot path attempted discovery"))
    supervisor = HardwareSupervisor(backend, DEVICE, factory,
                                   DesiredHardwareState(restore_dpi=False))
    cycler = DpiCycler(supervisor, DEVICE, STAGES, 3000, notifier=notifier)
    assert backend.reads == [800]
    for _ in range(5):
        assert cycler.cycle()
    assert backend.reads == [800]  # no duplicate queries after confirmed setters
    assert backend.writes == [1500, 2000, 2500, 3000, 800]
    factory.assert_not_called()


def test_runtime_rebind_preserves_live_dpi_and_reads_once_before_next_press():
    first, second = LiveBackend(800), LiveBackend(2000)
    supervisor = HardwareSupervisor(first, DEVICE, lambda _: second,
        DesiredHardwareState(active_dpi=3000, dpi_stages=tuple(STAGES), restore_dpi=False))
    cycler = DpiCycler(supervisor, DEVICE, STAGES, 3000, notifier=Mock())
    supervisor.reconcile()
    supervisor.rebind(0)
    assert first.writes == second.writes == []
    assert cycler.cycle()
    assert second.reads == [2000]
    assert second.writes == [2500]


def test_wake_epoch_invalidates_cursor_without_backend_reselection():
    from mouse_control.runtime_wake import RuntimeWakeCoordinator
    wake = RuntimeWakeCoordinator()
    backend = LiveBackend(3000)
    supervisor = HardwareSupervisor(backend, DEVICE, Mock(),
                                   wake_coordinator=wake)
    cycler = DpiCycler(supervisor, DEVICE, STAGES, 800, notifier=Mock())
    backend.dpi = 800
    wake.device_event('test-reconnect')
    assert cycler.cycle()
    assert backend.reads == [3000, 800]
    assert backend.writes == [1500]


def test_legacy_writer_gets_exactly_one_authoritative_readback():
    backend = LiveBackend(800)
    def write(_device, dpi):
        backend.writes.append(dpi)
        backend.dpi = dpi
    backend.set_dpi = write
    cycler = DpiCycler(backend, DEVICE, STAGES, 3000, notifier=Mock())
    assert cycler.cycle()
    assert backend.reads == [800, 1500]
    assert backend.writes == [1500]


def test_failed_learned_read_does_not_present_cached_dpi_as_confirmed():
    from mouse_control.hardware.discovery_backend import DiscoveryBackend
    from unittest.mock import patch
    backend = DiscoveryBackend()
    backend._learned_operation = Mock()
    backend._learned_write_node = Mock()
    backend._last_dpi = 3000
    with patch.object(backend, '_bound_learned_adapter', side_effect=OSError('offline')):
        with pytest.raises(HardwareError, match='learned DPI read failed'):
            backend.get_dpi_state(DEVICE)
    assert backend._last_dpi is None
