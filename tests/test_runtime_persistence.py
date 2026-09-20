import threading
from unittest.mock import Mock

import pytest

from mouse_control import service, session_start
from mouse_control.runtime_lock import runtime_lock
from mouse_control.notifications import DpiMonitor


def test_runtime_excludes_duplicate_and_releases_after_failure(monkeypatch, tmp_path):
    monkeypatch.setenv('XDG_RUNTIME_DIR', str(tmp_path))
    with runtime_lock():
        with pytest.raises(RuntimeError, match='already running'):
            with runtime_lock(): pass
    with pytest.raises(ValueError):
        with runtime_lock(): raise ValueError()
    with runtime_lock(): pass


def test_polling_monitor_accepts_supervisor_readiness_callback():
    stopped = threading.Event()
    backend = Mock()
    backend.get_dpi.return_value = 1500
    callback = Mock(side_effect=stopped.set)
    monitor = DpiMonitor(backend, object(), shutdown_event=stopped)
    monitor._run(callback)
    callback.assert_called_once()
    backend.get_dpi.assert_called_once()


def test_service_has_unlimited_bounded_restart_and_session_lifetime():
    text = service.build_service_text('/usr/bin/omus')
    assert 'StartLimitIntervalSec=0' in text
    assert 'Restart=on-failure' in text
    assert 'RestartSec=3' in text
    assert 'PartOf=graphical-session.target' in text
    assert 'WantedBy=graphical-session.target' in text


@pytest.mark.parametrize('exists,enabled', [(False, True), (True, True), (True, False)])
def test_login_bootstrap_preserves_disable_and_uses_systemd(monkeypatch, tmp_path, exists, enabled):
    config = tmp_path / 'config.toml'
    config.write_text('[device]')
    unit = tmp_path / 'omus.service'
    if exists: unit.write_text('custom unit')
    monkeypatch.setattr(session_start, 'get_config_path', lambda: config)
    monkeypatch.setattr(service, 'service_path', lambda: unit)
    monkeypatch.setattr(service.subprocess, 'run', Mock(return_value=Mock(returncode=0 if enabled else 1)))
    install, start = Mock(), Mock()
    monkeypatch.setattr(service, 'install_service', install)
    monkeypatch.setattr(service, 'start_service', start)
    assert session_start.main() == 0
    assert install.call_count == (0 if exists else 1)
    assert start.call_count == int(enabled)


def test_login_upgrades_only_exact_generated_unit(monkeypatch, tmp_path):
    config = tmp_path / 'config.toml'
    config.write_text('[device]')
    unit = tmp_path / 'omus.service'
    current = service.build_service_text('/usr/bin/omus')
    former = current.replace('After=graphical-session-pre.target\nPartOf=graphical-session.target\nStartLimitIntervalSec=0\n', '').replace(
        'RestartSec=3\nTimeoutStopSec=15', 'RestartSec=2').replace(
        'WantedBy=graphical-session.target', 'WantedBy=default.target')
    unit.write_text(former)
    monkeypatch.setattr(session_start, 'get_config_path', lambda: config)
    monkeypatch.setattr(service, 'service_path', lambda: unit)
    monkeypatch.setattr(service.subprocess, 'run', Mock(return_value=Mock(returncode=0)))
    install, start = Mock(), Mock()
    monkeypatch.setattr(service, 'install_service', install)
    monkeypatch.setattr(service, 'start_service', start)
    session_start.main()
    install.assert_called_once_with(start=False)
    unit.write_text(former + '# user customization\n')
    install.reset_mock()
    session_start.main()
    install.assert_not_called()


def test_vendor_unit_and_generated_unit_use_same_lifecycle():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    assert (root / 'packaging/omus.service').read_text() == service.build_service_text('/usr/bin/omus')
    desktop = (root / 'packaging/omus-autostart.desktop').read_text()
    assert 'Exec=/usr/bin/python3 -I -m mouse_control.session_start' in desktop


def test_fresh_runtime_constructions_restore_file_backed_preferences(monkeypatch, tmp_path):
    from mouse_control import cli, runtime_wake
    from mouse_control.discovery import MouseDevice
    from mouse_control.hardware import HardwareBackend
    from unittest.mock import MagicMock
    config = tmp_path / 'config.toml'
    config.write_text('''[device]
name = "Test"
event_path = "/dev/input/test"
[dpi]
active = 1500
stages = [800, 1500, 2000, 2500, 3000]
[polling]
rate_hz = 1000
[notifications]
dpi_changes = true
[remap]
BTN_FORWARD = "dpi-cycle"
[lighting.logo]
mode = "static"
color = "#123456"
persistence = "volatile"
''')
    device = MouseDevice('Test', '/dev/input/test')
    backend = MagicMock(spec=HardwareBackend)
    supervisor = MagicMock()
    supervisor.return_value.supports_dpi_cycle_trigger.return_value = False
    remapper, notifications, battery = MagicMock(), MagicMock(), MagicMock()
    monkeypatch.setattr(cli, 'get_mouse_devices', lambda: [device])
    monkeypatch.setattr(cli, 'get_backend', lambda *args, **kwargs: backend)
    monkeypatch.setattr(cli, 'HardwareSupervisor', supervisor)
    monkeypatch.setattr(cli, 'MouseRemapper', remapper)
    monkeypatch.setattr(cli, 'DpiMonitorSupervisor', notifications)
    monkeypatch.setattr(cli, 'BatteryMonitorSupervisor', battery)
    monkeypatch.setattr(runtime_wake, 'LinuxDeviceEventMonitor', MagicMock())
    for _ in range(2):
        assert cli.run_from_config(config) == 0
        desired = supervisor.call_args.args[3]
        assert desired.active_dpi == 1500
        assert desired.dpi_stages == (800, 1500, 2000, 2500, 3000)
        assert desired.polling_rate_hz == 1000
        assert desired.volatile_lighting[0].color == '#123456'
        assert remapper.call_args.args[1] == {'BTN_FORWARD': 'dpi-cycle'}
    assert notifications.call_count == battery.call_count == 2


def test_appimage_service_uses_persistent_image_not_temporary_mount(monkeypatch, tmp_path):
    image = tmp_path / 'OMUS.AppImage'
    image.write_text('image')
    image.chmod(0o755)
    unit = tmp_path / 'omus.service'
    monkeypatch.setenv('APPIMAGE', str(image))
    monkeypatch.setattr(service, 'service_path', lambda: unit)
    monkeypatch.setattr(service, 'legacy_service_path', lambda: tmp_path / 'missing')
    monkeypatch.setattr(service.shutil, 'which', lambda _: '/tmp/.mount-omus/usr/bin/omus')
    monkeypatch.setattr(service.subprocess, 'run', Mock())
    service.install_service(start=False)
    assert f'ExecStart="{image}" run' in unit.read_text()
    assert '.mount-omus' not in unit.read_text()


def test_failed_known_protocol_probe_stays_retryable_but_unknown_device_does_not():
    from mouse_control.discovery import MouseDevice
    from mouse_control.hardware.native_hid import NativeHidBackend
    from mouse_control.hardware.discovery_backend import DiscoveryBackend
    known = MouseDevice('G305', '/dev/input/test', vendor=0x046d, product=0x4074, bustype=3)
    unknown = MouseDevice('Unknown', '/dev/input/test', vendor=1, product=2, bustype=3)
    factory = lambda: NativeHidBackend(discovery=lambda _: [])
    backend = DiscoveryBackend(protocol_factories=(factory,))
    backend._bind_protocol_adapter(known)
    assert backend.discovery_pending
    assert backend.protocol_adapter_name is None
    backend._bind_protocol_adapter(unknown)
    assert not backend.discovery_pending


def test_polling_fallback_releases_control_when_backend_promotes_to_events():
    backend = Mock(generation=0)
    backend.get_dpi.return_value = 1500
    monitor = DpiMonitor(backend, object(), interval=.001)
    monitor._run(lambda: setattr(backend, 'generation', 1))
    backend.get_dpi.assert_called_once()
