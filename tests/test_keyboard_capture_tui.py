from pathlib import Path
from unittest.mock import patch

from mouse_control import keyboard_capture


def test_tui_capture_mode_does_not_touch_terminal(monkeypatch):
    monkeypatch.setattr(keyboard_capture, "_open_keyboards", lambda **kwargs: [])
    with patch.object(keyboard_capture, "_capture_terminal") as terminal:
        assert keyboard_capture.capture_keyboard_key(manage_terminal=False, reporter=None) is None
        assert keyboard_capture.capture_keyboard_chord(manage_terminal=False, reporter=None) is None
    terminal.assert_not_called()


def test_curses_tui_keeps_key_and_chord_capture_native():
    source = Path("src/mouse_control/setup_tui_curses.py").read_text()
    assert '"Record keyboard key"' in source
    assert '"Record keyboard chord"' in source
    assert source.count("manage_terminal=False") >= 2
    assert "_suspend_curses(\n                        lambda: capture_keyboard" not in source
