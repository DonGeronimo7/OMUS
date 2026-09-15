"""Wizard-to-TOML-to-runtime regression tests, using the real config writer."""
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'src'))
from mouse_control import cli, config
from mouse_control.discovery import MouseDevice
from mouse_control.remapper import DpiCycler

MOUSE = MouseDevice('G305 test', '/dev/input/test', vendor=0x046d, product=0x4074)
FINAL = [800, 1450, 2000, 2400, 3200]


def hardware():
    backend = MagicMock()
    backend.name = 'Test HID'
    backend.get_device_name.return_value = MOUSE.name
    backend.supports_dpi.return_value = True
    backend.get_dpi.return_value = 800
    backend.get_dpi_values.return_value = list(range(200, 12001, 50))
    backend.set_dpi.side_effect = lambda device, value: value
    backend.supports_polling_rate.return_value = False
    backend.supports_polling_rate_writes.return_value = False
    backend.supports_dpi_stages.return_value = False
    return backend


def run_wizard(path, backend, answers, capsys):
    with patch.object(config, 'get_config_path', return_value=path), \
         patch.object(cli, 'is_service_active', return_value=False), \
         patch.object(cli, 'get_mouse_devices', return_value=[MOUSE]), \
         patch.object(cli, 'select_mouse_device', return_value=MOUSE), \
         patch.object(cli, 'get_backend', return_value=backend), \
         patch.object(cli, 'map_mouse_buttons', return_value={'BTN_TASK': 'dpi-cycle'}), \
         patch('builtins.input', side_effect=answers):
        result = cli.run_setup_wizard()
    return result, capsys.readouterr().out


def test_finish_persists_reviewed_stages_and_runtime_loads_exact_list(tmp_path, capsys):
    path = tmp_path / 'config.toml'
    backend = hardware()
    answers = [
        '', '2', '1450', '', '4', '2400', '', '5', '3200', '', '',
        '', 'n', '',
    ]
    result, output = run_wizard(path, backend, answers, capsys)
    assert result == 0
    assert 'DPI stages: 800 → 1450 → 2000 → 2400 → 3200' in output
    saved = config.load_config(path)
    assert saved['dpi']['stages'] == FINAL
    assert saved['dpi']['active'] == 800
    assert backend.set_dpi.call_args.args[-1] == 800

    runtime_backend = hardware()
    observed = {}
    def exercise_runtime():
        target = observed['cycler'] = remapper.call_args.args[3]
        runtime_backend.get_dpi.return_value = 1450
        observed['cycled'] = target.cycle()
    with patch.object(cli, 'get_mouse_devices', return_value=[MOUSE]), \
         patch.object(cli, 'get_backend', return_value=runtime_backend), \
         patch.object(cli, 'DpiMonitorSupervisor') as monitor, \
         patch.object(cli, 'BatteryMonitorSupervisor'), \
         patch.object(cli, 'MouseRemapper') as remapper:
        remapper.return_value.run.side_effect = exercise_runtime
        assert cli.run_from_config(path) == 0
    cycler = observed['cycler']
    assert isinstance(cycler, DpiCycler)
    assert cycler.stages == FINAL
    assert monitor.call_args.args[3] == FINAL
    assert observed['cycled']
    assert runtime_backend.set_dpi.call_args.args[-1] == 1450
    assert cycler.current_dpi == 1450
    monitor.return_value.notify_dpi.assert_called_once_with(1450)


def test_back_keeps_accepted_stage_and_cancel_does_not_save(tmp_path, capsys):
    path = tmp_path / 'config.toml'
    path.write_text(config.generate_config(MOUSE, {'BTN_TASK': 'dpi-cycle'}))
    original = path.read_bytes()
    backend = hardware()
    answers = ['s', '2', '1450', '', '2', '1500', 'b', 'b', 's', 'q']
    result, output = run_wizard(path, backend, answers, capsys)
    assert result == 0
    assert '2. 1450 DPI' in output
    assert path.read_bytes() == original
    assert backend.set_dpi.call_args.args[-1] == 800
