import os

from mouse_control import keyboard_capture as capture


class FakeInputDevice:
    opened = []

    def __init__(self, path):
        self.path = path
        self.name = "Composite Titan"
        self.closed = False
        self.__class__.opened.append(path)

    def capabilities(self, verbose=False):
        from evdev import ecodes
        return {ecodes.EV_KEY: [ecodes.KEY_A]}

    def close(self):
        self.closed = True


def test_open_keyboards_never_reopens_selected_mouse(monkeypatch, tmp_path):
    mouse = tmp_path / "event-mouse"
    keyboard = tmp_path / "event-kbd"
    mouse.touch()
    keyboard.touch()
    FakeInputDevice.opened = []
    monkeypatch.setattr(capture, "_iter_candidate_paths", lambda: iter([str(mouse), str(keyboard)]))
    monkeypatch.setattr(capture, "InputDevice", FakeInputDevice)

    devices = capture._open_keyboards(exclude_paths=(str(mouse),))

    assert os.path.realpath(str(mouse)) not in {os.path.realpath(p) for p in FakeInputDevice.opened}
    assert [d.path for d in devices] == [str(keyboard)]
    for device in devices:
        device.close()

def test_keyboard_capture_api_accepts_mouse_exclusion():
    # Signature-level contract used by the setup TUI.
    assert "exclude_paths" in capture.capture_keyboard_key.__annotations__
    assert "exclude_paths" in capture.capture_keyboard_chord.__annotations__
