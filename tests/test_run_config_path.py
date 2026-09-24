# SPDX-License-Identifier: AGPL-3.0-or-later
"""The run command can use a separate configuration without service changes."""

from pathlib import Path
from unittest.mock import patch

from mouse_control import cli, config


def test_run_without_config_uses_default_loader_path():
    with patch.object(cli, "run_from_config", return_value=0) as run:
        assert cli.main(["run"]) == 0
    run.assert_called_once_with(None)


def test_run_without_config_loads_default_file(tmp_path, monkeypatch, capsys):
    default = tmp_path / "default.toml"
    default.write_text("[device]\n")
    monkeypatch.setattr(config, "get_config_path", lambda: default)
    assert cli.main(["run"]) == 1
    assert "missing [device].event_path" in capsys.readouterr().err


def test_run_with_config_passes_exact_path_and_does_not_touch_service():
    path = Path("/tmp/test.toml")
    with patch.object(cli, "run_from_config", return_value=0) as run, \
         patch.object(cli, "install_service") as install, \
         patch.object(cli, "start_service") as start, \
         patch.object(cli, "stop_service") as stop, \
         patch.object(cli, "restart_service") as restart:
        assert cli.main(["run", "--config", str(path)]) == 0
    run.assert_called_once_with(path)
    for action in (install, start, stop, restart):
        action.assert_not_called()


def test_explicit_missing_config_never_uses_default(tmp_path, monkeypatch, capsys):
    default = tmp_path / "default.toml"
    default.write_text('[device]\nevent_path = "/dev/input/default"\n')
    missing = tmp_path / "missing.toml"
    monkeypatch.setattr(config, "get_config_path", lambda: default)
    with patch.object(cli, "get_mouse_devices") as devices:
        assert cli.main(["run", "--config", str(missing)]) == 1
    assert str(missing) in capsys.readouterr().err
    assert default.read_text() == '[device]\nevent_path = "/dev/input/default"\n'
    devices.assert_not_called()


def test_unreadable_explicit_config_fails_cleanly(capsys):
    path = Path("/tmp/unreadable.toml")
    with patch.object(cli, "load_config", side_effect=PermissionError("access denied")) as load:
        assert cli.main(["run", "--config", str(path)]) == 1
    load.assert_called_once_with(path)
    assert "Could not read configuration: access denied" in capsys.readouterr().err
