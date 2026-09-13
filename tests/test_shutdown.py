"""Regression coverage for prompt, clean service shutdown."""

from pathlib import Path
import signal
import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mouse_control import remapper as remapper_module
from mouse_control.discovery import MouseDevice
from mouse_control.notifications import DpiEventMonitor, DpiMonitor


def make_remapper(shutdown_event=None):
    device = MagicMock(fd=7, name="Test Mouse")
    device.capabilities.return_value = {}
    ui = MagicMock()
    ui_context = MagicMock()
    ui_context.__enter__.return_value = ui
    with patch.object(remapper_module, "InputDevice", return_value=device), \
         patch.object(remapper_module, "UInput", return_value=ui_context):
        remapper = remapper_module.MouseRemapper(
            "/dev/input/test", {}, shutdown_event=shutdown_event
        )
        remapper.device = device
        remapper._test_ui_context = ui_context
    return remapper, device, ui_context


def test_no_input_loop_observes_shutdown_and_releases_resources():
    remapper, device, ui_context = make_remapper()

    def request_shutdown(*_args):
        remapper.stop()
        return [], [], []

    remapper.device = None
    with patch.object(remapper_module, "InputDevice", return_value=device), \
         patch.object(remapper_module.select, "select", side_effect=request_shutdown), \
         patch.object(remapper_module, "UInput", return_value=ui_context), \
         patch.object(remapper_module.signal, "signal") as install_signal:
        remapper.run()

    install_signal.assert_any_call(signal.SIGTERM, remapper.stop)
    install_signal.assert_any_call(signal.SIGINT, remapper.stop)
    device.grab.assert_called_once()
    device.ungrab.assert_called_once()
    device.close.assert_called_once()
    ui_context.close.assert_called_once()


def test_runtime_exception_still_releases_grab_and_uinput():
    remapper, device, ui_context = make_remapper()
    remapper.device = None
    with patch.object(remapper_module, "InputDevice", return_value=device), \
         patch.object(remapper_module.select, "select", side_effect=RuntimeError("select failed")), \
         patch.object(remapper_module, "UInput", return_value=ui_context), \
         patch.object(remapper_module.signal, "signal"), \
         pytest.raises(RuntimeError, match="select failed"):
        remapper.run()
    device.ungrab.assert_called_once()
    device.close.assert_called_once()
    ui_context.close.assert_called_once()


def test_notification_monitor_uses_shared_shutdown_event():
    shutdown_event = threading.Event()
    backend = MagicMock()
    backend.get_dpi.return_value = 800
    monitor = DpiMonitor(
        backend,
        MouseDevice("Test", "/dev/input/test"),
        notifier=MagicMock(),
        interval=10,
        shutdown_event=shutdown_event,
    )
    monitor.start()
    shutdown_event.set()
    monitor.stop()
    assert monitor._thread is not None
    assert not monitor._thread.is_alive()


def test_hidpp_event_monitor_shutdown_is_prompt():
    shutdown_event = threading.Event()
    backend = MagicMock()
    backend.watch_dpi_events.side_effect = lambda device, callback, stop, ready: (ready(), stop.wait(10))
    monitor = DpiEventMonitor(backend, MouseDevice("G305", "/dev/input/test"),
                              [800, 1500], 800, notifier=MagicMock(),
                              shutdown_event=shutdown_event)
    monitor.start()
    monitor.stop()
    assert monitor._thread is not None
    assert not monitor._thread.is_alive()
