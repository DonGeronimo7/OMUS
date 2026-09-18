from unittest.mock import Mock, patch

from mouse_control import app, cli, setup_entry
from mouse_control.discovery import MouseDevice
from mouse_control.setup_flow import SetupChoices
from mouse_control.setup_tui import SetupTuiResult, run_setup_tui


MOUSE = MouseDevice("Test Mouse", "/dev/input/test", vendor=1, product=2, phys="usb-test")

ESTABLISHED_CONFIG = {
    "device": {"vendor": 1, "product": 2, "phys": "usb-test"},
    "dpi": {"active": 800, "stages": [800, 1500, 2000, 2500, 3000]},
    "polling": {"rate_hz": 1000},
    "remap": {"BTN_FORWARD": "dpi-cycle"},
}


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


def test_interactive_setup_routes_to_tui(monkeypatch):
    monkeypatch.setattr(cli.sys, "stdin", Tty())
    monkeypatch.setattr(cli.sys, "stdout", Tty())
    with patch.object(setup_entry, "run_tui_setup_wizard", return_value=23) as tui:
        assert cli.run_setup_wizard() == 23
    tui.assert_called_once_with()


def test_noninteractive_setup_rejects_before_importing_curses(monkeypatch, capsys):
    monkeypatch.setattr(cli.sys, "stdin", NotTty())
    monkeypatch.setattr(cli.sys, "stdout", NotTty())
    with patch.object(setup_entry, "run_tui_setup_wizard") as tui:
        assert cli.run_setup_wizard() == 2
    tui.assert_not_called()
    assert "requires an interactive terminal" in capsys.readouterr().err


def test_installed_entrypoint_delegates_without_setup_override():
    with patch.object(cli, "main", return_value=0) as delegated:
        assert app.main(["setup"]) == 0
    delegated.assert_called_once_with(["setup"])


def test_explicit_setup_command_routes_to_tui(monkeypatch):
    monkeypatch.setattr(cli.sys, "stdin", Tty())
    monkeypatch.setattr(cli.sys, "stdout", Tty())
    with patch.object(setup_entry, "run_tui_setup_wizard", return_value=31) as tui:
        assert cli.main(["setup"]) == 31
    tui.assert_called_once_with()


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
         patch.object(cli, "install_service") as install, \
         patch("mouse_control.foreground_session.record_service_preference") as preference:
        assert setup_entry.run_tui_setup_wizard() == 0
    stop.assert_not_called()
    apply.assert_called_once_with(
        backend, MOUSE, choices.stages, 800, 500, setup=True
    )
    merge.assert_called_once()
    save.assert_called_once_with("config text")
    install.assert_called_once_with(start=False)
    preference.assert_called_once_with(True)
    restart.assert_not_called()


def test_tui_setup_cancel_restores_dpi_config_and_running_service():
    choices = SetupChoices(original_dpi=800, mappings={"BTN_LEFT": "passthrough"})
    backend = Mock()
    result = SetupTuiResult(False, MOUSE, backend, choices)
    with patch.object(cli, "is_service_active", return_value=True), \
         patch.object(cli, "stop_service"), \
         patch.object(cli, "restart_service") as restart, \
         patch.object(cli, "get_mouse_devices", return_value=[MOUSE]), \
         patch.object(cli, "_load_setup_config", return_value=ESTABLISHED_CONFIG), \
         patch.object(setup_entry, "run_setup_tui", return_value=result), \
         patch.object(setup_entry, "restore_dpi") as restore, \
         patch.object(cli, "save_config") as save:
        assert setup_entry.run_tui_setup_wizard() == 0
    restore.assert_called_once_with(backend, MOUSE, 800)
    save.assert_not_called()
    restart.assert_not_called()


def test_tui_cancel_discards_transient_choices_without_changing_established_config():
    choices = SetupChoices(
        original_dpi=800,
        stages=[400, 800],
        active_dpi=400,
        mappings={"BTN_FORWARD": "disable"},
    )
    result = SetupTuiResult(False, MOUSE, Mock(), choices)
    existing = {**ESTABLISHED_CONFIG, "future": {"preserve": "exactly"}}
    original = {**existing, "future": dict(existing["future"])}
    with patch.object(cli, "is_service_active", return_value=True), \
         patch.object(cli, "stop_service"), \
         patch.object(cli, "restart_service") as restart, \
         patch.object(cli, "get_mouse_devices", return_value=[MOUSE]), \
         patch.object(cli, "_load_setup_config", return_value=existing), \
         patch.object(setup_entry, "run_setup_tui", return_value=result), \
         patch.object(cli, "save_config") as save:
        assert setup_entry.run_tui_setup_wizard() == 0
    assert existing == original
    save.assert_not_called()
    restart.assert_not_called()


def test_tui_cancel_does_not_persist_staged_disable():
    choices = SetupChoices(original_dpi=800, enable_service=False)
    result = SetupTuiResult(False, MOUSE, Mock(), choices)
    with patch.object(cli, "is_service_active", return_value=True), \
         patch.object(cli, "stop_service"), \
         patch.object(cli, "restart_service") as restart, \
         patch.object(cli, "disable_service") as disable, \
         patch.object(cli, "get_mouse_devices", return_value=[MOUSE]), \
         patch.object(cli, "_load_setup_config", return_value=ESTABLISHED_CONFIG), \
         patch.object(setup_entry, "run_setup_tui", return_value=result):
        assert setup_entry.run_tui_setup_wizard() == 0
    restart.assert_not_called()
    disable.assert_not_called()


def test_tui_process_never_owns_background_service_lifecycle():
    choices = SetupChoices(original_dpi=800)
    result = SetupTuiResult(False, MOUSE, Mock(), choices)
    operations = []
    state = {"active": True}

    def is_active():
        operations.append("active" if state["active"] else "inactive")
        return state["active"]

    def stop():
        operations.append("stop")
        state["active"] = False

    def restart():
        operations.append("restart")
        state["active"] = True

    with patch.object(cli, "is_service_active", side_effect=is_active), \
         patch.object(cli, "stop_service", side_effect=stop), \
         patch.object(cli, "restart_service", side_effect=restart), \
         patch.object(cli, "get_mouse_devices", return_value=[MOUSE]), \
         patch.object(cli, "_load_setup_config", return_value=ESTABLISHED_CONFIG), \
         patch.object(setup_entry, "run_setup_tui", return_value=result):
        assert setup_entry.run_tui_setup_wizard() == 0
    assert operations == []
    assert state["active"] is True


def test_tui_setup_cancel_leaves_restoration_to_external_supervisor(capsys):
    choices = SetupChoices(original_dpi=800, mappings={"BTN_LEFT": "passthrough"})
    result = SetupTuiResult(False, MOUSE, Mock(), choices)
    with patch.object(cli, "is_service_active", side_effect=[True, False]), \
         patch.object(cli, "stop_service"), \
         patch.object(cli, "restart_service"), \
         patch.object(cli, "get_mouse_devices", return_value=[MOUSE]), \
         patch.object(cli, "_load_setup_config", return_value=ESTABLISHED_CONFIG), \
         patch.object(setup_entry, "run_setup_tui", return_value=result), \
         patch.object(cli, "save_config") as save:
        assert setup_entry.run_tui_setup_wizard() == 0
    save.assert_not_called()
    assert "could not restore the background service" not in capsys.readouterr().err.lower()


def test_tui_setup_rollback_failure_does_not_prevent_service_restoration():
    choices = SetupChoices(original_dpi=800, mappings={"BTN_LEFT": "passthrough"})
    result = SetupTuiResult(False, MOUSE, Mock(), choices)
    with patch.object(cli, "is_service_active", return_value=True), \
         patch.object(cli, "stop_service"), \
         patch.object(cli, "restart_service") as restart, \
         patch.object(cli, "get_mouse_devices", return_value=[MOUSE]), \
         patch.object(cli, "_load_setup_config", return_value=ESTABLISHED_CONFIG), \
         patch.object(setup_entry, "run_setup_tui", return_value=result), \
         patch.object(setup_entry, "restore_dpi", side_effect=OSError("disconnected")):
        assert setup_entry.run_tui_setup_wizard() == 0
    restart.assert_not_called()


def test_tui_setup_cancel_does_not_start_initially_inactive_service():
    choices = SetupChoices(original_dpi=800, mappings={"BTN_LEFT": "passthrough"})
    result = SetupTuiResult(False, MOUSE, Mock(), choices)
    with patch.object(cli, "is_service_active", return_value=False), \
         patch.object(cli, "stop_service") as stop, \
         patch.object(cli, "restart_service") as restart, \
         patch.object(cli, "get_mouse_devices", return_value=[MOUSE]), \
         patch.object(cli, "_load_setup_config", return_value={}), \
         patch.object(setup_entry, "run_setup_tui", return_value=result):
        assert setup_entry.run_tui_setup_wizard() == 0
    stop.assert_not_called()
    restart.assert_not_called()


def test_first_run_cancel_does_not_start_service_without_a_saved_configuration():
    result = SetupTuiResult(False, MOUSE, Mock(), SetupChoices())
    with patch.object(cli, "is_service_active", return_value=True), \
         patch.object(cli, "stop_service") as stop, \
         patch.object(cli, "restart_service") as restart, \
         patch.object(cli, "get_mouse_devices", return_value=[MOUSE]), \
         patch.object(cli, "_load_setup_config", return_value={}), \
         patch.object(setup_entry, "run_setup_tui", return_value=result):
        assert setup_entry.run_tui_setup_wizard() == 0
    stop.assert_not_called()
    restart.assert_not_called()


def test_explicit_saved_disable_does_not_restore_established_service(tmp_path):
    choices = SetupChoices(
        stages=[800, 1500, 2000, 2500, 3000],
        active_dpi=800,
        mappings={"BTN_FORWARD": "dpi-cycle"},
        enable_service=False,
    )
    result = SetupTuiResult(True, MOUSE, Mock(), choices)
    with patch.object(cli, "is_service_active", return_value=True), \
         patch.object(cli, "stop_service"), \
         patch.object(cli, "restart_service") as restart, \
         patch.object(cli, "get_mouse_devices", return_value=[MOUSE]), \
         patch.object(cli, "_load_setup_config", return_value=ESTABLISHED_CONFIG), \
         patch.object(setup_entry, "run_setup_tui", return_value=result), \
         patch.object(cli, "_apply_hardware"), \
         patch.object(cli, "merge_setup_config", return_value="updated config"), \
         patch.object(cli, "save_config", return_value=tmp_path / "config.toml") as save, \
         patch.object(cli, "install_service") as install, \
         patch.object(cli, "disable_service") as disable, \
         patch("mouse_control.foreground_session.record_service_preference") as preference:
        assert setup_entry.run_tui_setup_wizard() == 0
    save.assert_called_once_with("updated config")
    install.assert_not_called()
    restart.assert_not_called()
    disable.assert_called_once_with()
    preference.assert_called_once_with(False)


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
