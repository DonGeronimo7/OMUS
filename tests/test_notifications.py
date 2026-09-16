"""DPI notification and monitoring behavior."""
from __future__ import annotations

from unittest.mock import Mock

from mouse_control.discovery import MouseDevice
from mouse_control.hardware import (HardwareBackend, HardwareSupervisor)
from mouse_control.hardware.capabilities import DpiState
from mouse_control.hardware.generic import GenericBackend
from mouse_control.notifications import (DpiEventMonitor, DpiMonitor,
                                         DpiMonitorSupervisor,
                                         FreedesktopNotifier,
                                         create_dpi_monitor)


MOUSE = MouseDevice("G305", "/dev/input/test", vendor=0x046d, product=0x4074)


def polling_backend(values):
    backend = Mock(spec=HardwareBackend)
    backend.supports_dpi_events.return_value = False
    backend.supports_dpi_monitoring.return_value = True
    backend.get_dpi.side_effect = list(values)
    return backend


def event_backend():
    backend = Mock(spec=HardwareBackend)
    backend.name = "Native HID"
    backend.supports_dpi_events.return_value = True
    backend.supports_dpi_monitoring.return_value = True
    backend.supports_dpi.return_value = True
    backend.supports_polling_rate.return_value = False
    backend.supports_polling_rate_writes_without_takeover.return_value = False
    backend.supports_dpi_stages.return_value = False
    return backend


class ScriptedShutdown:
    def __init__(self):
        self.set_flag = False
        self.waits = []

    def is_set(self):
        return self.set_flag

    def set(self):
        self.set_flag = True

    def wait(self, timeout):
        self.waits.append(timeout)
        return self.set_flag


def test_body_formats_single_and_independent_axes():
    assert FreedesktopNotifier._body(800) == "800 DPI"
    assert FreedesktopNotifier._body((800, 800)) == "800 DPI"
    assert FreedesktopNotifier._body((800, 1600)) == "800 × 1600 DPI"


def test_polling_monitor_notifies_only_after_change():
    notifier = Mock()
    backend = polling_backend([800, 800, 1500])
    monitor = DpiMonitor(backend, MOUSE, notifier)
    monitor.poll_once()
    monitor.poll_once()
    monitor.poll_once()
    notifier.notify_dpi.assert_called_once_with(1500)


def test_polling_monitor_recovers_after_read_failure():
    notifier = Mock()
    backend = polling_backend([800, OSError("lost"), 1500])
    monitor = DpiMonitor(backend, MOUSE, notifier)
    monitor.poll_once()
    monitor.poll_once()
    monitor.poll_once()
    notifier.notify_dpi.assert_called_once_with(1500)


def test_create_monitor_prefers_events():
    backend = event_backend()
    monitor = create_dpi_monitor(backend, MOUSE, notifier=Mock())
    assert isinstance(monitor, DpiEventMonitor)


def test_create_monitor_falls_back_to_polling():
    backend = polling_backend([800])
    monitor = create_dpi_monitor(backend, MOUSE, notifier=Mock())
    assert isinstance(monitor, DpiMonitor)


def test_create_monitor_returns_none_when_unavailable():
    backend = Mock(spec=HardwareBackend)
    backend.supports_dpi_events.return_value = False
    backend.supports_dpi_monitoring.return_value = False
    assert create_dpi_monitor(backend, MOUSE, notifier=Mock()) is None


def test_event_monitor_ignores_unconfirmed_state():
    notifier = Mock()
    monitor = DpiEventMonitor(event_backend(), MOUSE, [], 800, notifier)
    monitor.handle_state(DpiState(1500, confirmed=False))
    notifier.notify_dpi.assert_not_called()


def test_event_monitor_notifies_confirmed_state():
    notifier = Mock()
    monitor = DpiEventMonitor(event_backend(), MOUSE, [], 800, notifier)
    monitor.handle_state(DpiState(1500, confirmed=True))
    notifier.notify_dpi.assert_called_once_with(1500)


def test_event_monitor_deduplicates_same_dpi():
    notifier = Mock()
    monitor = DpiEventMonitor(event_backend(), MOUSE, [], 800, notifier)
    monitor.handle_state(DpiState(1500, confirmed=True))
    monitor.handle_state(DpiState(1500, confirmed=True))
    notifier.notify_dpi.assert_called_once_with(1500)


def test_deliberate_notification_does_not_deduplicate():
    notifier = Mock()
    monitor = DpiEventMonitor(event_backend(), MOUSE, [], 800, notifier)
    assert monitor.notify_deliberate_dpi(1500)
    assert monitor.notify_deliberate_dpi(1500)
    assert notifier.notify_dpi.call_count == 2


def test_event_monitor_drives_cycler_only_with_active_stage():
    notifier = Mock()
    cycler = Mock()
    monitor = DpiEventMonitor(event_backend(), MOUSE, [], 800, notifier,
                              dpi_cycler=cycler)
    monitor.handle_state(DpiState(1500, confirmed=True, active_stage=2))
    cycler.cycle.assert_called_once()
    notifier.notify_dpi.assert_not_called()


def test_event_monitor_observes_read_only_state_without_cycling():
    notifier = Mock()
    cycler = Mock()
    monitor = DpiEventMonitor(event_backend(), MOUSE, [], 800, notifier,
                              dpi_cycler=cycler)
    monitor.handle_state(DpiState(1500, confirmed=True, active_stage=None))
    cycler.cycle.assert_not_called()
    cycler.observe_dpi.assert_called_once_with(1500)
    notifier.notify_dpi.assert_called_once_with(1500)


def test_event_monitor_suppresses_repeated_active_stage_echo():
    notifier = Mock()
    cycler = Mock()
    monitor = DpiEventMonitor(event_backend(), MOUSE, [], 800, notifier,
                              dpi_cycler=cycler)
    state = DpiState(1500, confirmed=True, active_stage=1)
    monitor.handle_state(state)
    monitor.handle_state(state)
    cycler.cycle.assert_called_once()


def test_event_monitor_run_surfaces_failure_when_requested():
    backend = event_backend()
    backend.watch_dpi_events.side_effect = OSError("lost")
    monitor = DpiEventMonitor(backend, MOUSE, [], 800, Mock(), log_errors=False)
    try:
        monitor._run()
    except OSError as exc:
        assert str(exc) == "lost"
    else:
        raise AssertionError("expected watcher failure")


def test_event_monitor_run_logs_failure_by_default(caplog):
    backend = event_backend()
    backend.watch_dpi_events.side_effect = OSError("lost")
    monitor = DpiEventMonitor(backend, MOUSE, [], 800, Mock())
    monitor._run()
    assert "monitoring stopped" in caplog.text


def test_supervisor_retries_unavailable_monitor():
    unavailable = Mock(spec=HardwareBackend)
    unavailable.supports_dpi_events.return_value = False
    unavailable.supports_dpi_monitoring.return_value = False
    ready = event_backend()
    notifier = Mock()
    shutdown = ScriptedShutdown()
    factory = Mock(return_value=ready)
    supervisor = DpiMonitorSupervisor(unavailable, MOUSE, factory, [], 800,
                                      shutdown, notifier, retry_interval=2.0)
    supervisor._run()
    assert factory.called


def test_supervisor_stops_fast_retry_when_discovery_is_final():
    unavailable = Mock(spec=HardwareBackend)
    unavailable.supports_dpi_events.return_value = False
    unavailable.supports_dpi_monitoring.return_value = False
    unavailable.discovery_pending = False
    notifier = Mock()
    shutdown = ScriptedShutdown()

    def stop_after_wait(timeout):
        shutdown.waits.append(timeout)
        shutdown.set()
        return True

    shutdown.wait = stop_after_wait
    supervisor = DpiMonitorSupervisor(unavailable, MOUSE, Mock(), [], 800,
                                      shutdown, notifier, retry_interval=2.0)
    supervisor._run()
    assert shutdown.waits == [30.0]


def test_supervisor_rebinds_after_watcher_disconnect_and_notifies_again():
    first = event_backend()
    second = event_backend()
    notifier = Mock()
    shutdown = ScriptedShutdown()

    def disconnect(_device, callback, _stop, ready):
        ready()
        callback(DpiState(1500, confirmed=True, active_stage=1))
        raise OSError("disconnected")

    def reconnect(_device, callback, stop, ready):
        ready()
        callback(DpiState(2000, confirmed=True, active_stage=2))
        stop.set()

    first.watch_dpi_events.side_effect = disconnect
    second.watch_dpi_events.side_effect = reconnect
    factory = Mock(return_value=second)
    supervisor = DpiMonitorSupervisor(first, MOUSE, factory, [800, 1500, 2000],
                                      800, shutdown, notifier, retry_interval=3.0)
    supervisor._run()

    assert shutdown.waits == [3.0]
    first.close.assert_called_once()
    factory.assert_called_once_with(MOUSE)
    second.watch_dpi_events.assert_called_once()
    assert [call.args[0] for call in notifier.notify_dpi.call_args_list] == [1500, 2000]


def test_event_monitor_recovers_when_adapter_arrives_after_discovery_only_rebinds():
    """Discovery-only rebinds must continue until a proven adapter returns."""
    first, promoted = event_backend(), event_backend()
    fallback = GenericBackend()
    fallback.close = Mock()
    notifier = Mock()
    shutdown = ScriptedShutdown()
    replacements = iter((fallback, GenericBackend(), promoted))

    def disconnect(_device, _callback, _stop, ready):
        ready()
        raise OSError("receiver removed")

    def deliver(_device, callback, stop, ready):
        ready()
        callback(DpiState(1500, confirmed=True, active_stage=1))
        stop.set()

    first.watch_dpi_events.side_effect = disconnect
    promoted.watch_dpi_events.side_effect = deliver
    hardware = HardwareSupervisor(first, MOUSE, lambda _device: next(replacements))
    monitor = DpiMonitorSupervisor(hardware, MOUSE, lambda _device: hardware,
                                   [800, 1500], 800, shutdown, notifier,
                                   retry_interval=2.0)
    monitor._run()

    assert hardware.current_backend is promoted
    assert hardware.generation == 3
    fallback.close.assert_called_once()
    promoted.watch_dpi_events.assert_called_once()
    notifier.notify_dpi.assert_called_once_with(1500)


def test_supervisor_rebind_allows_same_first_confirmed_value_after_disconnect():
    first = event_backend()
    second = event_backend()
    notifier = Mock()
    shutdown = ScriptedShutdown()

    def disconnect(_device, callback, _stop, ready):
        ready()
        callback(DpiState(800, confirmed=True, active_stage=0))
        raise OSError("disconnected")

    def reconnect(_device, callback, stop, ready):
        ready()
        callback(DpiState(800, confirmed=True, active_stage=0))
        stop.set()

    first.watch_dpi_events.side_effect = disconnect
    second.watch_dpi_events.side_effect = reconnect
    supervisor = DpiMonitorSupervisor(first, MOUSE, Mock(return_value=second), [800],
                                      800, shutdown, notifier, retry_interval=3.0)
    supervisor._run()

    assert [call.args[0] for call in notifier.notify_dpi.call_args_list] == [800, 800]


def test_late_event_backend_notifies_its_first_configured_value():
    unavailable = Mock(name="unavailable backend")
    unavailable.supports_dpi_events.side_effect = OSError("mouse absent")
    ready = event_backend()
    notifier = Mock()
    shutdown = ScriptedShutdown()

    def deliver(_device, callback, stop, ready_callback):
        ready_callback()
        callback(DpiState(800, confirmed=True, active_stage=0))
        stop.set()

    ready.watch_dpi_events.side_effect = deliver
    factory = Mock(return_value=ready)
    supervisor = DpiMonitorSupervisor(unavailable, MOUSE, factory, [800], 800,
                                      shutdown, notifier, retry_interval=2.0)
    supervisor._run()
    notifier.notify_dpi.assert_called_once_with(800)
