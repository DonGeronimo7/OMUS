"""Short service command surfaces share the existing systemd helpers."""
from pathlib import Path
import sys
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mouse_control import cli, service


def test_short_commands_call_existing_service_helpers():
    with patch.object(cli, "start_service") as start:
        assert cli.main(["start"]) == 0
    with patch.object(cli, "stop_service") as stop:
        assert cli.main(["stop"]) == 0
    with patch.object(cli, "restart_service") as restart:
        assert cli.main(["restart"]) == 0
    with patch.object(cli, "status_service", return_value=0) as status:
        assert cli.main(["status"]) == 0
    start.assert_called_once(); stop.assert_called_once(); restart.assert_called_once(); status.assert_called_once()


def test_start_and_restart_explain_missing_installation(capsys):
    with patch.object(service, "service_path", return_value=Path("/missing/service")):
        try:
            service.start_service()
        except service.ServiceNotInstalled as exc:
            assert "install-service" in str(exc)
        else:
            raise AssertionError("missing service was started")
        assert service.status_service() == 1
    assert "not installed" in capsys.readouterr().out


def test_status_reports_active_enabled_and_failure_states(capsys, tmp_path):
    unit = tmp_path / "mouse-control.service"; unit.write_text("[Service]\n")
    active = Mock(returncode=0, stdout="active\n")
    enabled = Mock(returncode=0, stdout="enabled\n")
    with patch.object(service, "service_path", return_value=unit), patch.object(service.subprocess, "run", side_effect=[active, enabled]):
        assert service.status_service() == 0
    assert "installed, active, enabled" in capsys.readouterr().out
    failed = Mock(returncode=3, stdout="failed\n")
    with patch.object(service, "service_path", return_value=unit), patch.object(service.subprocess, "run", side_effect=[failed, enabled]):
        assert service.status_service() == 3
