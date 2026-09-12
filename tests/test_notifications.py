"""DPI notification tests require neither hardware nor a desktop session."""

from pathlib import Path
import asyncio
import sys
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mouse_control.discovery import MouseDevice
from mouse_control.hardware.generic import GenericBackend
from mouse_control.hardware.capabilities import DpiState
from mouse_control.notifications import DpiEventMonitor, DpiMonitor, FreedesktopNotifier, create_dpi_monitor


MOUSE = MouseDevice("Test", "/dev/input/test", vendor=1, product=2)


def backend_with_dpi(*values):
    backend = Mock()
    backend.supports_dpi_events.return_value = False
    backend.supports_dpi_monitoring.return_value = True
    backend.get_dpi.side_effect = values
    return backend


def test_notification_emitted_only_when_dpi_changes():
    backend = backend_with_dpi(800, 800, 1500)
    notifier = Mock()
    monitor = DpiMonitor(backend, MOUSE, notifier)
    monitor.poll_once()
    monitor.poll_once()
    notifier.notify_dpi.assert_not_called()
    monitor.poll_once()
    notifier.notify_dpi.assert_called_once_with(1500)


def test_every_dpi_update_reuses_one_notification():
    notifier = FreedesktopNotifier()
    calls = []

    async def connect():
        return Mock()

    async def notify(bus, dpi):
        calls.append(dpi)
        return len(calls) * 10

    notifier._connect = connect
    notifier._notify = notify
    values = [800, 1500, 2000, 2500, 3000] * 4
    for dpi in values:
        notifier.notify_dpi(dpi)
    notifier.wait_idle()
    notifier.close()
    assert calls == values
    assert notifier._notification_id == len(values) * 10


def test_notification_uses_transient_silent_hints_and_short_timeout():
    from dbus_next.constants import MessageType

    notifier = FreedesktopNotifier()
    bus = Mock()
    reply = Mock(message_type=MessageType.METHOD_RETURN, body=[11])
    bus.call = Mock(return_value=reply)

    async def call(message):
        bus.message = message
        return reply

    bus.call = call
    assert asyncio.run(notifier._notify(bus, 1500)) == 11
    body = bus.message.body
    assert body[1] == 0
    assert body[4] == "1500 DPI"
    assert body[6]["urgency"].value == 1
    assert body[6]["transient"].value is True
    assert body[6]["suppress-sound"].value is True
    assert body[7] == 1500

    notifier._notification_id = 11
    assert asyncio.run(notifier._notify(bus, 2000)) == 11
    assert bus.message.body[1] == 11


def test_one_dbus_failure_does_not_disable_future_notifications(caplog):
    notifier = FreedesktopNotifier()
    attempts = 0

    async def connect():
        return Mock()

    async def notify(bus, dpi):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError('bus reset')
        return 31

    notifier._connect = connect
    notifier._notify = notify
    notifier.notify_dpi(1500)
    notifier.notify_dpi(2000)
    notifier.wait_idle()
    notifier.close()
    assert attempts == 2
    assert 'DPI notification failed' in caplog.text


def test_notification_body_displays_dpi():
    assert FreedesktopNotifier._body(1500) == "1500 DPI"
    assert FreedesktopNotifier._body((1500, 1500)) == "1500 DPI"
    assert FreedesktopNotifier._body((1200, 800)) == "1200 × 800 DPI"


def test_disabled_and_unsupported_backends_do_not_monitor():
    capable = backend_with_dpi(800)
    assert create_dpi_monitor(capable, MOUSE, enabled=False) is None
    capable.supports_dpi_monitoring.assert_not_called()
    assert create_dpi_monitor(GenericBackend(), MOUSE) is None


def test_monitor_capability_failure_is_nonfatal(caplog):
    backend = Mock()
    backend.supports_dpi_monitoring.side_effect = RuntimeError("service unavailable")
    assert create_dpi_monitor(backend, MOUSE) is None
    assert "service unavailable" in caplog.text


def test_notification_failure_does_not_stop_monitor_and_warning_is_deduplicated(caplog):
    backend = backend_with_dpi(800, 1500, 2000, 2500)
    notifier = Mock()
    notifier.notify_dpi.side_effect = [RuntimeError("no notification server"),
                                       RuntimeError("no notification server"), None]
    monitor = DpiMonitor(backend, MOUSE, notifier)
    for _ in range(4):
        monitor.poll_once()
    assert notifier.notify_dpi.call_count == 3
    assert caplog.text.count("Desktop DPI notification failed") == 1


def test_backend_read_failure_does_not_stop_monitor(caplog):
    backend = backend_with_dpi(800, RuntimeError("disconnected"), 1500)
    notifier = Mock()
    monitor = DpiMonitor(backend, MOUSE, notifier)
    monitor.poll_once()
    monitor.poll_once()
    monitor.poll_once()
    notifier.notify_dpi.assert_called_once_with(1500)
    assert "disconnected" in caplog.text


def test_event_monitor_uses_confirmed_hardware_dpi_not_configured_stage_array():
    notifier = Mock()
    monitor = DpiEventMonitor(Mock(), MOUSE, [800, 1500, 2000, 2500, 3000],
                              800, notifier)
    monitor.handle_state(DpiState(1750, 1750, active_stage=4, confirmed=True))
    notifier.notify_dpi.assert_called_once_with(1750)


def test_event_monitor_suppresses_only_duplicate_dpi_and_unconfirmed_state():
    notifier = Mock()
    monitor = DpiEventMonitor(Mock(), MOUSE, [800, 1500, 2000], 800, notifier)
    for state in (DpiState(800, confirmed=True), DpiState(1500),
                  DpiState(1500, confirmed=True), DpiState(1500, confirmed=True),
                  DpiState(2000, confirmed=True)):
        monitor.handle_state(state)
    assert [call.args[0] for call in notifier.notify_dpi.call_args_list] == [1500, 2000]


def test_event_monitor_continues_after_notification_failure():
    backend = Mock()
    notifier = Mock()
    notifier.notify_dpi.side_effect = [RuntimeError('relay failed'), None]
    monitor = DpiEventMonitor(backend, MOUSE, [800, 1500, 2000], 800, notifier)
    monitor.handle_state(DpiState(1500, confirmed=True))
    monitor.handle_state(DpiState(2000, confirmed=True))
    assert notifier.notify_dpi.call_count == 2
    assert monitor._last_dpi == 2000


def test_event_monitor_is_selected_and_disabled_monitor_never_probes():
    backend = Mock()
    backend.supports_dpi_events.return_value = True
    monitor = create_dpi_monitor(backend, MOUSE, stages=[800, 1500], active_dpi=800)
    assert isinstance(monitor, DpiEventMonitor)
    assert create_dpi_monitor(backend, MOUSE, enabled=False,
                              stages=[800, 1500], active_dpi=800) is None
    assert backend.supports_dpi_events.call_count == 1
