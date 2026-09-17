from pathlib import Path

# 1) Teach keyboard capture to exclude the already-grabbed mouse event node.
path = Path('src/mouse_control/keyboard_capture.py')
text = path.read_text()
text = text.replace(
    'def _open_keyboards() -> list[InputDevice]:\n',
    'def _open_keyboards(*, exclude_paths: tuple[str, ...] = ()) -> list[InputDevice]:\n',
    1,
)
text = text.replace(
    '    devices = []\n    seen = set()\n    paths = sorted(_iter_candidate_paths(),\n',
    '    devices = []\n    seen = set()\n    excluded = {os.path.realpath(item) for item in exclude_paths}\n    paths = sorted(_iter_candidate_paths(),\n',
    1,
)
text = text.replace(
    '            realpath = os.path.realpath(path)\n            if realpath in seen:\n',
    '            realpath = os.path.realpath(path)\n            if realpath in excluded or realpath in seen:\n',
    1,
)
text = text.replace(
    'def capture_keyboard_key() -> str | None:\n',
    'def capture_keyboard_key(*, exclude_paths: tuple[str, ...] = ()) -> str | None:\n',
    1,
)
text = text.replace(
    '            all_devices = _open_keyboards()\n            devices = _prepare_neutral_keyboards(all_devices)\n',
    '            all_devices = _open_keyboards(exclude_paths=exclude_paths)\n            devices = _prepare_neutral_keyboards(all_devices)\n',
    1,
)
text = text.replace(
    'def capture_keyboard_chord() -> str | None:\n',
    'def capture_keyboard_chord(*, exclude_paths: tuple[str, ...] = ()) -> str | None:\n',
    1,
)
# Replace the second remaining _open_keyboards() call (chord path).
text = text.replace(
    '            all_devices = _open_keyboards()\n            devices = _prepare_neutral_keyboards(all_devices)\n',
    '            all_devices = _open_keyboards(exclude_paths=exclude_paths)\n            devices = _prepare_neutral_keyboards(all_devices)\n',
    1,
)
path.write_text(text)

# 2) Always pass the selected mouse path from the TUI keyboard/key-chord actions.
path = Path('src/mouse_control/setup_tui_curses.py')
text = path.read_text()
text = text.replace(
    '                    name = self._suspend_curses(capture_keyboard_key)\n',
    '                    name = self._suspend_curses(\n                        lambda: capture_keyboard_key(\n                            exclude_paths=(self.controller.selected.path,)\n                        )\n                    )\n',
    1,
)
text = text.replace(
    '                    return self._suspend_curses(capture_keyboard_chord)\n',
    '                    return self._suspend_curses(\n                        lambda: capture_keyboard_chord(\n                            exclude_paths=(self.controller.selected.path,)\n                        )\n                    )\n',
    1,
)
path.write_text(text)

# 3) Add regression coverage for same-node composite mice.
path = Path('tests/test_keyboard_capture_mouse_exclusion.py')
path.write_text('''import os\n\nfrom mouse_control import keyboard_capture as capture\n\n\nclass FakeInputDevice:\n    opened = []\n\n    def __init__(self, path):\n        self.path = path\n        self.name = "Composite Titan"\n        self.closed = False\n        self.__class__.opened.append(path)\n\n    def capabilities(self, verbose=False):\n        from evdev import ecodes\n        return {ecodes.EV_KEY: [ecodes.KEY_A]}\n\n    def close(self):\n        self.closed = True\n\n\ndef test_open_keyboards_never_reopens_selected_mouse(monkeypatch, tmp_path):\n    mouse = tmp_path / "event-mouse"\n    keyboard = tmp_path / "event-kbd"\n    mouse.touch()\n    keyboard.touch()\n    FakeInputDevice.opened = []\n    monkeypatch.setattr(capture, "_iter_candidate_paths", lambda: iter([str(mouse), str(keyboard)]))\n    monkeypatch.setattr(capture, "InputDevice", FakeInputDevice)\n\n    devices = capture._open_keyboards(exclude_paths=(str(mouse),))\n\n    assert os.path.realpath(str(mouse)) not in {os.path.realpath(p) for p in FakeInputDevice.opened}\n    assert [d.path for d in devices] == [str(keyboard)]\n    for device in devices:\n        device.close()\n\ndef test_keyboard_capture_api_accepts_mouse_exclusion():\n    # Signature-level contract used by the setup TUI.\n    assert "exclude_paths" in capture.capture_keyboard_key.__annotations__\n    assert "exclude_paths" in capture.capture_keyboard_chord.__annotations__\n''')

print('excluded selected mouse from keyboard/key-chord capture')
