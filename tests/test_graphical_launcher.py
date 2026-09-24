# SPDX-License-Identifier: AGPL-3.0-or-later
"""Desktop helper selects an installed terminal without adding dependencies."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from mouse_control import graphical_launcher


def test_configured_terminal_has_priority(monkeypatch):
    monkeypatch.setenv("TERMINAL", "kitty --single-instance")
    monkeypatch.setattr(
        graphical_launcher.shutil,
        "which",
        lambda name: "/usr/bin/kitty" if name == "kitty" else None,
    )
    assert graphical_launcher.select_terminal() == ["/usr/bin/kitty", "--single-instance"]


def test_invalid_configured_terminal_falls_back_to_installed_candidate(monkeypatch):
    monkeypatch.setenv("TERMINAL", "not-installed")
    monkeypatch.setattr(
        graphical_launcher.shutil,
        "which",
        lambda name: "/usr/bin/foot" if name == "foot" else None,
    )
    assert graphical_launcher.select_terminal() == ["/usr/bin/foot"]


def test_xdg_terminal_exec_is_opportunistic_not_required(monkeypatch):
    monkeypatch.delenv("TERMINAL", raising=False)
    monkeypatch.setattr(
        graphical_launcher.shutil,
        "which",
        lambda name: "/usr/bin/kitty" if name == "kitty" else None,
    )
    assert graphical_launcher.select_terminal() == ["/usr/bin/kitty"]


@pytest.mark.parametrize(
    ("terminal", "expected"),
    [
        ("xdg-terminal-exec", ["/usr/bin/xdg-terminal-exec", "--", "/usr/bin/mouse-control"]),
        ("kitty", ["/usr/bin/kitty", "--class", "OMUS", "--title", "OMUS", "/usr/bin/mouse-control"]),
        ("foot", ["/usr/bin/foot", "--app-id=omus", "--title=OMUS", "/usr/bin/mouse-control"]),
        ("alacritty", ["/usr/bin/alacritty", "--class", "OMUS,OMUS", "--title", "OMUS", "-e", "/usr/bin/mouse-control"]),
        ("wezterm", ["/usr/bin/wezterm", "start", "--class", "OMUS", "--always-new-process", "--", "/usr/bin/mouse-control"]),
        ("gnome-terminal", ["/usr/bin/gnome-terminal", "--title=OMUS", "--", "/usr/bin/mouse-control"]),
        ("kgx", ["/usr/bin/kgx", "--title=OMUS", "--", "/usr/bin/mouse-control"]),
        ("konsole", ["/usr/bin/konsole", "--new-tab", "-p", "tabtitle=OMUS", "-e", "/usr/bin/mouse-control"]),
        ("xfce4-terminal", ["/usr/bin/xfce4-terminal", "--title=OMUS", "--execute", "/usr/bin/mouse-control"]),
        ("mate-terminal", ["/usr/bin/mate-terminal", "--title=OMUS", "--", "/usr/bin/mouse-control"]),
        ("xterm", ["/usr/bin/xterm", "-T", "OMUS", "-e", "/usr/bin/mouse-control"]),
    ],
)
def test_terminal_specific_invocation(terminal, expected):
    assert graphical_launcher._terminal_command(
        [f"/usr/bin/{terminal}"], ["/usr/bin/mouse-control"]
    ) == expected


def test_configured_terminal_arguments_are_preserved():
    assert graphical_launcher._terminal_command(
        ["/usr/bin/kitty", "--single-instance"], ["/usr/bin/mouse-control"]
    )[:2] == ["/usr/bin/kitty", "--single-instance"]


def test_launcher_starts_canonical_mouse_control_in_selected_terminal(monkeypatch):
    monkeypatch.setattr(graphical_launcher, "select_terminal", lambda: ["/usr/bin/kitty"])
    monkeypatch.setattr(
        graphical_launcher, "_mouse_control_command", lambda: ["/usr/bin/mouse-control"]
    )
    process = Mock()
    with patch.object(graphical_launcher.subprocess, "Popen", return_value=process) as popen:
        assert graphical_launcher.main() == 0
    arguments = popen.call_args.args[0]
    assert arguments[-1] == "/usr/bin/mouse-control"
    popen.assert_called_once_with(arguments, close_fds=True, start_new_session=True)


def test_missing_terminal_reports_actionable_error(monkeypatch, capsys):
    monkeypatch.setattr(graphical_launcher, "select_terminal", lambda: None)
    monkeypatch.setattr(graphical_launcher.shutil, "which", lambda _name: None)
    assert graphical_launcher.main() == 1
    error = capsys.readouterr().err
    assert "requires a terminal emulator" in error
    assert "$TERMINAL" in error


def test_appimage_relaunches_the_image_not_a_temporary_mount(monkeypatch, tmp_path):
    image = tmp_path / "Mouse-Control.AppImage"
    image.write_bytes(b"appimage")
    image.chmod(0o755)
    monkeypatch.setenv("MOUSE_CONTROL_APPIMAGE", str(image))
    assert graphical_launcher._mouse_control_command() == [str(image)]
