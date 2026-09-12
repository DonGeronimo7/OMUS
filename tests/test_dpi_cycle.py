from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from evdev import ecodes
from mouse_control.discovery import MouseDevice
from mouse_control.hardware import HardwareBackend, HardwareError
from mouse_control.hardware.capabilities import DpiState
from mouse_control.notifications import DpiEventMonitor
from mouse_control.remapper import DpiCycler, MouseRemapper
from mouse_control import cli


MOUSE = MouseDevice("Test", "/dev/input/test")


def cycler(stages=(800, 1500, 2000, 2500, 3000), current=800, enabled=True):
    backend = MagicMock(spec=HardwareBackend)
    backend.name = "Test"
    backend.supports_dpi.return_value = True
    notifier = MagicMock()
    return DpiCycler(backend, MOUSE, list(stages), current, enabled, notifier), backend, notifier


def test_cycles_all_configured_stages_and_wraps():
    target, backend, notifier = cycler()
    observed = []
    for _ in range(5):
        assert target.cycle()
        observed.append(target.current_dpi)
    assert observed == [1500, 2000, 2500, 3000, 800]
    assert [call.args[1] for call in backend.set_dpi.call_args_list] == observed
    assert [call.args[0] for call in notifier.notify_dpi.call_args_list] == observed


def test_failed_set_leaves_state_and_does_not_notify():
    target, backend, notifier = cycler()
    backend.set_dpi.side_effect = HardwareError("disconnected")
    assert not target.cycle()
    assert target.current_dpi == 800
    notifier.notify_dpi.assert_not_called()


def test_notifications_can_be_disabled_without_disabling_cycle():
    target, backend, notifier = cycler(enabled=False)
    assert target.cycle()
    backend.set_dpi.assert_called_once_with(MOUSE, 1500)
    notifier.notify_dpi.assert_not_called()


def test_backend_without_dpi_support_is_nonfatal():
    target, backend, notifier = cycler()
    backend.supports_dpi.return_value = False
    assert not target.cycle()
    assert target.current_dpi == 800
    backend.set_dpi.assert_not_called()
    notifier.notify_dpi.assert_not_called()


def test_remapper_consumes_dpi_action_on_press_only_and_key_mapping_still_emits():
    target, _, _ = cycler()
    remapper = object.__new__(MouseRemapper)
    remapper.mappings = {
        ecodes.BTN_TASK: __import__('mouse_control.remapper', fromlist=['parse_action']).parse_action('dpi-cycle'),
        ecodes.BTN_EXTRA: __import__('mouse_control.remapper', fromlist=['parse_action']).parse_action('key:KEY_LEFTMETA'),
    }
    remapper.dpi_cycler = target
    remapper.ui = MagicMock()
    remapper._handle(ecodes.EV_KEY, ecodes.BTN_TASK, 1)
    remapper._handle(ecodes.EV_KEY, ecodes.BTN_TASK, 0)
    assert target.current_dpi == 1500
    remapper._handle(ecodes.EV_KEY, ecodes.BTN_EXTRA, 1)
    remapper.ui.write.assert_called_once_with(ecodes.EV_KEY, ecodes.KEY_LEFTMETA, 1)


def run_config(mappings, backend):
    config = {
        'device': {'event_path': MOUSE.path},
        'dpi': {'active': 800, 'stages': [800, 1500]},
        'notifications': {'dpi_changes': True},
        'remap': mappings,
    }
    monitor_instance = MagicMock()
    with patch.object(cli, 'load_config', return_value=config), \
         patch.object(cli, 'get_mouse_devices', return_value=[MOUSE]), \
         patch.object(cli, 'get_backend', return_value=backend), \
         patch.object(cli, 'create_dpi_monitor', return_value=monitor_instance) as factory, \
         patch.object(cli, 'MouseRemapper') as remapper:
        assert cli.run_from_config() == 0
    return factory, monitor_instance, remapper


def runtime_backend():
    backend = MagicMock(spec=HardwareBackend)
    backend.name = 'Test'
    backend.supports_dpi.return_value = True
    backend.supports_dpi_stages.return_value = False
    backend.supports_polling_rate.return_value = False
    return backend


def test_runtime_without_dpi_cycle_creates_monitor_only():
    factory, monitor, remapper = run_config({'BTN_LEFT': 'passthrough'}, runtime_backend())
    factory.assert_called_once()
    monitor.start.assert_called_once()
    monitor.stop.assert_called_once()
    assert remapper.call_args.args[3] is None


def test_runtime_with_dpi_cycle_creates_cycler_and_monitor():
    factory, monitor, remapper = run_config({'BTN_TASK': 'dpi-cycle'}, runtime_backend())
    factory.assert_called_once()
    monitor.start.assert_called_once()
    monitor.stop.assert_called_once()
    target = remapper.call_args.args[3]
    assert isinstance(target, DpiCycler)
    assert target.notifier is monitor
    assert factory.call_args.args[3] is remapper.call_args.args[2]


def test_cycler_and_event_monitor_suppress_same_value_hardware_echo():
    target, backend, _ = cycler(stages=(800, 1500))
    notifier = MagicMock()
    monitor = DpiEventMonitor(backend, MOUSE, [800, 1500], 800, notifier)
    target.notifier = monitor
    backend.set_dpi.return_value = DpiState(1500, confirmed=True)
    assert target.cycle()
    monitor.handle_state(DpiState(1500, active_stage=1, confirmed=True))
    notifier.notify_dpi.assert_called_once_with(1500)


def test_runtime_with_dpi_cycle_tolerates_backend_without_monitoring():
    config = {
        'device': {'event_path': MOUSE.path},
        'dpi': {'active': 800, 'stages': [800, 1500]},
        'remap': {'BTN_TASK': 'dpi-cycle'},
    }
    backend = runtime_backend()
    with patch.object(cli, 'load_config', return_value=config), \
         patch.object(cli, 'get_mouse_devices', return_value=[MOUSE]), \
         patch.object(cli, 'get_backend', return_value=backend), \
         patch.object(cli, 'create_dpi_monitor', return_value=None) as factory, \
         patch.object(cli, 'MouseRemapper') as remapper:
        assert cli.run_from_config() == 0
    factory.assert_called_once()
    assert isinstance(remapper.call_args.args[3], DpiCycler)
