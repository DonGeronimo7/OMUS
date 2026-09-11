from pathlib import Path
import sys
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from evdev import ecodes
from mouse_control.discovery import MouseDevice
from mouse_control.hardware import HardwareBackend, HardwareError
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


def test_application_owned_cycle_does_not_start_polling_monitor():
    config = {
        'device': {'event_path': MOUSE.path},
        'dpi': {'active': 800, 'stages': [800, 1500]},
        'notifications': {'dpi_changes': True},
        'remap': {'BTN_TASK': 'dpi-cycle'},
    }
    backend = MagicMock(spec=HardwareBackend)
    backend.name = 'Test'
    backend.supports_dpi.return_value = True
    backend.supports_dpi_stages.return_value = False
    backend.supports_polling_rate.return_value = False
    with __import__('unittest.mock', fromlist=['patch']).patch.object(cli, 'load_config', return_value=config), \
         __import__('unittest.mock', fromlist=['patch']).patch.object(cli, 'get_mouse_devices', return_value=[MOUSE]), \
         __import__('unittest.mock', fromlist=['patch']).patch.object(cli, 'get_backend', return_value=backend), \
         __import__('unittest.mock', fromlist=['patch']).patch.object(cli, 'create_dpi_monitor') as monitor, \
         __import__('unittest.mock', fromlist=['patch']).patch.object(cli, 'MouseRemapper') as remapper:
        assert cli.run_from_config() == 0
    monitor.assert_not_called()
    assert remapper.call_args.args[3].current_dpi == 800
