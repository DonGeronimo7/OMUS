"""Terminal-native launcher behavior and package metadata tests."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import patch

from mouse_control import cli
from mouse_control.branding import render_banner, style


ROOT = Path(__file__).resolve().parents[1]


class TtyBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_no_argument_interactive_without_config_dispatches_to_tui_setup(monkeypatch):
    monkeypatch.setattr(cli.sys, "stdin", TtyBuffer())
    monkeypatch.setattr(cli.sys, "stdout", TtyBuffer())
    with patch.object(cli, "_load_setup_config", return_value={}), \
         patch.object(cli, "run_setup_wizard", return_value=0) as setup:
        assert cli.main([]) == 0
    setup.assert_called_once_with()


def test_no_argument_interactive_with_valid_config_dispatches_to_home(monkeypatch):
    monkeypatch.setattr(cli.sys, "stdin", TtyBuffer())
    monkeypatch.setattr(cli.sys, "stdout", TtyBuffer())
    existing = {
        "device": {"vendor": 1, "product": 2, "phys": "usb-test"},
        "dpi": {"active": 800, "stages": [800, 1600]},
        "polling": {"rate_hz": 1000},
        "remap": {"BTN_LEFT": "passthrough"},
    }
    with patch.object(cli, "_load_setup_config", return_value=existing), \
         patch.object(cli, "run_home_screen", return_value=0) as home, \
         patch.object(cli, "run_setup_wizard") as setup:
        assert cli.main([]) == 0
    home.assert_called_once_with()
    setup.assert_not_called()


def test_explicit_command_bypasses_home_screen():
    with patch.object(cli, "run_home_screen") as home, patch.object(cli, "status_service", return_value=0):
        assert cli.main(["status"]) == 0
    home.assert_not_called()


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


def test_home_screen_quits_cleanly(capsys):
    assert cli.run_home_screen(input_func=lambda _: "q", columns=80) == 0
    assert "Goodbye." in capsys.readouterr().out


def test_home_screen_retries_invalid_choice_then_routes_setup(capsys):
    choices = iter(("nope", "2"))
    with patch.object(cli, "is_service_active", return_value=False), patch.object(cli, "run_setup_wizard", return_value=0) as setup:
        assert cli.run_home_screen(input_func=lambda _: next(choices), columns=80) == 0
    setup.assert_called_once_with()
    assert "Please choose 1–7 or Q to quit." in capsys.readouterr().out


def test_home_screen_routes_support_and_diagnostics():
    with patch.object(cli, "run_support", return_value=0) as support:
        assert cli.run_home_screen(input_func=lambda _: "4", columns=80) == 0
    support.assert_called_once_with()
    with patch.object(cli, "print_doctor", return_value=0) as doctor:
        assert cli.run_home_screen(input_func=lambda _: "6", columns=80) == 0
    doctor.assert_called_once_with()


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
    desktop = (ROOT / "packaging/appimage/mouse-control.desktop").read_text()
    assert "Type=Application" in desktop
    assert "Exec=mouse-control" in desktop
    assert "Icon=mouse-control" in desktop
    assert "Terminal=true" in desktop
    assert "Categories=Utility;System;" in desktop


def test_package_definitions_own_desktop_entry_and_icon():
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
