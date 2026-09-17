from pathlib import Path

root = Path('.')
keyboard = root / 'src/mouse_control/keyboard_capture.py'
tui = root / 'src/mouse_control/setup_tui_curses.py'
test = root / 'tests/test_keyboard_capture_tui.py'

text = keyboard.read_text()
text = text.replace('from contextlib import contextmanager\n', 'from contextlib import contextmanager, nullcontext\n')
text = text.replace(
    'def capture_keyboard_key(*, exclude_paths: tuple[str, ...] = ()) -> str | None:\n',
    'def capture_keyboard_key(\n    *,\n    exclude_paths: tuple[str, ...] = (),\n    manage_terminal: bool = True,\n    reporter=print,\n) -> str | None:\n'
)
text = text.replace(
    '        with _capture_terminal():\n',
    '        terminal_context = _capture_terminal() if manage_terminal else nullcontext()\n        with terminal_context:\n',
    1,
)
text = text.replace('                print("No readable keyboard devices found. Check input permissions or use manual entry.")\n', '                if reporter is not None:\n                    reporter("No readable keyboard devices found. Check input permissions or use manual entry.")\n')
text = text.replace('                    print("Press the keyboard key you want to assign... (Ctrl+C to cancel)", flush=True)\n', '                    if reporter is not None:\n                        reporter("Press the keyboard key you want to assign... (Ctrl+C to cancel)")\n')
text = text.replace('                    print("Keyboard devices disconnected. Try again or use manual entry.")\n', '                    if reporter is not None:\n                        reporter("Keyboard devices disconnected. Try again or use manual entry.")\n')
text = text.replace('                _print_grab_failure()\n', '                if reporter is not None:\n                    reporter("Safe keyboard capture is unavailable because Mouse Control could not reserve every keyboard input device.")\n')
text = text.replace('        print("\\nKeyboard capture cancelled.")\n', '        if reporter is not None:\n            reporter("Keyboard capture cancelled.")\n')
text = text.replace('        print("Keyboard capture stopped. Use manual entry.")\n', '        if reporter is not None:\n            reporter("Keyboard capture stopped. Use manual entry.")\n')
text = text.replace(
    'def capture_keyboard_chord(*, exclude_paths: tuple[str, ...] = ()) -> str | None:\n',
    'def capture_keyboard_chord(\n    *,\n    exclude_paths: tuple[str, ...] = (),\n    manage_terminal: bool = True,\n    reporter=print,\n) -> str | None:\n'
)
text = text.replace(
    '        # Escape cancels; disabling terminal signals permits Ctrl+C chords.\n        with _capture_terminal(keep_signals=False):\n',
    '        # Escape cancels; disabling terminal signals permits Ctrl+C chords.\n        terminal_context = (\n            _capture_terminal(keep_signals=False) if manage_terminal else nullcontext()\n        )\n        with terminal_context:\n',
    1,
)
text = text.replace('                print("No readable keyboard devices found. Use manual chord entry.")\n', '                if reporter is not None:\n                    reporter("No readable keyboard devices found. Use manual chord entry.")\n')
text = text.replace('                    print("Press and hold the keyboard shortcut, then release it... (Esc to cancel)",\n                          flush=True)\n', '                    if reporter is not None:\n                        reporter("Press and hold the keyboard shortcut, then release it... (Esc to cancel)")\n')
text = text.replace('                    print("Keyboard devices disconnected. Use manual chord entry.")\n', '                    if reporter is not None:\n                        reporter("Keyboard devices disconnected. Use manual chord entry.")\n')
text = text.replace('                _print_grab_failure(chord=True)\n', '                if reporter is not None:\n                    reporter("Safe keyboard chord capture is unavailable because Mouse Control could not reserve every keyboard input device.")\n')
text = text.replace('        print("\\nKeyboard chord capture cancelled.")\n', '        if reporter is not None:\n            reporter("Keyboard chord capture cancelled.")\n')
text = text.replace('        print("Keyboard chord capture stopped. Use manual chord entry.")\n', '        if reporter is not None:\n            reporter("Keyboard chord capture stopped. Use manual chord entry.")\n')
keyboard.write_text(text)

text = tui.read_text()
old_key = '''                if action == "__key__":\n                    name = self._suspend_curses(\n                        lambda: capture_keyboard_key(\n                            exclude_paths=(self.controller.selected.path,)\n                        )\n                    )\n                    return f"key:{name}" if name else None\n                if action == "__chord__":\n                    return self._suspend_curses(\n                        lambda: capture_keyboard_chord(\n                            exclude_paths=(self.controller.selected.path,)\n                        )\n                    )\n'''
new_key = '''                if action == "__key__":\n                    self._modal(\n                        "Record keyboard key",\n                        [\n                            "Press the keyboard key you want to assign.",\n                            "Ctrl+C cancels capture.",\n                            "Mouse Control temporarily reserves keyboard input while recording.",\n                        ],\n                        prompt="Waiting for key…",\n                    )\n                    name = capture_keyboard_key(\n                        exclude_paths=(self.controller.selected.path,),\n                        manage_terminal=False,\n                        reporter=None,\n                    )\n                    if name is None:\n                        self.controller.status = "Keyboard key capture cancelled or unavailable."\n                        return None\n                    return f"key:{name}"\n                if action == "__chord__":\n                    self._modal(\n                        "Record keyboard chord",\n                        [\n                            "Press and hold the shortcut, then release all keys.",\n                            "Esc cancels capture.",\n                            "Mouse Control temporarily reserves keyboard input while recording.",\n                        ],\n                        prompt="Waiting for chord…",\n                    )\n                    chord = capture_keyboard_chord(\n                        exclude_paths=(self.controller.selected.path,),\n                        manage_terminal=False,\n                        reporter=None,\n                    )\n                    if chord is None:\n                        self.controller.status = "Keyboard chord capture cancelled or unavailable."\n                    return chord\n'''
if old_key not in text:
    raise SystemExit('expected TUI keyboard capture block not found')
text = text.replace(old_key, new_key)
tui.write_text(text)

test.write_text('''from pathlib import Path\nfrom unittest.mock import patch\n\nfrom mouse_control import keyboard_capture\n\n\ndef test_tui_capture_mode_does_not_touch_terminal(monkeypatch):\n    monkeypatch.setattr(keyboard_capture, "_open_keyboards", lambda **kwargs: [])\n    with patch.object(keyboard_capture, "_capture_terminal") as terminal:\n        assert keyboard_capture.capture_keyboard_key(manage_terminal=False, reporter=None) is None\n        assert keyboard_capture.capture_keyboard_chord(manage_terminal=False, reporter=None) is None\n    terminal.assert_not_called()\n\n\ndef test_curses_tui_keeps_key_and_chord_capture_native():\n    source = Path("src/mouse_control/setup_tui_curses.py").read_text()\n    assert '"Record keyboard key"' in source\n    assert '"Record keyboard chord"' in source\n    assert source.count("manage_terminal=False") >= 2\n    assert "_suspend_curses(\\n                        lambda: capture_keyboard" not in source\n''')
print('converted key/chord recording to native TUI flow')
