# SPDX-License-Identifier: AGPL-3.0-or-later
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


def test_nonblocking_stop_only_queues_the_existing_service_unit(tmp_path):
    canonical = tmp_path / "omus.service"
    canonical.write_text("[Service]\n")
    with patch.object(service, "service_path", return_value=canonical), \
         patch.object(service, "legacy_service_path", return_value=tmp_path / "missing.service"), \
         patch.object(service.subprocess, "run") as run:
        service.request_stop_service()
    run.assert_called_once_with(
        [service.SYSTEMCTL, "--user", "--no-block", "stop", service.SERVICE_NAME],
        check=True,
    )


def test_disable_service_is_idempotent_when_not_installed(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "service_path", lambda: tmp_path / "missing.service")
    monkeypatch.setattr(service, "legacy_service_path", lambda: tmp_path / "missing-legacy.service")
    with patch.object(service.subprocess, "run") as run:
        service.disable_service()
    run.assert_not_called()


def test_start_and_restart_explain_missing_installation(capsys):
    with patch.object(service, "service_path", return_value=Path("/missing/service")), \
         patch.object(service, "legacy_service_path", return_value=Path("/missing/legacy-service")):
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


def test_user_service_has_compatible_process_hardening_and_quoted_exec():
    text = service.build_service_text('/opt/Mouse Control/bin/mouse-control')
    assert 'ExecStart="/opt/Mouse Control/bin/mouse-control" run' in text
    for directive in (
        "NoNewPrivileges=true", "PrivateTmp=true", "ProtectSystem=strict",
        "ProtectKernelTunables=true", "ProtectKernelModules=true",
        "ProtectControlGroups=true", "RestrictSUIDSGID=true", "LockPersonality=true",
    ):
        assert directive in text
    assert "Environment=" not in text


def test_install_service_refuses_symlink_destination(monkeypatch, tmp_path):
    executable = tmp_path / "mouse-control"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    real_unit = tmp_path / "real.service"
    real_unit.write_text("unchanged", encoding="utf-8")
    unit = tmp_path / "mouse-control.service"
    unit.symlink_to(real_unit)
    monkeypatch.setattr(service.shutil, "which", lambda _name: str(executable))
    monkeypatch.setattr(service, "service_path", lambda: unit)
    try:
        service.install_service()
    except RuntimeError as exc:
        assert "symlinked" in str(exc)
    else:
        raise AssertionError("symlinked service destination was replaced")
    assert real_unit.read_text(encoding="utf-8") == "unchanged"


def test_install_migrates_legacy_unit_without_duplicate_daemons(monkeypatch, tmp_path):
    executable = tmp_path / "omus"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    canonical = tmp_path / "omus.service"
    legacy = tmp_path / "mouse-control.service"
    legacy.write_text("[Service]\nExecStart=mouse-control run\n")
    monkeypatch.setattr(service.shutil, "which", lambda name: str(executable) if name == "omus" else None)
    monkeypatch.setattr(service, "service_path", lambda: canonical)
    monkeypatch.setattr(service, "legacy_service_path", lambda: legacy)
    with patch.object(service.subprocess, "run") as run:
        service.install_service()
    assert canonical.is_file()
    calls = [call.args[0] for call in run.call_args_list]
    assert [service.SYSTEMCTL, "--user", "disable", "--now", service.LEGACY_SERVICE_NAME] in calls
    assert calls[-1] == [service.SYSTEMCTL, "--user", "enable", "--now", service.SERVICE_NAME]
