"""Hardware tests use no daemon, input device, or real hardware writes."""
from types import SimpleNamespace
from unittest.mock import Mock, patch
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'src'))
from mouse_control import cli
from mouse_control.discovery import MouseDevice
from mouse_control.hardware import HardwareBackend, HardwareError, get_backend
from mouse_control.hardware.generic import GenericBackend
from mouse_control.hardware.openrazer import OpenRazerBackend
from mouse_control.hardware.ratbag import RatbagBackend, RatbagClient, RatbagDevice, RatbagError

G305 = MouseDevice('misleading name', '/dev/input/test', vendor=0x046d, product=0x4074)
RAZER = MouseDevice('generic name', '/dev/input/test', vendor=0x1532, product=0x0099)


def razer_device(features=('dpi', 'poll_rate', 'supported_poll_rates'), **kwargs):
    return SimpleNamespace(_vid=0x1532, _pid=0x0099, type='mouse', name='Razer mouse',
                           has=lambda feature: feature in features, dpi=(800, 800),
                           max_dpi=20000, available_dpi=[400, 800, 1600],
                           poll_rate=500, supported_poll_rates=[125, 500, 1000], **kwargs)


def razer_backend(*devices):
    return OpenRazerBackend(lambda: SimpleNamespace(devices=list(devices)))


def ratbag_backend():
    client = RatbagClient()
    client.binary = '/mock/ratbagctl'
    def run(*args):
        if args == ('list',):
            return 'mouse: Logitech G305'
        if args == ('mouse', 'info'):
            return 'Model: usb:046d:4074:0\nResolutions:\n  0: 800dpi (active) (default)\n  1: 1600dpi\n  2: 3200dpi (disabled)\nButton: 0'
        return {('dpi', 'get'): '800', ('dpi', 'get-all'): '800 1600',
                ('rate', 'get'): '500', ('rate', 'get-all'): '125 500 1000'}.get(args[1:], '')
    client._run = Mock(side_effect=run)
    return RatbagBackend(client)


def test_logitech_selects_ratbag_first_and_usb_identity():
    backend = ratbag_backend()
    later = Mock()
    assert get_backend(G305, [lambda: backend, later]) is backend
    later.assert_not_called()
    assert backend.get_device_name(G305) == 'Logitech G305'
    assert not backend.supports_device(RAZER)


def test_razer_selects_openrazer_after_ratbag_miss():
    backend = razer_backend(razer_device())
    assert get_backend(RAZER, [ratbag_backend, lambda: backend]) is backend
    assert backend.get_device_name(RAZER) == 'Razer mouse'


def test_unsupported_and_missing_identity_select_generic():
    for mouse in (MouseDevice('Razer', '/test'), MouseDevice('Razer', '/test', vendor=1, product=2)):
        factory = Mock(side_effect=AssertionError('must stay lazy'))
        assert isinstance(get_backend(mouse, [ratbag_backend, lambda: OpenRazerBackend(factory)]), GenericBackend)
        factory.assert_not_called()


def test_openrazer_import_unavailable_is_nonfatal(caplog):
    with patch.dict(sys.modules, {'openrazer': None, 'openrazer.client': None}):
        assert isinstance(get_backend(RAZER, [OpenRazerBackend]), GenericBackend)
    assert 'OpenRazer' in caplog.text


def test_daemon_unavailable_is_nonfatal(caplog):
    backend = OpenRazerBackend(Mock(side_effect=RuntimeError('session bus unavailable')))
    assert isinstance(get_backend(RAZER, [lambda: backend]), GenericBackend)
    assert 'session bus unavailable' in caplog.text


def test_wrong_product_and_nonmouse_rejected():
    wrong = razer_device(); wrong._pid = 1
    keyboard = razer_device(); keyboard.type = 'keyboard'
    assert not razer_backend(wrong, keyboard).supports_device(RAZER)


def test_ambiguous_identity_rejected_for_both_backends():
    assert isinstance(get_backend(RAZER, [lambda: razer_backend(razer_device(), razer_device())]), GenericBackend)
    backend = ratbag_backend()
    with patch.object(backend.client, 'list_devices', return_value=[RatbagDevice('a', 'a'), RatbagDevice('b', 'b')]), \
         patch.object(backend.client, '_model_for', return_value='usb:046d:4074:0'):
        assert isinstance(get_backend(G305, [lambda: backend]), GenericBackend)


def test_generic_capability_defaults():
    backend = GenericBackend()
    assert not backend.supports_dpi(G305)
    assert not backend.supports_dpi_stages(G305)
    assert not backend.supports_dpi_monitoring(G305)
    assert not backend.supports_polling_rate(G305)
    assert backend.get_dpi(G305) is None
    assert backend.get_polling_rate(G305) is None
    assert backend.get_dpi_values(G305) == backend.get_polling_rates(G305) == []
    with pytest.raises(HardwareError):
        backend.set_dpi(G305, 800)


def test_openrazer_capabilities_and_writes():
    target = razer_device()
    backend = razer_backend(target)
    assert backend.supports_dpi(RAZER)
    assert backend.get_dpi(RAZER) == (800, 800)
    assert backend.get_dpi_values(RAZER) == []
    backend.set_dpi(RAZER, 1500)
    assert target.dpi == (1500, 1500)
    assert backend.get_polling_rates(RAZER) == [125, 500, 1000]
    backend.set_polling_rate(RAZER, 1000)
    assert target.poll_rate == 1000
    with pytest.raises(HardwareError):
        backend.set_polling_rate(RAZER, 8000)
    with pytest.raises(HardwareError):
        backend.set_dpi(RAZER, 30000)


def test_fixed_dpi_uses_zero_y_and_rejects_unreported_values():
    target = razer_device(('dpi', 'available_dpi'))
    backend = razer_backend(target)
    assert backend.get_dpi_values(RAZER) == [400, 800, 1600]
    backend.set_dpi(RAZER, 800)
    assert target.dpi == (800, 0)
    with pytest.raises(HardwareError):
        backend.set_dpi(RAZER, 1500)


def test_missing_capabilities_and_old_daemon_do_not_guess_rates():
    backend = razer_backend(razer_device(()))
    assert not backend.supports_dpi(RAZER)
    assert backend.get_dpi(RAZER) is None
    assert not backend.supports_polling_rate(RAZER)
    assert backend.get_polling_rate(RAZER) is None
    for setter in (backend.set_dpi, backend.set_polling_rate):
        with pytest.raises(HardwareError):
            setter(RAZER, 800)
    backend = razer_backend(razer_device(('poll_rate',)))
    assert backend.get_polling_rates(RAZER) == []
    assert cli._select_max_polling_rate(backend, RAZER) == 500


def test_g305_stages_skip_disabled_and_set_active_default_and_max_rate():
    backend = ratbag_backend()
    assert cli._choose_default_dpi(backend, G305) == ([800, 1500, 2000, 2500, 3000], 800)
    rate = cli._select_max_polling_rate(backend, G305)
    assert rate == 1000
    cli._apply_hardware(backend, G305, [800, 1500, 2000, 2500, 3000], 800, rate, setup=True)
    calls = [call.args for call in backend.client._run.call_args_list]
    assert ('mouse', 'resolution', '0', 'dpi', 'set', '800') in calls
    assert ('mouse', 'resolution', '1', 'dpi', 'set', '1500') in calls
    assert ('mouse', 'resolution', '2', 'dpi', 'set', '2000') not in calls
    assert ('mouse', 'resolution', 'active', 'set', '0') in calls
    assert ('mouse', 'resolution', 'default', 'set', '0') in calls
    assert ('mouse', 'rate', 'set', '1000') in calls


def test_ratbag_does_not_claim_runtime_dpi_monitoring():
    backend = ratbag_backend()
    assert backend.supports_dpi(G305)
    assert not backend.supports_dpi_monitoring(G305)


def test_passive_hidpp_events_are_scoped_to_validated_g305():
    backend = ratbag_backend()
    assert backend.supports_dpi_events(G305)
    assert not backend.supports_dpi_events(RAZER)
    assert not backend.supports_dpi_events(
        MouseDevice('Other Logitech', '/dev/input/test', vendor=0x046d, product=0xc332)
    )


def test_rejected_ratbag_slot_warns_and_keeps_other_slots(caplog):
    backend = ratbag_backend()
    with patch.object(backend.client, 'set_resolution_dpi', side_effect=[RatbagError('rejected'), None]) as setter:
        assert backend.apply_dpi_stages(G305, [800, 1500], 1500) == 1
    assert setter.call_count == 2
    assert 'rejected' in caplog.text


def test_ratbag_runtime_active_dpi_fallback_preserved():
    backend = ratbag_backend()
    cli._apply_hardware(backend, G305, [1500], 800, None)
    backend.client._run.assert_any_call('mouse', 'dpi', 'set', '800')


def test_hardware_write_error_translated():
    class BrokenMouse:
        _vid, _pid, type = 0x1532, 0x0099, 'mouse'
        def has(self, feature):
            return feature == 'poll_rate'
        @property
        def poll_rate(self):
            raise RuntimeError('device disconnected')
    with pytest.raises(HardwareError, match='device disconnected'):
        razer_backend(BrokenMouse()).get_polling_rate(RAZER)


@pytest.mark.parametrize('unavailable', [False, True])
def test_startup_remaps_despite_hardware_failure(unavailable, caplog):
    backend = Mock(spec=HardwareBackend)
    backend.name = 'Test'
    backend.supports_dpi.side_effect = HardwareError('disconnected')
    backend.supports_polling_rate.return_value = True
    config = {'device': {'event_path': RAZER.path}, 'dpi': {'active': 800},
              'polling': {'rate_hz': 1000}, 'remap': {'BTN_SIDE': 'key:KEY_F13'}}
    with patch.object(cli, 'load_config', return_value=config), \
         patch.object(cli, 'get_mouse_devices', return_value=[RAZER]), \
         patch.object(cli, 'MouseRemapper') as remapper:
        if unavailable:
            with patch.dict(sys.modules, {'openrazer': None, 'openrazer.client': None}), \
                 patch('mouse_control.hardware.registry.BACKEND_FACTORIES', (OpenRazerBackend,)):
                assert cli.run_from_config() == 0
        else:
            with patch.object(cli, 'get_backend', return_value=backend):
                assert cli.run_from_config() == 0
            backend.set_polling_rate.assert_called_once_with(RAZER, 1000)
        remapper.assert_called_once()
        assert remapper.call_args.args[:2] == (RAZER.path, config['remap'])
        assert remapper.call_args.args[2] is not None
        remapper.return_value.run.assert_called_once()
    assert 'disconnected' in caplog.text or 'OpenRazer' in caplog.text


def test_setup_saves_compatible_config_and_preserves_service_prompt():
    backend = ratbag_backend()
    with patch.object(cli, 'get_mouse_devices', return_value=[G305]), \
         patch.object(cli, 'is_service_active', return_value=False), \
         patch.object(cli, 'select_mouse_device', return_value=G305), \
         patch.object(cli, 'map_mouse_buttons', return_value={'BTN_SIDE': 'key:KEY_F13'}), \
         patch.object(cli, 'get_backend', return_value=backend), \
         patch.object(cli, 'save_config') as save, \
         patch.object(cli, '_ask_enable_service', return_value=True) as ask, \
         patch.object(cli, 'install_service') as install:
        assert cli.run_setup_wizard() == 0
    import tomllib
    config = tomllib.loads(save.call_args.args[0])
    assert set(config) == {'device', 'dpi', 'polling', 'notifications', 'remap'}
    assert config['dpi'] == {'active': 800, 'stages': [800, 1500, 2000, 2500, 3000]}
    assert config['polling']['rate_hz'] == 1000
    assert config['notifications']['dpi_changes'] is True
    assert config['remap']['BTN_SIDE'] == 'key:KEY_F13'
    assert not any('button' in call.args for call in backend.client._run.call_args_list)
    ask.assert_called_once()
    install.assert_called_once()
