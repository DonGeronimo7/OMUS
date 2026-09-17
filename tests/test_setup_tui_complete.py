import errno
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


def test_button_capture_translates_eagain_into_recoverable_editor_error(monkeypatch):
    selected = MouseDevice(
        "SIGMACHIP USB Mouse",
        "/dev/input/by-id/usb-SIGMACHIP_USB_Mouse-event-mouse",
        phys="usb-sigmachip",
        vendor=0x1C4F,
        product=0x0048,
        bustype=3,
    )
    app = object.__new__(CompleteCursesSetupApp)
    app.controller = SimpleNamespace(selected=selected)
    app.stdscr = object()
    monkeypatch.setattr(app, "_resolved_button_path", lambda: selected.path)

    def busy_input_device(_path):
        raise BlockingIOError(errno.EAGAIN, "Resource temporarily unavailable")

    monkeypatch.setattr("mouse_control.setup_tui_complete.InputDevice", busy_input_device)
    with pytest.raises(ButtonCaptureError, match="temporarily busy"):
        app._button_editor()


def test_busy_error_message_is_specific_for_eagain():
    message = CompleteCursesSetupApp._input_error_message(
        BlockingIOError(errno.EAGAIN, "Resource temporarily unavailable")
    )
    assert "temporarily busy" in message
    assert "mappings unchanged" in message
