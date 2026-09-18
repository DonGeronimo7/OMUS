"""The user manager, not the TUI process, owns foreground restoration."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from mouse_control import foreground_session


def _use_state_directory(monkeypatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(foreground_session, "_runtime_directory", lambda: tmp_path)
    return tmp_path / "mouse-control" / "foreground-session.json"


def test_prepare_records_active_state_before_stopping(monkeypatch, tmp_path):
    state_path = _use_state_directory(monkeypatch, tmp_path)
    events = []

    def stop():
        events.append(("stop", json.loads(state_path.read_text())))

    monkeypatch.setattr(foreground_session, "is_service_active", lambda: True)
    monkeypatch.setattr(foreground_session, "stop_service", stop)
    assert foreground_session.prepare() == 0
    assert events == [("stop", {"preference": None, "was_active": True})]


def test_prepare_does_not_stop_an_initially_inactive_service(monkeypatch, tmp_path):
    state_path = _use_state_directory(monkeypatch, tmp_path)
    monkeypatch.setattr(foreground_session, "is_service_active", lambda: False)
    with patch.object(foreground_session, "stop_service") as stop:
        assert foreground_session.prepare() == 0
    stop.assert_not_called()
    assert json.loads(state_path.read_text())["was_active"] is False


@pytest.mark.parametrize("termination", ["save", "cancel", "sigterm", "exception"])
def test_all_ordinary_terminations_restore_a_previously_active_service(
    monkeypatch, tmp_path, termination,
):
    state_path = _use_state_directory(monkeypatch, tmp_path)
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps({"was_active": True, "preference": None}))
    active = iter([True])
    monkeypatch.setattr(foreground_session, "is_service_active", lambda: next(active))
    with patch.object(foreground_session, "restart_service") as restart:
        assert foreground_session.restore() == 0
    restart.assert_called_once_with()
    assert not state_path.exists()


def test_initially_inactive_service_remains_inactive(monkeypatch, tmp_path):
    state_path = _use_state_directory(monkeypatch, tmp_path)
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps({"was_active": False, "preference": None}))
    with patch.object(foreground_session, "restart_service") as restart:
        assert foreground_session.restore() == 0
    restart.assert_not_called()


def test_saved_explicit_disable_suppresses_restoration(monkeypatch, tmp_path):
    state_path = _use_state_directory(monkeypatch, tmp_path)
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps({"was_active": True, "preference": None}))
    foreground_session.record_service_preference(False)
    with patch.object(foreground_session, "restart_service") as restart:
        assert foreground_session.restore() == 0
    restart.assert_not_called()


def test_unsaved_staged_disable_never_changes_supervisor_state(monkeypatch, tmp_path):
    state_path = _use_state_directory(monkeypatch, tmp_path)
    state_path.parent.mkdir(parents=True)
    original = {"was_active": True, "preference": None}
    state_path.write_text(json.dumps(original))
    assert json.loads(state_path.read_text()) == original


def test_saved_enable_starts_even_if_service_was_initially_inactive(monkeypatch, tmp_path):
    state_path = _use_state_directory(monkeypatch, tmp_path)
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps({"was_active": False, "preference": None}))
    foreground_session.record_service_preference(True)
    monkeypatch.setattr(foreground_session, "is_service_active", lambda: True)
    with patch.object(foreground_session, "restart_service") as restart:
        assert foreground_session.restore() == 0
    restart.assert_called_once_with()


def test_restoration_is_consumed_once(monkeypatch, tmp_path):
    state_path = _use_state_directory(monkeypatch, tmp_path)
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps({"was_active": True, "preference": None}))
    monkeypatch.setattr(foreground_session, "is_service_active", lambda: True)
    with patch.object(foreground_session, "restart_service") as restart:
        assert foreground_session.restore() == 0
        assert foreground_session.restore() == 0
    restart.assert_called_once_with()


@pytest.mark.parametrize("arguments", [[], ["setup"], ["tui"]])
def test_every_canonical_interactive_entry_uses_same_supervisor(arguments):
    assert foreground_session.should_supervise(arguments, interactive=True)


def test_noninteractive_and_runtime_commands_bypass_foreground_supervisor():
    assert not foreground_session.should_supervise([], interactive=False)
    assert not foreground_session.should_supervise(["run"], interactive=True)


def test_launch_execs_transient_service_with_external_pre_and_post_hooks(monkeypatch):
    monkeypatch.setattr(foreground_session.shutil, "which", lambda _name: "/usr/bin/systemd-run")
    monkeypatch.setattr(foreground_session.sys, "executable", "/usr/bin/python3")
    captured = {}

    def execute(path, arguments):
        captured.update(path=path, arguments=arguments)
        raise RuntimeError("exec captured")

    monkeypatch.setattr(foreground_session.os, "execv", execute)
    with pytest.raises(RuntimeError, match="exec captured"):
        foreground_session.launch(["setup"])

    arguments = captured["arguments"]
    assert captured["path"] == "/usr/bin/systemd-run"
    assert "--pty" in arguments
    assert "--wait" in arguments
    assert "--collect" in arguments
    assert any(value.startswith("--property=ExecStartPre=") and '"prepare"' in value for value in arguments)
    assert any(value.startswith("--property=ExecStopPost=") and '"restore"' in value for value in arguments)
    assert arguments[-4:] == ["/usr/bin/python3", "-m", "mouse_control", "setup"]


def test_supervised_child_does_not_reenter_systemd(monkeypatch):
    monkeypatch.setenv(foreground_session.SESSION_ENV, "1")
    assert not foreground_session.should_supervise(["setup"], interactive=True)
