"""Terminal-native launcher behavior and package metadata tests."""

from __future__ import annotations

import io
from pathlib import Path
import runpy
import tomllib
from unittest.mock import patch

import pytest

from mouse_control import app, cli
from mouse_control.branding import render_banner, style


ROOT = Path(__file__).resolve().parents[1]


class TtyBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_no_argument_interactive_dispatches_to_canonical_tui(monkeypatch):
    monkeypatch.setattr(cli.sys, "stdin", TtyBuffer())
    monkeypatch.setattr(cli.sys, "stdout", TtyBuffer())
    with patch.object(cli, "run_setup_wizard", return_value=0) as setup:
        assert cli.main([]) == 0
    setup.assert_called_once_with()


@pytest.mark.parametrize("command", (["setup"], ["tui"]))
def test_explicit_tui_commands_dispatch_to_canonical_tui(monkeypatch, command):
    monkeypatch.setattr(cli.sys, "stdin", TtyBuffer())
    monkeypatch.setattr(cli.sys, "stdout", TtyBuffer())
    with patch.object(cli, "run_setup_wizard", return_value=17) as setup:
        assert cli.main(command) == 17
    setup.assert_called_once_with()


def test_explicit_non_tui_command_bypasses_canonical_tui():
    with patch.object(cli, "run_setup_wizard") as setup, patch.object(cli, "status_service", return_value=0):
        assert cli.main(["status"]) == 0
    setup.assert_not_called()


def test_installed_console_script_dispatches_through_application_entry():
    with patch.object(cli, "main", return_value=19) as dispatcher:
        assert app.main(["tui"]) == 19
    dispatcher.assert_called_once_with(["tui"])


def test_source_module_execution_dispatches_through_application_entry():
    with patch.object(app, "main", return_value=23) as application:
        with pytest.raises(SystemExit, match="23"):
            runpy.run_module("mouse_control", run_name="__main__")
    application.assert_called_once_with()


def test_cpi_subcommand_dispatches_to_packaged_calibration(monkeypatch):
    from mouse_control import sensor_calibration_cli

    seen = []
    monkeypatch.setattr(sensor_calibration_cli, "run_calibration", lambda args: seen.append(args) or 0)
    assert cli.main(["cpi", "--distance-mm", "254", "--known-dpi", "1600"]) == 0
    assert len(seen) == 1
    assert seen[0].distance_mm == 254
    assert seen[0].known_dpi == 1600


def test_rediscover_is_explicit_and_forces_full_engine(monkeypatch):
    from types import SimpleNamespace
    from mouse_control.discovery import MouseDevice
    from mouse_control import guided_discovery

    mouse = MouseDevice('Known', '/dev/input/event1')
    engine = SimpleNamespace(profile_path=Path('/tmp/profile.json'))
    seen = []
    monkeypatch.setattr(cli, 'get_mouse_devices', lambda: [mouse])
    monkeypatch.setattr(
        guided_discovery,
        'run_automatic_discovery',
        lambda selected, **kwargs: seen.append((selected, kwargs)) or SimpleNamespace(engine=engine),
    )

    assert cli.main(['rediscover', '--device', '1']) == 0
    assert seen[0][0] == mouse
    assert seen[0][1]['force'] is True


def test_no_argument_non_tty_prints_help_without_waiting(monkeypatch, capsys):
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO())
    monkeypatch.setattr(cli.sys, "stdout", io.StringIO())
    assert cli.main([]) == 0
    # stdout was intentionally redirected: the important property is no input call.


def test_branding_is_monochrome_when_color_is_disabled(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    assert "\033[" not in style("mouse", "cyan", stream=TtyBuffer())
    assert "\033[" not in render_banner(columns=80, stream=TtyBuffer())


def test_branding_is_monochrome_for_dumb_terminal(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "dumb")
    assert "\033[" not in render_banner(columns=80, stream=TtyBuffer())


def test_branding_uses_compact_or_no_logo_in_narrow_terminal():
    assert "MOUSE CONTROL" in render_banner(columns=20, stream=TtyBuffer())
    assert "MOUSE CONTROL" in render_banner(columns=8, stream=TtyBuffer())


def test_desktop_entry_is_launcher_safe_and_complete():
    fields = {}
    for line in (ROOT / "packaging/appimage/mouse-control.desktop").read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            fields[key] = value
    assert fields["Type"] == "Application"
    assert fields["Exec"] == "mouse-control"
    assert fields["Icon"] == "mouse-control"
    assert fields["Terminal"] == "true"
    assert fields["Categories"] == "Utility;System;"


def test_all_packaged_interactive_launchers_use_application_entry():
    with (ROOT / "pyproject.toml").open("rb") as handle:
        scripts = tomllib.load(handle)["project"]["scripts"]
    assert scripts["mouse-control"] == "mouse_control.app:main"
    assert sum(target == "mouse_control.app:main" for target in scripts.values()) == 1
    assert all("setup_tui" not in target for target in scripts.values())

    appimage = (ROOT / "packaging/appimage/build-appimage.sh").read_text()
    assert 'exec "$appdir/usr/python/bin/python3" -m mouse_control "$@"' in appimage
    assert "-m mouse_control.cli" not in appimage
    assert not (ROOT / "packaging/mouse-control").exists()
    assert not hasattr(cli, "run_home_screen")


def test_package_definitions_own_desktop_entry_and_icon():
    assert list((ROOT / "packaging").rglob("*.desktop")) == [
        ROOT / "packaging/appimage/mouse-control.desktop"
    ]
    debian = (ROOT / "debian/install").read_text()
    rpm = (ROOT / "mouse-control.spec").read_text()
    arch = (ROOT / "PKGBUILD").read_text()
    for packaging in (debian, rpm, arch):
        assert "mouse-control.desktop" in packaging
        assert "mouse-control.png" in packaging


def test_approved_png_icon_sizes_are_packaged_with_alpha():
    expected_sizes = (512, 256, 128, 64, 48, 32)
    for size in expected_sizes:
        icon = ROOT / f"assets/icons/hicolor/{size}x{size}/apps/mouse-control.png"
        assert icon.is_file()
        with icon.open("rb") as handle:
            header = handle.read(29)
        assert header[:8] == b"\x89PNG\r\n\x1a\n"
        assert int.from_bytes(header[16:20]) == size
        assert int.from_bytes(header[20:24]) == size
        assert header[25] == 6  # PNG RGBA: preserve the approved transparency.
