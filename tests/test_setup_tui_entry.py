from unittest.mock import Mock, patch

from mouse_control import app, cli, setup_entry
from mouse_control.discovery import MouseDevice
from mouse_control.setup_flow import SetupChoices
from mouse_control.setup_tui import SetupTuiResult, run_setup_tui


MOUSE = MouseDevice("Test Mouse", "/dev/input/test", vendor=1, product=2, phys="usb-test")


class Tty:
    def isatty(self):
        return True


class NotTty:
    def isatty(self):
        return False


class FakeBackend:
    protocol_adapter_name = None
    has_proven_learned_adapter = False

    def __init__(self):
        self.dpi = 800
        self.set_calls = []

    def supports_dpi(self, _device):
        return True

    def get_dpi_values(self, _device):
        return [800, 1500, 2000, 2500, 3000]

    def get_dpi(self, _device):
        return self.dpi

    def set_dpi(self, _device, value):
        self.set_calls.append(value)
        self.dpi = value
        return value

    def supports_polling_rate(self, _device):
        return False

    def supports_polling_rate_writes(self, _device):
        return False

    def supports_dpi_events(self, _device):
        return False

    def close(self):
        pass


def _choices(_existing):
    return SetupChoices(mappings={"BTN_LEFT": "passthrough"})


def test_installed_entrypoint_routes_interactive_setup_to_tui(monkeypatch):
    monkeypatch.setattr(app.sys, "stdin", Tty())
    monkeypatch.setattr(app.sys, "stdout", Tty())
    with patch.object(app, "run_tui_setup_wizard", return_value=23) as tui, \
         patch.object(app, "_LEGACY_SETUP", return_value=99) as legacy:
        assert app.run_setup_wizard() == 23
    tui.assert_called_once_with()
    legacy.assert_not_called()


def test_installed_entrypoint_preserves_non_tty_legacy_compatibility(monkeypatch):
    monkeypatch.setattr(app.sys, "stdin", NotTty())
    monkeypatch.setattr(app.sys, "stdout", NotTty())
    with patch.object(app, "run_tui_setup_wizard", return_value=23) as tui, \
         patch.object(app, "_LEGACY_SETUP", return_value=7) as legacy:
        assert app.run_setup_wizard() == 7
    legacy.assert_called_once_with()
    tui.assert_not_called()


def test_app_main_scopes_cli_setup_override():
    original = cli.run_setup_wizard
    with patch.object(cli, "main", return_value=0) as delegated:
        assert app.main(["setup"]) == 0
        assert cli.run_setup_wizard is original
    delegated.assert_called_once_with(["setup"])


def test_tui_setup_success_reuses_existing_commit_and_service_flow(tmp_path):
    choices = SetupChoices(
        stages=[800, 1500, 2000, 2500, 3000],
        active_dpi=800,
        polling_rate=500,
        mappings={"BTN_FORWARD": "dpi-cycle"},
        enable_service=True,
        dpi_changed=True,
        polling_changed=True,
        dpi_writable=True,
        polling_writable=True,
    )
    backend = Mock()
    result = SetupTuiResult(True, MOUSE, backend, choices)
    existing = {
        "device": {"vendor": 1, "product": 2, "phys": "usb-test"},
        "dpi": {"active": 800, "stages": [800, 1500, 2000, 2500, 3000]},
        "polling": {"rate_hz": 1000},
        "remap": {"BTN_FORWARD": "dpi-cycle"},
    }
    target = tmp_path / "config.toml"
    with patch.object(cli, "is_service_active", return_value=True), \
         patch.object(cli, "stop_service") as stop, \
         patch.object(cli, "restart_service") as restart, \
         patch.object(cli, "get_mouse_devices", return_value=[MOUSE]), \
         patch.object(cli, "_load_setup_config", return_value=existing), \
         patch.object(setup_entry, "run_setup_tui", return_value=result), \
         patch.object(cli, "_apply_hardware") as apply, \
         patch.object(cli, "merge_setup_config", return_value="config text") as merge, \
         patch.object(cli, "save_config", return_value=target) as save, \
         patch.object(cli, "install_service") as install:
        assert setup_entry.run_tui_setup_wizard() == 0
    stop.assert_called_once_with()
    apply.assert_called_once_with(
        backend, MOUSE, choices.stages, 800, 500, setup=True
    )
    merge.assert_called_once()
    save.assert_called_once_with("config text")
    install.assert_called_once_with()
    restart.assert_not_called()


def test_tui_setup_cancel_restores_dpi_config_and_running_service():
    choices = SetupChoices(original_dpi=800, mappings={"BTN_LEFT": "passthrough"})
    backend = Mock()
    result = SetupTuiResult(False, MOUSE, backend, choices)
    with patch.object(cli, "is_service_active", return_value=True), \
         patch.object(cli, "stop_service"), \
         patch.object(cli, "restart_service") as restart, \
         patch.object(cli, "get_mouse_devices", return_value=[MOUSE]), \
         patch.object(cli, "_load_setup_config", return_value={}), \
         patch.object(setup_entry, "run_setup_tui", return_value=result), \
         patch.object(setup_entry, "restore_dpi") as restore, \
         patch.object(cli, "save_config") as save:
        assert setup_entry.run_tui_setup_wizard() == 0
    restore.assert_called_once_with(backend, MOUSE, 800)
    save.assert_not_called()
    restart.assert_called_once_with()


def test_tui_wrapper_restores_temporary_dpi_when_curses_aborts(monkeypatch):
    backend = FakeBackend()
    monkeypatch.setattr("mouse_control.setup_tui_curses.curses.wrapper", lambda _call: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        run_setup_tui(
            [MOUSE], {}, choices_factory=_choices, backend_factory=lambda _device: backend
        )
    except KeyboardInterrupt:
        pass
    else:
        raise AssertionError("KeyboardInterrupt should propagate to setup transaction")
    assert backend.set_calls[-1] == 800
