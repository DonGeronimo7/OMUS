from types import SimpleNamespace

import pytest

from mouse_control.discovery import MouseDevice
from mouse_control.setup_tui import DisplayRow, SetupSection
from mouse_control.setup_tui_complete import CompleteCursesSetupApp
from mouse_control.setup_tui_integrated import IntegratedCursesSetupApp, _TuiWriter
from mouse_control.wizard import ButtonCaptureError


class ViewController:
    section = SetupSection.HARDWARE
    row_cursor = 8

    def detail_rows(self):
        return [DisplayRow("header")] + [
            DisplayRow(f"action-{index}", index) for index in range(14)
        ]


def test_complete_tui_keeps_selected_discovery_action_visible_at_minimum_height():
    app = object.__new__(CompleteCursesSetupApp)
    app.controller = ViewController()
    visible = app._hardware_viewport(20)
    assert len(visible) == 12
    assert any(row.cursor_index == 8 for row in visible)
    assert visible != app.controller.detail_rows()


def test_complete_tui_overrides_integrated_button_capture():
    assert CompleteCursesSetupApp._button_editor is not IntegratedCursesSetupApp._button_editor


def test_integrated_tui_overrides_legacy_escape_paths():
    from mouse_control.setup_tui_curses import CursesSetupApp

    assert IntegratedCursesSetupApp._run_discovery_tool is not CursesSetupApp._run_discovery_tool
    assert IntegratedCursesSetupApp._choose_button_action is not CursesSetupApp._choose_button_action


def test_tui_writer_keeps_experiment_output_inside_transcript():
    seen = []
    app = SimpleNamespace(_append_lab_line=seen.append)
    writer = _TuiWriter(app)
    writer.write("first\nsecond")
    assert seen == ["first"]
    writer.flush()
    assert seen == ["first", "second"]


def test_labelled_cycle_parser_accepts_user_edited_cycle():
    assert IntegratedCursesSetupApp._parse_cycle_labels("400, 800,1600,3200") == [
        400, 800, 1600, 3200
    ]


@pytest.mark.parametrize(
    "raw, message",
    [
        ("800", "at least two"),
        ("800,800", "distinct"),
        ("800,0", "positive"),
    ],
)
def test_labelled_cycle_parser_rejects_invalid_cycle(raw, message):
    with pytest.raises(ValueError, match=message):
        IntegratedCursesSetupApp._parse_cycle_labels(raw)


def test_button_capture_resolves_same_physical_mouse(monkeypatch):
    selected = MouseDevice(
        "Titan", "/dev/input/event-old", phys="usb-1/titan", vendor=0x1234,
        product=0x5678, bustype=3,
    )
    live = MouseDevice(
        "Titan", "/dev/input/event-new", phys="usb-1/titan", vendor=0x1234,
        product=0x5678, bustype=3,
    )
    app = object.__new__(CompleteCursesSetupApp)
    app.controller = SimpleNamespace(selected=selected)
    monkeypatch.setattr("mouse_control.setup_tui_complete.get_mouse_devices", lambda: [live])
    assert app._resolved_button_path() == "/dev/input/event-new"


def test_button_capture_refuses_ambiguous_identity(monkeypatch):
    selected = MouseDevice(
        "Titan", "/dev/input/event-old", vendor=0x1234, product=0x5678, bustype=3,
    )
    first = MouseDevice("Titan A", "/dev/input/event1", vendor=0x1234, product=0x5678, bustype=3)
    second = MouseDevice("Titan B", "/dev/input/event2", vendor=0x1234, product=0x5678, bustype=3)
    app = object.__new__(CompleteCursesSetupApp)
    app.controller = SimpleNamespace(selected=selected)
    monkeypatch.setattr(
        "mouse_control.setup_tui_complete.get_mouse_devices", lambda: [first, second]
    )
    with pytest.raises(ButtonCaptureError, match="ambiguous"):
        app._resolved_button_path()


def test_selected_mouse_is_excluded_from_keyboard_capture(tmp_path):
    mouse_path = tmp_path / "event-mouse"
    keyboard_path = tmp_path / "event-kbd"
    mouse_path.touch()
    keyboard_path.touch()

    class FakeInput:
        def __init__(self, path):
            self.path = str(path)
            self.closed = False

        def close(self):
            self.closed = True

    mouse = FakeInput(mouse_path)
    keyboard = FakeInput(keyboard_path)

    kept = CompleteCursesSetupApp._exclude_selected_mouse_from_keyboards(
        [mouse, keyboard], str(mouse_path)
    )

    assert kept == [keyboard]
    assert mouse.closed is True
    assert keyboard.closed is False


def test_sigmachip_busy_capture_is_reported_as_recoverable():
    exc = BlockingIOError(11, "Resource temporarily unavailable")
    message = CompleteCursesSetupApp._input_error_message(exc)
    assert "temporarily busy" in message
    assert "mappings unchanged" in message
